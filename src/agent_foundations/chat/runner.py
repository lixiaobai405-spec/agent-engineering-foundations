from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from agent_foundations.chat.durable_checkpoint import (
    load_latest_conversation_plan,
    load_provider_attempts,
    make_chat_checkpoint_sink,
)
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
from agent_foundations.chat.repository import (
    ConversationRepository,
    cancel_durable_run_if_active,
)
from agent_foundations.domain.messages import Message, Role
from agent_foundations.durable.models import DurableRun, DurableRunStatus
from agent_foundations.durable.repository import (
    DurableRunNotFoundError,
    DurableRunRepository,
)
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
        durable_repository: DurableRunRepository | None = None,
    ) -> None:
        self._repository = repository
        self._broker = broker
        self._runtime_factory = runtime_factory
        self._trace_dir = Path(trace_dir)
        self._redactor_factory = redactor_factory
        self._tool_executor_factory = tool_executor_factory
        self._durable_repository = durable_repository

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
            await self._ensure_durable_run(session_id, conversation)
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
                project_root=Path(conversation.project_root),
            )
            event_sink: EventSink = CompositeEventSink(
                [
                    JsonlEventSink(self._trace_dir, redactor),
                    ChatProjectionSink(projector, self._repository, self._broker),
                ],
            )
            tool_executor = self._tool_executor_factory(conversation, session_id)
            loop = self._runtime_factory(conversation, event_sink, tool_executor)
            checkpoint_sink = None
            provider_attempts: dict[str, int] = {}
            plan_snapshot = None
            if self._durable_repository is not None:
                checkpoint_sink = await make_chat_checkpoint_sink(
                    self._durable_repository,
                    session_id,
                )
                provider_attempts = await load_provider_attempts(
                    self._durable_repository,
                    session_id,
                )
                prior_runs = await self._repository.list_runs(conversation_id)
                plan_snapshot = await load_latest_conversation_plan(
                    self._durable_repository,
                    [run.session_id for run in prior_runs],
                    exclude_session_id=session_id,
                )
            result = await loop.run(
                Path(conversation.project_root),
                query,
                history=history,
                session_id=session_id,
                checkpoint_sink=checkpoint_sink,
                provider_attempts=provider_attempts,
                plan_snapshot=plan_snapshot,
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

            await self._transition_durable(
                session_id,
                DurableRunStatus.RUNNING,
                DurableRunStatus.COMPLETED,
            )
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

    async def interrupt_run(self, session_id: str) -> None:
        await self._safe_interrupt_run(session_id)

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
        await cancel_durable_run_if_active(self._durable_repository, session_id)

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
        await self._transition_durable(
            session_id,
            DurableRunStatus.RUNNING,
            DurableRunStatus.FAILED,
        )
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

    async def _ensure_durable_run(
        self,
        session_id: str,
        conversation: Conversation,
    ) -> None:
        if self._durable_repository is None:
            return
        try:
            await self._durable_repository.get_run(session_id)
            return
        except DurableRunNotFoundError:
            pass
        now = utc_now()
        await self._durable_repository.create_run(
            DurableRun(
                run_id=session_id,
                project_root=conversation.project_root,
                status=DurableRunStatus.RUNNING,
                schema_version=1,
                state_version=0,
                attempt=1,
                created_at=now,
                updated_at=now,
            ),
        )

    async def _transition_durable(
        self,
        session_id: str,
        expected: DurableRunStatus,
        target: DurableRunStatus,
    ) -> None:
        if self._durable_repository is None:
            return
        try:
            await self._durable_repository.transition_status(
                session_id,
                expected,
                target,
            )
        except DurableRunNotFoundError:
            return
