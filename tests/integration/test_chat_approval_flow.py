from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from fastapi.testclient import TestClient

from agent_foundations.chat.approvals import ApprovalCoordinator
from agent_foundations.chat.events import ChatEventBroker
from agent_foundations.chat.models import (
    ApprovalStatus,
    ChatEvent,
    ChatEventType,
    Conversation,
    PermissionMode,
    RunStatus,
)
from agent_foundations.chat.repository import ConversationRepository
from agent_foundations.chat.runner import ConversationRunner
from agent_foundations.chat.supervisor import RunSupervisor
from agent_foundations.context.budget import ContextBudget
from agent_foundations.context.builder import ContextBuilder
from agent_foundations.domain.model import ModelResponse
from agent_foundations.domain.tool import ToolCall
from agent_foundations.providers.fake import FakeModelProvider
from agent_foundations.runtime.agent import AgentConfig
from agent_foundations.runtime.loop import AgentLoop
from agent_foundations.runtime.redaction import Redactor
from agent_foundations.runtime.tool_execution import ToolCallExecutor
from agent_foundations.runtime.trace import EventSink
from agent_foundations.tools.filesystem.list_directory import ListDirectoryTool
from agent_foundations.tools.filesystem.path_policy import PathPolicy
from agent_foundations.tools.filesystem.read_file import ReadFileTool
from agent_foundations.tools.filesystem.search_text import SearchTextTool
from agent_foundations.tools.registry import ToolRegistry
from agent_foundations.viewer.app import create_app


def _require_task9_components() -> tuple[Any, Any, Any]:
    try:
        from agent_foundations.chat.api import ChatServices
        from agent_foundations.chat.tool_execution import ApprovalAwareToolExecutor
    except ImportError as exc:
        raise AssertionError(f"Task 9 integration is missing: {exc}") from exc
    return ChatServices, ApprovalAwareToolExecutor, create_app


class RecordingBroker(ChatEventBroker):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[ChatEvent] = []

    async def publish(self, event: ChatEvent) -> None:
        self.events.append(event)
        await super().publish(event)


class OrderedApprovalCoordinator(ApprovalCoordinator):
    def __init__(
        self,
        repository: ConversationRepository,
        broker: ChatEventBroker,
        shutdown_order: list[str],
    ) -> None:
        super().__init__(repository, broker)
        self._shutdown_order = shutdown_order

    async def shutdown(self) -> None:
        self._shutdown_order.append("coordinator")
        await super().shutdown()


class OrderedRunSupervisor(RunSupervisor):
    def __init__(self, shutdown_order: list[str]) -> None:
        super().__init__()
        self._shutdown_order = shutdown_order

    async def shutdown(self) -> None:
        self._shutdown_order.append("supervisor")
        await super().shutdown()


def _runtime_factory(provider: FakeModelProvider) -> Any:
    def factory(
        conversation: Conversation,
        event_sink: EventSink,
        tool_executor: ToolCallExecutor,
    ) -> AgentLoop:
        policy = PathPolicy(Path(conversation.project_root))
        return AgentLoop(
            provider=provider,
            registry=ToolRegistry(
                [
                    ListDirectoryTool(policy),
                    ReadFileTool(policy),
                    SearchTextTool(policy),
                ],
            ),
            context_builder=ContextBuilder(ContextBudget()),
            event_sink=event_sink,
            config=AgentConfig(max_steps=8),
            tool_executor=tool_executor,
        )

    return factory


def _build_stack(
    tmp_path: Path,
    responses: list[ModelResponse],
    *,
    ordered_shutdown: bool = False,
) -> tuple[
    Any,
    ConversationRepository,
    RecordingBroker,
    FakeModelProvider,
    list[str],
]:
    ChatServices, ApprovalAwareToolExecutor, app_factory = _require_task9_components()
    repository = ConversationRepository(tmp_path / "state" / "chat.sqlite3")
    asyncio.run(repository.initialize())
    broker = RecordingBroker()
    shutdown_order: list[str] = []
    coordinator: ApprovalCoordinator
    supervisor: RunSupervisor
    if ordered_shutdown:
        coordinator = OrderedApprovalCoordinator(
            repository,
            broker,
            shutdown_order,
        )
        supervisor = OrderedRunSupervisor(shutdown_order)
    else:
        coordinator = ApprovalCoordinator(repository, broker)
        supervisor = RunSupervisor()
    provider = FakeModelProvider(responses)
    runner = ConversationRunner(
        repository=repository,
        broker=broker,
        runtime_factory=_runtime_factory(provider),
        trace_dir=tmp_path / "traces",
        redactor_factory=lambda conversation: Redactor(
            Path(conversation.project_root),
        ),
        tool_executor_factory=lambda conversation, _session_id: (
            ApprovalAwareToolExecutor(conversation, coordinator)
        ),
    )
    services = ChatServices(
        repository=repository,
        broker=broker,
        runner=runner,
        supervisor=supervisor,
        coordinator=coordinator,
    )
    return (
        app_factory(tmp_path / "traces", chat_services=services),
        repository,
        broker,
        provider,
        shutdown_order,
    )


def _create_conversation(
    client: TestClient,
    project: Path,
    mode: PermissionMode,
) -> str:
    response = client.post(
        "/api/chat/conversations",
        json={
            "title": "Approval flow",
            "project_root": str(project),
            "permission_mode": mode.value,
        },
    )
    assert response.status_code == 201
    return str(response.json()["conversation_id"])


def _post_message(client: TestClient, conversation_id: str) -> str:
    response = client.post(
        f"/api/chat/conversations/{conversation_id}/messages",
        json={"query": "Read the external fixture"},
    )
    assert response.status_code == 202
    return str(response.json()["session_id"])


def _wait_for_approval(
    broker: RecordingBroker,
    seen_ids: set[str],
) -> str:
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        for event in broker.events:
            if event.type is not ChatEventType.APPROVAL_REQUESTED:
                continue
            approval_id = str(event.data["approval_id"])
            if approval_id not in seen_ids:
                return approval_id
        time.sleep(0.01)
    raise AssertionError("approval.requested was not published")


def _wait_for_run_status(
    client: TestClient,
    session_id: str,
    expected: set[str],
) -> dict[str, Any]:
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        response = client.get(f"/api/chat/runs/{session_id}")
        assert response.status_code == 200
        payload = cast(dict[str, Any], response.json())
        if payload["status"] in expected:
            return payload
        time.sleep(0.01)
    raise AssertionError(f"run did not reach one of {sorted(expected)}")


def test_external_approval_api_approve_repeat_and_deny_flow(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    external = tmp_path / "external.txt"
    external.write_text("external fixture\n", encoding="utf-8")
    provider_responses = [
        ModelResponse(
            tool_calls=(
                ToolCall(
                    id="external-call-1",
                    name="read_file",
                    arguments={"path": str(external)},
                ),
            ),
        ),
        ModelResponse(content="first approved answer"),
        ModelResponse(
            tool_calls=(
                ToolCall(
                    id="external-call-2",
                    name="read_file",
                    arguments={"path": str(external)},
                ),
            ),
        ),
        ModelResponse(content="second approved answer"),
        ModelResponse(
            tool_calls=(
                ToolCall(
                    id="external-call-3",
                    name="read_file",
                    arguments={"path": str(external)},
                ),
            ),
        ),
        ModelResponse(content="denied but continued"),
    ]
    app, repository, broker, provider, _ = _build_stack(
        tmp_path,
        provider_responses,
    )
    seen_ids: set[str] = set()

    with TestClient(app) as client:
        conversation_id = _create_conversation(
            client,
            project,
            PermissionMode.ASK_FOR_ACCESS,
        )

        first_session = _post_message(client, conversation_id)
        first_approval = _wait_for_approval(broker, seen_ids)
        seen_ids.add(first_approval)
        assert _wait_for_run_status(
            client,
            first_session,
            {RunStatus.WAITING_APPROVAL.value},
        )["status"] == RunStatus.WAITING_APPROVAL.value
        approved = client.post(
            f"/api/chat/approvals/{first_approval}/decision",
            json={"decision": "approve"},
        )
        assert approved.status_code == 200
        assert approved.json()["approval_id"] == first_approval
        assert approved.json()["status"] == ApprovalStatus.APPROVED.value
        assert _wait_for_run_status(
            client,
            first_session,
            {RunStatus.COMPLETED.value},
        )["status"] == RunStatus.COMPLETED.value

        messages = client.get(
            f"/api/chat/conversations/{conversation_id}/messages",
        ).json()
        assert messages[-1]["content"] == "first approved answer"
        trace_path = tmp_path / "traces" / f"{first_session}.jsonl"
        trace_types = [
            json.loads(line)["event_type"]
            for line in trace_path.read_text(encoding="utf-8").splitlines()
        ]
        assert "tool.call.requested" in trace_types
        assert "tool.call.completed" in trace_types

        duplicate = client.post(
            f"/api/chat/approvals/{first_approval}/decision",
            json={"decision": "approve"},
        )
        assert duplicate.status_code == 409
        assert duplicate.json() == {"detail": "conflict"}

        second_session = _post_message(client, conversation_id)
        second_approval = _wait_for_approval(broker, seen_ids)
        seen_ids.add(second_approval)
        assert second_approval != first_approval
        second = client.post(
            f"/api/chat/approvals/{second_approval}/decision",
            json={"decision": "approve"},
        )
        assert second.status_code == 200
        assert _wait_for_run_status(
            client,
            second_session,
            {RunStatus.COMPLETED.value},
        )["status"] == RunStatus.COMPLETED.value

        denied_session = _post_message(client, conversation_id)
        denied_approval = _wait_for_approval(broker, seen_ids)
        denied = client.post(
            f"/api/chat/approvals/{denied_approval}/decision",
            json={"decision": "deny"},
        )
        assert denied.status_code == 200
        assert denied.json()["status"] == ApprovalStatus.DENIED.value
        assert _wait_for_run_status(
            client,
            denied_session,
            {RunStatus.COMPLETED.value},
        )["status"] == RunStatus.COMPLETED.value

        serialized_requests = json.dumps(
            [request.model_dump(mode="json") for request in provider.requests],
        )
        assert "access_denied" in serialized_requests
        assert "denied but continued" in [
            message["content"]
            for message in client.get(
                f"/api/chat/conversations/{conversation_id}/messages",
            ).json()
        ]

    assert asyncio.run(repository.get_run(first_session)).status is RunStatus.COMPLETED


def test_approval_decision_validation_and_unavailable_pending_record(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    app, repository, _broker, _provider, _ = _build_stack(tmp_path, [])

    with TestClient(app) as client:
        stale_approval_id = str(uuid4())
        conversation = asyncio.run(
            repository.create_conversation(
                title="Stale approval",
                project_root=project,
                permission_mode=PermissionMode.ASK_FOR_ACCESS,
            ),
        )
        _, run = asyncio.run(
            repository.begin_run(
                conversation.conversation_id,
                content="stale",
                session_id=str(uuid4()),
            ),
        )
        asyncio.run(
            repository.transition_run(
                run.session_id,
                RunStatus.QUEUED,
                RunStatus.RUNNING,
            ),
        )
        asyncio.run(
            repository.transition_run(
                run.session_id,
                RunStatus.RUNNING,
                RunStatus.WAITING_APPROVAL,
            ),
        )
        stale = asyncio.run(
            repository.create_approval(
                conversation_id=conversation.conversation_id,
                session_id=run.session_id,
                tool_call_id="stale-call",
                tool_name="read_file",
                canonical_path=str((tmp_path / "external.txt").resolve()),
                approval_id=stale_approval_id,
            ),
        )
        assert stale.status is ApprovalStatus.PENDING

        malformed = client.post(
            "/api/chat/approvals/not-a-uuid/decision",
            json={"decision": "approve"},
        )
        assert malformed.status_code == 422
        unknown = client.post(
            f"/api/chat/approvals/{uuid4()}/decision",
            json={"decision": "approve"},
        )
        assert unknown.status_code == 404
        assert unknown.json() == {"detail": "not found"}
        invalid_decision = client.post(
            f"/api/chat/approvals/{uuid4()}/decision",
            json={"decision": "allow"},
        )
        assert invalid_decision.status_code == 422
        extra = client.post(
            f"/api/chat/approvals/{uuid4()}/decision",
            json={"decision": "approve", "scope": "forever"},
        )
        assert extra.status_code == 422
        unavailable = client.post(
            f"/api/chat/approvals/{stale_approval_id}/decision",
            json={"decision": "approve"},
        )
        assert unavailable.status_code == 409
        assert unavailable.json() == {"detail": "conflict"}


def test_project_read_only_external_path_never_creates_approval(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    external = tmp_path / "external.txt"
    external.write_text("external fixture\n", encoding="utf-8")
    app, _repository, broker, provider, _ = _build_stack(
        tmp_path,
        [
            ModelResponse(
                tool_calls=(
                    ToolCall(
                        id="project-only-call",
                        name="read_file",
                        arguments={"path": str(external)},
                    ),
                ),
            ),
            ModelResponse(content="project-only continued"),
        ],
    )

    with TestClient(app) as client:
        conversation_id = _create_conversation(
            client,
            project,
            PermissionMode.PROJECT_READ_ONLY,
        )
        session_id = _post_message(client, conversation_id)
        final = _wait_for_run_status(
            client,
            session_id,
            {RunStatus.COMPLETED.value, RunStatus.FAILED.value},
        )
        assert final["status"] == RunStatus.COMPLETED.value
        assert all(
            event.type is not ChatEventType.APPROVAL_REQUESTED
            for event in broker.events
        )
        serialized_requests = json.dumps(
            [request.model_dump(mode="json") for request in provider.requests],
        )
        assert "PathPolicyViolationError" in serialized_requests


def test_chat_lifespan_shuts_down_coordinator_before_supervisor(
    tmp_path: Path,
) -> None:
    app, _repository, _broker, _provider, shutdown_order = _build_stack(
        tmp_path,
        [],
        ordered_shutdown=True,
    )

    with TestClient(app) as client:
        assert client.get("/api/chat/conversations").status_code == 200

    assert shutdown_order == ["coordinator", "supervisor"]
