import asyncio
import json
import types
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

from agent_foundations.chat.models import ChatEvent, ChatEventType, ToolActivityStatus
from agent_foundations.runtime.redaction import Redactor
from agent_foundations.runtime.trace import EventSink, TraceEvent

CONVERSATION_ID = "11111111-1111-4111-8111-111111111111"
SESSION_ID = "22222222-2222-4222-8222-222222222222"
TRACE_TIMESTAMP = datetime(2026, 8, 3, 12, 0, 0, tzinfo=UTC)


def _import_events_module() -> types.ModuleType:
    from agent_foundations.chat import events

    return events


def _make_trace_event(
    *,
    event_type: str,
    status: str = "started",
    payload: dict[str, Any] | None = None,
    summary: str = "summary",
    event_id: str = "33333333-3333-4333-8333-333333333333",
) -> TraceEvent:
    return TraceEvent(
        event_id=event_id,
        session_id=SESSION_ID,
        step_id=1,
        event_type=event_type,
        status=status,
        summary=summary,
        timestamp=TRACE_TIMESTAMP,
        payload=payload or {},
    )


def _make_chat_event(
    *,
    event_type: ChatEventType = ChatEventType.TOOL_REQUESTED,
    data: dict[str, Any] | None = None,
) -> ChatEvent:
    return ChatEvent(
        event_id="44444444-4444-4444-8444-444444444444",
        conversation_id=CONVERSATION_ID,
        session_id=SESSION_ID,
        type=event_type,
        occurred_at=TRACE_TIMESTAMP,
        data=data or {"status": "started"},
    )


async def _wait_for_next(subscription: AsyncGenerator[ChatEvent, None]) -> ChatEvent:
    return await anext(subscription)


@pytest.fixture
def redactor(tmp_path: Path) -> Redactor:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "README.md").write_text("readme", encoding="utf-8")
    return Redactor(project_root, secrets=("secret-token",))


@pytest.fixture
def projector(redactor: Redactor) -> Any:
    events = _import_events_module()
    return events.TraceToChatProjector(
        conversation_id=CONVERSATION_ID,
        redactor=redactor,
        project_root=Path.cwd(),
        max_summary_chars=240,
    )


def test_trace_to_chat_projects_safe_chat_event(
    projector: Any,
    tmp_path: Path,
    redactor: Redactor,
) -> None:
    project_root = tmp_path / "project"
    trace_event = _make_trace_event(
        event_type="tool.call.requested",
        status="started",
        summary="Calling read_file",
        payload={
            "tool_call_id": "call-1",
            "name": "read_file",
            "arguments": {
                "path": str(project_root / "README.md"),
                "token": "secret-token",
            },
            "unrelated": {
                "authorization": "Bearer hidden-value",
            },
        },
    )

    chat_event = projector.project(trace_event)

    assert isinstance(chat_event, ChatEvent)
    assert chat_event.type is ChatEventType.TOOL_REQUESTED
    assert chat_event.conversation_id == CONVERSATION_ID
    assert chat_event.session_id == SESSION_ID
    assert chat_event.event_id == trace_event.event_id
    assert chat_event.occurred_at == trace_event.timestamp
    serialized = chat_event.model_dump_json()
    assert "secret-token" not in serialized
    assert str(tmp_path) not in serialized
    assert str(project_root) not in serialized
    assert "hidden-value" not in serialized
    assert '"arguments":' not in serialized
    assert "unrelated" not in serialized
    assert chat_event.data["tool_call_id"] == "call-1"
    assert chat_event.data["arguments_summary"] == "README.md"
    assert set(chat_event.data.keys()) <= {
        "tool_call_id",
        "name",
        "arguments_summary",
        "result_summary",
        "status",
    }


@pytest.mark.parametrize(
    ("trace_type", "chat_type"),
    [
        ("model.request.started", ChatEventType.MODEL_REQUESTED),
        ("tool.call.requested", ChatEventType.TOOL_REQUESTED),
        ("tool.call.completed", ChatEventType.TOOL_COMPLETED),
        ("tool.call.failed", ChatEventType.TOOL_FAILED),
    ],
)
def test_trace_to_chat_maps_supported_trace_events(
    projector: Any,
    trace_type: str,
    chat_type: ChatEventType,
) -> None:
    payload: dict[str, Any] = {"status": "started"}
    if trace_type.startswith("tool.call"):
        payload["name"] = "read_file"
        payload["tool_call_id"] = "call-1"
    if trace_type == "tool.call.requested":
        payload["arguments"] = {"path": "src"}
    if trace_type in {"tool.call.completed", "tool.call.failed"}:
        payload["result"] = {"success": True, "content": "ok"}

    chat_event = projector.project(
        _make_trace_event(event_type=trace_type, status="completed", payload=payload),
    )

    assert chat_event is not None
    assert chat_event.type is chat_type


@pytest.mark.parametrize(
    "trace_type",
    [
        "session.started",
        "user.message",
        "model.response.received",
        "tool.call.validated",
        "agent.final_answer",
        "session.completed",
        "session.failed",
        "agent.loop.stopped",
        "unknown.event",
    ],
)
def test_trace_to_chat_ignores_unsupported_trace_events(
    projector: Any,
    trace_type: str,
) -> None:
    assert projector.project(_make_trace_event(event_type=trace_type)) is None


def test_trace_to_chat_data_uses_minimal_whitelist(projector: Any) -> None:
    model_event = projector.project(
        _make_trace_event(
            event_type="model.request.started",
            status="started",
            payload={
                "context": [{"role": "user", "content": "secret"}],
                "tools": [{"name": "read_file"}],
                "raw_response": {"token": "hidden"},
            },
        ),
    )
    assert model_event is not None
    assert model_event.data == {"status": "started"}

    requested = projector.project(
        _make_trace_event(
            event_type="tool.call.requested",
            status="started",
            payload={
                "tool_call_id": "call-1",
                "name": "read_file",
                "arguments": {"path": "src/auth.py"},
                "context": "hidden",
            },
        ),
    )
    assert requested is not None
    assert set(requested.data.keys()) == {
        "tool_call_id",
        "name",
        "arguments_summary",
        "status",
    }
    assert "context" not in requested.data
    assert "arguments" not in requested.data

    completed = projector.project(
        _make_trace_event(
            event_type="tool.call.completed",
            status="completed",
            payload={
                "tool_call_id": "call-1",
                "name": "read_file",
                "result": {
                    "success": True,
                    "content": "file contents",
                    "metadata": {"returned_lines": 12, "traceback": "hidden stack"},
                },
            },
        ),
    )
    assert completed is not None
    assert set(completed.data.keys()) == {
        "tool_call_id",
        "name",
        "result_summary",
        "status",
    }
    assert completed.data["result_summary"] == "12 lines"
    assert "file contents" not in completed.model_dump_json()
    assert "result" not in completed.data


def test_trace_to_chat_redacts_before_selecting_summary_fields(
    tmp_path: Path,
) -> None:
    events = _import_events_module()
    project_root = tmp_path / "project"
    project_root.mkdir(exist_ok=True)
    secret = "secret-token"
    redactor_with_secret = Redactor(project_root, secrets=(secret,))
    projector = events.TraceToChatProjector(
        conversation_id=CONVERSATION_ID,
        redactor=redactor_with_secret,
        project_root=project_root,
        max_summary_chars=240,
    )
    absolute_path = str(project_root / "src" / "auth.py")
    trace_event = _make_trace_event(
        event_type="tool.call.requested",
        status="Bearer secret-token",
        payload={
            "tool_call_id": "call-1",
            "name": "read_file",
            "arguments": {
                "path": absolute_path,
                "token": secret,
                "password": "plain-password",
                "authorization": "Bearer hidden-value",
            },
        },
    )

    chat_event = projector.project(trace_event)

    assert chat_event is not None
    summary = chat_event.data["arguments_summary"]
    assert secret not in summary
    assert absolute_path not in summary
    assert str(project_root) not in summary
    assert "hidden-value" not in summary
    assert summary == "src/auth.py"
    assert chat_event.data["status"] == "Bearer [REDACTED]"


@pytest.mark.parametrize(
    ("name", "result", "expected", "forbidden"),
    [
        (
            "list_directory",
            {
                "success": True,
                "content": json.dumps(
                    {"path": ".", "entries": [{"name": "secret.py"}], "truncated": False},
                ),
                "metadata": {},
            },
            "1 entry",
            "secret.py",
        ),
        (
            "search_text",
            {
                "success": True,
                "content": json.dumps(
                    {
                        "query": "secret-token",
                        "matches": [{"path": "auth.py", "line": "secret-token"}],
                        "scanned_files": 3,
                    },
                ),
                "metadata": {},
            },
            "1 match in 3 files",
            "auth.py",
        ),
    ],
)
def test_trace_to_chat_result_summaries_store_counts_not_content(
    projector: Any,
    name: str,
    result: dict[str, Any],
    expected: str,
    forbidden: str,
) -> None:
    projected = projector.project(
        _make_trace_event(
            event_type="tool.call.completed",
            status="completed",
            payload={"tool_call_id": "call-1", "name": name, "result": result},
        ),
    )

    assert projected is not None
    assert projected.data["result_summary"] == expected
    assert forbidden not in projected.model_dump_json()
    assert "secret-token" not in projected.model_dump_json()


def test_trace_to_chat_external_path_is_not_persisted(
    projector: Any,
    tmp_path: Path,
) -> None:
    projected = projector.project(
        _make_trace_event(
            event_type="tool.call.requested",
            payload={
                "tool_call_id": "call-1",
                "name": "read_file",
                "arguments": {"path": str(tmp_path.parent / "outside.txt")},
            },
        ),
    )

    assert projected is not None
    assert projected.data["arguments_summary"] == "[external path]"
    assert str(tmp_path.parent) not in projected.model_dump_json()


def test_trace_to_chat_summary_respects_length_limit(redactor: Redactor) -> None:
    events = _import_events_module()
    projector = events.TraceToChatProjector(
        conversation_id=CONVERSATION_ID,
        redactor=redactor,
        project_root=Path.cwd(),
        max_summary_chars=20,
    )
    long_arguments = {"query": "x" * 100}
    chat_event = projector.project(
        _make_trace_event(
            event_type="tool.call.requested",
            status="started",
            payload={
                "tool_call_id": "call-1",
                "name": "search_text",
                "arguments": long_arguments,
            },
        ),
    )
    assert chat_event is not None
    summary = chat_event.data["arguments_summary"]
    assert len(summary) <= 20
    assert summary.endswith("…")
    assert not summary.endswith("...")
    assert "……" not in summary

    short_event = projector.project(
        _make_trace_event(
            event_type="tool.call.requested",
            status="started",
            payload={
                "tool_call_id": "call-1",
                "name": "read_file",
                "arguments": {"path": "src"},
            },
        ),
    )
    assert short_event is not None
    assert len(short_event.data["arguments_summary"]) <= 20
    assert not short_event.data["arguments_summary"].endswith("…")

    tiny_projector = events.TraceToChatProjector(
        conversation_id=CONVERSATION_ID,
        redactor=redactor,
        project_root=Path.cwd(),
        max_summary_chars=1,
    )
    tiny_event = tiny_projector.project(
        _make_trace_event(
            event_type="tool.call.completed",
            status="completed",
            payload={
                "tool_call_id": "call-1",
                "name": "read_file",
                "result": {
                    "success": True,
                    "content": "never persist this",
                    "metadata": {"returned_lines": 12},
                },
            },
        ),
    )
    assert tiny_event is not None
    assert tiny_event.data["result_summary"] == "…"


def test_truncate_summary_avoids_consecutive_ellipsis() -> None:
    events = _import_events_module()
    truncate = events._truncate_summary

    assert truncate("hel…oooooo", 5) == "hel…"
    assert "……" not in truncate("hel…oooooo", 5)
    assert len(truncate("hel…oooooo", 5)) <= 5

    assert truncate("ab…cde", 4) == "ab…"
    assert "……" not in truncate("ab…cde", 4)

    assert truncate("prefix…", 8) == "prefix…"
    assert truncate("………x", 3) == "…"


def test_trace_to_chat_summary_avoids_double_ellipsis_in_projection(
    redactor: Redactor,
) -> None:
    events = _import_events_module()
    projector = events.TraceToChatProjector(
        conversation_id=CONVERSATION_ID,
        redactor=redactor,
        project_root=Path.cwd(),
        max_summary_chars=6,
    )
    chat_event = projector.project(
        _make_trace_event(
            event_type="tool.call.requested",
            status="started",
            payload={
                "tool_call_id": "call-1",
                "name": "search_text",
                "arguments": {"query": "hel…" + "o" * 20},
            },
        ),
    )

    assert chat_event is not None
    summary = chat_event.data["arguments_summary"]
    assert summary.endswith("…")
    assert "……" not in summary
    assert len(summary) <= 6


def test_trace_to_chat_rejects_non_positive_summary_limit(redactor: Redactor) -> None:
    events = _import_events_module()
    with pytest.raises(ValueError, match="max_summary_chars"):
        events.TraceToChatProjector(
            conversation_id=CONVERSATION_ID,
            redactor=redactor,
            project_root=Path.cwd(),
            max_summary_chars=0,
        )
    with pytest.raises(ValueError, match="max_summary_chars"):
        events.TraceToChatProjector(
            conversation_id=CONVERSATION_ID,
            redactor=redactor,
            project_root=Path.cwd(),
            max_summary_chars=-1,
        )


@pytest.mark.asyncio
async def test_chat_projection_sink_publishes_projected_events_only(
    projector: Any,
) -> None:
    events = _import_events_module()
    broker = AsyncMock()
    repository = AsyncMock()
    repository.upsert_tool_activity.side_effect = lambda activity: activity
    sink = events.ChatProjectionSink(
        projector=projector,
        repository=repository,
        broker=broker,
    )
    trace_event = _make_trace_event(
        event_type="tool.call.requested",
        payload={
            "tool_call_id": "call-1",
            "name": "read_file",
            "arguments": {"path": "README.md"},
        },
    )

    await sink.emit(trace_event)

    broker.publish.assert_awaited_once()
    published = broker.publish.await_args.args[0]
    assert isinstance(published, ChatEvent)
    assert published.type is ChatEventType.TOOL_REQUESTED
    persisted = repository.upsert_tool_activity.await_args.args[0]
    assert persisted.tool_call_id == "call-1"
    assert persisted.status is ToolActivityStatus.RUNNING

    broker.publish.reset_mock()
    await sink.emit(_make_trace_event(event_type="session.started"))
    broker.publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_chat_projection_sink_does_not_publish_same_trace_event_twice(
    projector: Any,
) -> None:
    events = _import_events_module()
    broker = AsyncMock()
    repository = AsyncMock()
    repository.upsert_tool_activity.side_effect = lambda activity: activity
    sink = events.ChatProjectionSink(
        projector=projector,
        repository=repository,
        broker=broker,
    )
    trace_event = _make_trace_event(
        event_type="tool.call.requested",
        payload={
            "tool_call_id": "call-1",
            "name": "read_file",
            "arguments": {"path": "README.md"},
        },
    )

    await sink.emit(trace_event)
    await sink.emit(trace_event)

    broker.publish.assert_awaited_once()
    repository.upsert_tool_activity.assert_awaited_once()


def test_chat_projection_sink_satisfies_event_sink_protocol() -> None:
    events = _import_events_module()
    broker = events.ChatEventBroker()
    sink = events.ChatProjectionSink(
        projector=AsyncMock(),
        repository=AsyncMock(),
        broker=broker,
    )
    assert isinstance(sink, EventSink)


@pytest.mark.asyncio
async def test_chat_projection_sink_swallows_non_cancel_projection_errors(
    projector: Any,
) -> None:
    events = _import_events_module()
    broker = AsyncMock()
    broker.publish.side_effect = RuntimeError("broker failure")
    repository = AsyncMock()
    repository.upsert_tool_activity.side_effect = lambda activity: activity
    sink = events.ChatProjectionSink(
        projector=projector,
        repository=repository,
        broker=broker,
    )

    await sink.emit(
        _make_trace_event(
            event_type="tool.call.requested",
            payload={
                "tool_call_id": "call-1",
                "name": "read_file",
                "arguments": {"path": "README.md"},
            },
        ),
    )


@pytest.mark.asyncio
async def test_chat_projection_sink_persists_before_publish(projector: Any) -> None:
    events = _import_events_module()
    call_order: list[str] = []
    repository = AsyncMock()
    broker = AsyncMock()

    async def persist(activity: Any) -> Any:
        call_order.append("persist")
        return activity

    async def publish(event: Any) -> None:
        call_order.append("publish")

    repository.upsert_tool_activity.side_effect = persist
    broker.publish.side_effect = publish
    sink = events.ChatProjectionSink(projector, repository, broker)

    await sink.emit(
        _make_trace_event(
            event_type="tool.call.requested",
            payload={
                "tool_call_id": "call-1",
                "name": "read_file",
                "arguments": {"path": "README.md"},
            },
        ),
    )

    assert call_order == ["persist", "publish"]


@pytest.mark.asyncio
async def test_chat_projection_sink_reraises_cancellation(projector: Any) -> None:
    events = _import_events_module()
    repository = AsyncMock()
    repository.upsert_tool_activity.side_effect = asyncio.CancelledError
    sink = events.ChatProjectionSink(projector, repository, AsyncMock())

    with pytest.raises(asyncio.CancelledError):
        await sink.emit(
            _make_trace_event(
                event_type="tool.call.requested",
                payload={
                    "tool_call_id": "call-1",
                    "name": "read_file",
                    "arguments": {"path": "README.md"},
                },
            ),
        )


@pytest.mark.asyncio
async def test_chat_event_broker_isolates_conversations() -> None:
    events = _import_events_module()
    broker = events.ChatEventBroker()
    other_conversation = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    first_subscription = broker.subscribe(CONVERSATION_ID)
    second_subscription = broker.subscribe(other_conversation)
    first_task = asyncio.create_task(_wait_for_next(first_subscription))
    second_task = asyncio.create_task(_wait_for_next(second_subscription))
    await asyncio.sleep(0)

    await broker.publish(_make_chat_event())
    await broker.publish(
        ChatEvent(
            event_id="55555555-5555-4555-8555-555555555555",
            conversation_id=other_conversation,
            session_id=SESSION_ID,
            type=ChatEventType.MODEL_REQUESTED,
            occurred_at=TRACE_TIMESTAMP,
            data={"status": "started"},
        ),
    )

    first_event = await asyncio.wait_for(first_task, timeout=1)
    second_event = await asyncio.wait_for(second_task, timeout=1)
    assert first_event.conversation_id == CONVERSATION_ID
    assert second_event.conversation_id == other_conversation

    await first_subscription.aclose()
    await second_subscription.aclose()


@pytest.mark.asyncio
async def test_chat_event_broker_broadcasts_to_multiple_subscribers() -> None:
    events = _import_events_module()
    broker = events.ChatEventBroker()
    first_subscription = broker.subscribe(CONVERSATION_ID)
    second_subscription = broker.subscribe(CONVERSATION_ID)
    first_tasks = [
        asyncio.create_task(_wait_for_next(first_subscription)),
        asyncio.create_task(_wait_for_next(second_subscription)),
    ]
    await asyncio.sleep(0)
    await broker.publish(_make_chat_event())
    received = await asyncio.gather(*first_tasks)
    assert all(event.type is ChatEventType.TOOL_REQUESTED for event in received)

    await first_subscription.aclose()
    await second_subscription.aclose()


@pytest.mark.asyncio
async def test_chat_event_broker_preserves_order_for_subscriber() -> None:
    events = _import_events_module()
    broker = events.ChatEventBroker()
    subscription = broker.subscribe(CONVERSATION_ID)
    first_task = asyncio.create_task(_wait_for_next(subscription))
    await asyncio.sleep(0)
    await broker.publish(_make_chat_event(event_type=ChatEventType.MODEL_REQUESTED))
    assert (await first_task).type is ChatEventType.MODEL_REQUESTED

    second_task = asyncio.create_task(_wait_for_next(subscription))
    await asyncio.sleep(0)
    await broker.publish(_make_chat_event(event_type=ChatEventType.TOOL_COMPLETED))
    assert (await second_task).type is ChatEventType.TOOL_COMPLETED

    await subscription.aclose()


@pytest.mark.asyncio
async def test_chat_event_broker_publish_without_subscribers_is_noop() -> None:
    events = _import_events_module()
    broker = events.ChatEventBroker()
    await broker.publish(_make_chat_event())
    assert broker._subscribers == {}


@pytest.mark.asyncio
async def test_chat_event_broker_cleans_up_closed_subscriptions() -> None:
    events = _import_events_module()
    broker = events.ChatEventBroker()
    subscription = broker.subscribe(CONVERSATION_ID)
    registration_task = asyncio.create_task(_wait_for_next(subscription))
    await asyncio.sleep(0)
    assert CONVERSATION_ID in broker._subscribers

    await broker.publish(_make_chat_event())
    await registration_task
    await subscription.aclose()
    assert CONVERSATION_ID not in broker._subscribers


@pytest.mark.asyncio
async def test_chat_event_broker_slow_subscriber_drops_oldest_without_blocking_publish() -> None:
    events = _import_events_module()
    broker = events.ChatEventBroker(queue_size=2)
    slow_queue: asyncio.Queue[ChatEvent] = asyncio.Queue(maxsize=2)
    broker._subscribers[CONVERSATION_ID] = {slow_queue}

    event_one = _make_chat_event(
        event_type=ChatEventType.MODEL_REQUESTED,
        data={"status": "one"},
    )
    event_two = _make_chat_event(
        event_type=ChatEventType.TOOL_REQUESTED,
        data={"status": "two"},
    )
    event_three = _make_chat_event(
        event_type=ChatEventType.TOOL_COMPLETED,
        data={"status": "three"},
    )

    await asyncio.wait_for(broker.publish(event_one), timeout=0.05)
    await asyncio.wait_for(broker.publish(event_two), timeout=0.05)
    await asyncio.wait_for(broker.publish(event_three), timeout=0.05)

    assert slow_queue.get_nowait().data["status"] == "two"
    assert slow_queue.get_nowait().data["status"] == "three"
    assert slow_queue.empty()


@pytest.mark.asyncio
async def test_chat_event_broker_keeps_independent_queues_for_subscribers() -> None:
    events = _import_events_module()
    broker = events.ChatEventBroker(queue_size=2)
    event_one = _make_chat_event(
        event_type=ChatEventType.MODEL_REQUESTED,
        data={"status": "one"},
    )
    event_two = _make_chat_event(
        event_type=ChatEventType.TOOL_REQUESTED,
        data={"status": "two"},
    )
    event_three = _make_chat_event(
        event_type=ChatEventType.TOOL_COMPLETED,
        data={"status": "three"},
    )

    fast_subscription = broker.subscribe(CONVERSATION_ID)
    first_task = asyncio.create_task(_wait_for_next(fast_subscription))
    await asyncio.sleep(0)
    await broker.publish(event_one)
    assert (await first_task).data["status"] == "one"

    second_task = asyncio.create_task(_wait_for_next(fast_subscription))
    await asyncio.sleep(0)
    await broker.publish(event_two)
    assert (await second_task).data["status"] == "two"

    third_task = asyncio.create_task(_wait_for_next(fast_subscription))
    await asyncio.sleep(0)
    await broker.publish(event_three)
    assert (await third_task).data["status"] == "three"

    await fast_subscription.aclose()


def test_chat_event_broker_queue_size_validation() -> None:
    events = _import_events_module()
    events.ChatEventBroker(queue_size=1)
    with pytest.raises(ValueError, match="queue_size"):
        events.ChatEventBroker(queue_size=0)
    with pytest.raises(ValueError, match="queue_size"):
        events.ChatEventBroker(queue_size=-3)


def test_encode_chat_sse_formats_event_and_json_data() -> None:
    events = _import_events_module()
    chat_event = ChatEvent(
        event_id="66666666-6666-4666-8666-666666666666",
        conversation_id=CONVERSATION_ID,
        session_id=SESSION_ID,
        type=ChatEventType.TOOL_REQUESTED,
        occurred_at=TRACE_TIMESTAMP,
        data={"name": "read_file", "status": "started", "note": "line1\nline2"},
    )

    encoded = events.encode_chat_sse(chat_event)

    assert encoded.startswith("event: tool.requested\n")
    lines = encoded.splitlines()
    assert lines[0] == "event: tool.requested"
    assert lines[1].startswith("data: ")
    assert len([line for line in lines if line.startswith("event:")]) == 1
    assert len([line for line in lines if line.startswith("data:")]) == 1
    assert encoded.endswith("\n\n")
    payload = json.loads(lines[1].removeprefix("data: "))
    assert payload == chat_event.model_dump(mode="json")
    assert "event_type" not in payload
    assert "\\n" in lines[1] or "\n" not in lines[1].removeprefix("data: ")
