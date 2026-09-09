from __future__ import annotations

import asyncio
import importlib.util
import logging
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from starlette.requests import Request
from starlette.types import Message

from agent_foundations.chat.api import ChatServices, create_chat_router
from agent_foundations.chat.approvals import ApprovalCoordinator
from agent_foundations.chat.errors import ChatConflictError
from agent_foundations.chat.events import ChatEventBroker
from agent_foundations.chat.models import PermissionMode, RunStatus
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
from agent_foundations.viewer.app import create_app
from agent_foundations.viewer.stream import EventBroker
from tests.unit.tools.registry_helpers import readonly_tool_registry

SECRET = "sk-test_placeholder_not_real"
LIFECYCLE_LOGGER = "agent_foundations.chat.lifecycle"


def _require_lifecycle() -> Any:
    spec = importlib.util.find_spec("agent_foundations.chat.lifecycle")
    assert spec is not None, "chat lifecycle module is missing"
    from agent_foundations.chat.lifecycle import (
        CHAT_LIFESPAN_SHUTDOWN,
        SSE_CLIENT_DISCONNECT,
        SSE_FAILED,
        SSE_LIFESPAN_CANCEL,
        is_shutting_down,
    )

    return (
        SSE_CLIENT_DISCONNECT,
        SSE_LIFESPAN_CANCEL,
        SSE_FAILED,
        CHAT_LIFESPAN_SHUTDOWN,
        is_shutting_down,
    )


def _runtime_factory(provider: FakeModelProvider) -> Any:
    def factory(
        conversation: Any,
        event_sink: EventSink,
        tool_executor: ToolCallExecutor,
    ) -> AgentLoop:
        return AgentLoop(
            provider=provider,
            registry=readonly_tool_registry(Path(conversation.project_root)),
            context_builder=ContextBuilder(ContextBudget()),
            event_sink=event_sink,
            config=AgentConfig(max_steps=5),
            tool_executor=tool_executor,
        )

    return factory


async def _receive() -> Message:
    return {"type": "http.request", "body": b"", "more_body": False}


class _CancellingRequest(Request):
    async def is_disconnected(self) -> bool:
        raise asyncio.CancelledError()


class _FailingRequest(Request):
    async def is_disconnected(self) -> bool:
        raise RuntimeError("injected-sse-failure")


def _asgi_scope(
    path: str,
    *,
    query: bytes = b"",
    app: object | None = None,
) -> dict[str, Any]:
    scope: dict[str, Any] = {
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
    }
    if app is not None:
        scope["app"] = app
    return scope


def _services(
    tmp_path: Path,
    *,
    durable_repository: Any | None = None,
) -> ChatServices:
    repository = ConversationRepository(tmp_path / "chat.sqlite3")
    broker = ChatEventBroker()
    provider = FakeModelProvider([ModelResponse(content="ok")])
    runner = ConversationRunner(
        repository=repository,
        broker=broker,
        runtime_factory=_runtime_factory(provider),
        trace_dir=tmp_path / "traces",
        redactor_factory=lambda conversation: Redactor(Path(conversation.project_root)),
        tool_executor_factory=direct_executor_factory,
        durable_repository=durable_repository,
    )
    return ChatServices(
        repository=repository,
        broker=broker,
        runner=runner,
        supervisor=RunSupervisor(),
        coordinator=ApprovalCoordinator(repository, broker),
        durable_repository=durable_repository,
    )


async def _prepared_chat(
    tmp_path: Path,
) -> tuple[ChatServices, str, APIRoute]:
    services = _services(tmp_path)
    await services.repository.initialize()
    project_root = tmp_path / "project"
    project_root.mkdir()
    conversation = await services.repository.create_conversation(
        title="Lifecycle SSE",
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
    return services, conversation.conversation_id, route


def _no_error_records(caplog: pytest.LogCaptureFixture) -> None:
    errors = [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert errors == []


def test_lifecycle_locked_messages_and_logger_name() -> None:
    (
        disconnect,
        lifespan_cancel,
        failed,
        shutdown,
        _is_shutting_down,
    ) = _require_lifecycle()
    assert disconnect == "sse cancelled: client disconnect"
    assert lifespan_cancel == "sse cancelled: lifespan shutdown"
    assert failed == "sse failed"
    assert shutdown == "chat lifespan shutdown"
    from agent_foundations.chat.lifecycle import logger

    assert logger.name == LIFECYCLE_LOGGER


def test_is_shutting_down_without_app_is_false() -> None:
    _disconnect, _cancel, _failed, _shutdown, is_shutting_down = _require_lifecycle()
    request = Request(_asgi_scope("/api/chat/events"), _receive)
    assert is_shutting_down(request) is False


def test_is_shutting_down_reads_app_state_flag() -> None:
    _disconnect, _cancel, _failed, _shutdown, is_shutting_down = _require_lifecycle()
    app = FastAPI()
    app.state.chat_shutting_down = True
    request = Request(_asgi_scope("/api/chat/events", app=app), _receive)
    assert is_shutting_down(request) is True
    app.state.chat_shutting_down = False
    assert is_shutting_down(request) is False


async def test_chat_and_trace_sse_cancelled_logs_debug_client_disconnect(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    disconnect, _cancel, _failed, _shutdown, _is_shutting_down = _require_lifecycle()
    caplog.set_level(logging.DEBUG, logger=LIFECYCLE_LOGGER)
    services, conversation_id, route = await _prepared_chat(tmp_path)
    request = _CancellingRequest(
        _asgi_scope(f"/api/chat/conversations/{conversation_id}/events"),
        _receive,
    )
    response = cast(
        StreamingResponse,
        await route.endpoint(request, UUID(conversation_id)),
    )
    stream = cast(AsyncGenerator[str, None], response.body_iterator)
    assert await anext(stream) == ": connected\n\n"
    with pytest.raises(StopAsyncIteration):
        await anext(stream)
    await stream.aclose()
    count = getattr(services.broker, "subscriber_count", None)
    assert callable(count)
    assert count(conversation_id) == 0
    messages = [record.getMessage() for record in caplog.records]
    assert any(
        disconnect in message and "(chat)" in message and record.levelno == logging.DEBUG
        for record, message in zip(caplog.records, messages, strict=True)
    )
    _no_error_records(caplog)
    await services.supervisor.shutdown()

    trace_broker = EventBroker()
    app = create_app(tmp_path / "traces", broker=trace_broker)
    trace_route = next(
        item
        for item in app.routes
        if isinstance(item, APIRoute) and item.path == "/api/events/stream"
    )
    trace_request = _CancellingRequest(_asgi_scope("/api/events/stream"), _receive)
    trace_response = cast(
        StreamingResponse,
        await trace_route.endpoint(trace_request, "*"),
    )
    trace_stream = cast(AsyncGenerator[str, None], trace_response.body_iterator)
    assert await anext(trace_stream) == ": connected\n\n"
    with pytest.raises(StopAsyncIteration):
        await anext(trace_stream)
    await trace_stream.aclose()
    trace_count = getattr(trace_broker, "subscriber_count", None)
    assert callable(trace_count)
    assert trace_count("*") == 0
    assert any(
        disconnect in record.getMessage()
        and "(trace)" in record.getMessage()
        and record.levelno == logging.DEBUG
        for record in caplog.records
    )
    _no_error_records(caplog)


async def test_sse_cancelled_during_lifespan_shutdown_logs_info(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _disconnect, lifespan_cancel, _failed, _shutdown, _is_shutting_down = _require_lifecycle()
    caplog.set_level(logging.DEBUG, logger=LIFECYCLE_LOGGER)
    services, conversation_id, route = await _prepared_chat(tmp_path)
    app = FastAPI()
    app.state.chat_shutting_down = True
    request = _CancellingRequest(
        _asgi_scope(
            f"/api/chat/conversations/{conversation_id}/events",
            app=app,
        ),
        _receive,
    )
    response = cast(
        StreamingResponse,
        await route.endpoint(request, UUID(conversation_id)),
    )
    stream = cast(AsyncGenerator[str, None], response.body_iterator)
    assert await anext(stream) == ": connected\n\n"
    with pytest.raises(StopAsyncIteration):
        await anext(stream)
    await stream.aclose()
    assert any(
        lifespan_cancel in record.getMessage()
        and "(chat)" in record.getMessage()
        and record.levelno == logging.INFO
        for record in caplog.records
    )
    _no_error_records(caplog)
    await services.supervisor.shutdown()


async def test_sse_other_exception_logs_error_type_without_payload(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _disconnect, _cancel, failed, _shutdown, _is_shutting_down = _require_lifecycle()
    caplog.set_level(logging.DEBUG, logger=LIFECYCLE_LOGGER)
    services, conversation_id, route = await _prepared_chat(tmp_path)
    query = f"q={SECRET}&payload=user-query-secret".encode()
    request = _FailingRequest(
        _asgi_scope(
            f"/api/chat/conversations/{conversation_id}/events",
            query=query,
        ),
        _receive,
    )
    response = cast(
        StreamingResponse,
        await route.endpoint(request, UUID(conversation_id)),
    )
    stream = cast(AsyncGenerator[str, None], response.body_iterator)
    assert await anext(stream) == ": connected\n\n"
    with pytest.raises(RuntimeError, match="injected-sse-failure"):
        await anext(stream)
    await stream.aclose()
    error_messages = [
        record.getMessage()
        for record in caplog.records
        if record.levelno >= logging.ERROR
    ]
    assert any(
        failed in message and "RuntimeError" in message and "(chat)" in message
        for message in error_messages
    )
    joined = "\n".join(error_messages)
    assert SECRET not in joined
    assert "user-query-secret" not in joined
    count = getattr(services.broker, "subscriber_count", lambda _cid: -1)
    assert count(conversation_id) == 0
    await services.supervisor.shutdown()


def test_chat_lifespan_logs_shutdown_and_clears_supervisor(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _disconnect, _cancel, _failed, shutdown, _is_shutting_down = _require_lifecycle()
    caplog.set_level(logging.INFO, logger=LIFECYCLE_LOGGER)
    services = _services(tmp_path)
    with TestClient(create_app(tmp_path / "traces", chat_services=services)):
        pass
    assert any(
        shutdown in record.getMessage() and record.levelno == logging.INFO
        for record in caplog.records
    )
    assert services.supervisor.is_active("any-conversation") is False

    async def _noop() -> None:
        return None

    with pytest.raises(ChatConflictError):
        asyncio.run(services.supervisor.start("any-conversation", _noop))


def test_create_app_lifespan_interrupts_preloaded_running_run(tmp_path: Path) -> None:
    services = _services(tmp_path)
    repository = services.repository
    asyncio.run(repository.initialize())
    project_root = tmp_path / "project"
    project_root.mkdir()
    conversation = asyncio.run(
        repository.create_conversation(
            title="Interrupt via lifespan",
            project_root=project_root,
            permission_mode=PermissionMode.PROJECT_READ_ONLY,
        )
    )
    _message, run = asyncio.run(
        repository.begin_run(
            conversation.conversation_id,
            content="leftover run",
            session_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        )
    )
    asyncio.run(
        repository.transition_run(
            run.session_id,
            RunStatus.QUEUED,
            RunStatus.RUNNING,
        )
    )
    with TestClient(create_app(tmp_path / "traces", chat_services=services)):
        loaded = asyncio.run(repository.get_run(run.session_id))
        assert loaded.status is RunStatus.INTERRUPTED
    assert services.supervisor.is_active(conversation.conversation_id) is False


def test_create_app_lifespan_cancels_matching_durable_running_run(tmp_path: Path) -> None:
    from datetime import UTC, datetime

    from agent_foundations.durable.models import DurableRun, DurableRunStatus
    from agent_foundations.durable.repository import DurableRunRepository

    database_path = tmp_path / "chat.sqlite3"
    durable = DurableRunRepository(database_path)
    services = _services(tmp_path, durable_repository=durable)
    repository = services.repository
    asyncio.run(repository.initialize())
    asyncio.run(durable.initialize())
    project_root = tmp_path / "project"
    project_root.mkdir()
    conversation = asyncio.run(
        repository.create_conversation(
            title="Interrupt durable via lifespan",
            project_root=project_root,
            permission_mode=PermissionMode.PROJECT_READ_ONLY,
        )
    )
    _message, run = asyncio.run(
        repository.begin_run(
            conversation.conversation_id,
            content="leftover durable run",
            session_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        )
    )
    asyncio.run(
        repository.transition_run(
            run.session_id,
            RunStatus.QUEUED,
            RunStatus.RUNNING,
        )
    )
    now = datetime(2026, 9, 8, 12, 0, 0, tzinfo=UTC)
    asyncio.run(
        durable.create_run(
            DurableRun(
                run_id=run.session_id,
                project_root=str(project_root),
                status=DurableRunStatus.RUNNING,
                schema_version=1,
                state_version=0,
                attempt=1,
                created_at=now,
                updated_at=now,
            ),
        )
    )
    with TestClient(create_app(tmp_path / "traces", chat_services=services)):
        loaded = asyncio.run(repository.get_run(run.session_id))
        durable_run = asyncio.run(durable.get_run(run.session_id))
        assert loaded.status is RunStatus.INTERRUPTED
        assert durable_run.status is DurableRunStatus.CANCELLED
    assert services.supervisor.is_active(conversation.conversation_id) is False
