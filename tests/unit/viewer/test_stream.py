import asyncio
import json
from collections.abc import AsyncGenerator
from pathlib import Path

import httpx
import pytest

from agent_foundations.runtime.redaction import Redactor
from agent_foundations.runtime.sinks import LiveEventSink
from agent_foundations.runtime.trace import TraceEvent
from agent_foundations.viewer.stream import EventBroker, encode_sse


def make_event(
    *,
    session_id: str = "session-1",
    step_id: int = 1,
) -> TraceEvent:
    return TraceEvent(
        session_id=session_id,
        step_id=step_id,
        event_type="test.event",
        status="completed",
        summary=str(step_id),
    )


async def wait_for_next(subscription: AsyncGenerator[TraceEvent, None]) -> TraceEvent:
    return await anext(subscription)


@pytest.mark.asyncio
async def test_broker_preserves_order_for_subscriber() -> None:
    broker = EventBroker()
    subscription = broker.subscribe("session-1")
    first_task = asyncio.create_task(wait_for_next(subscription))
    await asyncio.sleep(0)
    await broker.publish(make_event(step_id=1))
    assert (await first_task).step_id == 1

    second_task = asyncio.create_task(wait_for_next(subscription))
    await asyncio.sleep(0)
    await broker.publish(make_event(step_id=2))
    assert (await second_task).step_id == 2

    await subscription.aclose()


@pytest.mark.asyncio
async def test_broker_broadcasts_same_ordered_events_to_multiple_subscribers() -> None:
    broker = EventBroker()
    first_subscription = broker.subscribe("session-1")
    second_subscription = broker.subscribe("session-1")

    first_tasks = [
        asyncio.create_task(wait_for_next(first_subscription)),
        asyncio.create_task(wait_for_next(second_subscription)),
    ]
    await asyncio.sleep(0)
    await broker.publish(make_event(step_id=1))
    first_events = await asyncio.gather(*first_tasks)
    assert [event.step_id for event in first_events] == [1, 1]

    second_tasks = [
        asyncio.create_task(wait_for_next(first_subscription)),
        asyncio.create_task(wait_for_next(second_subscription)),
    ]
    await asyncio.sleep(0)
    await broker.publish(make_event(step_id=2))
    second_events = await asyncio.gather(*second_tasks)
    assert [event.step_id for event in second_events] == [2, 2]

    await first_subscription.aclose()
    await second_subscription.aclose()


@pytest.mark.asyncio
async def test_broker_delivers_to_session_and_global_subscribers() -> None:
    broker = EventBroker()
    session_subscription = broker.subscribe("session-1")
    global_subscription = broker.subscribe("*")
    other_session_subscription = broker.subscribe("session-2")

    session_task = asyncio.create_task(wait_for_next(session_subscription))
    global_task = asyncio.create_task(wait_for_next(global_subscription))
    other_session_task = asyncio.create_task(wait_for_next(other_session_subscription))
    await asyncio.sleep(0)

    await broker.publish(make_event(session_id="session-1", step_id=1))

    session_event = await session_task
    global_event = await global_task
    assert session_event.step_id == 1
    assert global_event.step_id == 1

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(other_session_task, timeout=0.05)

    await session_subscription.aclose()
    await global_subscription.aclose()
    await other_session_subscription.aclose()


@pytest.mark.asyncio
async def test_broker_removes_subscriber_queue_on_close() -> None:
    broker = EventBroker()
    subscription = broker.subscribe("session-1")
    task = asyncio.create_task(wait_for_next(subscription))
    await asyncio.sleep(0)
    assert "session-1" in broker._subscribers
    assert len(broker._subscribers["session-1"]) == 1

    await broker.publish(make_event(step_id=1))
    await task

    await subscription.aclose()
    assert "session-1" not in broker._subscribers


@pytest.mark.asyncio
async def test_publish_does_not_create_empty_subscriber_buckets() -> None:
    broker = EventBroker()
    await broker.publish(make_event(session_id="session-a"))
    await broker.publish(make_event(session_id="session-b"))
    await broker.publish(make_event(session_id="session-c"))
    assert broker._subscribers == {}


def test_sse_encoding_has_event_and_data_fields() -> None:
    encoded = encode_sse(make_event(step_id=1))

    assert encoded.startswith("event: test.event\n")
    assert "data: {" in encoded
    assert encoded.endswith("\n\n")
    assert json.loads(encoded.split("data: ", 1)[1].strip())["step_id"] == 1


@pytest.mark.parametrize(
    "viewer_url",
    [
        "http://localhost:8765",
        "http://0.0.0.0:8765",
        "http://[::1]:8765",
        "http://192.168.1.1:8765",
        "http://8.8.8.8:8765",
        "http://127.0.0.1.evil.example",
        "ftp://127.0.0.1:8765",
        "not-a-url",
    ],
)
def test_live_sink_rejects_non_loopback_viewer_urls(viewer_url: str) -> None:
    with pytest.raises(ValueError, match="viewer_url"):
        LiveEventSink(viewer_url, Redactor(Path(".")))


@pytest.mark.asyncio
async def test_live_sink_does_not_follow_redirects_to_remote() -> None:
    requested_hosts: list[str] = []

    def transport(request: httpx.Request) -> httpx.Response:
        requested_hosts.append(request.url.host or "")
        return httpx.Response(
            302,
            headers={"Location": "http://evil.example/api/events"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        sink = LiveEventSink("http://127.0.0.1:8765", Redactor(Path(".")), client=client)
        await sink.emit(make_event(step_id=1))

    assert requested_hosts == ["127.0.0.1"]


@pytest.mark.asyncio
async def test_live_sink_is_best_effort_when_viewer_is_offline() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(503))
    async with httpx.AsyncClient(transport=transport) as client:
        sink = LiveEventSink("http://127.0.0.1:8765", Redactor(Path(".")), client=client)
        await sink.emit(make_event(step_id=1))


@pytest.mark.asyncio
async def test_live_sink_is_best_effort_on_transport_timeout() -> None:
    def slow_response(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    transport = httpx.MockTransport(slow_response)
    async with httpx.AsyncClient(transport=transport) as client:
        sink = LiveEventSink("http://127.0.0.1:8765", Redactor(Path(".")), client=client)
        await sink.emit(make_event(step_id=1))


@pytest.mark.asyncio
async def test_live_sink_redacts_before_transport(tmp_path: Path) -> None:
    received: dict[str, object] = {}

    def capture(request: httpx.Request) -> httpx.Response:
        received.update(json.loads(request.content))
        return httpx.Response(202)

    event = make_event(step_id=1).model_copy(
        update={"payload": {"api_key": "secret-value"}},
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(capture)) as client:
        sink = LiveEventSink(
            "http://127.0.0.1:8765",
            Redactor(tmp_path, secrets=("secret-value",)),
            client=client,
        )
        await sink.emit(event)

    assert received["payload"] == {"api_key": "[REDACTED]"}
