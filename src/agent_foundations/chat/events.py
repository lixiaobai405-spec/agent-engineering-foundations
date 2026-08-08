from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Any

from agent_foundations.chat.models import ChatEvent, ChatEventType
from agent_foundations.domain._freeze import FrozenJSON
from agent_foundations.runtime.redaction import Redactor
from agent_foundations.runtime.trace import TraceEvent

_TRACE_TO_CHAT_TYPE: dict[str, ChatEventType] = {
    "model.request.started": ChatEventType.MODEL_REQUESTED,
    "tool.call.requested": ChatEventType.TOOL_REQUESTED,
    "tool.call.completed": ChatEventType.TOOL_COMPLETED,
    "tool.call.failed": ChatEventType.TOOL_FAILED,
}

_ALLOWED_DATA_KEYS = frozenset({"name", "arguments_summary", "result_summary", "status"})


def _truncate_summary(text: str, limit: int) -> str:
    if limit < 1:
        raise ValueError("max_summary_chars must be positive")
    if len(text) <= limit:
        return text
    if limit == 1:
        return "…"
    prefix = text[: limit - 1].rstrip("…")
    if not prefix:
        return "…"
    return f"{prefix}…"


def _json_summary(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class TraceToChatProjector:
    def __init__(
        self,
        conversation_id: str,
        redactor: Redactor,
        max_summary_chars: int = 240,
    ) -> None:
        if max_summary_chars < 1:
            raise ValueError("max_summary_chars must be positive")
        self._conversation_id = conversation_id
        self._redactor = redactor
        self._max_summary_chars = max_summary_chars

    def project(self, event: TraceEvent) -> ChatEvent | None:
        chat_type = _TRACE_TO_CHAT_TYPE.get(event.event_type)
        if chat_type is None:
            return None

        redacted_payload = self._redactor.redact(dict(event.payload))
        redacted_status = self._redactor.redact(event.status)
        data = self._build_data(
            event.event_type,
            redacted_payload,
            redacted_status,
        )
        return ChatEvent(
            conversation_id=self._conversation_id,
            session_id=event.session_id,
            type=chat_type,
            occurred_at=event.timestamp,
            data=data,
        )

    def _build_data(
        self,
        event_type: str,
        payload: dict[str, Any],
        status: Any,
    ) -> FrozenJSON:
        data: dict[str, Any] = {}
        if isinstance(status, str) and status:
            data["status"] = _truncate_summary(status, self._max_summary_chars)

        if event_type == "model.request.started":
            return FrozenJSON(data)

        name = payload.get("name")
        if isinstance(name, str) and name:
            data["name"] = name

        if event_type == "tool.call.requested" and "arguments" in payload:
            summary = _json_summary(payload["arguments"])
            data["arguments_summary"] = _truncate_summary(
                summary,
                self._max_summary_chars,
            )
        elif event_type in {"tool.call.completed", "tool.call.failed"} and "result" in payload:
            summary = _json_summary(payload["result"])
            data["result_summary"] = _truncate_summary(
                summary,
                self._max_summary_chars,
            )

        filtered = {key: value for key, value in data.items() if key in _ALLOWED_DATA_KEYS}
        return FrozenJSON(filtered)


class ChatProjectionSink:
    def __init__(
        self,
        projector: TraceToChatProjector,
        broker: ChatEventBroker,
    ) -> None:
        self._projector = projector
        self._broker = broker
        self._seen_event_ids: set[str] = set()

    async def emit(self, event: TraceEvent) -> None:
        if event.event_id in self._seen_event_ids:
            return
        self._seen_event_ids.add(event.event_id)
        chat_event = self._projector.project(event)
        if chat_event is None:
            return
        await self._broker.publish(chat_event)


class ChatEventBroker:
    def __init__(self, queue_size: int = 256) -> None:
        if queue_size < 1:
            raise ValueError("queue_size must be positive")
        self._queue_size = queue_size
        self._subscribers: dict[str, set[asyncio.Queue[ChatEvent]]] = {}

    async def publish(self, event: ChatEvent) -> None:
        queues = self._subscribers.get(event.conversation_id)
        if not queues:
            return
        for queue in queues:
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(event)

    async def subscribe(
        self,
        conversation_id: str,
    ) -> AsyncGenerator[ChatEvent, None]:
        queue: asyncio.Queue[ChatEvent] = asyncio.Queue(maxsize=self._queue_size)
        self._subscribers.setdefault(conversation_id, set()).add(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            subscribers = self._subscribers.get(conversation_id)
            if subscribers is not None:
                subscribers.discard(queue)
                if not subscribers:
                    del self._subscribers[conversation_id]


def encode_chat_sse(event: ChatEvent) -> str:
    return (
        f"event: {event.type.value}\n"
        f"data: {event.model_dump_json()}\n\n"
    )
