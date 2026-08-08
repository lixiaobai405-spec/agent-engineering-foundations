from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from agent_foundations.chat.repository import ConversationRepository
from agent_foundations.runtime.replay import TraceReplayError, list_sessions, load_trace

_PREVIEW_LIMIT = 96
_WHITESPACE = re.compile(r"\s+")


class _NavigationModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class TraceNavigationTurn(_NavigationModel):
    session_id: str
    short_id: str
    turn_number: int
    user_message_preview: str
    status: str
    started_at: datetime
    trace_available: bool


class TraceNavigationConversation(_NavigationModel):
    conversation_id: str
    title: str
    project_root: str
    turns: list[TraceNavigationTurn]


class StandaloneTraceRun(_NavigationModel):
    session_id: str
    short_id: str
    user_message_preview: str
    status: str
    started_at: datetime
    trace_available: bool


class TraceNavigation(_NavigationModel):
    chat_conversations: list[TraceNavigationConversation]
    standalone_runs: list[StandaloneTraceRun]


async def build_trace_navigation(
    trace_dir: Path,
    repository: ConversationRepository | None,
) -> TraceNavigation:
    chat_conversations: list[TraceNavigationConversation] = []
    associated_session_ids: set[str] = set()

    if repository is not None:
        for conversation in await repository.list_conversations():
            messages = await repository.list_messages(conversation.conversation_id)
            message_by_id = {message.message_id: message for message in messages}
            runs = await repository.list_runs(conversation.conversation_id)
            turns: list[TraceNavigationTurn] = []
            for turn_number, run in enumerate(runs, start=1):
                associated_session_ids.add(run.session_id)
                message = message_by_id[run.user_message_id]
                turns.append(
                    TraceNavigationTurn(
                        session_id=run.session_id,
                        short_id=_short_id(run.session_id),
                        turn_number=turn_number,
                        user_message_preview=_preview(message.content),
                        status=run.status.value,
                        started_at=run.started_at or run.created_at,
                        trace_available=(
                            trace_dir / f"{run.session_id}.jsonl"
                        ).is_file(),
                    ),
                )
            chat_conversations.append(
                TraceNavigationConversation(
                    conversation_id=conversation.conversation_id,
                    title=conversation.title,
                    project_root=conversation.project_root,
                    turns=turns,
                ),
            )

    standalone_runs = [
        _standalone_run(trace_dir, session_id)
        for session_id in list_sessions(trace_dir)
        if session_id not in associated_session_ids
    ]
    standalone_runs.sort(key=lambda run: run.started_at, reverse=True)
    return TraceNavigation(
        chat_conversations=chat_conversations,
        standalone_runs=standalone_runs,
    )


def _standalone_run(trace_dir: Path, session_id: str) -> StandaloneTraceRun:
    path = trace_dir / f"{session_id}.jsonl"
    try:
        events = load_trace(path)
    except TraceReplayError:
        return _unavailable_standalone_run(path, session_id)
    if not events:
        return _unavailable_standalone_run(path, session_id)

    first_event = min(events, key=lambda event: event.timestamp)
    user_event = next(
        (event for event in events if event.event_type == "user.message"),
        first_event,
    )
    return StandaloneTraceRun(
        session_id=session_id,
        short_id=_short_id(session_id),
        user_message_preview=_preview(user_event.summary),
        status=events[-1].status,
        started_at=first_event.timestamp,
        trace_available=True,
    )


def _unavailable_standalone_run(
    path: Path,
    session_id: str,
) -> StandaloneTraceRun:
    return StandaloneTraceRun(
        session_id=session_id,
        short_id=_short_id(session_id),
        user_message_preview="Trace unavailable",
        status="unavailable",
        started_at=datetime.fromtimestamp(path.stat().st_mtime, tz=UTC),
        trace_available=False,
    )


def _short_id(session_id: str) -> str:
    return session_id[:8]


def _preview(value: str) -> str:
    normalized = _WHITESPACE.sub(" ", value).strip()
    if len(normalized) <= _PREVIEW_LIMIT:
        return normalized
    return f"{normalized[: _PREVIEW_LIMIT - 1]}…"
