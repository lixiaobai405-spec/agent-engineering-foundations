import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from agent_foundations.domain.messages import Message, Role
from agent_foundations.runtime.session import AgentSession, SessionStatus
from agent_foundations.runtime.trace import (
    EventSink,
    InMemoryEventSink,
    NoOpEventSink,
    TraceEvent,
)

FIXTURE_SESSION_ID = "22222222-2222-4222-8222-222222222222"


def test_session_identity_root_and_status(tmp_path: Path) -> None:
    session = AgentSession(
        root=tmp_path,
        messages=[Message(role=Role.USER, content="inspect")],
    )

    # Root is resolved to an absolute directory
    assert session.root == tmp_path.resolve()
    assert session.root.is_absolute()

    # session_id is a valid UUID
    uuid.UUID(session.session_id)

    # Different sessions have different IDs
    session2 = AgentSession(root=tmp_path)
    assert session.session_id != session2.session_id

    # Default status
    assert session.status == SessionStatus.CREATED

    # Status transitions are allowed (session is mutable)
    session.status = SessionStatus.RUNNING
    assert session.status == SessionStatus.RUNNING
    session.status = SessionStatus.COMPLETED
    assert session.status == SessionStatus.COMPLETED

    # Root that is a file, not a directory, is rejected
    file_path = tmp_path / "file.txt"
    file_path.write_text("not a directory", encoding="utf-8")
    with pytest.raises(ValueError, match="directory"):
        AgentSession(root=file_path)


def test_agent_session_preserves_valid_session_id(tmp_path: Path) -> None:
    session = AgentSession(root=tmp_path, session_id=FIXTURE_SESSION_ID)
    assert session.session_id == FIXTURE_SESSION_ID
    assert session.root == tmp_path.resolve()


def test_agent_session_rejects_invalid_session_id(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="session_id"):
        AgentSession(root=tmp_path, session_id="not-a-uuid")


def test_agent_session_auto_generates_valid_uuid(tmp_path: Path) -> None:
    session = AgentSession(root=tmp_path)
    uuid.UUID(session.session_id)
    assert session.root.is_absolute()


def test_trace_event_identity_and_timestamp() -> None:
    event = TraceEvent(
        session_id="s1",
        step_id=0,
        event_type="session.started",
        status="started",
        summary="Session started",
    )

    # event_id is a valid UUID
    uuid.UUID(event.event_id)

    # Different events have different IDs
    event2 = TraceEvent(
        session_id="s1",
        step_id=0,
        event_type="other",
        status="ok",
        summary="another",
    )
    assert event.event_id != event2.event_id

    # timestamp carries UTC timezone
    assert event.timestamp.tzinfo is not None
    assert event.timestamp.utcoffset() is not None


def test_trace_event_payload_deeply_immutable() -> None:
    event = TraceEvent(
        session_id="s1",
        step_id=0,
        event_type="session.started",
        status="started",
        summary="Session started",
        payload={"arguments": {"tags": ["safe"]}},
    )

    # Public type is Mapping, runtime instance is FrozenJSON (not plain dict)
    assert isinstance(event.payload, Mapping)
    assert not isinstance(event.payload, dict)

    # Nested mutation is rejected
    payload: Any = event.payload
    with pytest.raises(TypeError):
        payload["arguments"]["tags"][0] = "mutated"


def test_trace_event_serializes_payload_to_plain_json() -> None:
    event = TraceEvent(
        session_id="s1",
        step_id=0,
        event_type="session.started",
        status="started",
        summary="Session started",
        payload={"arguments": {"tags": ["safe"]}},
    )

    dumped = event.model_dump(mode="json")

    assert dumped["payload"] == {"arguments": {"tags": ["safe"]}}
    assert isinstance(dumped["payload"], dict)
    assert isinstance(dumped["payload"]["arguments"]["tags"], list)


def test_trace_event_rejects_non_json_payload() -> None:
    # bytes are not JSON-compatible
    with pytest.raises(ValidationError):
        TraceEvent(
            session_id="s1",
            step_id=0,
            event_type="t",
            status="ok",
            summary="x",
            payload={"bad": b"bytes"},
        )

    # sets are not JSON-compatible
    with pytest.raises(ValidationError):
        TraceEvent(
            session_id="s1",
            step_id=0,
            event_type="t",
            status="ok",
            summary="x",
            payload={"bad": {1, 2}},
        )

    # NaN is not finite JSON
    with pytest.raises(ValidationError):
        TraceEvent(
            session_id="s1",
            step_id=0,
            event_type="t",
            status="ok",
            summary="x",
            payload={"bad": float("nan")},
        )


@pytest.mark.asyncio
async def test_in_memory_event_sink_stores_events_in_order() -> None:
    sink = InMemoryEventSink()
    assert isinstance(sink, EventSink)

    event1 = TraceEvent(
        session_id="s1", step_id=0, event_type="t1", status="ok", summary="first",
    )
    event2 = TraceEvent(
        session_id="s1", step_id=1, event_type="t2", status="ok", summary="second",
    )

    await sink.emit(event1)
    await sink.emit(event2)

    assert sink.events == [event1, event2]


@pytest.mark.asyncio
async def test_noop_event_sink_discards_events() -> None:
    sink = NoOpEventSink()
    assert isinstance(sink, EventSink)

    event = TraceEvent(
        session_id="s1", step_id=0, event_type="t", status="ok", summary="x",
    )
    # NoOpEventSink accepts events without storing state — verifies by not raising
    await sink.emit(event)


# ── TraceEvent regression tests ──────────────────────────────────────────


@pytest.mark.parametrize(
    "event_type",
    [
        "session.started",
        "model.request.started",
        "tool.call.completed",
    ],
)
def test_trace_event_accepts_stable_event_types(event_type: str) -> None:
    event = TraceEvent(
        session_id="s1",
        step_id=0,
        event_type=event_type,
        status="ok",
        summary="x",
    )
    assert event.event_type == event_type


@pytest.mark.parametrize(
    "event_type",
    [
        "safe\nid: injected",
        "safe\rid: injected",
        "",
        "has space",
        "has/slash",
    ],
)
def test_trace_event_rejects_unsafe_event_types(event_type: str) -> None:
    with pytest.raises(ValidationError):
        TraceEvent(
            session_id="s1",
            step_id=0,
            event_type=event_type,
            status="ok",
            summary="x",
        )


def test_trace_event_accepts_mapping_as_payload() -> None:
    """TraceEvent must accept any collections.abc.Mapping and freeze it."""
    from types import MappingProxyType

    event = TraceEvent(
        session_id="s1",
        step_id=0,
        event_type="t",
        status="ok",
        summary="x",
        payload=MappingProxyType({"key": "value"}),
    )
    assert isinstance(event.payload, Mapping)
    assert not isinstance(event.payload, dict)
    assert event.payload["key"] == "value"


def test_model_copy_revalidates() -> None:
    """model_copy(update=...) must re-enter validation."""
    event = TraceEvent(
        session_id="s1",
        step_id=0,
        event_type="t",
        status="ok",
        summary="x",
        payload={"items": ["a", "b"]},
    )

    # Legal update: result is still deeply immutable
    updated = event.model_copy(update={"summary": "updated"})
    assert updated.summary == "updated"
    assert isinstance(updated.payload, Mapping)
    assert not isinstance(updated.payload, dict)
    with pytest.raises(TypeError):
        updated.payload["items"][0] = "mutated"

    # step_id=-1 must be rejected
    with pytest.raises(ValidationError):
        event.model_copy(update={"step_id": -1})

    # Non-JSON payload via model_copy must be rejected
    with pytest.raises(ValidationError):
        event.model_copy(update={"payload": {"bad": b"bytes"}})
    with pytest.raises(ValidationError):
        event.model_copy(update={"payload": {"bad": {1, 2}}})
    with pytest.raises(ValidationError):
        event.model_copy(update={"payload": {"bad": float("nan")}})


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_duration_ms_rejects_non_finite_values(bad: float) -> None:
    with pytest.raises(ValidationError):
        TraceEvent(
            session_id="s1",
            step_id=0,
            event_type="t",
            status="ok",
            summary="x",
            duration_ms=bad,
        )


def test_timestamp_rejects_naive_and_normalizes_to_utc() -> None:
    from datetime import datetime, timedelta, timezone

    # Naive datetime is rejected
    with pytest.raises(ValidationError):
        TraceEvent(
            session_id="s1",
            step_id=0,
            event_type="t",
            status="ok",
            summary="x",
            timestamp=datetime(2025, 1, 1, 12, 0, 0),
        )

    # Timezone-aware datetime from a non-UTC zone is accepted and unified to UTC
    jst = timezone(timedelta(hours=9))
    event = TraceEvent(
        session_id="s1",
        step_id=0,
        event_type="t",
        status="ok",
        summary="x",
        timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=jst),
    )
    assert event.timestamp.utcoffset() == timedelta(0)
    assert event.timestamp.hour == 3


@pytest.mark.parametrize("serialized_form", ["json", "mapping"])
def test_trace_event_round_trips_serialized_timestamp(
    serialized_form: str,
) -> None:
    event = TraceEvent(
        session_id="s1",
        step_id=1,
        event_type="tool.call.completed",
        status="completed",
        summary="Tool completed",
        duration_ms=1.25,
        payload={"result": {"tags": ["safe"]}},
    )

    if serialized_form == "json":
        restored = TraceEvent.model_validate_json(event.model_dump_json())
    else:
        restored = TraceEvent.model_validate(event.model_dump(mode="json"))

    assert restored == event
    assert restored.timestamp.utcoffset() is not None
