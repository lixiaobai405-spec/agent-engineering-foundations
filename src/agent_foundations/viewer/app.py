import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from agent_foundations.chat.api import ChatServices, create_chat_router
from agent_foundations.chat.repository import ConversationRepository
from agent_foundations.runtime.replay import TraceReplayError, list_sessions, load_trace
from agent_foundations.runtime.trace import TraceEvent
from agent_foundations.viewer.navigation import TraceNavigation, build_trace_navigation
from agent_foundations.viewer.stream import EventBroker, encode_sse

STATIC_DIR = Path(__file__).parent / "static"
CHAT_BUILD_DIR = STATIC_DIR / "chat"


def create_app(
    trace_dir: Path,
    broker: EventBroker | None = None,
    chat_services: ChatServices | None = None,
    *,
    chat_keepalive_seconds: float = 15.0,
) -> FastAPI:
    event_broker = broker or EventBroker()

    if chat_services is None:
        app = FastAPI(title="Agent Foundations", docs_url=None, redoc_url=None)
        _register_trace_api(app, trace_dir, event_broker, repository=None)
        _mount_trace_viewer(app, path="/")
        return app

    services = chat_services

    @asynccontextmanager
    async def chat_lifespan(_app: FastAPI) -> AsyncIterator[None]:
        await services.repository.initialize()
        await services.repository.interrupt_unfinished()
        try:
            yield
        finally:
            try:
                await services.coordinator.shutdown()
            finally:
                await services.supervisor.shutdown()

    app = FastAPI(
        title="Agent Foundations",
        docs_url=None,
        redoc_url=None,
        lifespan=chat_lifespan,
    )
    _register_trace_api(
        app,
        trace_dir,
        event_broker,
        repository=services.repository,
    )
    app.include_router(
        create_chat_router(
            chat_services,
            keepalive_seconds=chat_keepalive_seconds,
        ),
        prefix="/api/chat",
    )
    _mount_trace_viewer(app, path="/trace")
    _mount_chat_ui(app)
    return app


def _register_trace_api(
    app: FastAPI,
    trace_dir: Path,
    event_broker: EventBroker,
    *,
    repository: ConversationRepository | None,
) -> None:
    @app.post("/api/events", status_code=status.HTTP_202_ACCEPTED)
    async def receive_event(event: TraceEvent) -> None:
        await event_broker.publish(event)

    @app.get("/api/sessions")
    async def sessions() -> list[str]:
        return list_sessions(trace_dir)

    @app.get("/api/trace-navigation", response_model=TraceNavigation)
    async def trace_navigation() -> TraceNavigation:
        return await build_trace_navigation(trace_dir, repository)

    @app.get("/api/sessions/{session_id}")
    async def session_events(session_id: str) -> list[dict[str, object]]:
        if not _valid_session_id(session_id):
            raise HTTPException(status_code=404, detail="session not found")
        path = trace_dir / f"{session_id}.jsonl"
        if not path.is_file():
            raise HTTPException(status_code=404, detail="session not found")
        try:
            return [event.model_dump(mode="json") for event in load_trace(path)]
        except TraceReplayError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/events/stream")
    async def event_stream(request: Request, session_id: str = "*") -> StreamingResponse:
        async def generate() -> AsyncIterator[str]:
            subscription = event_broker.subscribe(session_id)
            next_event: asyncio.Task[TraceEvent] | None = None
            try:
                yield ": connected\n\n"
                next_event = asyncio.create_task(anext(subscription))
                while not await request.is_disconnected():
                    done, _ = await asyncio.wait((next_event,), timeout=0.05)
                    if not done:
                        yield ": keepalive\n\n"
                        continue
                    try:
                        event = next_event.result()
                    except StopAsyncIteration:
                        break
                    yield encode_sse(event)
                    next_event = asyncio.create_task(anext(subscription))
            finally:
                if next_event is not None and not next_event.done():
                    next_event.cancel()
                    with suppress(asyncio.CancelledError):
                        await next_event
                await subscription.aclose()

        return StreamingResponse(generate(), media_type="text/event-stream")


def _mount_trace_viewer(app: FastAPI, *, path: str) -> None:
    if STATIC_DIR.exists():
        if not any(getattr(route, "path", None) == "/static" for route in app.routes):
            app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get(path, include_in_schema=False)
    async def trace_index() -> FileResponse:
        index_path = STATIC_DIR / "index.html"
        if not index_path.is_file():
            raise HTTPException(status_code=404, detail="not found")
        return FileResponse(index_path)


def _mount_chat_ui(app: FastAPI) -> None:
    chat_index = CHAT_BUILD_DIR / "index.html"
    if chat_index.is_file():
        app.mount(
            "/chat-static",
            StaticFiles(directory=CHAT_BUILD_DIR),
            name="chat-static",
        )

        @app.get("/", include_in_schema=False)
        @app.get("/chat", include_in_schema=False)
        async def chat_index_route() -> FileResponse:
            return FileResponse(chat_index)

        return

    @app.get("/", include_in_schema=False)
    @app.get("/chat", include_in_schema=False)
    async def chat_missing() -> None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chat UI build is missing",
        )


def _valid_session_id(value: str) -> bool:
    return bool(value) and all(
        character.isalnum() or character in {"-", "_"}
        for character in value
    )
