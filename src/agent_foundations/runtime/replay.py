import json
from pathlib import Path

from pydantic import ValidationError

from agent_foundations.runtime.trace import TraceEvent


class TraceReplayError(ValueError):
    pass


def load_trace(path: Path) -> list[TraceEvent]:
    events: list[TraceEvent] = []
    expected_session_id = path.stem

    with path.open("rb") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            if not raw_line.strip():
                continue
            try:
                text = raw_line.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise TraceReplayError(
                    f"invalid trace in {path.name} at line {line_number}: invalid UTF-8"
                ) from exc
            try:
                data = json.loads(text)
            except json.JSONDecodeError as exc:
                raise TraceReplayError(
                    f"invalid trace in {path.name} at line {line_number}: invalid JSON"
                ) from exc
            try:
                event = TraceEvent.model_validate(data)
            except ValidationError as exc:
                raise TraceReplayError(
                    f"invalid trace in {path.name} at line {line_number}: invalid event"
                ) from exc
            if event.session_id != expected_session_id:
                raise TraceReplayError(
                    f"invalid trace in {path.name} at line {line_number}: session_id mismatch"
                )
            events.append(event)

    return events


def list_sessions(trace_dir: Path) -> list[str]:
    if not trace_dir.exists():
        return []
    return sorted(
        item.stem
        for item in trace_dir.iterdir()
        if item.is_file() and item.suffix == ".jsonl"
    )
