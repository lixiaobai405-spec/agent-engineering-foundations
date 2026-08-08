import asyncio
import json
import threading
import time
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from agent_foundations.runtime.redaction import Redactor
from agent_foundations.runtime.sinks import CompositeEventSink, JsonlEventSink
from agent_foundations.runtime.trace import EventSink, InMemoryEventSink, TraceEvent

REDACTED = "[REDACTED]"
PROJECT_ROOT = "<PROJECT_ROOT>"
FAKE_SECRET = "explicit-secret-value"
FAKE_API_KEY = "sk-example1234567890"
FAKE_BEARER = "Bearer abc.def"


def _make_event(
    *,
    session_id: str = "session-1",
    step_id: int = 1,
    event_type: str = "model.request.started",
    status: str = "started",
    summary: str = "calling model",
    duration_ms: float | None = 12.5,
    payload: dict[str, Any] | None = None,
    event_id: str | None = None,
    timestamp: datetime | None = None,
) -> TraceEvent:
    return TraceEvent(
        event_id=event_id or str(uuid.uuid4()),
        session_id=session_id,
        step_id=step_id,
        event_type=event_type,
        status=status,
        timestamp=timestamp or datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC),
        duration_ms=duration_ms,
        summary=summary,
        payload=payload or {"safe": "value"},
    )


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    (root / "src").mkdir()
    (root / "src" / "main.py").write_text("print('ok')\n", encoding="utf-8")
    return root


@pytest.fixture
def trace_dir(tmp_path: Path) -> Path:
    return tmp_path / "traces"


@pytest.fixture
def redactor(project_root: Path) -> Redactor:
    return Redactor(project_root=project_root, secrets=(FAKE_SECRET,))


@pytest.fixture
def jsonl_sink(trace_dir: Path, redactor: Redactor) -> JsonlEventSink:
    return JsonlEventSink(trace_dir, redactor)


@pytest.mark.asyncio
async def test_jsonl_sink_creates_trace_dir_on_first_emit(
    trace_dir: Path,
    jsonl_sink: JsonlEventSink,
) -> None:
    assert not await asyncio.to_thread(trace_dir.exists)
    await jsonl_sink.emit(_make_event())
    assert await asyncio.to_thread(trace_dir.is_dir)


@pytest.mark.asyncio
async def test_jsonl_sink_writes_session_file_with_single_json_line(
    trace_dir: Path,
    jsonl_sink: JsonlEventSink,
) -> None:
    event = _make_event(
        session_id="session-1",
        payload={"note": "first"},
        event_id="event-123",
    )
    await jsonl_sink.emit(event)

    path = trace_dir / "session-1.jsonl"
    assert path.is_file()
    raw = path.read_bytes()
    assert raw.decode("utf-8").endswith("\n")
    assert raw.count(b"\n") == 1

    parsed = json.loads(raw.decode("utf-8").rstrip("\n"))
    assert parsed["event_id"] == "event-123"
    assert parsed["session_id"] == "session-1"
    assert parsed["step_id"] == 1
    assert parsed["event_type"] == "model.request.started"
    assert parsed["status"] == "started"
    assert parsed["timestamp"] == "2026-01-01T12:00:00Z"
    assert parsed["duration_ms"] == 12.5
    assert parsed["summary"] == "calling model"
    assert parsed["payload"] == {"note": "first"}


@pytest.mark.asyncio
async def test_jsonl_sink_appends_events_in_emit_order(
    jsonl_sink: JsonlEventSink,
    trace_dir: Path,
) -> None:
    first = _make_event(step_id=1, summary="first", event_id="event-1")
    second = _make_event(step_id=2, summary="second", event_id="event-2")
    await jsonl_sink.emit(first)
    await jsonl_sink.emit(second)

    lines = (trace_dir / "session-1.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["event_id"] == "event-1"
    assert json.loads(lines[1])["event_id"] == "event-2"


@pytest.mark.asyncio
async def test_jsonl_sink_isolates_sessions_by_file(
    jsonl_sink: JsonlEventSink,
    trace_dir: Path,
) -> None:
    await jsonl_sink.emit(_make_event(session_id="session-a", event_id="a-1"))
    await jsonl_sink.emit(_make_event(session_id="session-b", event_id="b-1"))

    lines_a = (trace_dir / "session-a.jsonl").read_text(encoding="utf-8").splitlines()
    lines_b = (trace_dir / "session-b.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines_a) == 1
    assert len(lines_b) == 1
    assert json.loads(lines_a[0])["event_id"] == "a-1"
    assert json.loads(lines_b[0])["event_id"] == "b-1"


@pytest.mark.asyncio
async def test_jsonl_sink_redacts_sensitive_values_on_disk(
    jsonl_sink: JsonlEventSink,
    trace_dir: Path,
    project_root: Path,
) -> None:
    absolute = str(await asyncio.to_thread(project_root.resolve))
    event = _make_event(
        payload={
            "api_key": FAKE_SECRET,
            "headers": {"Authorization": FAKE_BEARER},
            "model_key": FAKE_API_KEY,
            "path": f"read {absolute}/src/main.py",
        },
    )
    await jsonl_sink.emit(event)

    rendered = (trace_dir / "session-1.jsonl").read_text(encoding="utf-8")
    assert FAKE_SECRET not in rendered
    assert "abc.def" not in rendered
    assert FAKE_API_KEY not in rendered
    assert absolute not in rendered
    assert REDACTED in rendered
    assert PROJECT_ROOT in rendered

    parsed = json.loads(rendered.splitlines()[0])
    assert parsed["payload"]["api_key"] == REDACTED
    assert parsed["payload"]["headers"]["Authorization"] == REDACTED


@pytest.mark.asyncio
async def test_jsonl_sink_does_not_mutate_original_trace_event(
    jsonl_sink: JsonlEventSink,
) -> None:
    event = _make_event(payload={"api_key": FAKE_SECRET, "note": "safe"})
    original_payload = event.payload

    await jsonl_sink.emit(event)

    assert event.payload is original_payload
    assert event.payload["api_key"] == FAKE_SECRET
    assert event.payload["note"] == "safe"
    assert isinstance(event.payload, Mapping)
    assert not isinstance(event.payload, dict)
    payload: Any = event.payload
    with pytest.raises(TypeError):
        payload["api_key"] = "mutated"


@pytest.mark.parametrize(
    "unsafe_session_id",
    [
        "../escape",
        "..\\escape",
        "/absolute",
        r"C:\escape",
        ".",
        "..",
        "session/name",
        r"session\name",
        "",
        "a" * 129,
    ],
)
@pytest.mark.asyncio
async def test_jsonl_sink_rejects_unsafe_session_ids(
    jsonl_sink: JsonlEventSink,
    trace_dir: Path,
    unsafe_session_id: str,
) -> None:
    event = _make_event(session_id=unsafe_session_id)
    with pytest.raises(ValueError, match="session_id"):
        await jsonl_sink.emit(event)
    is_empty = await asyncio.to_thread(
        lambda: not trace_dir.exists() or not any(trace_dir.iterdir())
    )
    assert is_empty


@pytest.mark.parametrize(
    "safe_session_id",
    [
        str(uuid.uuid4()),
        "session-1",
        "session_1",
        "Session42",
        "a1b2c3",
    ],
)
@pytest.mark.asyncio
async def test_jsonl_sink_accepts_safe_session_ids(
    jsonl_sink: JsonlEventSink,
    trace_dir: Path,
    safe_session_id: str,
) -> None:
    await jsonl_sink.emit(_make_event(session_id=safe_session_id))
    assert (trace_dir / f"{safe_session_id}.jsonl").is_file()


@pytest.mark.asyncio
async def test_jsonl_sink_serializes_concurrent_appends(
    jsonl_sink: JsonlEventSink,
    trace_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active = 0
    max_active = 0
    counter_lock = threading.Lock()
    original_append = JsonlEventSink._append

    def tracked_append(path: Path, line: str) -> None:
        nonlocal active, max_active
        with counter_lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.02)
        try:
            original_append(path, line)
        finally:
            with counter_lock:
                active -= 1

    monkeypatch.setattr(JsonlEventSink, "_append", staticmethod(tracked_append))

    events = [
        _make_event(step_id=index, event_id=f"event-{index}")
        for index in range(6)
    ]
    await asyncio.gather(*(jsonl_sink.emit(event) for event in events))

    lines = (trace_dir / "session-1.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == len(events)
    assert max_active == 1

    event_ids = {json.loads(line)["event_id"] for line in lines}
    assert event_ids == {event.event_id for event in events}
    assert len(event_ids) == len(events)


@pytest.mark.asyncio
async def test_jsonl_sink_propagates_write_errors(
    tmp_path: Path,
    redactor: Redactor,
) -> None:
    blocked = tmp_path / "blocked"
    blocked.write_text("not a directory", encoding="utf-8")
    sink = JsonlEventSink(blocked, redactor)

    with pytest.raises(OSError):
        await sink.emit(_make_event())


@pytest.mark.asyncio
async def test_composite_emits_to_every_sink_in_order() -> None:
    first = InMemoryEventSink()
    second = InMemoryEventSink()
    composite = CompositeEventSink((first, second))
    event = _make_event(session_id="session-1", step_id=0, event_type="session.started")

    await composite.emit(event)

    assert first.events == second.events == [event]
    assert first.events[0] is event


@pytest.mark.asyncio
async def test_composite_allows_empty_sink_collection() -> None:
    composite = CompositeEventSink(())
    await composite.emit(_make_event())


@pytest.mark.asyncio
async def test_composite_stops_on_failure_and_preserves_prior_emits() -> None:
    first = InMemoryEventSink()

    class FailingSink:
        async def emit(self, event: TraceEvent) -> None:
            raise RuntimeError("sink failed")

    third = InMemoryEventSink()
    composite = CompositeEventSink((first, FailingSink(), third))
    event = _make_event()

    with pytest.raises(RuntimeError, match="sink failed"):
        await composite.emit(event)

    assert first.events == [event]
    assert third.events == []


def test_jsonl_and_composite_sinks_satisfy_event_sink_protocol() -> None:
    assert isinstance(JsonlEventSink(Path("."), Redactor(Path("."))), EventSink)
    assert isinstance(CompositeEventSink(()), EventSink)
