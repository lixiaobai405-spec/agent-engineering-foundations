from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator, Mapping
from pathlib import Path
from typing import Any

from agent_foundations.chat.models import (
    ChatEvent,
    ChatEventType,
    ChatToolActivity,
    ToolActivityStatus,
)
from agent_foundations.chat.repository import ConversationRepository
from agent_foundations.domain._freeze import FrozenJSON
from agent_foundations.runtime.redaction import Redactor
from agent_foundations.runtime.trace import TraceEvent

_TRACE_TO_CHAT_TYPE: dict[str, ChatEventType] = {
    "model.request.started": ChatEventType.MODEL_REQUESTED,
    "tool.call.requested": ChatEventType.TOOL_REQUESTED,
    "tool.call.completed": ChatEventType.TOOL_COMPLETED,
    "tool.call.failed": ChatEventType.TOOL_FAILED,
    "plan.created": ChatEventType.PLAN_UPDATED,
    "plan.step.updated": ChatEventType.PLAN_UPDATED,
    "plan.replanned": ChatEventType.PLAN_UPDATED,
}

_ALLOWED_DATA_KEYS = frozenset(
    {"tool_call_id", "name", "arguments_summary", "result_summary", "status"},
)
_PLAN_TRACE_TYPES = frozenset(
    {"plan.created", "plan.step.updated", "plan.replanned"},
)
_ALLOWED_PLAN_DATA_KEYS = frozenset(
    {"plan_id", "version", "goal", "replan_count", "max_replans", "steps"},
)
_ALLOWED_PLAN_STEP_KEYS = frozenset({"step_id", "status", "description"})
_PROJECT_ROOT_PLACEHOLDER = "<PROJECT_ROOT>"
logger = logging.getLogger(__name__)


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


def _safe_scalar(value: Any) -> str:
    if isinstance(value, str) and value:
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return "unknown"


def _safe_count(value: Any) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return 0


def _parse_json_object(value: Any) -> Mapping[str, Any] | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None
    return parsed if isinstance(parsed, Mapping) else None


def _count_label(count: int, singular: str, plural: str) -> str:
    return f"{count} {singular if count == 1 else plural}"


def _safe_path_summary(value: Any, project_root: Path) -> str:
    if not isinstance(value, str) or not value:
        return "[path hidden]"
    normalized = value.replace("\\", "/")
    if normalized.startswith(_PROJECT_ROOT_PLACEHOLDER):
        relative = normalized[len(_PROJECT_ROOT_PLACEHOLDER) :].lstrip("/")
        return relative or "."
    candidate = Path(value)
    if candidate.is_absolute():
        try:
            return candidate.resolve().relative_to(project_root).as_posix() or "."
        except (OSError, ValueError):
            return "[external path]"
    if ".." in candidate.parts:
        return "[path hidden]"
    return candidate.as_posix() or "."


def _summarize_arguments(
    name: str,
    arguments: Mapping[str, Any],
    project_root: Path,
) -> str:
    if name == "read_file":
        return _safe_path_summary(arguments.get("path"), project_root)
    if name == "list_directory":
        return _safe_path_summary(arguments.get("path", "."), project_root)
    if name == "search_text":
        return f"query={_safe_scalar(arguments.get('query'))}"
    if name == "run_command":
        argv = arguments.get("argv")
        if isinstance(argv, list):
            return " ".join(str(item) for item in argv[:6])
        return "run_command"
    if name in {"read_command_output", "search_command_output"}:
        return f"artifact={_safe_scalar(arguments.get('artifact_id'))}"
    return "arguments hidden"


def _summarize_result(name: str, result: Mapping[str, Any]) -> str:
    if result.get("success") is not True:
        return f"failed: {_safe_scalar(result.get('error_code'))}"
    metadata = result.get("metadata")
    if name == "read_file" and isinstance(metadata, Mapping):
        return _count_label(
            _safe_count(metadata.get("returned_lines")),
            "line",
            "lines",
        )
    payload = _parse_json_object(result.get("content"))
    if name == "list_directory" and payload is not None:
        entries = payload.get("entries")
        count = len(entries) if isinstance(entries, list) else 0
        return _count_label(count, "entry", "entries")
    if name == "search_text" and payload is not None:
        matches = payload.get("matches")
        count = len(matches) if isinstance(matches, list) else 0
        scanned = _safe_count(payload.get("scanned_files"))
        return f"{_count_label(count, 'match', 'matches')} in {scanned} files"
    if name == "run_command":
        metadata = result.get("metadata") if isinstance(result.get("metadata"), Mapping) else {}
        artifact = ""
        if isinstance(metadata, Mapping):
            artifact = _safe_scalar(metadata.get("artifact_id"))
        exit_code = metadata.get("exit_code") if isinstance(metadata, Mapping) else None
        failed = metadata.get("failed") if isinstance(metadata, Mapping) else None
        parser = metadata.get("parser_status") if isinstance(metadata, Mapping) else None
        return f"exit={exit_code} failed={failed} parser={parser} artifact={artifact}"
    if name in {"read_command_output", "search_command_output"}:
        metadata = result.get("metadata") if isinstance(result.get("metadata"), Mapping) else {}
        artifact_id = ""
        output_count: object = None
        if isinstance(metadata, Mapping):
            raw_artifact = metadata.get("artifact_id")
            if isinstance(raw_artifact, str):
                artifact_id = raw_artifact
            output_count = metadata.get("line_count", metadata.get("hits"))
        hit_count = (
            len(output_count) if isinstance(output_count, list) else output_count
        )
        return f"artifact={artifact_id} count={hit_count}"
    return "completed"


def _plan_step_view(step: Mapping[str, Any]) -> dict[str, str] | None:
    item: dict[str, str] = {}
    for key in _ALLOWED_PLAN_STEP_KEYS:
        value = step.get(key)
        if isinstance(value, str) and value:
            item[key] = value
    if {"step_id", "status", "description"} <= item.keys():
        return item
    return None


def _plan_event_data(payload: Mapping[str, Any]) -> dict[str, Any]:
    data: dict[str, Any] = {}
    plan_id = payload.get("plan_id")
    if isinstance(plan_id, str) and plan_id:
        data["plan_id"] = plan_id
    goal = payload.get("goal")
    if isinstance(goal, str) and goal:
        data["goal"] = goal
    for key in ("version", "replan_count", "max_replans"):
        value = payload.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            data[key] = value
    steps = payload.get("steps")
    if isinstance(steps, list):
        cleaned: list[dict[str, str]] = []
        for step in steps:
            if not isinstance(step, Mapping):
                continue
            item = _plan_step_view(step)
            if item is not None:
                cleaned.append(item)
        data["steps"] = cleaned
    return {key: value for key, value in data.items() if key in _ALLOWED_PLAN_DATA_KEYS}


class TraceToChatProjector:
    def __init__(
        self,
        conversation_id: str,
        redactor: Redactor,
        project_root: Path,
        max_summary_chars: int = 240,
    ) -> None:
        if max_summary_chars < 1:
            raise ValueError("max_summary_chars must be positive")
        self._conversation_id = conversation_id
        self._redactor = redactor
        self._project_root = project_root.resolve()
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
            event_id=event.event_id,
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
        if event_type in _PLAN_TRACE_TYPES:
            return FrozenJSON(_plan_event_data(payload))

        if isinstance(status, str) and status:
            data["status"] = _truncate_summary(status, self._max_summary_chars)

        if event_type == "model.request.started":
            return FrozenJSON(data)

        tool_call_id = payload.get("tool_call_id")
        if isinstance(tool_call_id, str) and tool_call_id:
            data["tool_call_id"] = tool_call_id

        name = payload.get("name")
        if isinstance(name, str) and name:
            data["name"] = name

        if (
            event_type == "tool.call.requested"
            and isinstance(name, str)
            and isinstance(payload.get("arguments"), Mapping)
        ):
            summary = _summarize_arguments(
                name,
                payload["arguments"],
                self._project_root,
            )
            data["arguments_summary"] = _truncate_summary(
                summary,
                self._max_summary_chars,
            )
        elif (
            event_type in {"tool.call.completed", "tool.call.failed"}
            and isinstance(name, str)
            and isinstance(payload.get("result"), Mapping)
        ):
            summary = _summarize_result(name, payload["result"])
            data["result_summary"] = _truncate_summary(
                summary,
                self._max_summary_chars,
            )

        filtered = {key: value for key, value in data.items() if key in _ALLOWED_DATA_KEYS}
        return FrozenJSON(filtered)


def activity_from_chat_event(event: ChatEvent) -> ChatToolActivity | None:
    status_by_type = {
        ChatEventType.TOOL_REQUESTED: ToolActivityStatus.RUNNING,
        ChatEventType.TOOL_COMPLETED: ToolActivityStatus.COMPLETED,
        ChatEventType.TOOL_FAILED: ToolActivityStatus.FAILED,
    }
    status = status_by_type.get(event.type)
    if status is None:
        return None
    tool_call_id = event.data.get("tool_call_id")
    if not isinstance(tool_call_id, str) or not tool_call_id:
        return None
    tool_name = event.data.get("name")
    if not isinstance(tool_name, str) or not tool_name:
        tool_name = "unknown_tool"
    arguments_summary = event.data.get("arguments_summary")
    result_summary = event.data.get("result_summary")
    return ChatToolActivity(
        conversation_id=event.conversation_id,
        session_id=event.session_id,
        tool_call_id=tool_call_id,
        tool_name=tool_name,
        status=status,
        arguments_summary=(
            arguments_summary if isinstance(arguments_summary, str) else None
        ),
        result_summary=result_summary if isinstance(result_summary, str) else None,
        started_at=event.occurred_at,
        finished_at=(
            None if status is ToolActivityStatus.RUNNING else event.occurred_at
        ),
        last_event_id=event.event_id,
    )


class ChatProjectionSink:
    def __init__(
        self,
        projector: TraceToChatProjector,
        repository: ConversationRepository,
        broker: ChatEventBroker,
    ) -> None:
        self._projector = projector
        self._repository = repository
        self._broker = broker
        self._seen_event_ids: set[str] = set()

    async def emit(self, event: TraceEvent) -> None:
        if event.event_id in self._seen_event_ids:
            return
        try:
            chat_event = self._projector.project(event)
            if chat_event is None:
                self._seen_event_ids.add(event.event_id)
                return
            activity = activity_from_chat_event(chat_event)
            if activity is not None:
                await self._repository.upsert_tool_activity(activity)
            await self._broker.publish(chat_event)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("chat projection skipped: %s", type(exc).__name__)
            return
        self._seen_event_ids.add(event.event_id)


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

    def subscriber_count(self, conversation_id: str) -> int:
        queues = self._subscribers.get(conversation_id)
        return 0 if queues is None else len(queues)

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
    if (
        event.type is ChatEventType.APPROVAL_REQUESTED
        and event.data.get("tool_name") == "apply_patch"
    ):
        safe_data = dict(event.data)
        safe_data.update(
            {
                "operation": "apply",
                "scope": "project_internal",
                "policy_decision": "ask",
                "resource_kind": "project_path",
                "one_time": True,
                "backend": "docker",
            },
        )
        event = event.model_copy(update={"data": safe_data})
    return (
        f"event: {event.type.value}\n"
        f"data: {event.model_dump_json()}\n\n"
    )
