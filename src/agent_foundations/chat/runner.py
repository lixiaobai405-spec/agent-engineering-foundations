from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from agent_foundations.chat.events import (
    ChatEventBroker,
    ChatProjectionSink,
    TraceToChatProjector,
)
from agent_foundations.chat.models import (
    ChatEvent,
    ChatEventType,
    ChatMessage,
    Conversation,
    MessageRole,
    RunStatus,
    utc_now,
)
from agent_foundations.chat.repository import ConversationRepository
from agent_foundations.domain.messages import Message, Role
from agent_foundations.runtime.loop import AgentLoop
from agent_foundations.runtime.redaction import Redactor
from agent_foundations.runtime.sinks import CompositeEventSink, JsonlEventSink
from agent_foundations.runtime.tool_execution import (
    DirectToolCallExecutor,
    ToolCallExecutor,
)
from agent_foundations.runtime.trace import EventSink

_TERMINAL_RUN_STATUSES = {
    RunStatus.COMPLETED,
    RunStatus.FAILED,
    RunStatus.INTERRUPTED,
}


class RuntimeFactory(Protocol):
    def __call__(
        self,
        conversation: Conversation,
        event_sink: EventSink,
        tool_executor: ToolCallExecutor,
    ) -> AgentLoop: ...


def direct_executor_factory(
    conversation: Conversation,
    session_id: str,
) -> ToolCallExecutor:
    return DirectToolCallExecutor()


def _to_domain_history(messages: list[ChatMessage]) -> tuple[Message, ...]:
    history: list[Message] = []
    for message in messages:
        if message.role is MessageRole.USER:
            history.append(Message(role=Role.USER, content=message.content))
        elif message.role is MessageRole.ASSISTANT:
            history.append(Message(role=Role.ASSISTANT, content=message.content))
    return tuple(history)


class ConversationRunner:
    def __init__(
        self,
        repository: ConversationRepository,
        broker: ChatEventBroker,
        runtime_factory: RuntimeFactory,
        trace_dir: Path,
        redactor_factory: Callable[[Conversation], Redactor],
        tool_executor_factory: Callable[
            [Conversation, str],
            ToolCallExecutor,
        ] = direct_executor_factory,
    ) -> None:
        self._repository = repository
        self._broker = broker
        self._runtime_factory = runtime_factory
        self._trace_dir = Path(trace_dir)
        self._redactor_factory = redactor_factory
        self._tool_executor_factory = tool_executor_factory

    async def run_turn(
        self,
        conversation_id: str,
        session_id: str,
        user_message_id: str,
        query: str,
    ) -> None:
        try:
            conversation = await self._repository.get_conversation(conversation_id)
            prior = await self._repository.list_context_before(
                conversation_id,
                user_message_id,
            )
            await self._repository.transition_run(
                session_id,
                RunStatus.QUEUED,
                RunStatus.RUNNING,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self._safe_fail_run(session_id, conversation_id, exc)
            return

        history = _to_domain_history(prior)

        try:
            await self._broker.publish(
                ChatEvent(
                    conversation_id=conversation_id,
                    session_id=session_id,
                    type=ChatEventType.RUN_STARTED,
                    occurred_at=utc_now(),
                    data={"status": "running"},
                ),
            )

            redactor = self._redactor_factory(conversation)
            projector = TraceToChatProjector(
                conversation_id=conversation_id,
                redactor=redactor,
            )
            event_sink: EventSink = CompositeEventSink(
                [
                    JsonlEventSink(self._trace_dir, redactor),
                    ChatProjectionSink(projector, self._broker),
                ],
            )
            tool_executor = self._tool_executor_factory(conversation, session_id)
            loop = self._runtime_factory(conversation, event_sink, tool_executor)
            result = await loop.run(
                Path(conversation.project_root),
                query,
                history=history,
                session_id=session_id,
            )

            complete_task = asyncio.create_task(
                self._repository.complete_run(session_id, result.answer),
            )
            try:
                assistant = await complete_task
            except asyncio.CancelledError:
                if complete_task.done():
                    assistant = complete_task.result()
                else:
                    try:
                        assistant = await asyncio.shield(complete_task)
                    except asyncio.CancelledError:
                        if not await self._is_completed(session_id):
                            await self._safe_interrupt_run(session_id)
                        raise
                if not await self._is_completed(session_id):
                    await self._safe_interrupt_run(session_id)
                raise

            await self._publish_completion_events(
                conversation_id,
                session_id,
                assistant,
            )
        except asyncio.CancelledError:
            if not await self._is_completed(session_id):
                await self._safe_interrupt_run(session_id)
            raise
        except Exception as exc:
            if await self._is_completed(session_id):
                raise
            await self._safe_fail_run(session_id, conversation_id, exc)

    async def _publish_completion_events(
        self,
        conversation_id: str,
        session_id: str,
        assistant: ChatMessage,
    ) -> None:
        await self._broker.publish(
            ChatEvent(
                conversation_id=conversation_id,
                session_id=session_id,
                type=ChatEventType.ASSISTANT_MESSAGE_COMPLETED,
                occurred_at=utc_now(),
                data={
                    "message_id": assistant.message_id,
                    "content": assistant.content,
                    "sequence": assistant.sequence,
                },
            ),
        )
        await self._broker.publish(
            ChatEvent(
                conversation_id=conversation_id,
                session_id=session_id,
                type=ChatEventType.RUN_COMPLETED,
                occurred_at=utc_now(),
                data={"status": "completed"},
            ),
        )

    async def _is_completed(self, session_id: str) -> bool:
        run = await self._repository.get_run(session_id)
        return run.status is RunStatus.COMPLETED

    async def _safe_interrupt_run(self, session_id: str) -> None:
        run = await self._repository.get_run(session_id)
        if run.status in _TERMINAL_RUN_STATUSES:
            return
        await self._repository.interrupt_run(session_id)

    async def _safe_fail_run(
        self,
        session_id: str,
        conversation_id: str,
        exc: BaseException,
    ) -> None:
        run = await self._repository.get_run(session_id)
        if run.status in _TERMINAL_RUN_STATUSES:
            return
        await self._repository.fail_run(session_id, type(exc).__name__)
        await self._broker.publish(
            ChatEvent(
                conversation_id=conversation_id,
                session_id=session_id,
                type=ChatEventType.RUN_FAILED,
                occurred_at=utc_now(),
                data={
                    "status": "failed",
                    "error_code": type(exc).__name__,
                },
            ),
        )
