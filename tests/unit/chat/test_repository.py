import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest

import agent_foundations.chat.repository as repository_module
from agent_foundations.chat.errors import ChatConflictError, ChatNotFoundError
from agent_foundations.chat.models import (
    AccessOperation,
    ApprovalStatus,
    MessageRole,
    PermissionMode,
    RunRecord,
    RunStatus,
)
from agent_foundations.chat.repository import (
    ConversationRepository,
    UnsupportedSchemaVersionError,
)

CONVERSATION_ID_A = "11111111-1111-4111-8111-111111111111"
CONVERSATION_ID_B = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
MESSAGE_ID = "33333333-3333-4333-8333-333333333333"
SESSION_ID = "22222222-2222-4222-8222-222222222222"
SESSION_ID_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
MESSAGE_ID_B = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
APPROVAL_ID = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
APPROVAL_ID_B = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
SESSION_ID_C = "c0000000-0000-4000-8000-000000000003"
SESSION_ID_D = "d0000000-0000-4000-8000-000000000004"
SESSION_ID_E = "e0000000-0000-4000-8000-000000000005"
SESSION_ID_F = "f0000000-0000-4000-8000-000000000006"
SESSION_ID_G = "a0000000-0000-4000-8000-000000000007"
APPROVAL_ID_C = "c0000000-0000-4000-8000-0000000000c3"
APPROVAL_ID_D = "d0000000-0000-4000-8000-0000000000d4"
TRACE_PATH = "traces/session.jsonl"
NOW = datetime(2026, 8, 2, 12, 0, 0, tzinfo=UTC)
NOW_TEXT = NOW.isoformat()


class _InterceptingConnection:
    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        fail_on: Callable[[str], bool],
    ) -> None:
        self._connection = connection
        self._fail_on = fail_on

    def execute(self, sql: str, parameters: Any = ()) -> sqlite3.Cursor:
        if self._fail_on(sql):
            raise sqlite3.OperationalError("simulated complete_run failure")
        return self._connection.execute(sql, parameters)

    def __getattr__(self, name: str) -> object:
        return getattr(self._connection, name)


async def _open_repository(path: Path) -> ConversationRepository:
    repository = ConversationRepository(path)
    await repository.initialize()
    return repository


def _insert_message(
    connection: sqlite3.Connection,
    *,
    message_id: str,
    conversation_id: str,
    sequence: int = 1,
    content: str = "fixture question",
) -> None:
    connection.execute(
        """
        INSERT INTO messages (
            message_id, conversation_id, role, content, sequence, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (message_id, conversation_id, MessageRole.USER.value, content, sequence, NOW_TEXT),
    )


def _insert_run(
    connection: sqlite3.Connection,
    *,
    session_id: str,
    conversation_id: str,
    user_message_id: str,
    status: str,
    trace_path: str = TRACE_PATH,
) -> None:
    connection.execute(
        """
        INSERT INTO runs (
            session_id,
            conversation_id,
            user_message_id,
            assistant_message_id,
            trace_path,
            status,
            error_code,
            created_at,
            started_at,
            finished_at
        ) VALUES (?, ?, ?, NULL, ?, ?, NULL, ?, NULL, NULL)
        """,
        (session_id, conversation_id, user_message_id, trace_path, status, NOW_TEXT),
    )


def _insert_pending_approval(
    connection: sqlite3.Connection,
    *,
    approval_id: str,
    conversation_id: str,
    session_id: str,
) -> None:
    connection.execute(
        """
        INSERT INTO approval_requests (
            approval_id,
            conversation_id,
            session_id,
            tool_call_id,
            tool_name,
            canonical_path,
            operation,
            status,
            requested_at,
            decided_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
        """,
        (
            approval_id,
            conversation_id,
            session_id,
            "call-1",
            "read_file",
            "/tmp/example.txt",
            "read",
            "pending",
            NOW_TEXT,
        ),
    )


def _insert_decided_approval(
    connection: sqlite3.Connection,
    *,
    approval_id: str,
    conversation_id: str,
    session_id: str,
    status: str,
) -> None:
    connection.execute(
        """
        INSERT INTO approval_requests (
            approval_id,
            conversation_id,
            session_id,
            tool_call_id,
            tool_name,
            canonical_path,
            operation,
            status,
            requested_at,
            decided_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            approval_id,
            conversation_id,
            session_id,
            "call-decided",
            "read_file",
            "/tmp/decided.txt",
            "read",
            status,
            NOW_TEXT,
            NOW_TEXT,
        ),
    )


def _count_approvals(
    repository: ConversationRepository,
    *,
    status: str | None = None,
) -> int:
    with repository._connect() as connection:
        if status is None:
            row = connection.execute(
                "SELECT COUNT(*) FROM approval_requests",
            ).fetchone()
        else:
            row = connection.execute(
                "SELECT COUNT(*) FROM approval_requests WHERE status = ?",
                (status,),
            ).fetchone()
    assert row is not None
    return int(row[0])


async def _run_to_waiting_approval(
    repository: ConversationRepository,
    conversation_id: str,
    *,
    session_id: str,
    content: str = "approval question",
) -> RunRecord:
    _, run = await repository.begin_run(
        conversation_id,
        content=content,
        session_id=session_id,
    )
    await repository.transition_run(
        run.session_id,
        RunStatus.QUEUED,
        RunStatus.RUNNING,
    )
    await repository.transition_run(
        run.session_id,
        RunStatus.RUNNING,
        RunStatus.WAITING_APPROVAL,
    )
    return await repository.get_run(run.session_id)


def _seed_active_run(
    repository: ConversationRepository,
    conversation_id: str,
    *,
    session_id: str = SESSION_ID,
    message_id: str = MESSAGE_ID,
    status: str = RunStatus.QUEUED.value,
) -> None:
    with repository._connect() as connection:
        _insert_message(connection, message_id=message_id, conversation_id=conversation_id)
        _insert_run(
            connection,
            session_id=session_id,
            conversation_id=conversation_id,
            user_message_id=message_id,
            status=status,
        )
        connection.commit()


@pytest.mark.asyncio
async def test_initialize_and_conversation_crud(tmp_path: Path) -> None:
    repository = await _open_repository(tmp_path / "state" / "chat.sqlite3")
    created = await repository.create_conversation(
        title="Runtime study",
        project_root=tmp_path,
        permission_mode=PermissionMode.PROJECT_READ_ONLY,
    )
    UUID(created.conversation_id)
    assert created.project_root == str(tmp_path)
    assert created.title == "Runtime study"
    assert created.permission_mode is PermissionMode.PROJECT_READ_ONLY
    assert created.created_at.tzinfo is UTC
    assert created.updated_at.tzinfo is UTC
    assert await repository.get_conversation(created.conversation_id) == created
    assert await repository.list_conversations() == [created]
    updated = await repository.update_conversation(
        created.conversation_id,
        title="Updated title",
        permission_mode=PermissionMode.ASK_FOR_ACCESS,
    )
    assert updated.title == "Updated title"
    assert updated.permission_mode is PermissionMode.ASK_FOR_ACCESS
    assert updated.created_at == created.created_at
    assert updated.updated_at >= created.updated_at


@pytest.mark.asyncio
async def test_initialize_creates_parent_directory(tmp_path: Path) -> None:
    database_path = tmp_path / "nested" / "state" / "chat.sqlite3"
    repository = ConversationRepository(database_path)
    await repository.initialize()
    assert database_path.is_file()


@pytest.mark.asyncio
async def test_initialize_is_idempotent(tmp_path: Path) -> None:
    repository = ConversationRepository(tmp_path / "chat.sqlite3")
    await repository.initialize()
    await repository.initialize()


@pytest.mark.asyncio
async def test_schema_enables_foreign_keys_and_version(tmp_path: Path) -> None:
    path = tmp_path / "chat.sqlite3"
    repository = ConversationRepository(path)
    await repository.initialize()
    with repository._connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1


@pytest.mark.asyncio
async def test_schema_contains_required_tables_and_index(tmp_path: Path) -> None:
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    with repository._connect() as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'",
            )
        }
        indexes = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'",
            )
        }
    assert tables >= {"conversations", "messages", "runs", "approval_requests"}
    assert "one_active_run_per_conversation" in indexes


@pytest.mark.asyncio
async def test_runs_table_includes_trace_path_column(tmp_path: Path) -> None:
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    with repository._connect() as connection:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(runs)")
        }
    assert columns >= {
        "session_id",
        "conversation_id",
        "user_message_id",
        "assistant_message_id",
        "trace_path",
        "status",
        "error_code",
        "created_at",
        "started_at",
        "finished_at",
    }


@pytest.mark.asyncio
async def test_initialize_rejects_newer_schema_version(tmp_path: Path) -> None:
    path = tmp_path / "chat.sqlite3"
    repository = ConversationRepository(path)
    await repository.initialize()
    with repository._connect() as connection:
        connection.execute("PRAGMA user_version = 2")
        connection.commit()
    with pytest.raises(UnsupportedSchemaVersionError):
        await repository.initialize()


@pytest.mark.asyncio
async def test_missing_conversation_raises_not_found(tmp_path: Path) -> None:
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    with pytest.raises(ChatNotFoundError):
        await repository.get_conversation(CONVERSATION_ID_A)


@pytest.mark.asyncio
async def test_create_conversation_strips_title(tmp_path: Path) -> None:
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    created = await repository.create_conversation(
        title="  Runtime study  ",
        project_root=tmp_path,
        permission_mode=PermissionMode.PROJECT_READ_ONLY,
    )
    assert created.title == "Runtime study"


@pytest.mark.asyncio
async def test_create_conversation_rejects_blank_title(tmp_path: Path) -> None:
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    with pytest.raises(ValueError, match="title"):
        await repository.create_conversation(
            title="   ",
            project_root=tmp_path,
            permission_mode=PermissionMode.PROJECT_READ_ONLY,
        )


@pytest.mark.asyncio
async def test_update_conversation_rejects_blank_title(tmp_path: Path) -> None:
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    created = await repository.create_conversation(
        title="Runtime study",
        project_root=tmp_path,
        permission_mode=PermissionMode.PROJECT_READ_ONLY,
    )
    with pytest.raises(ValueError, match="title"):
        await repository.update_conversation(created.conversation_id, title="   ")


@pytest.mark.asyncio
async def test_update_conversation_rejects_long_title(tmp_path: Path) -> None:
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    created = await repository.create_conversation(
        title="Runtime study",
        project_root=tmp_path,
        permission_mode=PermissionMode.PROJECT_READ_ONLY,
    )
    with pytest.raises(ValueError, match="title"):
        await repository.update_conversation(
            created.conversation_id,
            title="x" * 121,
        )


@pytest.mark.asyncio
async def test_list_conversations_orders_by_updated_at_desc_then_id(
    tmp_path: Path,
) -> None:
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    first = await repository.create_conversation(
        title="First",
        project_root=tmp_path,
        permission_mode=PermissionMode.PROJECT_READ_ONLY,
    )
    second = await repository.create_conversation(
        title="Second",
        project_root=tmp_path,
        permission_mode=PermissionMode.ASK_FOR_ACCESS,
    )
    await repository.update_conversation(second.conversation_id, title="Second updated")
    listed = await repository.list_conversations()
    assert [item.conversation_id for item in listed] == [
        second.conversation_id,
        first.conversation_id,
    ]


@pytest.mark.asyncio
async def test_get_conversation_returns_validated_model_not_row(
    tmp_path: Path,
) -> None:
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    created = await repository.create_conversation(
        title="Runtime study",
        project_root=tmp_path,
        permission_mode=PermissionMode.PROJECT_READ_ONLY,
    )
    loaded = await repository.get_conversation(created.conversation_id)
    assert type(loaded).__name__ == "Conversation"
    assert not isinstance(loaded, sqlite3.Row)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    [RunStatus.QUEUED, RunStatus.RUNNING, RunStatus.WAITING_APPROVAL],
)
async def test_update_permission_mode_rejects_active_run(
    tmp_path: Path,
    status: RunStatus,
) -> None:
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    created = await repository.create_conversation(
        title="Runtime study",
        project_root=tmp_path,
        permission_mode=PermissionMode.PROJECT_READ_ONLY,
    )
    _seed_active_run(repository, created.conversation_id, status=status.value)
    with pytest.raises(ChatConflictError):
        await repository.update_conversation(
            created.conversation_id,
            permission_mode=PermissionMode.ASK_FOR_ACCESS,
        )


@pytest.mark.asyncio
async def test_update_permission_mode_rejects_pending_approval(tmp_path: Path) -> None:
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    created = await repository.create_conversation(
        title="Runtime study",
        project_root=tmp_path,
        permission_mode=PermissionMode.PROJECT_READ_ONLY,
    )
    with repository._connect() as connection:
        _insert_message(connection, message_id=MESSAGE_ID, conversation_id=created.conversation_id)
        _insert_run(
            connection,
            session_id=SESSION_ID,
            conversation_id=created.conversation_id,
            user_message_id=MESSAGE_ID,
            status=RunStatus.COMPLETED.value,
        )
        _insert_pending_approval(
            connection,
            approval_id=APPROVAL_ID,
            conversation_id=created.conversation_id,
            session_id=SESSION_ID,
        )
        connection.commit()
    with pytest.raises(ChatConflictError):
        await repository.update_conversation(
            created.conversation_id,
            permission_mode=PermissionMode.ASK_FOR_ACCESS,
        )


@pytest.mark.asyncio
async def test_initialize_rolls_back_partial_schema_on_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broken_schema = (
        """
        CREATE TABLE conversations (
          conversation_id TEXT PRIMARY KEY,
          title TEXT NOT NULL,
          project_root TEXT NOT NULL,
          permission_mode TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE conversations (
          conversation_id TEXT PRIMARY KEY,
          title TEXT NOT NULL,
          project_root TEXT NOT NULL,
          permission_mode TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        )
        """,
    )
    monkeypatch.setattr(repository_module, "_SCHEMA_STATEMENTS", broken_schema)
    path = tmp_path / "chat.sqlite3"
    repository = ConversationRepository(path)
    with pytest.raises(sqlite3.OperationalError):
        repository._initialize_sync()
    with repository._connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 0
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'",
            )
        }
    assert "conversations" not in tables


@pytest.mark.asyncio
async def test_update_permission_mode_uses_single_connection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    created = await repository.create_conversation(
        title="Runtime study",
        project_root=tmp_path,
        permission_mode=PermissionMode.PROJECT_READ_ONLY,
    )
    connection_ids: list[int] = []
    original_connect = ConversationRepository._connect

    @contextmanager
    def tracking_connect(self: ConversationRepository) -> Iterator[sqlite3.Connection]:
        with original_connect(self) as connection:
            connection_ids.append(id(connection))
            yield connection

    monkeypatch.setattr(ConversationRepository, "_connect", tracking_connect)
    updated = repository._update_conversation_sync(
        created.conversation_id,
        "Updated title",
        PermissionMode.ASK_FOR_ACCESS,
    )
    assert updated.permission_mode is PermissionMode.ASK_FOR_ACCESS
    assert len(connection_ids) == 1


@pytest.mark.asyncio
async def test_update_title_allowed_while_active_run_exists(tmp_path: Path) -> None:
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    created = await repository.create_conversation(
        title="Runtime study",
        project_root=tmp_path,
        permission_mode=PermissionMode.PROJECT_READ_ONLY,
    )
    _seed_active_run(repository, created.conversation_id)
    updated = await repository.update_conversation(
        created.conversation_id,
        title="Renamed while active",
    )
    assert updated.title == "Renamed while active"
    assert updated.permission_mode is PermissionMode.PROJECT_READ_ONLY


def test_gitignore_ignores_agent_foundations_directory() -> None:
    contents = Path(".gitignore").read_text(encoding="utf-8")
    assert ".agent-foundations/" in contents
    assert "node_modules/" in contents
    assert "test-results/" in contents
    assert "playwright-report/" in contents


async def _create_conversation(
    repository: ConversationRepository,
    tmp_path: Path,
    *,
    title: str = "Runtime study",
) -> str:
    created = await repository.create_conversation(
        title=title,
        project_root=tmp_path,
        permission_mode=PermissionMode.PROJECT_READ_ONLY,
    )
    return created.conversation_id


# ── Task 3: message, run, and approval persistence ───────────────────────


@pytest.mark.asyncio
async def test_begin_run_creates_user_message_and_queued_run(tmp_path: Path) -> None:
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    conversation_id = await _create_conversation(repository, tmp_path)
    user_message, run = await repository.begin_run(
        conversation_id,
        content="first question",
        session_id=SESSION_ID,
    )
    assert user_message.role is MessageRole.USER
    assert user_message.sequence == 1
    assert user_message.conversation_id == conversation_id
    assert run.status is RunStatus.QUEUED
    assert run.user_message_id == user_message.message_id
    assert run.conversation_id == conversation_id
    assert run.trace_path == f"traces/{SESSION_ID}.jsonl"
    loaded_run = await repository.get_run(run.session_id)
    assert loaded_run == run
    messages = await repository.list_messages(conversation_id)
    assert messages == [user_message]


@pytest.mark.asyncio
async def test_begin_run_message_sequence_increments_per_conversation(
    tmp_path: Path,
) -> None:
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    conversation_id = await _create_conversation(repository, tmp_path)
    first_message, first_run = await repository.begin_run(
        conversation_id,
        content="first question",
        session_id=SESSION_ID,
    )
    await repository.transition_run(
        first_run.session_id,
        RunStatus.QUEUED,
        RunStatus.RUNNING,
    )
    await repository.complete_run(first_run.session_id, "first answer")
    second_message, second_run = await repository.begin_run(
        conversation_id,
        content="second question",
        session_id=SESSION_ID_B,
    )
    assert first_message.sequence == 1
    assert second_message.sequence == 3
    assert second_run.status is RunStatus.QUEUED
    assistant_messages = [
        message
        for message in await repository.list_messages(conversation_id)
        if message.role is MessageRole.ASSISTANT
    ]
    assert len(assistant_messages) == 1
    assert assistant_messages[0].sequence == 2


@pytest.mark.asyncio
async def test_list_runs_returns_conversation_turns_in_message_order(
    tmp_path: Path,
) -> None:
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    conversation_id = await _create_conversation(repository, tmp_path, title="Primary")
    other_conversation_id = await _create_conversation(repository, tmp_path, title="Other")

    _first_message, first_run = await repository.begin_run(
        conversation_id,
        content="first question",
        session_id=SESSION_ID,
    )
    await repository.transition_run(
        first_run.session_id,
        RunStatus.QUEUED,
        RunStatus.RUNNING,
    )
    first_answer = await repository.complete_run(first_run.session_id, "first answer")

    _second_message, second_run = await repository.begin_run(
        conversation_id,
        content="second question",
        session_id=SESSION_ID_B,
    )
    await repository.begin_run(
        other_conversation_id,
        content="other question",
        session_id=SESSION_ID_C,
    )

    runs = await repository.list_runs(conversation_id)

    assert [run.session_id for run in runs] == [SESSION_ID, SESSION_ID_B]
    assert runs[0].assistant_message_id == first_answer.message_id
    assert runs[1].assistant_message_id is None
    assert runs[1].status is RunStatus.QUEUED


@pytest.mark.asyncio
async def test_message_sequence_is_independent_across_conversations(
    tmp_path: Path,
) -> None:
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    conversation_a = await _create_conversation(repository, tmp_path, title="A")
    conversation_b = await _create_conversation(repository, tmp_path, title="B")
    message_a, _ = await repository.begin_run(
        conversation_a,
        content="question a",
        session_id=SESSION_ID,
    )
    message_b, _ = await repository.begin_run(
        conversation_b,
        content="question b",
        session_id=SESSION_ID_B,
    )
    assert message_a.sequence == 1
    assert message_b.sequence == 1


@pytest.mark.asyncio
async def test_second_begin_run_raises_conflict_without_orphan_message(
    tmp_path: Path,
) -> None:
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    conversation_id = await _create_conversation(repository, tmp_path)
    await repository.begin_run(
        conversation_id,
        content="first question",
        session_id=SESSION_ID,
    )
    with pytest.raises(ChatConflictError):
        await repository.begin_run(
            conversation_id,
            content="second question",
            session_id=SESSION_ID_B,
        )
    messages = await repository.list_messages(conversation_id)
    assert len(messages) == 1
    assert messages[0].content == "first question"


@pytest.mark.asyncio
async def test_transition_run_state_machine_and_timestamps(tmp_path: Path) -> None:
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    conversation_id = await _create_conversation(repository, tmp_path)
    _, run = await repository.begin_run(
        conversation_id,
        content="first question",
        session_id=SESSION_ID,
    )
    running = await repository.transition_run(
        run.session_id,
        RunStatus.QUEUED,
        RunStatus.RUNNING,
    )
    assert running.status is RunStatus.RUNNING
    assert running.started_at is not None
    assert running.finished_at is None

    waiting = await repository.transition_run(
        run.session_id,
        RunStatus.RUNNING,
        RunStatus.WAITING_APPROVAL,
    )
    assert waiting.status is RunStatus.WAITING_APPROVAL
    assert waiting.started_at == running.started_at

    resumed = await repository.transition_run(
        run.session_id,
        RunStatus.WAITING_APPROVAL,
        RunStatus.RUNNING,
    )
    assert resumed.status is RunStatus.RUNNING
    assert resumed.started_at == running.started_at


@pytest.mark.asyncio
async def test_transition_run_rejects_invalid_edges_and_expected_mismatch(
    tmp_path: Path,
) -> None:
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    conversation_id = await _create_conversation(repository, tmp_path)
    _, run = await repository.begin_run(
        conversation_id,
        content="first question",
        session_id=SESSION_ID,
    )
    with pytest.raises(ChatConflictError):
        await repository.transition_run(
            run.session_id,
            RunStatus.QUEUED,
            RunStatus.COMPLETED,
        )
    with pytest.raises(ChatConflictError):
        await repository.transition_run(
            run.session_id,
            RunStatus.RUNNING,
            RunStatus.COMPLETED,
        )
    await repository.transition_run(
        run.session_id,
        RunStatus.QUEUED,
        RunStatus.RUNNING,
    )
    assistant = await repository.complete_run(run.session_id, "final answer")
    assert assistant.role is MessageRole.ASSISTANT
    assert assistant.sequence == 2
    completed = await repository.get_run(run.session_id)
    assert completed.assistant_message_id == assistant.message_id
    with pytest.raises(ChatConflictError):
        await repository.transition_run(
            run.session_id,
            RunStatus.COMPLETED,
            RunStatus.RUNNING,
        )


@pytest.mark.asyncio
async def test_complete_run_requires_running_status(tmp_path: Path) -> None:
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    conversation_id = await _create_conversation(repository, tmp_path)
    _, run = await repository.begin_run(
        conversation_id,
        content="first question",
        session_id=SESSION_ID,
    )
    with pytest.raises(ChatConflictError):
        await repository.complete_run(run.session_id, "too early")


@pytest.mark.asyncio
async def test_complete_run_rolls_back_on_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    conversation_id = await _create_conversation(repository, tmp_path)
    _, run = await repository.begin_run(
        conversation_id,
        content="first question",
        session_id=SESSION_ID,
    )
    await repository.transition_run(
        run.session_id,
        RunStatus.QUEUED,
        RunStatus.RUNNING,
    )
    original_connect = ConversationRepository._connect

    @contextmanager
    def failing_connect(self: ConversationRepository) -> Iterator[sqlite3.Connection]:
        with original_connect(self) as connection:
            wrapped = _InterceptingConnection(
                connection,
                fail_on=lambda sql: "UPDATE runs" in sql and "assistant_message_id" in sql,
            )
            yield cast(sqlite3.Connection, wrapped)

    monkeypatch.setattr(ConversationRepository, "_connect", failing_connect)
    with pytest.raises(sqlite3.OperationalError):
        await repository.complete_run(run.session_id, "final answer")
    messages = await repository.list_messages(conversation_id)
    assert len(messages) == 1
    loaded = await repository.get_run(run.session_id)
    assert loaded.status is RunStatus.RUNNING
    assert loaded.assistant_message_id is None


@pytest.mark.asyncio
async def test_list_context_before_returns_only_earlier_messages(
    tmp_path: Path,
) -> None:
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    conversation_id = await _create_conversation(repository, tmp_path)
    first_message, first_run = await repository.begin_run(
        conversation_id,
        content="first question",
        session_id=SESSION_ID,
    )
    await repository.transition_run(
        first_run.session_id,
        RunStatus.QUEUED,
        RunStatus.RUNNING,
    )
    await repository.complete_run(first_run.session_id, "first answer")
    second_message, _ = await repository.begin_run(
        conversation_id,
        content="second question",
        session_id=SESSION_ID_B,
    )
    context = await repository.list_context_before(
        conversation_id,
        second_message.message_id,
    )
    assert [message.message_id for message in context] == [
        first_message.message_id,
        (await repository.list_messages(conversation_id))[1].message_id,
    ]
    assert second_message.message_id not in {message.message_id for message in context}


@pytest.mark.asyncio
async def test_list_context_before_raises_for_missing_or_foreign_message(
    tmp_path: Path,
) -> None:
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    conversation_id = await _create_conversation(repository, tmp_path)
    other_conversation = await _create_conversation(repository, tmp_path, title="Other")
    user_message, _ = await repository.begin_run(
        conversation_id,
        content="first question",
        session_id=SESSION_ID,
    )
    with pytest.raises(ChatNotFoundError):
        await repository.list_context_before(conversation_id, MESSAGE_ID_B)
    with pytest.raises(ChatNotFoundError):
        await repository.list_context_before(other_conversation, user_message.message_id)


@pytest.mark.asyncio
async def test_fail_run_stores_stable_error_code_only(tmp_path: Path) -> None:
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    conversation_id = await _create_conversation(repository, tmp_path)
    _, run = await repository.begin_run(
        conversation_id,
        content="first question",
        session_id=SESSION_ID,
    )
    failed = await repository.fail_run(run.session_id, "provider_timeout")
    assert failed.status is RunStatus.FAILED
    assert failed.error_code == "provider_timeout"
    assert failed.finished_at is not None
    with pytest.raises(ChatConflictError):
        await repository.fail_run(run.session_id, "again")


@pytest.mark.asyncio
async def test_interrupt_run_from_active_states(tmp_path: Path) -> None:
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    conversation_id = await _create_conversation(repository, tmp_path)
    _, queued_run = await repository.begin_run(
        conversation_id,
        content="queued question",
        session_id=SESSION_ID,
    )
    interrupted = await repository.interrupt_run(queued_run.session_id)
    assert interrupted.status is RunStatus.INTERRUPTED
    assert interrupted.finished_at is not None

    _, running_run = await repository.begin_run(
        conversation_id,
        content="running question",
        session_id=SESSION_ID_B,
    )
    await repository.transition_run(
        running_run.session_id,
        RunStatus.QUEUED,
        RunStatus.RUNNING,
    )
    interrupted_running = await repository.interrupt_run(running_run.session_id)
    assert interrupted_running.status is RunStatus.INTERRUPTED


@pytest.mark.asyncio
async def test_create_approval_requires_waiting_approval_run(tmp_path: Path) -> None:
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    conversation_id = await _create_conversation(repository, tmp_path)
    _, run = await repository.begin_run(
        conversation_id,
        content="first question",
        session_id=SESSION_ID,
    )
    with pytest.raises(ChatConflictError):
        await repository.create_approval(
            conversation_id=conversation_id,
            session_id=run.session_id,
            tool_call_id="call-1",
            tool_name="read_file",
            canonical_path="/tmp/example.txt",
        )
    await repository.transition_run(
        run.session_id,
        RunStatus.QUEUED,
        RunStatus.RUNNING,
    )
    await repository.transition_run(
        run.session_id,
        RunStatus.RUNNING,
        RunStatus.WAITING_APPROVAL,
    )
    approval = await repository.create_approval(
        conversation_id=conversation_id,
        session_id=run.session_id,
        tool_call_id="call-1",
        tool_name="read_file",
        canonical_path="/tmp/example.txt",
        approval_id=APPROVAL_ID,
    )
    assert approval.status is ApprovalStatus.PENDING
    assert approval.operation is AccessOperation.READ
    assert approval.conversation_id == conversation_id
    with pytest.raises(ChatConflictError):
        await repository.create_approval(
            conversation_id=conversation_id,
            session_id=run.session_id,
            tool_call_id="call-1",
            tool_name="read_file",
            canonical_path="/tmp/example.txt",
            approval_id=APPROVAL_ID_B,
        )


@pytest.mark.asyncio
async def test_resolve_approval_allows_single_decision(tmp_path: Path) -> None:
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    conversation_id = await _create_conversation(repository, tmp_path)
    _, run = await repository.begin_run(
        conversation_id,
        content="first question",
        session_id=SESSION_ID,
    )
    await repository.transition_run(
        run.session_id,
        RunStatus.QUEUED,
        RunStatus.RUNNING,
    )
    await repository.transition_run(
        run.session_id,
        RunStatus.RUNNING,
        RunStatus.WAITING_APPROVAL,
    )
    approval = await repository.create_approval(
        conversation_id=conversation_id,
        session_id=run.session_id,
        tool_call_id="call-1",
        tool_name="read_file",
        canonical_path="/tmp/example.txt",
        approval_id=APPROVAL_ID,
    )
    approved = await repository.resolve_approval(
        approval.approval_id,
        ApprovalStatus.APPROVED,
    )
    assert approved.status is ApprovalStatus.APPROVED
    assert approved.decided_at is not None
    with pytest.raises(ChatConflictError):
        await repository.resolve_approval(
            approval.approval_id,
            ApprovalStatus.DENIED,
        )
    with pytest.raises(ChatConflictError):
        await repository.resolve_approval(
            approval.approval_id,
            ApprovalStatus.PENDING,
        )


@pytest.mark.asyncio
async def test_interrupt_unfinished_is_atomic_and_idempotent(tmp_path: Path) -> None:
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    queued_conversation = await _create_conversation(repository, tmp_path, title="Queued")
    waiting_conversation = await _create_conversation(
        repository,
        tmp_path,
        title="Waiting",
    )
    _, queued_run = await repository.begin_run(
        queued_conversation,
        content="queued question",
        session_id=SESSION_ID,
    )
    _, waiting_run = await repository.begin_run(
        waiting_conversation,
        content="waiting question",
        session_id=SESSION_ID_B,
    )
    await repository.transition_run(
        waiting_run.session_id,
        RunStatus.QUEUED,
        RunStatus.RUNNING,
    )
    await repository.transition_run(
        waiting_run.session_id,
        RunStatus.RUNNING,
        RunStatus.WAITING_APPROVAL,
    )
    approval = await repository.create_approval(
        conversation_id=waiting_conversation,
        session_id=waiting_run.session_id,
        tool_call_id="call-1",
        tool_name="read_file",
        canonical_path="/tmp/example.txt",
        approval_id=APPROVAL_ID,
    )
    interrupted_runs, invalidated_approvals = await repository.interrupt_unfinished()
    assert interrupted_runs == 2
    assert invalidated_approvals == 1
    assert (await repository.get_run(queued_run.session_id)).status is RunStatus.INTERRUPTED
    assert (await repository.get_run(waiting_run.session_id)).status is RunStatus.INTERRUPTED
    assert (await repository.get_approval(approval.approval_id)).status is (
        ApprovalStatus.INVALIDATED
    )
    assert await repository.interrupt_unfinished() == (0, 0)


@pytest.mark.asyncio
async def test_repository_public_methods_return_pydantic_models(
    tmp_path: Path,
) -> None:
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    conversation_id = await _create_conversation(repository, tmp_path)
    user_message, run = await repository.begin_run(
        conversation_id,
        content="first question",
        session_id=SESSION_ID,
    )
    await repository.transition_run(
        run.session_id,
        RunStatus.QUEUED,
        RunStatus.RUNNING,
    )
    await repository.transition_run(
        run.session_id,
        RunStatus.RUNNING,
        RunStatus.WAITING_APPROVAL,
    )
    approval = await repository.create_approval(
        conversation_id=conversation_id,
        session_id=run.session_id,
        tool_call_id="call-1",
        tool_name="read_file",
        canonical_path="/tmp/example.txt",
        approval_id=APPROVAL_ID,
    )
    assert type(user_message).__name__ == "ChatMessage"
    assert type(run).__name__ == "RunRecord"
    assert type(approval).__name__ == "ApprovalRequest"
    assert not isinstance(user_message, sqlite3.Row)


# ── Task 3 acceptance supplements ────────────────────────────────────────


@pytest.mark.asyncio
async def test_resolve_approval_denied_success_path(tmp_path: Path) -> None:
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    conversation_id = await _create_conversation(repository, tmp_path)
    run = await _run_to_waiting_approval(
        repository,
        conversation_id,
        session_id=SESSION_ID,
    )
    approval = await repository.create_approval(
        conversation_id=conversation_id,
        session_id=run.session_id,
        tool_call_id="call-deny",
        tool_name="read_file",
        canonical_path="/tmp/deny.txt",
        approval_id=APPROVAL_ID,
    )
    denied = await repository.resolve_approval(
        approval.approval_id,
        ApprovalStatus.DENIED,
    )
    assert denied.status is ApprovalStatus.DENIED
    assert denied.decided_at is not None
    with pytest.raises(ChatConflictError):
        await repository.resolve_approval(
            approval.approval_id,
            ApprovalStatus.APPROVED,
        )


@pytest.mark.asyncio
async def test_invalidate_approval_from_pending(tmp_path: Path) -> None:
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    conversation_id = await _create_conversation(repository, tmp_path)
    run = await _run_to_waiting_approval(
        repository,
        conversation_id,
        session_id=SESSION_ID,
    )
    approval = await repository.create_approval(
        conversation_id=conversation_id,
        session_id=run.session_id,
        tool_call_id="call-invalidate",
        tool_name="read_file",
        canonical_path="/tmp/invalidate.txt",
        approval_id=APPROVAL_ID,
    )
    invalidated = await repository.invalidate_approval(approval.approval_id)
    assert invalidated.status is ApprovalStatus.INVALIDATED
    assert invalidated.decided_at is not None
    with pytest.raises(ChatConflictError):
        await repository.invalidate_approval(approval.approval_id)
    with pytest.raises(ChatConflictError):
        await repository.resolve_approval(
            approval.approval_id,
            ApprovalStatus.APPROVED,
        )


@pytest.mark.asyncio
async def test_invalidate_approval_not_found(tmp_path: Path) -> None:
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    with pytest.raises(ChatNotFoundError):
        await repository.invalidate_approval(
            "00000000-0000-4000-8000-000000000099",
        )


@pytest.mark.asyncio
async def test_fail_run_from_all_active_states(tmp_path: Path) -> None:
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    queued_conversation = await _create_conversation(repository, tmp_path, title="Queued")
    running_conversation = await _create_conversation(repository, tmp_path, title="Running")
    waiting_conversation = await _create_conversation(repository, tmp_path, title="Waiting")

    _, queued_run = await repository.begin_run(
        queued_conversation,
        content="queued question",
        session_id=SESSION_ID,
    )
    failed_queued = await repository.fail_run(queued_run.session_id, "queued_error")
    assert failed_queued.status is RunStatus.FAILED
    assert failed_queued.error_code == "queued_error"
    assert failed_queued.finished_at is not None

    _, running_run = await repository.begin_run(
        running_conversation,
        content="running question",
        session_id=SESSION_ID_B,
    )
    await repository.transition_run(
        running_run.session_id,
        RunStatus.QUEUED,
        RunStatus.RUNNING,
    )
    failed_running = await repository.fail_run(running_run.session_id, "running_error")
    assert failed_running.status is RunStatus.FAILED
    assert failed_running.error_code == "running_error"
    assert failed_running.finished_at is not None

    waiting_run = await _run_to_waiting_approval(
        repository,
        waiting_conversation,
        session_id=SESSION_ID_C,
    )
    failed_waiting = await repository.fail_run(waiting_run.session_id, "waiting_error")
    assert failed_waiting.status is RunStatus.FAILED
    assert failed_waiting.error_code == "waiting_error"
    assert failed_waiting.finished_at is not None

    with pytest.raises(ChatConflictError):
        await repository.fail_run(queued_run.session_id, "again")
    with pytest.raises(ChatConflictError):
        await repository.fail_run(running_run.session_id, "again")
    with pytest.raises(ChatConflictError):
        await repository.fail_run(waiting_run.session_id, "again")


@pytest.mark.asyncio
async def test_interrupt_run_all_state_coverage(tmp_path: Path) -> None:
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    queued_conversation = await _create_conversation(repository, tmp_path, title="Queued")
    running_conversation = await _create_conversation(repository, tmp_path, title="Running")
    waiting_conversation = await _create_conversation(repository, tmp_path, title="Waiting")
    completed_conversation = await _create_conversation(
        repository,
        tmp_path,
        title="Completed",
    )
    failed_conversation = await _create_conversation(repository, tmp_path, title="Failed")
    interrupted_conversation = await _create_conversation(
        repository,
        tmp_path,
        title="Interrupted",
    )

    _, queued_run = await repository.begin_run(
        queued_conversation,
        content="queued",
        session_id=SESSION_ID,
    )
    interrupted_queued = await repository.interrupt_run(queued_run.session_id)
    assert interrupted_queued.status is RunStatus.INTERRUPTED
    assert interrupted_queued.finished_at is not None

    _, running_run = await repository.begin_run(
        running_conversation,
        content="running",
        session_id=SESSION_ID_B,
    )
    await repository.transition_run(
        running_run.session_id,
        RunStatus.QUEUED,
        RunStatus.RUNNING,
    )
    interrupted_running = await repository.interrupt_run(running_run.session_id)
    assert interrupted_running.status is RunStatus.INTERRUPTED
    assert interrupted_running.finished_at is not None

    waiting_run = await _run_to_waiting_approval(
        repository,
        waiting_conversation,
        session_id=SESSION_ID_C,
    )
    interrupted_waiting = await repository.interrupt_run(waiting_run.session_id)
    assert interrupted_waiting.status is RunStatus.INTERRUPTED
    assert interrupted_waiting.finished_at is not None

    _, completed_run = await repository.begin_run(
        completed_conversation,
        content="complete me",
        session_id=SESSION_ID_D,
    )
    await repository.transition_run(
        completed_run.session_id,
        RunStatus.QUEUED,
        RunStatus.RUNNING,
    )
    await repository.complete_run(completed_run.session_id, "done")
    with pytest.raises(ChatConflictError):
        await repository.interrupt_run(completed_run.session_id)

    _, failed_run = await repository.begin_run(
        failed_conversation,
        content="fail me",
        session_id=SESSION_ID_E,
    )
    await repository.fail_run(failed_run.session_id, "terminal_fail")
    with pytest.raises(ChatConflictError):
        await repository.interrupt_run(failed_run.session_id)

    _, interrupted_run = await repository.begin_run(
        interrupted_conversation,
        content="interrupt me",
        session_id=SESSION_ID_F,
    )
    await repository.interrupt_run(interrupted_run.session_id)
    with pytest.raises(ChatConflictError):
        await repository.interrupt_run(interrupted_run.session_id)


@pytest.mark.asyncio
async def test_create_approval_rejects_conversation_mismatch(tmp_path: Path) -> None:
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    conversation_a = await _create_conversation(repository, tmp_path, title="A")
    conversation_b = await _create_conversation(repository, tmp_path, title="B")
    run = await _run_to_waiting_approval(
        repository,
        conversation_a,
        session_id=SESSION_ID,
    )
    with pytest.raises(ChatConflictError):
        await repository.create_approval(
            conversation_id=conversation_b,
            session_id=run.session_id,
            tool_call_id="call-mismatch",
            tool_name="read_file",
            canonical_path="/tmp/mismatch.txt",
            approval_id=APPROVAL_ID,
        )
    assert _count_approvals(repository) == 0


@pytest.mark.asyncio
async def test_interrupt_unfinished_full_recovery_behavior(tmp_path: Path) -> None:
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    queued_conversation = await _create_conversation(repository, tmp_path, title="Queued")
    running_conversation = await _create_conversation(repository, tmp_path, title="Running")
    waiting_conversation = await _create_conversation(repository, tmp_path, title="Waiting")
    completed_conversation = await _create_conversation(
        repository,
        tmp_path,
        title="Completed",
    )
    decided_conversation = await _create_conversation(repository, tmp_path, title="Decided")

    _, queued_run = await repository.begin_run(
        queued_conversation,
        content="queued",
        session_id=SESSION_ID,
    )
    queued_before = await repository.get_run(queued_run.session_id)

    _, running_run = await repository.begin_run(
        running_conversation,
        content="running",
        session_id=SESSION_ID_B,
    )
    await repository.transition_run(
        running_run.session_id,
        RunStatus.QUEUED,
        RunStatus.RUNNING,
    )
    running_before = await repository.get_run(running_run.session_id)

    waiting_run = await _run_to_waiting_approval(
        repository,
        waiting_conversation,
        session_id=SESSION_ID_C,
    )
    waiting_before = await repository.get_run(waiting_run.session_id)
    pending_approval = await repository.create_approval(
        conversation_id=waiting_conversation,
        session_id=waiting_run.session_id,
        tool_call_id="call-pending",
        tool_name="read_file",
        canonical_path="/tmp/pending.txt",
        approval_id=APPROVAL_ID,
    )
    pending_before = await repository.get_approval(pending_approval.approval_id)

    _, completed_run = await repository.begin_run(
        completed_conversation,
        content="complete",
        session_id=SESSION_ID_D,
    )
    await repository.transition_run(
        completed_run.session_id,
        RunStatus.QUEUED,
        RunStatus.RUNNING,
    )
    await repository.complete_run(completed_run.session_id, "done")
    completed_before = await repository.get_run(completed_run.session_id)

    _, decided_run = await repository.begin_run(
        decided_conversation,
        content="decided",
        session_id=SESSION_ID_E,
    )
    await repository.transition_run(
        decided_run.session_id,
        RunStatus.QUEUED,
        RunStatus.RUNNING,
    )
    await repository.complete_run(decided_run.session_id, "also done")
    with repository._connect() as connection:
        _insert_decided_approval(
            connection,
            approval_id=APPROVAL_ID_C,
            conversation_id=decided_conversation,
            session_id=decided_run.session_id,
            status=ApprovalStatus.APPROVED.value,
        )
        connection.commit()
    decided_before = await repository.get_approval(APPROVAL_ID_C)

    interrupted_runs, invalidated_approvals = await repository.interrupt_unfinished()
    assert interrupted_runs == 3
    assert invalidated_approvals == 1

    queued_after = await repository.get_run(queued_run.session_id)
    assert queued_after.status is RunStatus.INTERRUPTED
    assert queued_after.finished_at is not None
    assert queued_before.status is RunStatus.QUEUED

    running_after = await repository.get_run(running_run.session_id)
    assert running_after.status is RunStatus.INTERRUPTED
    assert running_after.finished_at is not None
    assert running_before.status is RunStatus.RUNNING

    waiting_after = await repository.get_run(waiting_run.session_id)
    assert waiting_after.status is RunStatus.INTERRUPTED
    assert waiting_after.finished_at is not None
    assert waiting_before.status is RunStatus.WAITING_APPROVAL

    pending_after = await repository.get_approval(pending_approval.approval_id)
    assert pending_after.status is ApprovalStatus.INVALIDATED
    assert pending_after.decided_at is not None
    assert pending_before.status is ApprovalStatus.PENDING

    completed_after = await repository.get_run(completed_run.session_id)
    assert completed_after == completed_before

    decided_after = await repository.get_approval(APPROVAL_ID_C)
    assert decided_after == decided_before

    assert await repository.interrupt_unfinished() == (0, 0)


@pytest.mark.asyncio
async def test_interrupt_unfinished_rolls_back_on_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    queued_conversation = await _create_conversation(repository, tmp_path, title="Queued")
    waiting_conversation = await _create_conversation(repository, tmp_path, title="Waiting")

    _, queued_run = await repository.begin_run(
        queued_conversation,
        content="queued",
        session_id=SESSION_ID,
    )
    queued_before = await repository.get_run(queued_run.session_id)

    waiting_run = await _run_to_waiting_approval(
        repository,
        waiting_conversation,
        session_id=SESSION_ID_B,
    )
    waiting_before = await repository.get_run(waiting_run.session_id)
    pending_approval = await repository.create_approval(
        conversation_id=waiting_conversation,
        session_id=waiting_run.session_id,
        tool_call_id="call-rollback",
        tool_name="read_file",
        canonical_path="/tmp/rollback.txt",
        approval_id=APPROVAL_ID,
    )
    pending_before = await repository.get_approval(pending_approval.approval_id)

    original_connect = ConversationRepository._connect

    @contextmanager
    def failing_connect(self: ConversationRepository) -> Iterator[sqlite3.Connection]:
        with original_connect(self) as connection:
            wrapped = _InterceptingConnection(
                connection,
                fail_on=lambda sql: "UPDATE approval_requests" in sql,
            )
            yield cast(sqlite3.Connection, wrapped)

    monkeypatch.setattr(ConversationRepository, "_connect", failing_connect)
    with pytest.raises(sqlite3.OperationalError):
        await repository.interrupt_unfinished()

    assert (await repository.get_run(queued_run.session_id)) == queued_before
    assert (await repository.get_run(waiting_run.session_id)) == waiting_before
    assert (await repository.get_approval(pending_approval.approval_id)) == pending_before


# ── Task 12: conversation state recovery ─────────────────────────────────


@pytest.mark.asyncio
async def test_get_conversation_state_returns_none_when_no_runs(tmp_path: Path) -> None:
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    conversation_id = await _create_conversation(repository, tmp_path)

    latest_run, pending_approval = await repository.get_conversation_state(conversation_id)

    assert latest_run is None
    assert pending_approval is None


@pytest.mark.asyncio
async def test_get_conversation_state_selects_latest_run_by_message_sequence(
    tmp_path: Path,
) -> None:
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    conversation_id = await _create_conversation(repository, tmp_path)

    _, first_run = await repository.begin_run(
        conversation_id,
        content="first",
        session_id=SESSION_ID,
    )
    await repository.transition_run(
        first_run.session_id,
        RunStatus.QUEUED,
        RunStatus.RUNNING,
    )
    await repository.complete_run(first_run.session_id, "first answer")

    _, second_run = await repository.begin_run(
        conversation_id,
        content="second",
        session_id=SESSION_ID_B,
    )
    await repository.transition_run(
        second_run.session_id,
        RunStatus.QUEUED,
        RunStatus.RUNNING,
    )

    latest_run, pending_approval = await repository.get_conversation_state(conversation_id)

    assert latest_run is not None
    assert latest_run.session_id == SESSION_ID_B
    assert pending_approval is None


@pytest.mark.asyncio
async def test_get_conversation_state_does_not_use_created_at_for_latest_run(
    tmp_path: Path,
) -> None:
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    conversation_id = await _create_conversation(repository, tmp_path)
    with repository._connect() as connection:
        _insert_message(
            connection,
            message_id=MESSAGE_ID,
            conversation_id=conversation_id,
            sequence=1,
            content="older run question",
        )
        _insert_run(
            connection,
            session_id=SESSION_ID,
            conversation_id=conversation_id,
            user_message_id=MESSAGE_ID,
            status=RunStatus.COMPLETED.value,
        )
        _insert_message(
            connection,
            message_id=MESSAGE_ID_B,
            conversation_id=conversation_id,
            sequence=2,
            content="newer run question",
        )
        _insert_run(
            connection,
            session_id=SESSION_ID_B,
            conversation_id=conversation_id,
            user_message_id=MESSAGE_ID_B,
            status=RunStatus.RUNNING.value,
        )
        connection.execute(
            """
            UPDATE runs
            SET created_at = ?
            WHERE session_id = ?
            """,
            (NOW_TEXT, SESSION_ID),
        )
        connection.execute(
            """
            UPDATE runs
            SET created_at = '2020-01-01T00:00:00+00:00'
            WHERE session_id = ?
            """,
            (SESSION_ID_B,),
        )
        connection.commit()

    latest_run, _pending = await repository.get_conversation_state(conversation_id)

    assert latest_run is not None
    assert latest_run.session_id == SESSION_ID_B


@pytest.mark.asyncio
async def test_get_conversation_state_running_run_has_no_pending_approval(
    tmp_path: Path,
) -> None:
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    conversation_id = await _create_conversation(repository, tmp_path)
    _, run = await repository.begin_run(
        conversation_id,
        content="running",
        session_id=SESSION_ID,
    )
    await repository.transition_run(run.session_id, RunStatus.QUEUED, RunStatus.RUNNING)

    latest_run, pending_approval = await repository.get_conversation_state(conversation_id)

    assert latest_run is not None
    assert latest_run.status is RunStatus.RUNNING
    assert pending_approval is None


@pytest.mark.asyncio
async def test_get_conversation_state_waiting_approval_returns_pending(
    tmp_path: Path,
) -> None:
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    conversation_id = await _create_conversation(repository, tmp_path)
    waiting_run = await _run_to_waiting_approval(
        repository,
        conversation_id,
        session_id=SESSION_ID,
    )
    pending = await repository.create_approval(
        conversation_id=conversation_id,
        session_id=waiting_run.session_id,
        tool_call_id="call-wait",
        tool_name="read_file",
        canonical_path="/tmp/waiting.txt",
        approval_id=APPROVAL_ID,
    )

    latest_run, pending_approval = await repository.get_conversation_state(conversation_id)

    assert latest_run is not None
    assert latest_run.status is RunStatus.WAITING_APPROVAL
    assert pending_approval == pending


@pytest.mark.asyncio
async def test_get_conversation_state_terminal_run_has_no_pending_approval(
    tmp_path: Path,
) -> None:
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    conversation_id = await _create_conversation(repository, tmp_path)
    _, run = await repository.begin_run(
        conversation_id,
        content="done",
        session_id=SESSION_ID,
    )
    await repository.transition_run(run.session_id, RunStatus.QUEUED, RunStatus.RUNNING)
    await repository.complete_run(run.session_id, "done")
    with repository._connect() as connection:
        _insert_pending_approval(
            connection,
            approval_id=APPROVAL_ID,
            conversation_id=conversation_id,
            session_id=run.session_id,
        )
        connection.commit()

    latest_run, pending_approval = await repository.get_conversation_state(conversation_id)

    assert latest_run is not None
    assert latest_run.status is RunStatus.COMPLETED
    assert pending_approval is None


@pytest.mark.asyncio
async def test_get_conversation_state_does_not_recover_resolved_approvals(
    tmp_path: Path,
) -> None:
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    conversation_id = await _create_conversation(repository, tmp_path)
    waiting_run = await _run_to_waiting_approval(
        repository,
        conversation_id,
        session_id=SESSION_ID,
    )
    with repository._connect() as connection:
        _insert_decided_approval(
            connection,
            approval_id=APPROVAL_ID,
            conversation_id=conversation_id,
            session_id=waiting_run.session_id,
            status=ApprovalStatus.DENIED.value,
        )
        connection.commit()

    _latest_run, pending_approval = await repository.get_conversation_state(conversation_id)

    assert pending_approval is None


@pytest.mark.asyncio
async def test_get_conversation_state_does_not_leak_other_conversation(
    tmp_path: Path,
) -> None:
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    conversation_a = await _create_conversation(repository, tmp_path, title="A")
    conversation_b = await _create_conversation(repository, tmp_path, title="B")
    await _run_to_waiting_approval(repository, conversation_b, session_id=SESSION_ID_B)
    await repository.create_approval(
        conversation_id=conversation_b,
        session_id=SESSION_ID_B,
        tool_call_id="call-b",
        tool_name="read_file",
        canonical_path="/tmp/other.txt",
        approval_id=APPROVAL_ID_B,
    )

    latest_run, pending_approval = await repository.get_conversation_state(conversation_a)

    assert latest_run is None
    assert pending_approval is None


@pytest.mark.asyncio
async def test_get_conversation_state_missing_conversation_raises_not_found(
    tmp_path: Path,
) -> None:
    repository = await _open_repository(tmp_path / "chat.sqlite3")

    with pytest.raises(ChatNotFoundError):
        await repository.get_conversation_state(CONVERSATION_ID_A)
