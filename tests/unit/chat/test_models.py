from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from pydantic import ValidationError

from agent_foundations.chat.models import (
    AccessOperation,
    AccessScope,
    ApprovalRequest,
    ApprovalStatus,
    ChatEvent,
    ChatEventType,
    ChatMessage,
    Conversation,
    MessageRole,
    PermissionMode,
    PolicyDecision,
    ResourceKind,
    RunRecord,
    RunStatus,
)

NOW = datetime(2026, 8, 2, tzinfo=UTC)
NAIVE = datetime(2026, 8, 2, 12, 0, 0)
CONVERSATION_ID = "11111111-1111-4111-8111-111111111111"
SESSION_ID = "22222222-2222-4222-8222-222222222222"
MESSAGE_ID = "33333333-3333-4333-8333-333333333333"
APPROVAL_ID = "44444444-4444-4444-8444-444444444444"
EVENT_ID = "55555555-5555-4555-8555-555555555555"
TRACE_PATH = f"traces/{SESSION_ID}.jsonl"


def test_conversation_normalizes_existing_project_root(tmp_path: Path) -> None:
    conversation = Conversation(
        conversation_id=CONVERSATION_ID,
        title="Learn Agent Runtime",
        project_root=str(tmp_path),
        permission_mode=PermissionMode.PROJECT_READ_ONLY,
        created_at=NOW,
        updated_at=NOW,
    )
    assert conversation.project_root == str(tmp_path.resolve())
    assert conversation.permission_mode.value == "PROJECT_READ_ONLY"


def test_conversation_rejects_missing_root(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="existing directory"):
        Conversation(
            conversation_id=CONVERSATION_ID,
            title="Invalid",
            project_root=str(tmp_path / "missing"),
            permission_mode=PermissionMode.ASK_FOR_ACCESS,
            created_at=NOW,
            updated_at=NOW,
        )


def test_conversation_rejects_non_directory_root(tmp_path: Path) -> None:
    file_path = tmp_path / "not-a-dir.txt"
    file_path.write_text("x", encoding="utf-8")
    with pytest.raises(ValidationError, match="existing directory"):
        Conversation(
            conversation_id=CONVERSATION_ID,
            title="Invalid",
            project_root=str(file_path),
            permission_mode=PermissionMode.PROJECT_READ_ONLY,
            created_at=NOW,
            updated_at=NOW,
        )


def test_run_and_approval_identifiers_are_validated(tmp_path: Path) -> None:
    run = RunRecord(
        session_id=SESSION_ID,
        conversation_id=CONVERSATION_ID,
        user_message_id=MESSAGE_ID,
        trace_path=TRACE_PATH,
        status=RunStatus.QUEUED,
        created_at=NOW,
    )
    UUID(run.session_id)
    approval = ApprovalRequest(
        approval_id=APPROVAL_ID,
        conversation_id=run.conversation_id,
        session_id=run.session_id,
        tool_call_id="call-1",
        tool_name="read_file",
        canonical_path=str(tmp_path.resolve()),
        operation=AccessOperation.READ,
        status=ApprovalStatus.PENDING,
        requested_at=NOW,
    )
    assert approval.operation == AccessOperation.READ
    with pytest.raises(ValidationError):
        approval.model_copy(update={"operation": "write"})


def test_run_requires_relative_trace_path() -> None:
    run = RunRecord(
        session_id=SESSION_ID,
        conversation_id=CONVERSATION_ID,
        user_message_id=MESSAGE_ID,
        trace_path=TRACE_PATH,
        created_at=NOW,
    )
    assert run.trace_path == TRACE_PATH
    with pytest.raises(ValidationError, match="relative trace path"):
        run.model_copy(update={"trace_path": "../outside.jsonl"})


@pytest.mark.parametrize(
    "invalid_trace_path",
    [
        "traces/id.jsonl:secret",
        "traces/id.jsonl::$DATA",
        "traces/id.jsonl\x00hidden",
        "traces/id.jsonl\nhidden",
        "traces/id.jsonl\rhidden",
        "traces/id.jsonl\thidden",
    ],
)
def test_run_trace_path_rejects_ads_and_control_characters(
    invalid_trace_path: str,
) -> None:
    with pytest.raises(ValidationError, match="relative trace path"):
        RunRecord(
            session_id=SESSION_ID,
            conversation_id=CONVERSATION_ID,
            user_message_id=MESSAGE_ID,
            trace_path=invalid_trace_path,
            created_at=NOW,
        )


@pytest.mark.parametrize(
    "invalid_trace_path",
    [
        "traces/id.jsonl:secret",
        "traces/id.jsonl::$DATA",
        "traces/id.jsonl\x00hidden",
        "traces/id.jsonl\nhidden",
        "traces/id.jsonl\rhidden",
        "traces/id.jsonl\thidden",
    ],
)
def test_run_trace_path_model_copy_rejects_ads_and_control_characters(
    invalid_trace_path: str,
) -> None:
    run = RunRecord(
        session_id=SESSION_ID,
        conversation_id=CONVERSATION_ID,
        user_message_id=MESSAGE_ID,
        trace_path=TRACE_PATH,
        created_at=NOW,
    )
    with pytest.raises(ValidationError, match="relative trace path"):
        run.model_copy(update={"trace_path": invalid_trace_path})


def test_chat_event_is_utc_frozen_and_json_safe() -> None:
    event = ChatEvent(
        event_id=EVENT_ID,
        conversation_id=CONVERSATION_ID,
        session_id=SESSION_ID,
        type=ChatEventType.RUN_STARTED,
        occurred_at=NOW,
        data={"status": "running"},
    )
    assert event.model_dump(mode="json")["data"] == {"status": "running"}
    mutable_view: Any = event.data
    with pytest.raises(TypeError):
        mutable_view["status"] = "changed"


def test_visible_message_roles_exclude_system_and_tool() -> None:
    assert {role.value for role in MessageRole} == {"user", "assistant"}
    assert RunStatus.active() == {
        RunStatus.QUEUED,
        RunStatus.RUNNING,
        RunStatus.WAITING_APPROVAL,
    }


def test_access_dimensions_are_explicit() -> None:
    assert ResourceKind.FILESYSTEM.value == "filesystem"
    assert AccessOperation.READ.value == "read"
    assert {scope.value for scope in AccessScope} == {"project", "external_exact_path"}
    assert {decision.value for decision in PolicyDecision} == {"allow", "deny", "ask"}


@pytest.mark.parametrize(
    "build_invalid",
    [
        lambda: Conversation(
            conversation_id="not-a-uuid",
            title="Bad id",
            project_root=".",
            permission_mode=PermissionMode.PROJECT_READ_ONLY,
            created_at=NOW,
            updated_at=NOW,
        ),
        lambda: RunRecord(
            session_id="bad",
            conversation_id=CONVERSATION_ID,
            user_message_id=MESSAGE_ID,
            trace_path=TRACE_PATH,
            created_at=NOW,
        ),
        lambda: ChatMessage(
            message_id="bad",
            conversation_id=CONVERSATION_ID,
            role=MessageRole.USER,
            content="hello",
            sequence=1,
            created_at=NOW,
        ),
        lambda: ApprovalRequest(
            approval_id="bad",
            conversation_id=CONVERSATION_ID,
            session_id=SESSION_ID,
            tool_call_id="call-1",
            tool_name="read_file",
            canonical_path="/tmp/example",
            requested_at=NOW,
        ),
        lambda: ChatEvent(
            event_id="bad",
            conversation_id=CONVERSATION_ID,
            session_id=SESSION_ID,
            type=ChatEventType.RUN_STARTED,
            occurred_at=NOW,
        ),
    ],
)
def test_uuid_fields_are_validated(build_invalid: Callable[[], object]) -> None:
    with pytest.raises(ValidationError):
        build_invalid()


@pytest.mark.parametrize(
    "build_invalid",
    [
        lambda tmp_path: Conversation(
            conversation_id=CONVERSATION_ID,
            title="Naive time",
            project_root=str(tmp_path),
            permission_mode=PermissionMode.PROJECT_READ_ONLY,
            created_at=NAIVE,
            updated_at=NOW,
        ),
        lambda tmp_path: ChatMessage(
            message_id=MESSAGE_ID,
            conversation_id=CONVERSATION_ID,
            role=MessageRole.USER,
            content="hello",
            sequence=1,
            created_at=NAIVE,
        ),
        lambda tmp_path: RunRecord(
            session_id=SESSION_ID,
            conversation_id=CONVERSATION_ID,
            user_message_id=MESSAGE_ID,
            trace_path=TRACE_PATH,
            created_at=NAIVE,
        ),
        lambda tmp_path: ApprovalRequest(
            approval_id=APPROVAL_ID,
            conversation_id=CONVERSATION_ID,
            session_id=SESSION_ID,
            tool_call_id="call-1",
            tool_name="read_file",
            canonical_path=str(tmp_path.resolve()),
            requested_at=NAIVE,
        ),
        lambda tmp_path: ChatEvent(
            event_id=EVENT_ID,
            conversation_id=CONVERSATION_ID,
            session_id=SESSION_ID,
            type=ChatEventType.RUN_STARTED,
            occurred_at=NAIVE,
        ),
    ],
)
def test_datetime_fields_reject_naive_and_normalize_to_utc(
    tmp_path: Path,
    build_invalid: Callable[[Path], object],
) -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        build_invalid(tmp_path)


def test_non_utc_datetime_is_normalized_to_utc() -> None:
    from datetime import timedelta, timezone

    east = timezone(timedelta(hours=8))
    event = ChatEvent(
        event_id=EVENT_ID,
        conversation_id=CONVERSATION_ID,
        session_id=SESSION_ID,
        type=ChatEventType.RUN_STARTED,
        occurred_at=datetime(2026, 8, 2, 20, 0, 0, tzinfo=east),
    )
    assert event.occurred_at.tzinfo is UTC
    assert event.occurred_at.hour == 12
