from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from agent_foundations.chat.errors import (
    ApprovalUnavailableError,
    ChatConflictError,
)
from agent_foundations.chat.events import ChatEventBroker
from agent_foundations.chat.models import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalStatus,
    ChatEvent,
    ChatEventType,
    RunStatus,
    utc_now,
)
from agent_foundations.chat.repository import ConversationRepository


@dataclass
class _WaiterState:
    future: asyncio.Future[ApprovalStatus]
    request: ApprovalRequest
    ready: asyncio.Event = field(default_factory=asyncio.Event)
    lifecycle_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    finished: asyncio.Event = field(default_factory=asyncio.Event)
    resolved_publish_started: bool = False


class ApprovalCoordinator:
    def __init__(
        self,
        repository: ConversationRepository,
        broker: ChatEventBroker,
    ) -> None:
        self._repository = repository
        self._broker = broker
        self._lock = asyncio.Lock()
        self._waiters: dict[str, _WaiterState] = {}
        self._shutting_down = False

    async def request(self, request: ApprovalRequest) -> ApprovalStatus:
        if request.status is not ApprovalStatus.PENDING:
            raise ChatConflictError("approval request must be pending")

        loop = asyncio.get_running_loop()
        future: asyncio.Future[ApprovalStatus] = loop.create_future()
        state = _WaiterState(future=future, request=request)
        try:
            async with state.lifecycle_lock:
                async with self._lock:
                    if self._shutting_down:
                        raise ApprovalUnavailableError(
                            "approval coordinator is shutting down",
                        )
                    if request.approval_id in self._waiters:
                        raise ChatConflictError("approval already pending")
                    self._waiters[request.approval_id] = state

                await self._repository.transition_run(
                    request.session_id,
                    RunStatus.RUNNING,
                    RunStatus.WAITING_APPROVAL,
                )
                try:
                    await self._repository.create_approval(
                        conversation_id=request.conversation_id,
                        session_id=request.session_id,
                        tool_call_id=request.tool_call_id,
                        tool_name=request.tool_name,
                        canonical_path=request.canonical_path,
                        approval_id=request.approval_id,
                    )
                except Exception:
                    await self._restore_run_to_running(request.session_id)
                    raise
                try:
                    await self._broker.publish(self._build_requested_event(request))
                except Exception:
                    await self._repository.invalidate_approval(request.approval_id)
                    await self._restore_run_to_running(request.session_id)
                    raise
                state.ready.set()

            try:
                decision = await asyncio.shield(future)
                async with state.lifecycle_lock:
                    await self._finish_decision(state, decision)
                return decision
            except asyncio.CancelledError:
                await self._settle_cancelled_request(state)
                raise
        finally:
            try:
                async with self._lock:
                    current = self._waiters.get(request.approval_id)
                    if current is state:
                        del self._waiters[request.approval_id]
            finally:
                state.finished.set()

    async def resolve(
        self,
        approval_id: str,
        decision: ApprovalDecision,
    ) -> ApprovalRequest:
        target = (
            ApprovalStatus.APPROVED
            if decision is ApprovalDecision.APPROVE
            else ApprovalStatus.DENIED
        )
        async with self._lock:
            state = self._waiters.get(approval_id)
        if state is None:
            return await self._resolve_without_waiter(approval_id, target)

        async with state.lifecycle_lock:
            async with self._lock:
                current = self._waiters.get(approval_id)
                if current is not state or self._shutting_down:
                    raise ApprovalUnavailableError(
                        "approval is not available in this process",
                    )
                if not state.ready.is_set():
                    raise ApprovalUnavailableError(
                        "approval is not available in this process",
                    )
                if state.future.cancelled():
                    raise ApprovalUnavailableError("approval waiter was cancelled")
                if state.future.done():
                    raise ChatConflictError("approval already resolved")

            updated = await self._repository.resolve_approval(approval_id, target)
            state.future.set_result(updated.status)

        return updated

    async def shutdown(self) -> None:
        async with self._lock:
            self._shutting_down = True
            waiters = list(self._waiters.items())

        for approval_id, state in waiters:
            async with state.lifecycle_lock:
                async with self._lock:
                    current = self._waiters.get(approval_id)
                    if current is state:
                        del self._waiters[approval_id]
                        if not state.future.done():
                            state.future.cancel()

        if waiters:
            await asyncio.gather(*(state.finished.wait() for _, state in waiters))

    async def _restore_run_to_running(self, session_id: str) -> None:
        run = await self._repository.get_run(session_id)
        if run.status is RunStatus.WAITING_APPROVAL:
            await self._repository.transition_run(
                session_id,
                RunStatus.WAITING_APPROVAL,
                RunStatus.RUNNING,
            )

    async def _settle_cancelled_request(self, state: _WaiterState) -> None:
        async with state.lifecycle_lock:
            if state.future.done() and not state.future.cancelled():
                await self._finish_decision(state, state.future.result())
                return

            async with self._lock:
                approval_id = state.request.approval_id
                current = self._waiters.get(approval_id)
                if current is state:
                    del self._waiters[approval_id]
            if not state.future.done():
                state.future.cancel()

    async def _finish_decision(
        self,
        state: _WaiterState,
        decision: ApprovalStatus,
    ) -> None:
        await self._restore_run_to_running(state.request.session_id)
        if state.resolved_publish_started:
            return
        state.resolved_publish_started = True
        try:
            await self._broker.publish(
                self._build_resolved_event(state.request, decision),
            )
        except Exception:
            pass

    async def _resolve_without_waiter(
        self,
        approval_id: str,
        target: ApprovalStatus,
    ) -> ApprovalRequest:
        approval = await self._repository.get_approval(approval_id)
        if approval.status is ApprovalStatus.PENDING:
            raise ApprovalUnavailableError(
                "approval is not available in this process",
            )
        raise ChatConflictError("approval is not pending")

    def _build_requested_event(self, request: ApprovalRequest) -> ChatEvent:
        return ChatEvent(
            conversation_id=request.conversation_id,
            session_id=request.session_id,
            type=ChatEventType.APPROVAL_REQUESTED,
            occurred_at=utc_now(),
            data={
                "approval_id": request.approval_id,
                "tool_call_id": request.tool_call_id,
                "tool_name": request.tool_name,
                "canonical_path": request.canonical_path,
                "operation": request.operation.value,
                "scope": "external_exact_path",
            },
        )

    def _build_resolved_event(
        self,
        request: ApprovalRequest,
        decision: ApprovalStatus,
    ) -> ChatEvent:
        return ChatEvent(
            conversation_id=request.conversation_id,
            session_id=request.session_id,
            type=ChatEventType.APPROVAL_RESOLVED,
            occurred_at=utc_now(),
            data={
                "approval_id": request.approval_id,
                "status": decision.value,
            },
        )
