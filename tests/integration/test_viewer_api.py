import asyncio
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from starlette.types import Message

from agent_foundations.chat.api import ChatServices
from agent_foundations.chat.approvals import ApprovalCoordinator
from agent_foundations.chat.events import ChatEventBroker
from agent_foundations.chat.models import PermissionMode, RunStatus
from agent_foundations.chat.repository import ConversationRepository
from agent_foundations.chat.supervisor import RunSupervisor
from agent_foundations.runtime.trace import TraceEvent
from agent_foundations.viewer.app import create_app
from agent_foundations.viewer.stream import EventBroker


def make_event() -> TraceEvent:
    return TraceEvent(
        session_id="session-api",
        step_id=1,
        event_type="tool.call.completed",
        status="completed",
        summary="read_file completed",
    )


def event_stream_route(app: FastAPI) -> APIRoute:
    return next(
        route
        for route in app.routes
        if isinstance(route, APIRoute) and route.path == "/api/events/stream"
    )


async def receive_request() -> Message:
    return {"type": "http.request", "body": b"", "more_body": False}


def connected_request() -> Request:
    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/api/events/stream",
            "raw_path": b"/api/events/stream",
            "query_string": b"",
            "root_path": "",
            "headers": [],
            "client": ("127.0.0.1", 50000),
            "server": ("127.0.0.1", 8765),
        },
        receive_request,
    )


def test_accepts_event_and_lists_persisted_session(tmp_path: Path) -> None:
    event = make_event()
    (tmp_path / "session-api.jsonl").write_text(
        event.model_dump_json() + "\n",
        encoding="utf-8",
    )
    with TestClient(create_app(tmp_path, EventBroker())) as client:
        assert client.post("/api/events", json=event.model_dump(mode="json")).status_code == 202
        assert client.get("/api/sessions").json() == ["session-api"]
        history = client.get("/api/sessions/session-api").json()
        assert history[0]["event_type"] == "tool.call.completed"
        assert client.get("/").status_code == 200


def test_create_app_signature_accepts_optional_chat_services(tmp_path: Path) -> None:
    # Trace-only callers keep working without chat_services.
    app = create_app(tmp_path)
    with TestClient(app) as client:
        assert client.get("/api/sessions").status_code == 200
        assert client.get("/").status_code == 200


def test_trace_navigation_lists_standalone_runs_and_keeps_legacy_sessions(
    tmp_path: Path,
) -> None:
    session_id = "standalone-session"
    event = TraceEvent(
        session_id=session_id,
        step_id=0,
        event_type="user.message",
        status="completed",
        summary="Inspect the runtime architecture",
    )
    (tmp_path / f"{session_id}.jsonl").write_text(
        event.model_dump_json() + "\n",
        encoding="utf-8",
    )

    with TestClient(create_app(tmp_path, EventBroker())) as client:
        response = client.get("/api/trace-navigation")

        assert response.status_code == 200
        assert response.json() == {
            "chat_conversations": [],
            "standalone_runs": [
                {
                    "session_id": session_id,
                    "short_id": "standalo",
                    "user_message_preview": "Inspect the runtime architecture",
                    "status": "completed",
                    "started_at": event.timestamp.isoformat().replace("+00:00", "Z"),
                    "trace_available": True,
                },
            ],
        }
        assert client.get("/api/sessions").json() == [session_id]


def test_trace_navigation_groups_chat_turns_and_retains_missing_trace(
    tmp_path: Path,
) -> None:
    trace_dir = tmp_path / "traces"
    trace_dir.mkdir()
    project_root = tmp_path / "project"
    project_root.mkdir()
    repository = ConversationRepository(tmp_path / "state" / "chat.sqlite3")
    asyncio.run(repository.initialize())
    broker = ChatEventBroker()
    supervisor = RunSupervisor()
    services = ChatServices(
        repository=repository,
        broker=broker,
        runner=cast(Any, object()),
        supervisor=supervisor,
        coordinator=ApprovalCoordinator(repository, broker),
    )

    with TestClient(create_app(trace_dir, chat_services=services)) as client:
        conversation = asyncio.run(
            repository.create_conversation(
                title="Runtime study",
                project_root=project_root,
                permission_mode=PermissionMode.PROJECT_READ_ONLY,
            ),
        )
        first_session = str(uuid4())
        _first_message, first_run = asyncio.run(
            repository.begin_run(
                conversation.conversation_id,
                content="Explain how the agent loop works",
                session_id=first_session,
            ),
        )
        asyncio.run(
            repository.transition_run(
                first_session,
                RunStatus.QUEUED,
                RunStatus.RUNNING,
            ),
        )
        asyncio.run(repository.complete_run(first_session, "It iterates over steps."))
        first_run = asyncio.run(repository.get_run(first_session))
        first_event = TraceEvent(
            session_id=first_session,
            step_id=0,
            event_type="user.message",
            status="completed",
            summary="Explain how the agent loop works",
        )
        (trace_dir / f"{first_session}.jsonl").write_text(
            first_event.model_dump_json() + "\n",
            encoding="utf-8",
        )

        second_session = str(uuid4())
        _second_message, second_run = asyncio.run(
            repository.begin_run(
                conversation.conversation_id,
                content="Now explain tool execution",
                session_id=second_session,
            ),
        )
        standalone_session = "cli-analyze"
        standalone_event = TraceEvent(
            session_id=standalone_session,
            step_id=0,
            event_type="user.message",
            status="completed",
            summary="Analyze this standalone project",
        )
        (trace_dir / f"{standalone_session}.jsonl").write_text(
            standalone_event.model_dump_json() + "\n",
            encoding="utf-8",
        )

        response = client.get("/api/trace-navigation")

        assert response.status_code == 200
        body = response.json()
        assert body["chat_conversations"] == [
            {
                "conversation_id": conversation.conversation_id,
                "title": "Runtime study",
                "project_root": str(project_root.resolve()),
                "turns": [
                    {
                        "session_id": first_session,
                        "short_id": first_session[:8],
                        "turn_number": 1,
                        "user_message_preview": "Explain how the agent loop works",
                        "status": "completed",
                        "started_at": (first_run.started_at or first_run.created_at)
                        .isoformat()
                        .replace(
                            "+00:00",
                            "Z",
                        ),
                        "trace_available": True,
                    },
                    {
                        "session_id": second_session,
                        "short_id": second_session[:8],
                        "turn_number": 2,
                        "user_message_preview": "Now explain tool execution",
                        "status": "queued",
                        "started_at": second_run.created_at.isoformat().replace(
                            "+00:00",
                            "Z",
                        ),
                        "trace_available": False,
                    },
                ],
            },
        ]
        assert body["standalone_runs"][0]["session_id"] == standalone_session
        assert body["standalone_runs"][0]["trace_available"] is True


def test_rejects_session_path_traversal(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path, EventBroker())) as client:
        response = client.get("/api/sessions/..%2Foutside")
        assert response.status_code in {404, 422}


@pytest.mark.asyncio
async def test_event_stream_returns_sse_content_type(tmp_path: Path) -> None:
    app = create_app(tmp_path, EventBroker())
    response = cast(
        StreamingResponse,
        await event_stream_route(app).endpoint(connected_request(), "*"),
    )
    assert response.media_type == "text/event-stream"


@pytest.mark.asyncio
async def test_event_stream_delivers_event_after_keepalive(tmp_path: Path) -> None:
    broker = EventBroker()
    app = create_app(tmp_path, broker)
    response = cast(
        StreamingResponse,
        await event_stream_route(app).endpoint(connected_request(), "*"),
    )
    stream = cast(AsyncGenerator[str, None], response.body_iterator)

    try:
        assert await anext(stream) == ": connected\n\n"
        assert await anext(stream) == ": keepalive\n\n"

        await broker.publish(make_event())

        encoded = await asyncio.wait_for(anext(stream), timeout=0.2)
        assert encoded.startswith("event: tool.call.completed\n")
    finally:
        await stream.aclose()
