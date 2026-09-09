from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import timedelta

from agent_foundations.chat.errors import (
    ApprovalUnavailableError,
    ChatConflictError,
    ChatNotFoundError,
)
from agent_foundations.chat.events import ChatEventBroker
from agent_foundations.chat.models import (
    AccessOperation,
    ApprovalDecision,
    ApprovalRequest,
    ApprovalStatus,
    ChatEvent,
    ChatEventType,
    RunStatus,
    utc_now,
)
from agent_foundations.chat.repository import ConversationRepository
from agent_foundations.security.approvals import (
    AuthorizationApproval,
    AuthorizationStatus,
    Clock,
)
from agent_foundations.security.approvals import (
    utc_now as authorization_utc_now,
)
from agent_foundations.security.capabilities import (
    Capability,
    CapabilityConsumer,
    CapabilityDeniedError,
    CapabilityIssuer,
)
from agent_foundations.security.models import (
    PermissionProfileName,
    PolicyOutcome,
    PolicyRequest,
    PolicyResource,
    ResourceScope,
)
from agent_foundations.security.models import (
    PolicyDecision as SecurityPolicyDecision,
)
from agent_foundations.security.repository import AuthorizationRepository


def _bounded_identifier(value: str, fallback: str) -> str:
    text = value.strip() or fallback
    return text[:256]


def approval_view_fields(
    request: ApprovalRequest,
    policy_request: PolicyRequest | None = None,
    outcome: PolicyOutcome | None = None,
) -> tuple[str, str, str, str]:
    resolved_request, resolved_outcome = _policy_for_approval_view(
        request,
        policy_request,
        outcome,
    )
    operation = resolved_request.operation
    if operation not in {"read", "apply", "run"}:
        operation = "read"
    decision = resolved_outcome.decision.value
    if decision not in {"allow", "ask", "deny"}:
        decision = "ask"
    return (
        operation,
        resolved_request.resource.kind,
        resolved_request.resource.scope.value,
        decision,
    )


def _policy_for_approval_view(
    request: ApprovalRequest,
    policy_request: PolicyRequest | None,
    outcome: PolicyOutcome | None,
) -> tuple[PolicyRequest, PolicyOutcome]:
    if policy_request is not None:
        return policy_request, outcome or _pending_ask_outcome()
    from agent_foundations.tools.command.run_command import RUN_COMMAND_MANIFEST
    from agent_foundations.tools.filesystem.read_file import READ_FILE_MANIFEST
    from agent_foundations.tools.patch.apply_patch import APPLY_PATCH_MANIFEST

    if request.tool_name == "run_command":
        manifest = RUN_COMMAND_MANIFEST
        operation = "run"
        resource = PolicyResource(
            kind="sandbox_command",
            scope=ResourceScope.PROJECT_INTERNAL,
            identifier=_bounded_identifier(request.canonical_path, "sandbox_command"),
        )
    elif request.tool_name == "apply_patch" or request.operation is AccessOperation.APPLY:
        manifest = APPLY_PATCH_MANIFEST
        operation = "apply"
        resource = PolicyResource(
            kind="project_path",
            scope=ResourceScope.PROJECT_INTERNAL,
            identifier=_bounded_identifier(request.canonical_path, "project_path"),
        )
    else:
        manifest = READ_FILE_MANIFEST
        operation = "read"
        resource = PolicyResource(
            kind="project_path",
            scope=ResourceScope.EXTERNAL_EXACT_PATH,
            identifier=_bounded_identifier(request.canonical_path, "project_path"),
        )
    derived = PolicyRequest(
        profile_version=1,
        run_id=request.session_id,
        tool_call_id=request.tool_call_id,
        tool_name=request.tool_name,
        manifest=manifest,
        resource=resource,
        operation=operation,
    )
    return derived, _pending_ask_outcome()


def _pending_ask_outcome() -> PolicyOutcome:
    return PolicyOutcome(
        decision=SecurityPolicyDecision.ASK,
        rule_id="chat.pending_approval",
        reason_code="approval_required",
    )


@dataclass
class _WaiterState:
    future: asyncio.Future[ApprovalStatus]
    request: ApprovalRequest
    policy_request: PolicyRequest | None = None
    outcome: PolicyOutcome | None = None
    ready: asyncio.Event = field(default_factory=asyncio.Event)
    lifecycle_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    finished: asyncio.Event = field(default_factory=asyncio.Event)
    resolved_publish_started: bool = False


class ApprovalCoordinator:
    def __init__(
        self,
        repository: ConversationRepository,
        broker: ChatEventBroker,
        *,
        authorization_repository: AuthorizationRepository | None = None,
        authorization_clock: Clock = authorization_utc_now,
    ) -> None:
        self._repository = repository
        self._broker = broker
        self._lock = asyncio.Lock()
        self._waiters: dict[str, _WaiterState] = {}
        self._shutting_down = False
        security_repository = authorization_repository or AuthorizationRepository(
            repository._database,
        )
        self._authorization_repository = security_repository
        self._authorization_approval = AuthorizationApproval(
            security_repository,
            PermissionProfileName.ASK_ALWAYS,
            clock=authorization_clock,
        )
        self._capability_issuer = CapabilityIssuer(
            security_repository,
            PermissionProfileName.ASK_ALWAYS,
            ttl=timedelta(minutes=5),
            clock=authorization_clock,
        )
        self._capability_consumer = CapabilityConsumer(
            security_repository,
            clock=authorization_clock,
        )

    async def request_capability(
        self,
        request: ApprovalRequest,
        policy_request: PolicyRequest,
        outcome: PolicyOutcome,
    ) -> Capability | None:
        pending = await self._authorization_approval.request(
            policy_request,
            authorization_id=request.approval_id,
        )
        legacy_status = await self._resolved_legacy_status(request)
        if legacy_status is None:
            try:
                legacy_status = await self.request(request, policy_request, outcome)
            except BaseException:
                await self._authorization_repository.invalidate_pending(
                    pending.authorization_id,
                    decided_at=authorization_utc_now(),
                )
                raise

        status = (
            AuthorizationStatus.APPROVED
            if legacy_status is ApprovalStatus.APPROVED
            else AuthorizationStatus.DENIED
        )
        decision = self._authorization_approval.decide(pending, status)
        try:
            return await self._capability_issuer.issue(
                policy_request,
                outcome,
                decision,
            )
        except CapabilityDeniedError:
            return None

    async def _resolved_legacy_status(
        self,
        request: ApprovalRequest,
    ) -> ApprovalStatus | None:
        try:
            existing = await self._repository.get_approval(request.approval_id)
        except ChatNotFoundError:
            return None
        exact_binding = (
            existing.conversation_id == request.conversation_id
            and existing.session_id == request.session_id
            and existing.tool_call_id == request.tool_call_id
            and existing.tool_name == request.tool_name
            and existing.canonical_path == request.canonical_path
            and existing.operation is request.operation
        )
        if not exact_binding:
            raise ChatConflictError("legacy approval does not match exact request")
        if existing.status in {ApprovalStatus.APPROVED, ApprovalStatus.DENIED}:
            return existing.status
        if existing.status is ApprovalStatus.PENDING:
            raise ApprovalUnavailableError("legacy approval is still pending")
        raise ChatConflictError("legacy approval is invalidated")

    async def consume_capability(
        self,
        capability_id: str,
        execution: PolicyRequest,
    ) -> Capability:
        return await self._capability_consumer.consume(capability_id, execution)

    async def request(
        self,
        request: ApprovalRequest,
        policy_request: PolicyRequest | None = None,
        outcome: PolicyOutcome | None = None,
    ) -> ApprovalStatus:
        if request.status is not ApprovalStatus.PENDING:
            raise ChatConflictError("approval request must be pending")

        loop = asyncio.get_running_loop()
        future: asyncio.Future[ApprovalStatus] = loop.create_future()
        state = _WaiterState(
            future=future,
            request=request,
            policy_request=policy_request,
            outcome=outcome,
        )
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
                    await self._broker.publish(
                        self._build_requested_event(
                            request,
                            policy_request,
                            outcome,
                        )
                    )
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

    def _build_requested_event(
        self,
        request: ApprovalRequest,
        policy_request: PolicyRequest | None = None,
        outcome: PolicyOutcome | None = None,
    ) -> ChatEvent:
        operation, resource_kind, scope, policy_decision = approval_view_fields(
            request,
            policy_request,
            outcome,
        )
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
                "operation": operation,
                "resource_kind": resource_kind,
                "scope": scope,
                "policy_decision": policy_decision,
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
