from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import AsyncGenerator, Iterator
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from starlette.types import Message

from agent_foundations.chat.approvals import ApprovalCoordinator
from agent_foundations.chat.events import ChatEventBroker, encode_chat_sse
from agent_foundations.chat.models import (
    ChatEvent,
    ChatEventType,
    Conversation,
    PermissionMode,
    RunStatus,
)
from agent_foundations.chat.repository import ConversationRepository
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
from agent_foundations.tools.filesystem.list_directory import ListDirectoryTool
from agent_foundations.tools.filesystem.path_policy import PathPolicy
from agent_foundations.tools.registry import ToolRegistry
from agent_foundations.viewer.app import create_app
from agent_foundations.viewer.stream import EventBroker


def _require_chat_api() -> Any:
    try:
        from agent_foundations.chat.api import ChatServices, create_chat_router
    except ImportError as exc:
        raise AssertionError(f"Chat API module missing: {exc}") from exc
    return ChatServices, create_chat_router


def _build_runtime_factory(
    provider: FakeModelProvider,
) -> Any:
    def factory(
        conversation: Conversation,
        event_sink: EventSink,
        tool_executor: ToolCallExecutor,
    ) -> AgentLoop:
        return AgentLoop(
            provider=provider,
            registry=ToolRegistry(
                [ListDirectoryTool(PathPolicy(Path(conversation.project_root)))],
            ),
            context_builder=ContextBuilder(ContextBudget()),
            event_sink=event_sink,
            config=AgentConfig(max_steps=5),
            tool_executor=tool_executor,
        )

    return factory


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    (root / "README.md").write_text("hello\n", encoding="utf-8")
    return root


@pytest.fixture
def chat_stack(
    tmp_path: Path,
    project_root: Path,
) -> Iterator[tuple[Any, ConversationRepository, ChatEventBroker, RunSupervisor, Path]]:
    ChatServices, _ = _require_chat_api()
    database_path = tmp_path / "state" / "chat.sqlite3"
    repository = ConversationRepository(database_path)
    asyncio.run(repository.initialize())
    broker = ChatEventBroker()
    supervisor = RunSupervisor()
    provider = FakeModelProvider([ModelResponse(content="runtime overview")])
    runner = ConversationRunner(
        repository=repository,
        broker=broker,
        runtime_factory=_build_runtime_factory(provider),
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
    yield services, repository, broker, supervisor, project_root
    asyncio.run(supervisor.shutdown())


def _make_client(
    services: Any,
    tmp_path: Path,
    *,
    keepalive_seconds: float = 0.05,
) -> TestClient:
    _require_chat_api()
    app = create_app(
        tmp_path / "traces",
        EventBroker(),
        chat_services=services,
        chat_keepalive_seconds=keepalive_seconds,
    )
    _ = keepalive_seconds
    return TestClient(app)


def test_create_list_get_patch_conversation_flow(
    tmp_path: Path,
    chat_stack: tuple[Any, ConversationRepository, ChatEventBroker, RunSupervisor, Path],
) -> None:
    services, _repository, _broker, _supervisor, project_root = chat_stack
    with _make_client(services, tmp_path) as client:
        created = client.post(
            "/api/chat/conversations",
            json={
                "title": "Runtime study",
                "project_root": str(project_root),
                "permission_mode": "PROJECT_READ_ONLY",
            },
        )
        assert created.status_code == 201
        body = created.json()
        assert body["title"] == "Runtime study"
        assert Path(body["project_root"]).resolve() == project_root.resolve()
        assert body["permission_mode"] == "PROJECT_READ_ONLY"
        conversation_id = body["conversation_id"]

        listed = client.get("/api/chat/conversations")
        assert listed.status_code == 200
        assert [item["conversation_id"] for item in listed.json()] == [conversation_id]

        fetched = client.get(f"/api/chat/conversations/{conversation_id}")
        assert fetched.status_code == 200
        assert fetched.json()["conversation_id"] == conversation_id

        patched = client.patch(
            f"/api/chat/conversations/{conversation_id}",
            json={
                "title": "New title",
                "permission_mode": "ASK_FOR_ACCESS",
            },
        )
        assert patched.status_code == 200
        assert patched.json()["title"] == "New title"
        assert patched.json()["permission_mode"] == "ASK_FOR_ACCESS"
        assert Path(patched.json()["project_root"]).resolve() == project_root.resolve()


def test_patch_rejects_project_root_and_unknown_fields(
    tmp_path: Path,
    chat_stack: tuple[Any, ConversationRepository, ChatEventBroker, RunSupervisor, Path],
) -> None:
    services, _repository, _broker, _supervisor, project_root = chat_stack
    with _make_client(services, tmp_path) as client:
        created = client.post(
            "/api/chat/conversations",
            json={
                "title": "Runtime study",
                "project_root": str(project_root),
                "permission_mode": "PROJECT_READ_ONLY",
            },
        ).json()
        conversation_id = created["conversation_id"]
        response = client.patch(
            f"/api/chat/conversations/{conversation_id}",
            json={"title": "x", "project_root": str(project_root)},
        )
        assert response.status_code == 422
        detail = json.dumps(response.json())
        assert "Traceback" not in detail
        assert "sqlite" not in detail.lower()


@pytest.mark.parametrize("blank_root", ["", "   "])
def test_create_conversation_rejects_blank_project_root(
    tmp_path: Path,
    chat_stack: tuple[Any, ConversationRepository, ChatEventBroker, RunSupervisor, Path],
    blank_root: str,
) -> None:
    services, repository, _broker, _supervisor, project_root = chat_stack
    with _make_client(services, tmp_path) as client:
        before = asyncio.run(repository.list_conversations())
        response = client.post(
            "/api/chat/conversations",
            json={
                "title": "Example",
                "project_root": blank_root,
                "permission_mode": "PROJECT_READ_ONLY",
            },
        )
        assert response.status_code == 422
        payload = json.dumps(response.json())
        assert "Traceback" not in payload
        assert "codex-pj" not in payload.lower()
        assert "search_agent" not in payload.lower()
        assert asyncio.run(repository.list_conversations()) == before

        valid = client.post(
            "/api/chat/conversations",
            json={
                "title": "Runtime study",
                "project_root": str(project_root),
                "permission_mode": "PROJECT_READ_ONLY",
            },
        )
        assert valid.status_code == 201


def test_chat_routes_reject_malformed_uuid_path_parameters(
    tmp_path: Path,
    chat_stack: tuple[Any, ConversationRepository, ChatEventBroker, RunSupervisor, Path],
) -> None:
    services, _repository, _broker, _supervisor, _project_root = chat_stack
    malformed = "not-a-uuid"
    missing = str(uuid4())
    with _make_client(services, tmp_path) as client:
        malformed_routes = [
            ("GET", f"/api/chat/conversations/{malformed}"),
            ("PATCH", f"/api/chat/conversations/{malformed}"),
            ("GET", f"/api/chat/conversations/{malformed}/messages"),
            ("POST", f"/api/chat/conversations/{malformed}/messages"),
            ("GET", f"/api/chat/conversations/{malformed}/events"),
            ("GET", f"/api/chat/runs/{malformed}"),
        ]
        for method, path in malformed_routes:
            if method == "GET":
                response = client.get(path)
            elif method == "PATCH":
                response = client.patch(path, json={"title": "x"})
            else:
                response = client.post(path, json={"query": "Explain the runtime"})
            assert response.status_code == 422, f"{method} {path} -> {response.status_code}"
            assert response.json().keys() <= {"detail"}
            assert "detail" in response.json()
            assert "Traceback" not in json.dumps(response.json())

        missing_conversation = client.get(f"/api/chat/conversations/{missing}")
        assert missing_conversation.status_code == 404
        assert missing_conversation.json() == {"detail": "not found"}
        missing_run = client.get(f"/api/chat/runs/{missing}")
        assert missing_run.status_code == 404
        assert missing_run.json() == {"detail": "not found"}


@pytest.mark.asyncio
async def test_supervisor_conflict_returns_detail_only_and_persists_failed_run(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixed_session_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    monkeypatch.setattr(
        "agent_foundations.chat.api.new_id",
        lambda: fixed_session_id,
    )
    ChatServices, create_chat_router = _require_chat_api()
    repository = ConversationRepository(tmp_path / "state" / "chat.sqlite3")
    await repository.initialize()
    broker = ChatEventBroker()
    supervisor = RunSupervisor()
    provider = FakeModelProvider([ModelResponse(content="unused")])
    runner = ConversationRunner(
        repository=repository,
        broker=broker,
        runtime_factory=_build_runtime_factory(provider),
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

    async def hang() -> None:
        await asyncio.Event().wait()

    conversation = await repository.create_conversation(
        title="Conflict study",
        project_root=project_root,
        permission_mode=PermissionMode.PROJECT_READ_ONLY,
    )
    await supervisor.start(conversation.conversation_id, hang)
    app = FastAPI()
    app.include_router(create_chat_router(services), prefix="/api/chat")
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                f"/api/chat/conversations/{conversation.conversation_id}/messages",
                json={"query": "Explain the runtime"},
            )
            assert response.status_code == 409
            assert response.json() == {"detail": "conflict"}
            assert "session_id" not in response.json()
            assert "Traceback" not in response.text

            run = await repository.get_run(fixed_session_id)
            assert run.status is RunStatus.FAILED
            assert run.error_code == "RunSupervisorConflict"
            messages = await repository.list_messages(conversation.conversation_id)
            assert len(messages) == 1
    finally:
        await supervisor.shutdown()


def test_validation_errors_are_stable_422(
    tmp_path: Path,
    chat_stack: tuple[Any, ConversationRepository, ChatEventBroker, RunSupervisor, Path],
) -> None:
    services, _repository, _broker, _supervisor, project_root = chat_stack
    with _make_client(services, tmp_path) as client:
        blank_title = client.post(
            "/api/chat/conversations",
            json={
                "title": "   ",
                "project_root": str(project_root),
                "permission_mode": "PROJECT_READ_ONLY",
            },
        )
        assert blank_title.status_code == 422

        missing_root = client.post(
            "/api/chat/conversations",
            json={
                "title": "Runtime study",
                "project_root": str(tmp_path / "missing"),
                "permission_mode": "PROJECT_READ_ONLY",
            },
        )
        assert missing_root.status_code == 422

        file_root = tmp_path / "not-a-dir.txt"
        file_root.write_text("x", encoding="utf-8")
        not_dir = client.post(
            "/api/chat/conversations",
            json={
                "title": "Runtime study",
                "project_root": str(file_root),
                "permission_mode": "PROJECT_READ_ONLY",
            },
        )
        assert not_dir.status_code == 422

        created = client.post(
            "/api/chat/conversations",
            json={
                "title": "Runtime study",
                "project_root": str(project_root),
                "permission_mode": "PROJECT_READ_ONLY",
            },
        ).json()
        blank_query = client.post(
            f"/api/chat/conversations/{created['conversation_id']}/messages",
            json={"query": "   "},
        )
        assert blank_query.status_code == 422
        for response in (blank_title, missing_root, not_dir, blank_query):
            payload = json.dumps(response.json())
            assert "Traceback" not in payload
            assert "do-not-leak" not in payload


def test_not_found_returns_404(
    tmp_path: Path,
    chat_stack: tuple[Any, ConversationRepository, ChatEventBroker, RunSupervisor, Path],
) -> None:
    services, _repository, _broker, _supervisor, _project_root = chat_stack
    missing_id = str(uuid4())
    with _make_client(services, tmp_path) as client:
        conversation = client.get(f"/api/chat/conversations/{missing_id}")
        assert conversation.status_code == 404
        run = client.get(f"/api/chat/runs/{missing_id}")
        assert run.status_code == 404
        for response in (conversation, run):
            body = response.json()
            assert "detail" in body
            assert "Traceback" not in json.dumps(body)


def test_conversation_list_order_is_repository_deterministic(
    tmp_path: Path,
    chat_stack: tuple[Any, ConversationRepository, ChatEventBroker, RunSupervisor, Path],
) -> None:
    services, repository, _broker, _supervisor, project_root = chat_stack
    with _make_client(services, tmp_path) as client:
        first = client.post(
            "/api/chat/conversations",
            json={
                "title": "First",
                "project_root": str(project_root),
                "permission_mode": "PROJECT_READ_ONLY",
            },
        ).json()
        second = client.post(
            "/api/chat/conversations",
            json={
                "title": "Second",
                "project_root": str(project_root),
                "permission_mode": "PROJECT_READ_ONLY",
            },
        ).json()
        client.patch(
            f"/api/chat/conversations/{first['conversation_id']}",
            json={"title": "First updated"},
        )
        expected = [
            item.conversation_id
            for item in asyncio.run(repository.list_conversations())
        ]
        listed = [item["conversation_id"] for item in client.get("/api/chat/conversations").json()]
        assert listed == expected
        assert listed[0] == first["conversation_id"]
        assert second["conversation_id"] in listed


def test_post_message_persists_then_supervises_and_returns_202(
    tmp_path: Path,
    chat_stack: tuple[Any, ConversationRepository, ChatEventBroker, RunSupervisor, Path],
) -> None:
    services, repository, _broker, _supervisor, project_root = chat_stack
    with _make_client(services, tmp_path) as client:
        created = client.post(
            "/api/chat/conversations",
            json={
                "title": "Runtime study",
                "project_root": str(project_root),
                "permission_mode": "PROJECT_READ_ONLY",
            },
        ).json()
        conversation_id = created["conversation_id"]
        response = client.post(
            f"/api/chat/conversations/{conversation_id}/messages",
            json={"query": "Explain the runtime"},
        )
        assert response.status_code == 202
        session_id = response.json()["session_id"]
        assert session_id

        run = client.get(f"/api/chat/runs/{session_id}")
        assert run.status_code == 200
        assert run.json()["session_id"] == session_id
        assert run.json()["conversation_id"] == conversation_id

        messages = client.get(f"/api/chat/conversations/{conversation_id}/messages")
        assert messages.status_code == 200
        assert any(item["role"] == "user" for item in messages.json())

        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            status = client.get(f"/api/chat/runs/{session_id}").json()["status"]
            if status in {"completed", "failed", "interrupted"}:
                break
            time.sleep(0.05)
        final = client.get(f"/api/chat/runs/{session_id}").json()
        assert final["status"] == "completed"
        persisted = asyncio.run(repository.get_run(session_id))
        assert persisted.status is RunStatus.COMPLETED


def test_active_run_conflicts_return_409(
    tmp_path: Path,
    project_root: Path,
) -> None:
    ChatServices, _ = _require_chat_api()
    repository = ConversationRepository(tmp_path / "state" / "chat.sqlite3")
    asyncio.run(repository.initialize())
    broker = ChatEventBroker()
    supervisor = RunSupervisor()
    started = asyncio.Event()

    class HangingProvider:
        async def complete(self, request: Any) -> ModelResponse:
            started.set()
            await asyncio.Event().wait()
            return ModelResponse(content="unreachable")

    def factory(
        conversation: Conversation,
        event_sink: EventSink,
        tool_executor: ToolCallExecutor,
    ) -> AgentLoop:
        return AgentLoop(
            provider=HangingProvider(),
            registry=ToolRegistry(
                [ListDirectoryTool(PathPolicy(Path(conversation.project_root)))],
            ),
            context_builder=ContextBuilder(ContextBudget()),
            event_sink=event_sink,
            config=AgentConfig(max_steps=5),
            tool_executor=tool_executor,
        )

    runner = ConversationRunner(
        repository=repository,
        broker=broker,
        runtime_factory=factory,
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
    try:
        with _make_client(services, tmp_path) as client:
            created = client.post(
                "/api/chat/conversations",
                json={
                    "title": "Runtime study",
                    "project_root": str(project_root),
                    "permission_mode": "PROJECT_READ_ONLY",
                },
            ).json()
            conversation_id = created["conversation_id"]
            first = client.post(
                f"/api/chat/conversations/{conversation_id}/messages",
                json={"query": "Explain the runtime"},
            )
            assert first.status_code == 202
            session_id = first.json()["session_id"]
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                if started.is_set():
                    break
                time.sleep(0.01)
            assert started.is_set()
            assert asyncio.run(repository.get_run(session_id)).status in RunStatus.active()

            second = client.post(
                f"/api/chat/conversations/{conversation_id}/messages",
                json={"query": "Another question"},
            )
            assert second.status_code == 409
            assert "detail" in second.json()
            assert "Traceback" not in json.dumps(second.json())

            permission = client.patch(
                f"/api/chat/conversations/{conversation_id}",
                json={"permission_mode": "ASK_FOR_ACCESS"},
            )
            assert permission.status_code == 409
    finally:
        asyncio.run(supervisor.shutdown())


def _chat_events_route_from_router(router: Any) -> APIRoute:
    return next(
        route
        for route in router.routes
        if isinstance(route, APIRoute)
        and route.path == "/conversations/{conversation_id}/events"
    )


async def _receive_request() -> Message:
    return {"type": "http.request", "body": b"", "more_body": False}


def _connected_request(conversation_id: str) -> Request:
    path = f"/api/chat/conversations/{conversation_id}/events"
    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "root_path": "",
            "headers": [],
            "client": ("127.0.0.1", 50000),
            "server": ("127.0.0.1", 8765),
        },
        _receive_request,
    )


@pytest.mark.asyncio
async def test_chat_sse_connected_keepalive_and_events(
    tmp_path: Path,
    project_root: Path,
) -> None:
    ChatServices, create_chat_router = _require_chat_api()
    repository = ConversationRepository(tmp_path / "state" / "chat.sqlite3")
    await repository.initialize()
    broker = ChatEventBroker()
    supervisor = RunSupervisor()
    provider = FakeModelProvider([ModelResponse(content="unused")])
    runner = ConversationRunner(
        repository=repository,
        broker=broker,
        runtime_factory=_build_runtime_factory(provider),
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
        title="SSE study",
        project_root=project_root,
        permission_mode=PermissionMode.PROJECT_READ_ONLY,
    )
    router = create_chat_router(services, keepalive_seconds=0.05)
    app = FastAPI()
    app.include_router(router, prefix="/api/chat")

    response = cast(
        StreamingResponse,
        await _chat_events_route_from_router(router).endpoint(
            _connected_request(conversation.conversation_id),
            conversation.conversation_id,
        ),
    )
    assert response.media_type == "text/event-stream"
    stream = cast(AsyncGenerator[str, None], response.body_iterator)
    try:
        assert await anext(stream) == ": connected\n\n"
        assert await anext(stream) == ": keepalive\n\n"
        event = ChatEvent(
            conversation_id=conversation.conversation_id,
            session_id=str(uuid4()),
            type=ChatEventType.RUN_STARTED,
            data={"status": "running"},
        )
        await broker.publish(event)
        encoded = await asyncio.wait_for(anext(stream), timeout=0.5)
        assert encoded == encode_chat_sse(event)
        assert "arguments" not in encoded or "arguments_summary" in encoded
        assert "payload" not in encoded
    finally:
        await stream.aclose()

    await supervisor.shutdown()


@pytest.mark.asyncio
async def test_chat_sse_missing_conversation_is_404(
    tmp_path: Path,
    project_root: Path,
) -> None:
    ChatServices, create_chat_router = _require_chat_api()
    repository = ConversationRepository(tmp_path / "state" / "chat.sqlite3")
    await repository.initialize()
    broker = ChatEventBroker()
    services = ChatServices(
        repository=repository,
        broker=broker,
        runner=ConversationRunner(
            repository=repository,
            broker=broker,
            runtime_factory=_build_runtime_factory(FakeModelProvider([])),
            trace_dir=tmp_path / "traces",
            redactor_factory=lambda conversation: Redactor(
                Path(conversation.project_root),
            ),
            tool_executor_factory=direct_executor_factory,
        ),
        supervisor=RunSupervisor(),
        coordinator=ApprovalCoordinator(repository, broker),
    )
    app = FastAPI()
    app.include_router(create_chat_router(services), prefix="/api/chat")
    with TestClient(app) as client:
        response = client.get(f"/api/chat/conversations/{uuid4()}/events")
        assert response.status_code == 404
    _ = project_root


def test_chat_enabled_routes_with_present_build_200(
    tmp_path: Path,
    chat_stack: tuple[Any, ConversationRepository, ChatEventBroker, RunSupervisor, Path],
) -> None:
    from agent_foundations.viewer.app import CHAT_BUILD_DIR

    chat_index = CHAT_BUILD_DIR / "index.html"
    if not chat_index.is_file():
        pytest.skip("Chat UI build is missing")

    services, _repository, _broker, _supervisor, _project_root = chat_stack
    with TestClient(create_app(tmp_path / "traces", chat_services=services)) as client:
        root = client.get("/")
        chat = client.get("/chat")
        assert root.status_code == 200
        assert chat.status_code == 200
        assert "text/html" in root.headers["content-type"]
        assert "text/html" in chat.headers["content-type"]
        assert "/chat-static/assets/" in root.text
        match = re.search(r'src="(/chat-static/assets/[^"]+)"', root.text)
        assert match is not None
        asset = client.get(match.group(1))
        assert asset.status_code == 200
        trace = client.get("/trace")
        assert trace.status_code == 200
        assert "text/html" in trace.headers["content-type"]


def test_chat_enabled_routes_and_missing_build_503(
    tmp_path: Path,
    chat_stack: tuple[Any, ConversationRepository, ChatEventBroker, RunSupervisor, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import agent_foundations.viewer.app as viewer_app

    services, _repository, _broker, _supervisor, _project_root = chat_stack
    missing_build_dir = tmp_path / "missing-chat-build"
    monkeypatch.setattr(viewer_app, "CHAT_BUILD_DIR", missing_build_dir)
    with TestClient(create_app(tmp_path / "traces", chat_services=services)) as client:
        root = client.get("/")
        chat = client.get("/chat")
        assert root.status_code == 503
        assert chat.status_code == 503
        assert root.json() == {"detail": "Chat UI build is missing"}
        assert chat.json() == {"detail": "Chat UI build is missing"}
        trace = client.get("/trace")
        assert trace.status_code == 200
        assert "text/html" in trace.headers["content-type"]


def test_trace_only_app_keeps_root_viewer(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path)) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert client.get("/api/sessions").status_code == 200


# ── Task 12: conversation state recovery API ───────────────────────────────


def _create_conversation_via_api(
    client: TestClient,
    project_root: Path,
    *,
    permission_mode: str = "PROJECT_READ_ONLY",
) -> str:
    response = client.post(
        "/api/chat/conversations",
        json={
            "title": "Recovery study",
            "project_root": str(project_root),
            "permission_mode": permission_mode,
        },
    )
    assert response.status_code == 201
    return str(response.json()["conversation_id"])


def test_conversation_state_no_run_shape(
    tmp_path: Path,
    chat_stack: tuple[Any, ConversationRepository, ChatEventBroker, RunSupervisor, Path],
) -> None:
    services, _repository, _broker, _supervisor, project_root = chat_stack
    with _make_client(services, tmp_path) as client:
        conversation_id = _create_conversation_via_api(client, project_root)
        response = client.get(f"/api/chat/conversations/{conversation_id}/state")
        assert response.status_code == 200
        assert response.json() == {"latest_run": None, "pending_approval": None}


def test_conversation_state_running_run(
    tmp_path: Path,
    chat_stack: tuple[Any, ConversationRepository, ChatEventBroker, RunSupervisor, Path],
) -> None:
    services, repository, _broker, _supervisor, project_root = chat_stack
    with _make_client(services, tmp_path) as client:
        conversation_id = _create_conversation_via_api(client, project_root)
        session_id = str(uuid4())
        asyncio.run(
            repository.begin_run(
                conversation_id,
                content="running question",
                session_id=session_id,
            ),
        )
        asyncio.run(
            repository.transition_run(
                session_id,
                RunStatus.QUEUED,
                RunStatus.RUNNING,
            ),
        )
        response = client.get(f"/api/chat/conversations/{conversation_id}/state")
        assert response.status_code == 200
        body = response.json()
        assert body["pending_approval"] is None
        assert body["latest_run"]["session_id"] == session_id
        assert body["latest_run"]["status"] == "running"


def test_conversation_state_waiting_approval_exact_fields(
    tmp_path: Path,
    chat_stack: tuple[Any, ConversationRepository, ChatEventBroker, RunSupervisor, Path],
) -> None:
    services, repository, _broker, _supervisor, project_root = chat_stack
    with _make_client(services, tmp_path) as client:
        conversation_id = _create_conversation_via_api(
            client,
            project_root,
            permission_mode="ASK_FOR_ACCESS",
        )
        session_id = str(uuid4())
        approval_id = str(uuid4())
        asyncio.run(
            repository.begin_run(
                conversation_id,
                content="approval question",
                session_id=session_id,
            ),
        )
        asyncio.run(
            repository.transition_run(
                session_id,
                RunStatus.QUEUED,
                RunStatus.RUNNING,
            ),
        )
        asyncio.run(
            repository.transition_run(
                session_id,
                RunStatus.RUNNING,
                RunStatus.WAITING_APPROVAL,
            ),
        )
        asyncio.run(
            repository.create_approval(
                conversation_id=conversation_id,
                session_id=session_id,
                tool_call_id="call-recovery",
                tool_name="read_file",
                canonical_path="/tmp/recovery.txt",
                approval_id=approval_id,
            ),
        )
        response = client.get(f"/api/chat/conversations/{conversation_id}/state")
        assert response.status_code == 200
        body = response.json()
        assert body["latest_run"]["status"] == "waiting_approval"
        assert body["pending_approval"] == {
            "approval_id": approval_id,
            "conversation_id": conversation_id,
            "session_id": session_id,
            "tool_call_id": "call-recovery",
            "tool_name": "read_file",
            "canonical_path": "/tmp/recovery.txt",
            "operation": "read",
            "scope": "external_exact_path",
            "status": "pending",
            "requested_at": body["pending_approval"]["requested_at"],
        }


@pytest.mark.parametrize("terminal_status", ["completed", "failed", "interrupted"])
def test_conversation_state_terminal_run_has_no_pending_approval(
    terminal_status: str,
    tmp_path: Path,
    chat_stack: tuple[Any, ConversationRepository, ChatEventBroker, RunSupervisor, Path],
) -> None:
    services, repository, _broker, _supervisor, project_root = chat_stack
    with _make_client(services, tmp_path) as client:
        conversation_id = _create_conversation_via_api(client, project_root)
        session_id = str(uuid4())
        asyncio.run(
            repository.begin_run(
                conversation_id,
                content="terminal question",
                session_id=session_id,
            ),
        )
        asyncio.run(
            repository.transition_run(
                session_id,
                RunStatus.QUEUED,
                RunStatus.RUNNING,
            ),
        )
        if terminal_status == "completed":
            asyncio.run(repository.complete_run(session_id, "done"))
        elif terminal_status == "failed":
            asyncio.run(repository.fail_run(session_id, "TestFailure"))
        else:
            asyncio.run(repository.interrupt_run(session_id))
        response = client.get(f"/api/chat/conversations/{conversation_id}/state")
        assert response.status_code == 200
        body = response.json()
        assert body["latest_run"]["status"] == terminal_status
        assert body["pending_approval"] is None


def test_conversation_state_malformed_uuid_returns_422(
    tmp_path: Path,
    chat_stack: tuple[Any, ConversationRepository, ChatEventBroker, RunSupervisor, Path],
) -> None:
    services, _repository, _broker, _supervisor, _project_root = chat_stack
    with _make_client(services, tmp_path) as client:
        response = client.get("/api/chat/conversations/not-a-uuid/state")
        assert response.status_code == 422


def test_conversation_state_missing_conversation_returns_404(
    tmp_path: Path,
    chat_stack: tuple[Any, ConversationRepository, ChatEventBroker, RunSupervisor, Path],
) -> None:
    services, _repository, _broker, _supervisor, _project_root = chat_stack
    with _make_client(services, tmp_path) as client:
        response = client.get(f"/api/chat/conversations/{uuid4()}/state")
        assert response.status_code == 404
        assert response.json() == {"detail": "not found"}


def test_conversation_state_response_has_no_secrets_or_stack(
    tmp_path: Path,
    chat_stack: tuple[Any, ConversationRepository, ChatEventBroker, RunSupervisor, Path],
) -> None:
    services, _repository, _broker, _supervisor, project_root = chat_stack
    with _make_client(services, tmp_path) as client:
        conversation_id = _create_conversation_via_api(client, project_root)
        response = client.get(f"/api/chat/conversations/{conversation_id}/state")
        text = response.text.lower()
        assert response.status_code == 200
        assert "traceback" not in text
        assert "sqlite" not in text
        assert "api_key" not in text
        assert "stack" not in text


def test_list_conversation_runs_returns_turn_mapping_and_stable_errors(
    tmp_path: Path,
    chat_stack: tuple[Any, ConversationRepository, ChatEventBroker, RunSupervisor, Path],
) -> None:
    services, repository, _broker, _supervisor, project_root = chat_stack
    with _make_client(services, tmp_path) as client:
        conversation_id = _create_conversation_via_api(client, project_root)
        first_session_id = str(uuid4())
        second_session_id = str(uuid4())
        _first_message, first_run = asyncio.run(
            repository.begin_run(
                conversation_id,
                content="first question",
                session_id=first_session_id,
            ),
        )
        asyncio.run(
            repository.transition_run(
                first_run.session_id,
                RunStatus.QUEUED,
                RunStatus.RUNNING,
            ),
        )
        first_answer = asyncio.run(repository.complete_run(first_run.session_id, "answer"))
        asyncio.run(
            repository.begin_run(
                conversation_id,
                content="second question",
                session_id=second_session_id,
            ),
        )

        response = client.get(f"/api/chat/conversations/{conversation_id}/runs")

        assert response.status_code == 200
        body = response.json()
        assert [item["session_id"] for item in body] == [
            first_session_id,
            second_session_id,
        ]
        assert body[0]["assistant_message_id"] == first_answer.message_id
        assert body[1]["assistant_message_id"] is None

        malformed = client.get("/api/chat/conversations/not-a-uuid/runs")
        assert malformed.status_code == 422
        missing = client.get(f"/api/chat/conversations/{uuid4()}/runs")
        assert missing.status_code == 404
        assert missing.json() == {"detail": "not found"}
