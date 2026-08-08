import json
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from agent_foundations.runtime.redaction import Redactor
from agent_foundations.runtime.replay import TraceReplayError, list_sessions, load_trace
from agent_foundations.runtime.sinks import JsonlEventSink
from agent_foundations.runtime.trace import TraceEvent

CORRUPT_MARKER = "SUPER_SECRET_CORRUPT_CONTENT_12345"


def _make_event(
    *,
    session_id: str = "session-a",
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
        payload=payload or {"note": "safe"},
    )


def _event_json(event: TraceEvent) -> str:
    return json.dumps(event.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"))


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    return root


@pytest.fixture
def trace_dir(tmp_path: Path) -> Path:
    return tmp_path / "traces"


@pytest.fixture
def jsonl_sink(trace_dir: Path, project_root: Path) -> JsonlEventSink:
    return JsonlEventSink(trace_dir, Redactor(project_root=project_root))


@pytest.mark.asyncio
async def test_load_trace_round_trips_jsonl_sink_events(
    jsonl_sink: JsonlEventSink,
    trace_dir: Path,
) -> None:
    first = _make_event(
        session_id="session-a",
        step_id=1,
        event_id="event-1",
        event_type="session.started",
        status="started",
        summary="first",
        duration_ms=1.0,
        payload={"tags": ["alpha"]},
        timestamp=datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC),
    )
    second = _make_event(
        session_id="session-a",
        step_id=2,
        event_id="event-2",
        event_type="tool.call.completed",
        status="completed",
        summary="second",
        duration_ms=2.5,
        payload={"tags": ["beta"]},
        timestamp=datetime(2026, 1, 1, 12, 0, 1, tzinfo=UTC),
    )
    await jsonl_sink.emit(first)
    await jsonl_sink.emit(second)

    loaded = load_trace(trace_dir / "session-a.jsonl")

    assert isinstance(loaded, list)
    assert len(loaded) == 2
    assert [event.step_id for event in loaded] == [1, 2]
    assert loaded[0].event_id == "event-1"
    assert loaded[0].session_id == "session-a"
    assert loaded[0].event_type == "session.started"
    assert loaded[0].status == "started"
    assert loaded[0].summary == "first"
    assert loaded[0].duration_ms == 1.0
    assert loaded[0].timestamp == datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    assert loaded[0].timestamp.utcoffset() == UTC.utcoffset(datetime.now(UTC))
    assert isinstance(loaded[0].payload, Mapping)
    assert not isinstance(loaded[0].payload, dict)
    assert loaded[0].payload["tags"] == ("alpha",)
    assert loaded[1].event_id == "event-2"
    assert loaded[1].payload["tags"] == ("beta",)


def test_load_trace_accepts_final_line_without_trailing_newline(tmp_path: Path) -> None:
    path = tmp_path / "session-a.jsonl"
    first = _event_json(_make_event(step_id=1))
    second = _event_json(_make_event(step_id=2))
    path.write_bytes(first.encode("utf-8") + b"\n" + second.encode("utf-8"))

    loaded = load_trace(path)

    assert [event.step_id for event in loaded] == [1, 2]


def test_load_trace_returns_empty_list_for_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "session-a.jsonl"
    path.write_bytes(b"")

    assert load_trace(path) == []


def test_load_trace_reports_physical_line_number_for_blank_line_before_corruption(
    tmp_path: Path,
) -> None:
    path = tmp_path / "broken.jsonl"
    path.write_text(
        _event_json(_make_event(session_id="broken", step_id=1)) + "\n\n"
        f"{CORRUPT_MARKER}\n",
        encoding="utf-8",
    )

    with pytest.raises(TraceReplayError, match="line 3") as exc_info:
        load_trace(path)

    assert CORRUPT_MARKER not in str(exc_info.value)
    assert exc_info.value.__cause__ is not None


def test_load_trace_reports_invalid_json_with_filename_and_line_number(
    tmp_path: Path,
) -> None:
    path = tmp_path / "broken.jsonl"
    path.write_text(
        _event_json(_make_event(session_id="broken", step_id=1)) + f"\n{CORRUPT_MARKER}\n",
        encoding="utf-8",
    )

    with pytest.raises(TraceReplayError, match="broken.jsonl") as exc_info:
        load_trace(path)
    with pytest.raises(TraceReplayError, match="line 2"):
        load_trace(path)

    assert CORRUPT_MARKER not in str(exc_info.value)
    assert isinstance(exc_info.value.__cause__, json.JSONDecodeError)


@pytest.mark.parametrize(
    ("invalid_line", "description"),
    [
        ('{"session_id":"session-a"}', "missing required fields"),
        (
            json.dumps({
                **_make_event(step_id=1).model_dump(mode="json"),
                "step_id": -1,
            }),
            "negative step_id",
        ),
        (
            json.dumps({
                **_make_event(step_id=1).model_dump(mode="json"),
                "timestamp": "2026-01-01T12:00:00",
            }),
            "naive timestamp",
        ),
        ("[]", "top-level array"),
        ('"not-an-object"', "top-level string"),
        ("null", "top-level null"),
    ],
)
def test_load_trace_reports_invalid_trace_event_structures(
    tmp_path: Path,
    invalid_line: str,
    description: str,
) -> None:
    path = tmp_path / "session-a.jsonl"
    path.write_text(
        _event_json(_make_event()) + f"\n{invalid_line}\n",
        encoding="utf-8",
    )

    with pytest.raises(TraceReplayError, match="session-a.jsonl") as exc_info:
        load_trace(path)
    with pytest.raises(TraceReplayError, match="line 2"):
        load_trace(path)

    assert description  # documents intent for each parametrized case
    assert CORRUPT_MARKER not in str(exc_info.value)
    assert exc_info.value.__cause__ is not None


def test_load_trace_reports_invalid_utf8_with_filename_and_line_number(
    tmp_path: Path,
) -> None:
    path = tmp_path / "session-a.jsonl"
    path.write_bytes(
        _event_json(_make_event()).encode("utf-8") + b"\n\xff\xfe\n",
    )

    with pytest.raises(TraceReplayError, match="session-a.jsonl") as exc_info:
        load_trace(path)
    with pytest.raises(TraceReplayError, match="line 2"):
        load_trace(path)

    assert "\xff" not in str(exc_info.value)
    assert exc_info.value.__cause__ is not None


def test_load_trace_rejects_session_id_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "session-a.jsonl"
    mismatched = _make_event(session_id="session-b", step_id=2)
    path.write_text(
        _event_json(_make_event(session_id="session-a", step_id=1)) + "\n"
        + _event_json(mismatched) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(TraceReplayError, match="session-a.jsonl") as exc_info:
        load_trace(path)
    with pytest.raises(TraceReplayError, match="line 2"):
        load_trace(path)

    assert "session-b" not in str(exc_info.value)


def test_load_trace_preserves_file_not_found_error(tmp_path: Path) -> None:
    missing = tmp_path / "missing.jsonl"

    with pytest.raises(FileNotFoundError):
        load_trace(missing)


def test_list_sessions_returns_empty_for_missing_or_empty_directory(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    empty = tmp_path / "empty"
    empty.mkdir()

    assert list_sessions(missing) == []
    assert list_sessions(empty) == []


def test_list_sessions_lists_sorted_jsonl_stems_only(tmp_path: Path) -> None:
    trace_dir = tmp_path / "traces"
    trace_dir.mkdir()
    (trace_dir / "session-b.jsonl").write_text("{}", encoding="utf-8")
    (trace_dir / "session-a.jsonl").write_text("{}", encoding="utf-8")
    (trace_dir / "notes.txt").write_text("ignore", encoding="utf-8")
    nested = trace_dir / "nested"
    nested.mkdir()
    (nested / "nested.jsonl").write_text("{}", encoding="utf-8")
    directory_named_jsonl = trace_dir / "looks-like.jsonl"
    directory_named_jsonl.mkdir()

    assert list_sessions(trace_dir) == ["session-a", "session-b"]
