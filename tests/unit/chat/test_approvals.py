from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from agent_foundations.chat.errors import (
    ApprovalUnavailableError,
    ChatConflictError,
    ChatNotFoundError,
)
from agent_foundations.chat.events import ChatEventBroker
from agent_foundations.chat.models import (
    AccessOperation,
    ApprovalRequest,
    ApprovalStatus,
    ChatEventType,
    PermissionMode,
    RunStatus,
)
from agent_foundations.chat.repository import ConversationRepository

CONVERSATION_ID = "11111111-1111-4111-8111-111111111111"
SESSION_ID = "22222222-2222-4222-8222-222222222222"
SESSION_ID_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
APPROVAL_ID = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
APPROVAL_ID_B = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"


def _require_coordinator() -> Any:
    try:
        from agent_foundations.chat.approvals import ApprovalCoordinator
        from agent_foundations.chat.models import ApprovalDecision
    except ImportError as exc:
        raise AssertionError(f"ApprovalCoordinator missing: {exc}") from exc
    return ApprovalCoordinator, ApprovalDecision


async def _open_repository(database_path: Path) -> ConversationRepository:
    repository = ConversationRepository(database_path)
    await repository.initialize()
    return repository


async def _running_run(
    repository: ConversationRepository,
    tmp_path: Path,
    *,
    session_id: str = SESSION_ID,
) -> tuple[str, str]:
    conversation = await repository.create_conversation(
        title="Approval study",
        project_root=tmp_path,
        permission_mode=PermissionMode.ASK_FOR_ACCESS,
    )
    _, run = await repository.begin_run(
        conversation.conversation_id,
        content="approval question",
        session_id=session_id,
    )
    await repository.transition_run(
        run.session_id,
        RunStatus.QUEUED,
        RunStatus.RUNNING,
    )
    return conversation.conversation_id, run.session_id


def _approval_request(
    conversation_id: str,
    session_id: str,
    *,
    approval_id: str = APPROVAL_ID,
    tool_call_id: str = "tool-call-1",
) -> ApprovalRequest:
    return ApprovalRequest(
        approval_id=approval_id,
        conversation_id=conversation_id,
        session_id=session_id,
        tool_call_id=tool_call_id,
        tool_name="read_file",
        canonical_path="/outside/project/secret.txt",
        operation=AccessOperation.READ,
        status=ApprovalStatus.PENDING,
    )


async def _wait_for_pending(
    repository: ConversationRepository,
    approval_id: str,
) -> ApprovalRequest:
    deadline = asyncio.get_running_loop().time() + 2.0
    while asyncio.get_running_loop().time() < deadline:
        try:
            approval = await repository.get_approval(approval_id)
        except ChatNotFoundError:
            await asyncio.sleep(0.01)
            continue
        if approval.status is ApprovalStatus.PENDING:
            return approval
        await asyncio.sleep(0.01)
    raise AssertionError("approval did not reach pending state in time")


class RecordingBroker(ChatEventBroker):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[Any] = []

    async def publish(self, event: Any) -> None:
        self.events.append(event)
        await super().publish(event)


class FailingBroker(ChatEventBroker):
    def __init__(self, *, fail_on: ChatEventType) -> None:
        super().__init__()
        self.fail_on = fail_on

    async def publish(self, event: Any) -> None:
        if event.type is self.fail_on:
            raise RuntimeError("do-not-leak-publish-secret")
        await super().publish(event)


class BlockingCreateApprovalRepository:
    def __init__(self, repository: ConversationRepository) -> None:
        self._repository = repository
        self.create_started = asyncio.Event()
        self.release_create = asyncio.Event()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._repository, name)

    async def create_approval(self, *args: Any, **kwargs: Any) -> ApprovalRequest:
        self.create_started.set()
        await self.release_create.wait()
        return await self._repository.create_approval(*args, **kwargs)


class BlockingResolveApprovalRepository:
    def __init__(self, repository: ConversationRepository) -> None:
        self._repository = repository
        self.resolve_started = asyncio.Event()
        self.release_resolve = asyncio.Event()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._repository, name)

    async def resolve_approval(
        self,
        approval_id: str,
        decision: ApprovalStatus,
    ) -> ApprovalRequest:
        self.resolve_started.set()
        await self.release_resolve.wait()
        return await self._repository.resolve_approval(approval_id, decision)


class BlockingRequestedPublishBroker(RecordingBroker):
    def __init__(self) -> None:
        super().__init__()
        self.requested_publish_started = asyncio.Event()
        self.release_requested_publish = asyncio.Event()
        self.fail_requested_publish = False

    async def publish(self, event: Any) -> None:
        if event.type is ChatEventType.APPROVAL_REQUESTED:
            self.requested_publish_started.set()
            if self.fail_requested_publish:
                raise RuntimeError("do-not-leak-requested-publish")
            await self.release_requested_publish.wait()
        await super().publish(event)


class FailingResolvedPublishBroker(RecordingBroker):
    async def publish(self, event: Any) -> None:
        if event.type is ChatEventType.APPROVAL_RESOLVED:
            raise RuntimeError("do-not-leak-resolved-publish")
        await super().publish(event)


@pytest.mark.asyncio
async def test_request_approve_flow_transitions_run_and_returns_approved(
    tmp_path: Path,
) -> None:
    ApprovalCoordinator, ApprovalDecision = _require_coordinator()
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    conversation_id, session_id = await _running_run(repository, tmp_path)
    broker = RecordingBroker()
    coordinator = ApprovalCoordinator(repository, broker)
    request = _approval_request(conversation_id, session_id)

    waiter = asyncio.create_task(coordinator.request(request))
    created = await _wait_for_pending(repository, request.approval_id)
    assert created.status is ApprovalStatus.PENDING
    assert (await repository.get_run(session_id)).status is RunStatus.WAITING_APPROVAL

    resolved = await coordinator.resolve(
        request.approval_id,
        ApprovalDecision.APPROVE,
    )
    assert resolved.status is ApprovalStatus.APPROVED
    assert await waiter is ApprovalStatus.APPROVED
    assert (await repository.get_run(session_id)).status is RunStatus.RUNNING


@pytest.mark.asyncio
async def test_request_deny_returns_denied_and_restores_running_run(
    tmp_path: Path,
) -> None:
    ApprovalCoordinator, ApprovalDecision = _require_coordinator()
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    conversation_id, session_id = await _running_run(repository, tmp_path)
    coordinator = ApprovalCoordinator(repository, ChatEventBroker())
    request = _approval_request(conversation_id, session_id)

    waiter = asyncio.create_task(coordinator.request(request))
    await _wait_for_pending(repository, request.approval_id)
    assert await coordinator.resolve(
        request.approval_id,
        ApprovalDecision.DENY,
    )
    assert await waiter is ApprovalStatus.DENIED
    assert (await repository.get_run(session_id)).status is RunStatus.RUNNING


@pytest.mark.asyncio
async def test_approval_events_contain_safe_metadata_only(tmp_path: Path) -> None:
    ApprovalCoordinator, ApprovalDecision = _require_coordinator()
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    conversation_id, session_id = await _running_run(repository, tmp_path)
    broker = RecordingBroker()
    coordinator = ApprovalCoordinator(repository, broker)
    request = _approval_request(conversation_id, session_id)

    waiter = asyncio.create_task(coordinator.request(request))
    await _wait_for_pending(repository, request.approval_id)
    await coordinator.resolve(request.approval_id, ApprovalDecision.APPROVE)
    assert await waiter is ApprovalStatus.APPROVED

    event_types = [event.type for event in broker.events]
    assert event_types == [
        ChatEventType.APPROVAL_REQUESTED,
        ChatEventType.APPROVAL_RESOLVED,
    ]
    requested = broker.events[0].model_dump(mode="json")
    resolved = broker.events[1].model_dump(mode="json")
    assert requested["data"] == {
        "approval_id": APPROVAL_ID,
        "tool_call_id": "tool-call-1",
        "tool_name": "read_file",
        "canonical_path": "/outside/project/secret.txt",
        "operation": "read",
        "resource_kind": "project_path",
        "scope": "external_exact_path",
        "policy_decision": "ask",
    }
    assert "capability_id" not in requested["data"]
    assert resolved["data"] == {
        "approval_id": APPROVAL_ID,
        "status": "approved",
    }
    serialized = json.dumps({"requested": requested, "resolved": resolved})
    assert "do-not-leak" not in serialized
    assert "Traceback" not in serialized
    assert "api_key" not in serialized.lower()


@pytest.mark.asyncio
async def test_run_command_approval_event_uses_project_internal_scope(
    tmp_path: Path,
) -> None:
    ApprovalCoordinator, ApprovalDecision = _require_coordinator()
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    conversation_id, session_id = await _running_run(repository, tmp_path)
    broker = RecordingBroker()
    coordinator = ApprovalCoordinator(repository, broker)
    request = ApprovalRequest(
        approval_id=APPROVAL_ID_B,
        conversation_id=conversation_id,
        session_id=session_id,
        tool_call_id="tool-call-command",
        tool_name="run_command",
        canonical_path="command:run_command",
        operation=AccessOperation.READ,
        status=ApprovalStatus.PENDING,
    )

    waiter = asyncio.create_task(coordinator.request(request))
    await _wait_for_pending(repository, request.approval_id)
    await coordinator.resolve(request.approval_id, ApprovalDecision.APPROVE)
    assert await waiter is ApprovalStatus.APPROVED

    requested = broker.events[0].model_dump(mode="json")
    assert requested["data"]["tool_name"] == "run_command"
    assert requested["data"]["operation"] == "run"
    assert requested["data"]["resource_kind"] == "sandbox_command"
    assert requested["data"]["scope"] == "project_internal"
    assert requested["data"]["policy_decision"] == "ask"
    assert requested["data"]["scope"] != "external_exact_path"
    assert "capability_id" not in requested["data"]


@pytest.mark.asyncio
async def test_apply_patch_approval_event_uses_project_path_apply(
    tmp_path: Path,
) -> None:
    ApprovalCoordinator, ApprovalDecision = _require_coordinator()
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    conversation_id, session_id = await _running_run(repository, tmp_path)
    broker = RecordingBroker()
    coordinator = ApprovalCoordinator(repository, broker)
    request = ApprovalRequest(
        approval_id=APPROVAL_ID_B,
        conversation_id=conversation_id,
        session_id=session_id,
        tool_call_id="tool-call-patch",
        tool_name="apply_patch",
        canonical_path="patch:0123456789abcdef",
        operation=AccessOperation.APPLY,
        status=ApprovalStatus.PENDING,
    )

    waiter = asyncio.create_task(coordinator.request(request))
    await _wait_for_pending(repository, request.approval_id)
    await coordinator.resolve(request.approval_id, ApprovalDecision.APPROVE)
    assert await waiter is ApprovalStatus.APPROVED

    requested = broker.events[0].model_dump(mode="json")
    assert requested["data"]["operation"] == "apply"
    assert requested["data"]["resource_kind"] == "project_path"
    assert requested["data"]["scope"] == "project_internal"
    assert requested["data"]["policy_decision"] == "ask"
    assert "capability_id" not in requested["data"]


def test_pending_approval_state_maps_sqlite_read_run_command_to_policy_view() -> None:
    from agent_foundations.chat.api import _pending_approval_state

    approval = ApprovalRequest(
        approval_id=APPROVAL_ID,
        conversation_id=CONVERSATION_ID,
        session_id=SESSION_ID,
        tool_call_id="call-command",
        tool_name="run_command",
        canonical_path="command:run_command",
        operation=AccessOperation.READ,
        status=ApprovalStatus.PENDING,
    )
    state = _pending_approval_state(approval)
    payload = state.model_dump(mode="json")
    assert payload["operation"] == "run"
    assert payload["resource_kind"] == "sandbox_command"
    assert payload["scope"] == "project_internal"
    assert payload["policy_decision"] == "ask"
    assert "capability_id" not in payload


def test_pending_approval_state_maps_apply_and_external_read() -> None:
    from agent_foundations.chat.api import _pending_approval_state

    patch = _pending_approval_state(
        ApprovalRequest(
            approval_id=APPROVAL_ID,
            conversation_id=CONVERSATION_ID,
            session_id=SESSION_ID,
            tool_call_id="call-patch",
            tool_name="apply_patch",
            canonical_path="patch:abc",
            operation=AccessOperation.APPLY,
            status=ApprovalStatus.PENDING,
        )
    ).model_dump(mode="json")
    assert patch["operation"] == "apply"
    assert patch["resource_kind"] == "project_path"
    assert patch["scope"] == "project_internal"
    assert patch["policy_decision"] == "ask"

    external = _pending_approval_state(
        ApprovalRequest(
            approval_id=APPROVAL_ID_B,
            conversation_id=CONVERSATION_ID,
            session_id=SESSION_ID,
            tool_call_id="call-read",
            tool_name="read_file",
            canonical_path="/outside/secret.txt",
            operation=AccessOperation.READ,
            status=ApprovalStatus.PENDING,
        )
    ).model_dump(mode="json")
    assert external["operation"] == "read"
    assert external["resource_kind"] == "project_path"
    assert external["scope"] == "external_exact_path"
    assert external["policy_decision"] == "ask"


@pytest.mark.asyncio
async def test_fast_resolve_does_not_lose_decision(tmp_path: Path) -> None:
    ApprovalCoordinator, ApprovalDecision = _require_coordinator()
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    conversation_id, session_id = await _running_run(repository, tmp_path)
    coordinator = ApprovalCoordinator(repository, ChatEventBroker())
    request = _approval_request(conversation_id, session_id)

    waiter = asyncio.create_task(coordinator.request(request))
    await _wait_for_pending(repository, request.approval_id)
    await coordinator.resolve(request.approval_id, ApprovalDecision.APPROVE)
    assert await asyncio.wait_for(waiter, timeout=2.0) is ApprovalStatus.APPROVED


@pytest.mark.asyncio
async def test_resolve_rejects_duplicate_unknown_and_invalidated(
    tmp_path: Path,
) -> None:
    ApprovalCoordinator, ApprovalDecision = _require_coordinator()
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    conversation_id, session_id = await _running_run(repository, tmp_path)
    coordinator = ApprovalCoordinator(repository, ChatEventBroker())
    request = _approval_request(conversation_id, session_id)

    waiter = asyncio.create_task(coordinator.request(request))
    await _wait_for_pending(repository, request.approval_id)
    await coordinator.resolve(request.approval_id, ApprovalDecision.APPROVE)
    assert await waiter is ApprovalStatus.APPROVED

    with pytest.raises(ChatConflictError):
        await coordinator.resolve(request.approval_id, ApprovalDecision.APPROVE)
    with pytest.raises(ChatNotFoundError):
        await coordinator.resolve(
            "00000000-0000-4000-8000-000000000099",
            ApprovalDecision.APPROVE,
        )

    _approval_request(
        conversation_id,
        session_id,
        approval_id=APPROVAL_ID_B,
        tool_call_id="tool-call-2",
    )
    await repository.transition_run(
        session_id,
        RunStatus.RUNNING,
        RunStatus.WAITING_APPROVAL,
    )
    await repository.create_approval(
        conversation_id=conversation_id,
        session_id=session_id,
        tool_call_id="tool-call-2",
        tool_name="read_file",
        canonical_path="/outside/other.txt",
        approval_id=APPROVAL_ID_B,
    )
    await repository.invalidate_approval(APPROVAL_ID_B)
    with pytest.raises(ChatConflictError):
        await coordinator.resolve(APPROVAL_ID_B, ApprovalDecision.APPROVE)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("decision", "expected_status"),
    [
        (pytest.param("approve", ApprovalStatus.APPROVED, id="approve")),
        (pytest.param("deny", ApprovalStatus.DENIED, id="deny")),
    ],
)
async def test_fast_resolve_waits_for_persistence_before_completing(
    tmp_path: Path,
    decision: str,
    expected_status: ApprovalStatus,
) -> None:
    ApprovalCoordinator, ApprovalDecision = _require_coordinator()
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    conversation_id, session_id = await _running_run(repository, tmp_path)
    blocking_repository = BlockingCreateApprovalRepository(repository)
    broker = RecordingBroker()
    coordinator = ApprovalCoordinator(blocking_repository, broker)
    request = _approval_request(conversation_id, session_id)
    approval_decision = (
        ApprovalDecision.APPROVE
        if decision == "approve"
        else ApprovalDecision.DENY
    )

    request_task = asyncio.create_task(coordinator.request(request))
    await asyncio.wait_for(blocking_repository.create_started.wait(), timeout=2.0)
    with pytest.raises(ChatNotFoundError):
        await repository.get_approval(request.approval_id)
    assert (await repository.get_run(session_id)).status is RunStatus.WAITING_APPROVAL

    resolve_task = asyncio.create_task(
        coordinator.resolve(request.approval_id, approval_decision),
    )
    await asyncio.sleep(0.05)
    assert not resolve_task.done()

    blocking_repository.release_create.set()
    resolved = await asyncio.wait_for(resolve_task, timeout=2.0)
    assert resolved.status is expected_status
    assert await asyncio.wait_for(request_task, timeout=2.0) is expected_status

    approval = await repository.get_approval(request.approval_id)
    assert approval.status is expected_status
    assert (await repository.get_run(session_id)).status is RunStatus.RUNNING
    assert [event.type for event in broker.events] == [
        ChatEventType.APPROVAL_REQUESTED,
        ChatEventType.APPROVAL_RESOLVED,
    ]


@pytest.mark.asyncio
async def test_create_approval_failure_restores_running_and_cleans_waiter(
    tmp_path: Path,
) -> None:
    ApprovalCoordinator, ApprovalDecision = _require_coordinator()
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    conversation_id, session_id = await _running_run(repository, tmp_path)
    await repository.transition_run(
        session_id,
        RunStatus.RUNNING,
        RunStatus.WAITING_APPROVAL,
    )
    existing = await repository.create_approval(
        conversation_id=conversation_id,
        session_id=session_id,
        tool_call_id="existing-tool",
        tool_name="read_file",
        canonical_path="/outside/existing.txt",
        approval_id=APPROVAL_ID,
    )
    await repository.resolve_approval(
        existing.approval_id,
        ApprovalStatus.APPROVED,
    )
    await repository.transition_run(
        session_id,
        RunStatus.WAITING_APPROVAL,
        RunStatus.RUNNING,
    )

    coordinator = ApprovalCoordinator(repository, ChatEventBroker())
    duplicate_request = _approval_request(conversation_id, session_id)

    with pytest.raises(ChatConflictError):
        await coordinator.request(duplicate_request)

    assert (await repository.get_run(session_id)).status is RunStatus.RUNNING
    unchanged = await repository.get_approval(APPROVAL_ID)
    assert unchanged.status is ApprovalStatus.APPROVED

    with pytest.raises(ChatConflictError):
        await coordinator.resolve(APPROVAL_ID, ApprovalDecision.APPROVE)


@pytest.mark.asyncio
async def test_requested_publish_blocks_resolve_until_ready_or_invalidates(
    tmp_path: Path,
) -> None:
    ApprovalCoordinator, ApprovalDecision = _require_coordinator()
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    conversation_id, session_id = await _running_run(repository, tmp_path)
    broker = BlockingRequestedPublishBroker()
    coordinator = ApprovalCoordinator(repository, broker)
    request = _approval_request(conversation_id, session_id)

    request_task = asyncio.create_task(coordinator.request(request))
    await asyncio.wait_for(broker.requested_publish_started.wait(), timeout=2.0)
    approval = await repository.get_approval(request.approval_id)
    assert approval.status is ApprovalStatus.PENDING

    resolve_task = asyncio.create_task(
        coordinator.resolve(request.approval_id, ApprovalDecision.APPROVE),
    )
    await asyncio.sleep(0.05)
    assert not resolve_task.done()

    broker.release_requested_publish.set()
    resolved = await asyncio.wait_for(resolve_task, timeout=2.0)
    assert resolved.status is ApprovalStatus.APPROVED
    assert await asyncio.wait_for(request_task, timeout=2.0) is ApprovalStatus.APPROVED
    assert (await repository.get_run(session_id)).status is RunStatus.RUNNING


@pytest.mark.asyncio
async def test_requested_publish_failure_races_resolve_without_approving(
    tmp_path: Path,
) -> None:
    ApprovalCoordinator, ApprovalDecision = _require_coordinator()
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    conversation_id, session_id = await _running_run(repository, tmp_path)
    broker = BlockingRequestedPublishBroker()
    broker.fail_requested_publish = True
    coordinator = ApprovalCoordinator(repository, broker)
    request = _approval_request(conversation_id, session_id)

    request_task = asyncio.create_task(coordinator.request(request))
    await asyncio.wait_for(broker.requested_publish_started.wait(), timeout=2.0)

    resolve_task = asyncio.create_task(
        coordinator.resolve(request.approval_id, ApprovalDecision.APPROVE),
    )

    with pytest.raises(RuntimeError, match="do-not-leak-requested-publish"):
        await asyncio.wait_for(request_task, timeout=2.0)

    with pytest.raises((ChatConflictError, ApprovalUnavailableError)):
        await asyncio.wait_for(resolve_task, timeout=2.0)

    approval = await repository.get_approval(request.approval_id)
    assert approval.status is ApprovalStatus.INVALIDATED
    assert (await repository.get_run(session_id)).status is RunStatus.RUNNING


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("decision", "expected_status"),
    [
        (pytest.param("approve", ApprovalStatus.APPROVED, id="approve")),
        (pytest.param("deny", ApprovalStatus.DENIED, id="deny")),
    ],
)
async def test_resolved_publish_failure_still_returns_persisted_decision(
    tmp_path: Path,
    decision: str,
    expected_status: ApprovalStatus,
) -> None:
    ApprovalCoordinator, ApprovalDecision = _require_coordinator()
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    conversation_id, session_id = await _running_run(repository, tmp_path)
    broker = FailingResolvedPublishBroker()
    coordinator = ApprovalCoordinator(repository, broker)
    request = _approval_request(conversation_id, session_id)
    approval_decision = (
        ApprovalDecision.APPROVE
        if decision == "approve"
        else ApprovalDecision.DENY
    )

    request_task = asyncio.create_task(coordinator.request(request))
    await _wait_for_pending(repository, request.approval_id)
    await coordinator.resolve(request.approval_id, approval_decision)
    assert await asyncio.wait_for(request_task, timeout=2.0) is expected_status

    approval = await repository.get_approval(request.approval_id)
    assert approval.status is expected_status
    assert (await repository.get_run(session_id)).status is RunStatus.RUNNING

    with pytest.raises(ChatConflictError):
        await coordinator.resolve(request.approval_id, approval_decision)

    resolved_events = [
        event for event in broker.events if event.type is ChatEventType.APPROVAL_RESOLVED
    ]
    assert resolved_events == []
    serialized = json.dumps([event.model_dump(mode="json") for event in broker.events])
    assert "do-not-leak-resolved-publish" not in serialized
    assert "Traceback" not in serialized


@pytest.mark.asyncio
async def test_stale_pending_approval_without_waiter_is_unavailable(
    tmp_path: Path,
) -> None:
    ApprovalCoordinator, ApprovalDecision = _require_coordinator()
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    conversation_id, session_id = await _running_run(repository, tmp_path)
    coordinator = ApprovalCoordinator(repository, ChatEventBroker())
    await repository.transition_run(
        session_id,
        RunStatus.RUNNING,
        RunStatus.WAITING_APPROVAL,
    )
    await repository.create_approval(
        conversation_id=conversation_id,
        session_id=session_id,
        tool_call_id="stale-tool",
        tool_name="read_file",
        canonical_path="/outside/stale.txt",
        approval_id=APPROVAL_ID,
    )
    with pytest.raises(ApprovalUnavailableError):
        await coordinator.resolve(APPROVAL_ID, ApprovalDecision.APPROVE)


@pytest.mark.asyncio
async def test_concurrent_approvals_are_isolated(tmp_path: Path) -> None:
    ApprovalCoordinator, ApprovalDecision = _require_coordinator()
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    conversation_id, session_id = await _running_run(repository, tmp_path)
    other_conversation = await repository.create_conversation(
        title="Other approval study",
        project_root=tmp_path,
        permission_mode=PermissionMode.ASK_FOR_ACCESS,
    )
    _, other_run = await repository.begin_run(
        other_conversation.conversation_id,
        content="other approval question",
        session_id=SESSION_ID_B,
    )
    await repository.transition_run(
        other_run.session_id,
        RunStatus.QUEUED,
        RunStatus.RUNNING,
    )
    coordinator = ApprovalCoordinator(repository, ChatEventBroker())
    request_a = _approval_request(conversation_id, session_id, approval_id=APPROVAL_ID)
    request_b = _approval_request(
        other_conversation.conversation_id,
        other_run.session_id,
        approval_id=APPROVAL_ID_B,
        tool_call_id="tool-call-2",
    )

    waiter_a = asyncio.create_task(coordinator.request(request_a))
    waiter_b = asyncio.create_task(coordinator.request(request_b))
    await _wait_for_pending(repository, APPROVAL_ID)
    await _wait_for_pending(repository, APPROVAL_ID_B)

    await coordinator.resolve(APPROVAL_ID, ApprovalDecision.APPROVE)
    assert await waiter_a is ApprovalStatus.APPROVED
    assert not waiter_b.done()

    await coordinator.resolve(APPROVAL_ID_B, ApprovalDecision.DENY)
    assert await waiter_b is ApprovalStatus.DENIED

    with pytest.raises(ChatConflictError):
        await coordinator.request(request_a)


@pytest.mark.asyncio
async def test_request_cancellation_removes_waiter_and_blocks_resolve(
    tmp_path: Path,
) -> None:
    ApprovalCoordinator, ApprovalDecision = _require_coordinator()
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    conversation_id, session_id = await _running_run(repository, tmp_path)
    coordinator = ApprovalCoordinator(repository, ChatEventBroker())
    request = _approval_request(conversation_id, session_id)

    task = asyncio.create_task(coordinator.request(request))
    await _wait_for_pending(repository, request.approval_id)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert (await repository.get_approval(request.approval_id)).status is (
        ApprovalStatus.PENDING
    )
    assert (await repository.get_run(session_id)).status is (
        RunStatus.WAITING_APPROVAL
    )
    assert coordinator._waiters == {}

    with pytest.raises(ApprovalUnavailableError):
        await coordinator.resolve(request.approval_id, ApprovalDecision.APPROVE)

    assert await repository.interrupt_unfinished() == (1, 1)
    assert (await repository.get_approval(request.approval_id)).status is (
        ApprovalStatus.INVALIDATED
    )
    assert (await repository.get_run(session_id)).status is RunStatus.INTERRUPTED


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("decision", "expected_status"),
    [
        (pytest.param("approve", ApprovalStatus.APPROVED, id="approve")),
        (pytest.param("deny", ApprovalStatus.DENIED, id="deny")),
    ],
)
async def test_request_cancellation_waits_for_in_flight_durable_resolve(
    tmp_path: Path,
    decision: str,
    expected_status: ApprovalStatus,
) -> None:
    ApprovalCoordinator, ApprovalDecision = _require_coordinator()
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    conversation_id, session_id = await _running_run(repository, tmp_path)
    blocking_repository = BlockingResolveApprovalRepository(repository)
    coordinator = ApprovalCoordinator(blocking_repository, ChatEventBroker())
    request = _approval_request(conversation_id, session_id)
    approval_decision = (
        ApprovalDecision.APPROVE
        if decision == "approve"
        else ApprovalDecision.DENY
    )

    request_task = asyncio.create_task(coordinator.request(request))
    await _wait_for_pending(repository, request.approval_id)
    resolve_task = asyncio.create_task(
        coordinator.resolve(request.approval_id, approval_decision),
    )
    await asyncio.wait_for(blocking_repository.resolve_started.wait(), timeout=2.0)

    request_task.cancel()
    await asyncio.sleep(0)
    request_finished_before_resolve = request_task.done()
    blocking_repository.release_resolve.set()

    resolver_outcome: ApprovalRequest | BaseException
    try:
        resolver_outcome = await asyncio.wait_for(resolve_task, timeout=2.0)
    except BaseException as exc:
        resolver_outcome = exc

    requester_cancelled = False
    try:
        await request_task
    except asyncio.CancelledError:
        requester_cancelled = True

    assert isinstance(resolver_outcome, ApprovalRequest), repr(resolver_outcome)
    assert not request_finished_before_resolve
    assert resolver_outcome.status is expected_status
    assert requester_cancelled
    assert (await repository.get_approval(request.approval_id)).status is (
        expected_status
    )
    assert (await repository.get_run(session_id)).status is RunStatus.RUNNING
    assert coordinator._waiters == {}
    assert getattr(coordinator, "_approval_locks", {}) == {}
    assert request_task.done()
    assert resolve_task.done()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("decision", "expected_status"),
    [
        (pytest.param("approve", ApprovalStatus.APPROVED, id="approve")),
        (pytest.param("deny", ApprovalStatus.DENIED, id="deny")),
    ],
)
async def test_shutdown_waits_for_in_flight_durable_resolve(
    tmp_path: Path,
    decision: str,
    expected_status: ApprovalStatus,
) -> None:
    ApprovalCoordinator, ApprovalDecision = _require_coordinator()
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    conversation_id, session_id = await _running_run(repository, tmp_path)
    blocking_repository = BlockingResolveApprovalRepository(repository)
    coordinator = ApprovalCoordinator(blocking_repository, ChatEventBroker())
    request = _approval_request(conversation_id, session_id)
    approval_decision = (
        ApprovalDecision.APPROVE
        if decision == "approve"
        else ApprovalDecision.DENY
    )

    request_task = asyncio.create_task(coordinator.request(request))
    await _wait_for_pending(repository, request.approval_id)
    resolve_task = asyncio.create_task(
        coordinator.resolve(request.approval_id, approval_decision),
    )
    await asyncio.wait_for(blocking_repository.resolve_started.wait(), timeout=2.0)

    shutdown_task = asyncio.create_task(coordinator.shutdown())
    shutdown_finished_before_resolve = False
    try:
        await asyncio.wait_for(asyncio.shield(shutdown_task), timeout=0.05)
        shutdown_finished_before_resolve = True
    except TimeoutError:
        pass
    finally:
        blocking_repository.release_resolve.set()

    resolved, requester_result, shutdown_result = await asyncio.gather(
        resolve_task,
        request_task,
        shutdown_task,
    )

    assert not shutdown_finished_before_resolve
    assert isinstance(resolved, ApprovalRequest)
    assert resolved.status is expected_status
    assert requester_result is expected_status
    assert shutdown_result is None
    assert (await repository.get_approval(request.approval_id)).status is expected_status
    assert (await repository.get_run(session_id)).status is RunStatus.RUNNING
    assert coordinator._waiters == {}


@pytest.mark.asyncio
async def test_shutdown_first_prevents_later_durable_resolve(tmp_path: Path) -> None:
    ApprovalCoordinator, ApprovalDecision = _require_coordinator()
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    conversation_id, session_id = await _running_run(repository, tmp_path)
    coordinator = ApprovalCoordinator(repository, ChatEventBroker())
    request = _approval_request(conversation_id, session_id)

    request_task = asyncio.create_task(coordinator.request(request))
    await _wait_for_pending(repository, request.approval_id)
    await coordinator.shutdown()

    with pytest.raises(asyncio.CancelledError):
        await request_task
    with pytest.raises(ApprovalUnavailableError):
        await coordinator.resolve(request.approval_id, ApprovalDecision.APPROVE)

    assert (await repository.get_approval(request.approval_id)).status is (
        ApprovalStatus.PENDING
    )
    assert (await repository.get_run(session_id)).status is (
        RunStatus.WAITING_APPROVAL
    )
    assert await repository.interrupt_unfinished() == (1, 1)
    assert (await repository.get_approval(request.approval_id)).status is (
        ApprovalStatus.INVALIDATED
    )
    assert (await repository.get_run(session_id)).status is RunStatus.INTERRUPTED
    assert coordinator._waiters == {}


@pytest.mark.asyncio
async def test_completed_approvals_release_all_coordination_state(
    tmp_path: Path,
) -> None:
    ApprovalCoordinator, ApprovalDecision = _require_coordinator()
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    conversation_id, session_id = await _running_run(repository, tmp_path)
    coordinator = ApprovalCoordinator(repository, ChatEventBroker())

    for index in range(1, 6):
        approval_id = f"00000000-0000-4000-8000-{index:012d}"
        request = _approval_request(
            conversation_id,
            session_id,
            approval_id=approval_id,
            tool_call_id=f"tool-call-{index}",
        )
        request_task = asyncio.create_task(coordinator.request(request))
        await _wait_for_pending(repository, approval_id)
        await coordinator.resolve(approval_id, ApprovalDecision.APPROVE)
        assert await request_task is ApprovalStatus.APPROVED

    assert coordinator._waiters == {}
    assert getattr(coordinator, "_approval_locks", {}) == {}


@pytest.mark.asyncio
async def test_shutdown_cancels_waiters_without_approving(tmp_path: Path) -> None:
    ApprovalCoordinator, ApprovalDecision = _require_coordinator()
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    conversation_id, session_id = await _running_run(repository, tmp_path)
    coordinator = ApprovalCoordinator(repository, ChatEventBroker())
    request = _approval_request(conversation_id, session_id)

    waiter = asyncio.create_task(coordinator.request(request))
    await _wait_for_pending(repository, request.approval_id)
    await coordinator.shutdown()
    await coordinator.shutdown()

    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(waiter, timeout=1.0)

    with pytest.raises(ApprovalUnavailableError):
        await coordinator.resolve(request.approval_id, ApprovalDecision.APPROVE)


@pytest.mark.asyncio
async def test_publish_failure_invalidates_approval_and_cleans_waiter(
    tmp_path: Path,
) -> None:
    ApprovalCoordinator, ApprovalDecision = _require_coordinator()
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    conversation_id, session_id = await _running_run(repository, tmp_path)
    broker = FailingBroker(fail_on=ChatEventType.APPROVAL_REQUESTED)
    coordinator = ApprovalCoordinator(repository, broker)
    request = _approval_request(conversation_id, session_id)

    with pytest.raises(RuntimeError, match="do-not-leak-publish-secret"):
        await coordinator.request(request)

    approval = await repository.get_approval(request.approval_id)
    assert approval.status is ApprovalStatus.INVALIDATED
    assert (await repository.get_run(session_id)).status is RunStatus.RUNNING

    with pytest.raises(ChatConflictError):
        await coordinator.resolve(request.approval_id, ApprovalDecision.APPROVE)


@pytest.mark.asyncio
async def test_chat_and_trace_sse_generate_swallows_cancelled_error(
    tmp_path: Path,
) -> None:
    from collections.abc import AsyncGenerator
    from typing import cast
    from uuid import UUID

    from fastapi.responses import StreamingResponse
    from fastapi.routing import APIRoute
    from starlette.requests import Request
    from starlette.types import Message

    from agent_foundations.chat.api import ChatServices, create_chat_router
    from agent_foundations.chat.approvals import ApprovalCoordinator
    from agent_foundations.chat.runner import ConversationRunner, direct_executor_factory
    from agent_foundations.chat.supervisor import RunSupervisor
    from agent_foundations.context.budget import ContextBudget
    from agent_foundations.context.builder import ContextBuilder
    from agent_foundations.domain.model import ModelResponse
    from agent_foundations.providers.fake import FakeModelProvider
    from agent_foundations.runtime.agent import AgentConfig
    from agent_foundations.runtime.loop import AgentLoop
    from agent_foundations.runtime.redaction import Redactor
    from agent_foundations.runtime.tool_execution import ToolCallExecutor
    from agent_foundations.runtime.trace import EventSink
    from agent_foundations.tools.filesystem.path_policy import PathPolicy
    from agent_foundations.tools.registry import ToolRegistry, build_standard_registered_tools
    from agent_foundations.viewer.app import create_app

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    class CancellingRequest(Request):
        async def is_disconnected(self) -> bool:
            raise asyncio.CancelledError()

    def asgi_request(path: str, query: bytes = b"") -> Request:
        return CancellingRequest(
            {
                "type": "http",
                "asgi": {"version": "3.0", "spec_version": "2.3"},
                "http_version": "1.1",
                "method": "GET",
                "scheme": "http",
                "path": path,
                "raw_path": path.encode(),
                "query_string": query,
                "root_path": "",
                "headers": [],
                "client": ("127.0.0.1", 50000),
                "server": ("127.0.0.1", 8765),
            },
            receive,
        )

    project_root = tmp_path / "project"
    project_root.mkdir()
    repository = await _open_repository(tmp_path / "chat.sqlite3")
    broker = ChatEventBroker()
    supervisor = RunSupervisor()
    provider = FakeModelProvider([ModelResponse(content="unused")])

    def runtime_factory(
        conversation: object,
        event_sink: EventSink,
        tool_executor: ToolCallExecutor,
    ) -> AgentLoop:
        del conversation, tool_executor
        return AgentLoop(
            provider=provider,
            registry=ToolRegistry(
                build_standard_registered_tools(PathPolicy(project_root)),
            ),
            context_builder=ContextBuilder(ContextBudget()),
            event_sink=event_sink,
            config=AgentConfig(),
        )

    runner = ConversationRunner(
        repository=repository,
        broker=broker,
        runtime_factory=runtime_factory,
        trace_dir=tmp_path / "traces",
        redactor_factory=lambda conversation: Redactor(
            Path(conversation.project_root),
        ),
        tool_executor_factory=direct_executor_factory,
    )
    services = ChatServices(
        repository=repository,
        broker=broker,
        runner=runner,
        supervisor=supervisor,
        coordinator=ApprovalCoordinator(repository, broker),
    )
    conversation = await repository.create_conversation(
        title="SSE cancel",
        project_root=project_root,
        permission_mode=PermissionMode.PROJECT_READ_ONLY,
    )
    router = create_chat_router(services, keepalive_seconds=0.05)
    route = next(
        item
        for item in router.routes
        if isinstance(item, APIRoute)
        and item.path == "/conversations/{conversation_id}/events"
    )
    request = asgi_request(
        f"/api/chat/conversations/{conversation.conversation_id}/events",
    )
    response = cast(
        StreamingResponse,
        await route.endpoint(request, UUID(conversation.conversation_id)),
    )
    stream = cast(AsyncGenerator[str, None], response.body_iterator)
    assert await anext(stream) == ": connected\n\n"
    with pytest.raises(StopAsyncIteration):
        await anext(stream)
    await stream.aclose()
    await supervisor.shutdown()

    app = create_app(tmp_path / "traces")
    trace_route = next(
        item
        for item in app.routes
        if isinstance(item, APIRoute) and item.path == "/api/events/stream"
    )
    trace_request = asgi_request("/api/events/stream")
    trace_response = cast(
        StreamingResponse,
        await trace_route.endpoint(trace_request, "*"),
    )
    trace_stream = cast(AsyncGenerator[str, None], trace_response.body_iterator)
    assert await anext(trace_stream) == ": connected\n\n"
    with pytest.raises(StopAsyncIteration):
        await anext(trace_stream)
    await trace_stream.aclose()
