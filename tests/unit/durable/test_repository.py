from __future__ import annotations

import asyncio
import importlib.util
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

RUN_ID = "22222222-2222-4222-8222-222222222222"
RUN_ID_B = "44444444-4444-4444-8444-444444444444"
CONVERSATION_ID = "11111111-1111-4111-8111-111111111111"
MESSAGE_ID = "33333333-3333-4333-8333-333333333333"
APPROVAL_ID = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
PROJECT_ROOT = "/tmp/project"
NOW_TEXT = "2026-08-02T12:00:00+00:00"
TRACE_PATH = "traces/session.jsonl"
ACTIVITY_EVENT_ID = "12345678-1234-4234-8234-123456789001"
NOW = datetime(2026, 8, 2, 12, 0, 0, tzinfo=UTC)


def _require_durable_repository() -> None:
    package_spec = importlib.util.find_spec("agent_foundations.durable")
    assert package_spec is not None, "agent_foundations.durable package must exist"
    module_spec = importlib.util.find_spec("agent_foundations.durable.repository")
    assert module_spec is not None, "agent_foundations.durable.repository must exist"


def _require_application_migrations() -> None:
    spec = importlib.util.find_spec("agent_foundations.storage.migrations")
    assert spec is not None
    from agent_foundations.storage.migrations import get_application_migrations

    migrations = get_application_migrations()
    assert len(migrations) == 7
    assert migrations[-1].version == 7


def _tables(connection: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'",
        )
    }


def _indexes(connection: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index'",
        )
    }


def _import_chat_schema() -> tuple[Any, Any, Any]:
    from agent_foundations.chat.schema import (
        CHAT_MIGRATIONS,
        MIGRATION_V1_TO_V2_STATEMENTS,
        SCHEMA_V1_STATEMENTS,
    )

    return CHAT_MIGRATIONS, SCHEMA_V1_STATEMENTS, MIGRATION_V1_TO_V2_STATEMENTS


def _insert_v1_core_rows(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        INSERT INTO conversations (
            conversation_id, title, project_root, permission_mode, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            CONVERSATION_ID,
            "fixture conversation",
            PROJECT_ROOT,
            "PROJECT_READ_ONLY",
            NOW_TEXT,
            NOW_TEXT,
        ),
    )
    connection.execute(
        """
        INSERT INTO messages (
            message_id, conversation_id, role, content, sequence, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (MESSAGE_ID, CONVERSATION_ID, "user", "fixture question", 1, NOW_TEXT),
    )
    connection.execute(
        """
        INSERT INTO runs (
            session_id, conversation_id, user_message_id, assistant_message_id,
            trace_path, status, error_code, created_at, started_at, finished_at
        ) VALUES (?, ?, ?, NULL, ?, ?, NULL, ?, NULL, NULL)
        """,
        (RUN_ID, CONVERSATION_ID, MESSAGE_ID, TRACE_PATH, "completed", NOW_TEXT),
    )
    connection.execute(
        """
        INSERT INTO approval_requests (
            approval_id, conversation_id, session_id, tool_call_id, tool_name,
            canonical_path, operation, status, requested_at, decided_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
        """,
        (
            APPROVAL_ID,
            CONVERSATION_ID,
            RUN_ID,
            "call-1",
            "read_file",
            "README.md",
            "read",
            "pending",
            NOW_TEXT,
        ),
    )


def _insert_v2_activity_row(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        INSERT INTO chat_tool_activities (
            session_id, tool_call_id, tool_name, status,
            arguments_summary, result_summary, started_at, finished_at, last_event_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            RUN_ID,
            "call-activity",
            "read_file",
            "completed",
            "README.md",
            "12 lines",
            NOW_TEXT,
            NOW_TEXT,
            ACTIVITY_EVENT_ID,
        ),
    )


def _create_real_v2_database(path: Path) -> dict[str, Any]:
    _, SCHEMA_V1_STATEMENTS, MIGRATION_V1_TO_V2 = _import_chat_schema()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        for statement in SCHEMA_V1_STATEMENTS:
            connection.execute(statement)
        _insert_v1_core_rows(connection)
        connection.execute("PRAGMA user_version = 1")
        connection.commit()
        preserved_v1 = {
            table: [
                tuple(row)
                for row in connection.execute(f"SELECT * FROM {table} ORDER BY rowid")
            ]
            for table in (
                "conversations",
                "messages",
                "runs",
                "approval_requests",
            )
        }
        for statement in MIGRATION_V1_TO_V2:
            connection.execute(statement)
        _insert_v2_activity_row(connection)
        connection.execute("PRAGMA user_version = 2")
        connection.commit()
        activity_rows = [
            tuple(row)
            for row in connection.execute(
                "SELECT * FROM chat_tool_activities ORDER BY rowid",
            )
        ]
        indexes = _indexes(connection)
    finally:
        connection.close()
    return {
        "v1_rows": preserved_v1,
        "activity_rows": activity_rows,
        "indexes": indexes,
    }


async def _open_repository(path: Path) -> Any:
    from agent_foundations.durable.repository import DurableRunRepository

    repository = DurableRunRepository(path)
    await repository.initialize()
    return repository


def _sample_run_state() -> Any:
    from agent_foundations.domain.messages import Message, Role
    from agent_foundations.durable.models import RunState

    return RunState(
        schema_version=1,
        messages=(Message(role=Role.USER, content="hello"),),
        next_step=1,
        attempt=1,
    )


def _sample_durable_run() -> Any:
    from agent_foundations.durable.models import DurableRun, DurableRunStatus

    return DurableRun(
        run_id=RUN_ID,
        project_root=PROJECT_ROOT,
        status=DurableRunStatus.CREATED,
        schema_version=1,
        state_version=0,
        attempt=1,
        created_at=NOW,
        updated_at=NOW,
    )


@pytest.mark.asyncio
async def test_empty_database_migrates_v1_v2_v3(tmp_path: Path) -> None:
    _require_durable_repository()
    _require_application_migrations()
    from agent_foundations.storage.database import SqliteDatabase
    from agent_foundations.storage.migrations import get_application_migrations

    path = tmp_path / "app.sqlite3"
    database = SqliteDatabase(path, get_application_migrations())
    await database.initialize()
    with database.connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 7
        assert _tables(connection) >= {
            "conversations",
            "messages",
            "runs",
            "approval_requests",
            "chat_tool_activities",
            "durable_runs",
            "run_checkpoints",
            "run_leases",
            "side_effects",
            "patch_proposals",
        }


@pytest.mark.asyncio
async def test_v2_database_upgrades_to_v3_preserving_chat_data(tmp_path: Path) -> None:
    _require_durable_repository()
    path = tmp_path / "chat.sqlite3"
    preserved = _create_real_v2_database(path)
    repository = await _open_repository(path)
    with repository._database.connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 7
        assert _tables(connection) >= {"durable_runs", "run_checkpoints"}
        preserved_after = {
            table: [
                tuple(row)
                for row in connection.execute(f"SELECT * FROM {table} ORDER BY rowid")
            ]
            for table in preserved["v1_rows"]
        }
        activity_rows = [
            tuple(row)
            for row in connection.execute(
                "SELECT * FROM chat_tool_activities ORDER BY rowid",
            )
        ]
        indexes = _indexes(connection)
    assert preserved_after == preserved["v1_rows"]
    assert activity_rows == preserved["activity_rows"]
    assert "idx_chat_tool_activities_session_started" in indexes
    assert preserved["indexes"] <= indexes


@pytest.mark.asyncio
async def test_conversation_repository_opens_v3_database(tmp_path: Path) -> None:
    _require_durable_repository()
    from agent_foundations.chat.repository import ConversationRepository

    path = tmp_path / "chat.sqlite3"
    durable = await _open_repository(path)
    assert durable is not None
    chat = ConversationRepository(path)
    await chat.initialize()
    with chat._connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 7


@pytest.mark.asyncio
async def test_create_run_preserves_session_uuid(tmp_path: Path) -> None:
    _require_durable_repository()
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    run = _sample_durable_run()
    created = await repository.create_run(run)
    assert created.run_id == RUN_ID
    with repository._database.connect() as connection:
        row = connection.execute(
            "SELECT run_id FROM durable_runs WHERE run_id = ?",
            (RUN_ID,),
        ).fetchone()
    assert row is not None
    assert row[0] == RUN_ID


@pytest.mark.asyncio
async def test_create_run_rejects_duplicate_run_id(tmp_path: Path) -> None:
    _require_durable_repository()
    from agent_foundations.durable.repository import DurableRunAlreadyExistsError

    repository = await _open_repository(tmp_path / "chat.sqlite3")
    run = _sample_durable_run()
    await repository.create_run(run)
    with pytest.raises(DurableRunAlreadyExistsError):
        await repository.create_run(run)


@pytest.mark.asyncio
async def test_save_checkpoint_starts_sequence_at_one(tmp_path: Path) -> None:
    _require_durable_repository()
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    await repository.create_run(_sample_durable_run())
    state = _sample_run_state()
    checkpoint = await repository.save_checkpoint(RUN_ID, 0, state)
    assert checkpoint.sequence == 1
    assert checkpoint.run_id == RUN_ID


@pytest.mark.asyncio
async def test_checkpoint_sequence_increases_monotonically(tmp_path: Path) -> None:
    _require_durable_repository()
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    await repository.create_run(_sample_durable_run())
    first = await repository.save_checkpoint(RUN_ID, 0, _sample_run_state())
    second = await repository.save_checkpoint(
        RUN_ID,
        1,
        _sample_run_state().model_copy(update={"next_step": 2}),
    )
    assert first.sequence == 1
    assert second.sequence == 2


@pytest.mark.asyncio
async def test_save_checkpoint_increments_state_version(tmp_path: Path) -> None:
    _require_durable_repository()
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    await repository.create_run(_sample_durable_run())
    await repository.save_checkpoint(RUN_ID, 0, _sample_run_state())
    with repository._database.connect() as connection:
        version = connection.execute(
            "SELECT state_version FROM durable_runs WHERE run_id = ?",
            (RUN_ID,),
        ).fetchone()[0]
    assert version == 1
    await repository.save_checkpoint(RUN_ID, 1, _sample_run_state())
    with repository._database.connect() as connection:
        version = connection.execute(
            "SELECT state_version FROM durable_runs WHERE run_id = ?",
            (RUN_ID,),
        ).fetchone()[0]
    assert version == 2


@pytest.mark.asyncio
async def test_save_checkpoint_rejects_cross_run_execution_fact(tmp_path: Path) -> None:
    _require_durable_repository()
    from agent_foundations.durable.repository import ExecutionFactRunMismatchError
    from agent_foundations.planning.execution import ExecutionFact

    repository = await _open_repository(tmp_path / "chat.sqlite3")
    await repository.create_run(_sample_durable_run())
    baseline = await repository.save_checkpoint(RUN_ID, 0, _sample_run_state())
    cross_run_state = _sample_run_state().model_copy(
        update={
            "last_committed_tool_fact": ExecutionFact(
                session_id=RUN_ID_B,
                tool_call_id="call-cross",
                tool_name="read_file",
                success=True,
            ),
        },
    )
    with pytest.raises(ExecutionFactRunMismatchError, match="session_id"):
        await repository.save_checkpoint(RUN_ID, 1, cross_run_state)
    with repository._database.connect() as connection:
        version = connection.execute(
            "SELECT state_version FROM durable_runs WHERE run_id = ?",
            (RUN_ID,),
        ).fetchone()[0]
        count = connection.execute(
            "SELECT COUNT(*) FROM run_checkpoints WHERE run_id = ?",
            (RUN_ID,),
        ).fetchone()[0]
    assert version == 1
    assert count == 1
    assert await repository.load_latest_checkpoint(RUN_ID) == baseline


@pytest.mark.asyncio
async def test_stale_expected_state_version_raises_conflict(tmp_path: Path) -> None:
    _require_durable_repository()
    from agent_foundations.durable.repository import StateVersionConflictError

    repository = await _open_repository(tmp_path / "chat.sqlite3")
    await repository.create_run(_sample_durable_run())
    await repository.save_checkpoint(RUN_ID, 0, _sample_run_state())
    with pytest.raises(StateVersionConflictError):
        await repository.save_checkpoint(RUN_ID, 0, _sample_run_state())
    latest = await repository.load_latest_checkpoint(RUN_ID)
    assert latest.sequence == 1


@pytest.mark.asyncio
async def test_concurrent_save_checkpoint_only_one_succeeds(tmp_path: Path) -> None:
    _require_durable_repository()
    from agent_foundations.durable.repository import StateVersionConflictError

    repository = await _open_repository(tmp_path / "chat.sqlite3")
    await repository.create_run(_sample_durable_run())
    results = await asyncio.gather(
        repository.save_checkpoint(RUN_ID, 0, _sample_run_state()),
        repository.save_checkpoint(RUN_ID, 0, _sample_run_state()),
        return_exceptions=True,
    )
    successes = [result for result in results if not isinstance(result, BaseException)]
    conflicts = [result for result in results if isinstance(result, StateVersionConflictError)]
    assert len(successes) == 1
    assert len(conflicts) == 1
    latest = await repository.load_latest_checkpoint(RUN_ID)
    assert latest.sequence == 1
    with repository._database.connect() as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM run_checkpoints WHERE run_id = ?",
            (RUN_ID,),
        ).fetchone()[0]
    assert count == 1


@pytest.mark.asyncio
async def test_save_checkpoint_rejects_unknown_run(tmp_path: Path) -> None:
    _require_durable_repository()
    from agent_foundations.durable.repository import DurableRunNotFoundError

    repository = await _open_repository(tmp_path / "chat.sqlite3")
    with pytest.raises(DurableRunNotFoundError):
        await repository.save_checkpoint(RUN_ID, 0, _sample_run_state())


@pytest.mark.asyncio
async def test_load_latest_checkpoint_rejects_when_none_exist(tmp_path: Path) -> None:
    _require_durable_repository()
    from agent_foundations.durable.repository import CheckpointNotFoundError

    repository = await _open_repository(tmp_path / "chat.sqlite3")
    await repository.create_run(_sample_durable_run())
    with pytest.raises(CheckpointNotFoundError):
        await repository.load_latest_checkpoint(RUN_ID)


@pytest.mark.asyncio
async def test_load_latest_checkpoint_returns_highest_sequence(tmp_path: Path) -> None:
    _require_durable_repository()
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    await repository.create_run(_sample_durable_run())
    await repository.save_checkpoint(RUN_ID, 0, _sample_run_state())
    await repository.save_checkpoint(
        RUN_ID,
        1,
        _sample_run_state().model_copy(update={"next_step": 2}),
    )
    latest = await repository.load_latest_checkpoint(RUN_ID)
    assert latest.sequence == 2
    assert latest.state.next_step == 2
    with pytest.raises(ValidationError):
        latest.state.next_step = 99


@pytest.mark.asyncio
async def test_load_latest_checkpoint_rejects_unknown_row_schema_version(
    tmp_path: Path,
) -> None:
    _require_durable_repository()
    from agent_foundations.durable.repository import UnsupportedCheckpointSchemaVersionError

    repository = await _open_repository(tmp_path / "chat.sqlite3")
    await repository.create_run(_sample_durable_run())
    checkpoint = await repository.save_checkpoint(RUN_ID, 0, _sample_run_state())
    with repository._database.connect() as connection:
        connection.execute(
            "UPDATE run_checkpoints SET schema_version = 99 WHERE checkpoint_id = ?",
            (checkpoint.checkpoint_id,),
        )
        connection.commit()
    with pytest.raises(UnsupportedCheckpointSchemaVersionError):
        await repository.load_latest_checkpoint(RUN_ID)


@pytest.mark.asyncio
async def test_load_latest_checkpoint_rejects_mismatched_state_json_schema_version(
    tmp_path: Path,
) -> None:
    _require_durable_repository()
    from agent_foundations.durable.repository import UnsupportedCheckpointSchemaVersionError

    repository = await _open_repository(tmp_path / "chat.sqlite3")
    await repository.create_run(_sample_durable_run())
    checkpoint = await repository.save_checkpoint(RUN_ID, 0, _sample_run_state())
    with repository._database.connect() as connection:
        connection.execute(
            "UPDATE run_checkpoints SET state_json = ? WHERE checkpoint_id = ?",
            (
                '{"schema_version":99,"messages":[],"next_step":1,"attempt":1}',
                checkpoint.checkpoint_id,
            ),
        )
        connection.commit()
    with pytest.raises(UnsupportedCheckpointSchemaVersionError):
        await repository.load_latest_checkpoint(RUN_ID)


@pytest.mark.asyncio
async def test_checkpoint_insert_failure_rolls_back_run_version(tmp_path: Path) -> None:
    _require_durable_repository()
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    await repository.create_run(_sample_durable_run())
    with repository._database.connect() as connection:
        connection.execute(
            """
            CREATE TRIGGER fail_checkpoint_insert
            BEFORE INSERT ON run_checkpoints
            BEGIN
              SELECT RAISE(ABORT, 'injected checkpoint failure');
            END
            """,
        )
        connection.commit()
    with pytest.raises(
        (sqlite3.OperationalError, sqlite3.IntegrityError),
        match="injected checkpoint failure",
    ):
        await repository.save_checkpoint(RUN_ID, 0, _sample_run_state())
    with repository._database.connect() as connection:
        version = connection.execute(
            "SELECT state_version FROM durable_runs WHERE run_id = ?",
            (RUN_ID,),
        ).fetchone()[0]
        count = connection.execute(
            "SELECT COUNT(*) FROM run_checkpoints WHERE run_id = ?",
            (RUN_ID,),
        ).fetchone()[0]
    assert version == 0
    assert count == 0


@pytest.mark.asyncio
async def test_v3_database_upgrades_to_v4_preserving_durable_data(tmp_path: Path) -> None:
    _require_durable_repository()
    from agent_foundations.storage.database import SqliteDatabase
    from agent_foundations.storage.migrations import get_application_migrations

    path = tmp_path / "chat.sqlite3"
    migrations = get_application_migrations()
    v3_migrations = migrations[:3]
    database = SqliteDatabase(path, v3_migrations)
    await database.initialize()
    from agent_foundations.durable.repository import DurableRunRepository

    repository = DurableRunRepository(path)
    await repository.create_run(_sample_durable_run())
    checkpoint = await repository.save_checkpoint(RUN_ID, 0, _sample_run_state())
    with repository._database.connect() as connection:
        preserved_runs = [
            tuple(row)
            for row in connection.execute("SELECT * FROM durable_runs ORDER BY rowid")
        ]
        preserved_checkpoints = [
            tuple(row)
            for row in connection.execute("SELECT * FROM run_checkpoints ORDER BY rowid")
        ]
    await repository.initialize()
    with repository._database.connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 7
        assert "run_leases" in _tables(connection)
        assert "idx_run_leases_active_run" in _indexes(connection)
        assert "idx_run_leases_run_acquired" in _indexes(connection)
        runs_after = [
            tuple(row)
            for row in connection.execute("SELECT * FROM durable_runs ORDER BY rowid")
        ]
        checkpoints_after = [
            tuple(row)
            for row in connection.execute("SELECT * FROM run_checkpoints ORDER BY rowid")
        ]
    assert runs_after == preserved_runs
    assert checkpoints_after == preserved_checkpoints
    assert checkpoint.run_id == RUN_ID


@pytest.mark.asyncio
async def test_initialize_rejects_future_user_version(tmp_path: Path) -> None:
    _require_durable_repository()
    from agent_foundations.storage.database import FutureSchemaVersionError

    repository = await _open_repository(tmp_path / "chat.sqlite3")
    with repository._database.connect() as connection:
        connection.execute("PRAGMA user_version = 8")
        connection.commit()
    with pytest.raises(FutureSchemaVersionError):
        await repository.initialize()
