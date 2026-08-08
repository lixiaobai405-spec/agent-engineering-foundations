import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Annotated, Any, Protocol, runtime_checkable
from uuid import uuid4

from pydantic import (
    ConfigDict,
    Field,
    PlainSerializer,
    PlainValidator,
    WithJsonSchema,
    field_validator,
)

from agent_foundations.domain._freeze import FrozenJSON, to_json_value
from agent_foundations.domain._model import ValidatedCopyModel

_EVENT_TYPE_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")


def _freeze_payload(value: Any) -> FrozenJSON:
    """Validate and freeze a JSON-compatible mapping into FrozenJSON."""
    if isinstance(value, FrozenJSON):
        return value
    if isinstance(value, Mapping):
        return FrozenJSON(dict(value))
    raise ValueError(f"expected a mapping, got {type(value).__name__}")


class TraceEvent(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True, allow_inf_nan=False)

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str
    step_id: int = Field(ge=0)
    event_type: str
    status: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    duration_ms: float | None = Field(default=None, ge=0)
    summary: str
    payload: Annotated[
        Mapping[str, Any],
        PlainValidator(_freeze_payload),
        PlainSerializer(to_json_value, return_type=dict[str, Any]),
        WithJsonSchema({"type": "object"}),
    ] = Field(default_factory=lambda: FrozenJSON({}))

    @field_validator("event_type")
    @classmethod
    def _validate_event_type(cls, value: str) -> str:
        if not _EVENT_TYPE_PATTERN.fullmatch(value):
            raise ValueError("event_type must be a non-empty stable identifier")
        return value

    @field_validator("timestamp")
    @classmethod
    def _ensure_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        return value.astimezone(UTC)


@runtime_checkable
class EventSink(Protocol):
    async def emit(self, event: TraceEvent) -> None: ...


class InMemoryEventSink:
    def __init__(self) -> None:
        self.events: list[TraceEvent] = []

    async def emit(self, event: TraceEvent) -> None:
        self.events.append(event)


class NoOpEventSink:
    async def emit(self, event: TraceEvent) -> None:
        ...
