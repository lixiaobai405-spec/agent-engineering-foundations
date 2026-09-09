from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import datetime
from typing import Any, Protocol
from uuid import uuid4

from agent_foundations.domain.tool import RegisteredTool, Tool, ToolResult
from agent_foundations.durable.effects import EffectResolutionRequiredError, SideEffectLedger
from agent_foundations.durable.faults import CrashPoint, FaultInjector, InjectedCrash
from agent_foundations.durable.models import EffectStatus, SideEffectIntent, SideEffectRecord
from agent_foundations.execution.backend import ExecutionBackend
from agent_foundations.execution.container_runner import ContainerRunner
from agent_foundations.execution.models import ExecutionRequest, ExecutionResult
from agent_foundations.runtime.tool_execution import (
    ToolCallExecutor,
    ToolExecutionContext,
    mark_effect_rolled_back,
)
from agent_foundations.security.approvals import (
    AuthorizationApproval,
    AuthorizationDecision,
    AuthorizationStatus,
)
from agent_foundations.security.capabilities import (
    Capability,
    CapabilityConsumer,
    CapabilityDeniedError,
    CapabilityIssuer,
    CapabilityMismatchError,
)
from agent_foundations.security.models import (
    PermissionProfile,
    PolicyDecision,
    PolicyOutcome,
    PolicyRequest,
    PolicyResource,
    ResourceScope,
    SideEffectKind,
    ToolManifest,
)
from agent_foundations.security.policy import PolicyEngine
from agent_foundations.tools.patch.applier import (
    PatchApplyError,
    PreparedPatch,
    build_applier_payload,
    docker_applier_argv,
    prepare_patch,
    verify_applied_patch,
    verify_prepared_patch,
)
from agent_foundations.tools.patch.models import ValidatedPatch
from agent_foundations.tools.patch.repository import (
    PatchProposalNotFoundError,
    PatchProposalRepository,
    PatchRepositoryError,
)

APPLY_PATCH_TOOL_NAME = "apply_patch"
_PATCH_ID_RE = re.compile(r"^[a-f0-9]{64}$")

APPLY_PATCH_MANIFEST = ToolManifest(
    name=APPLY_PATCH_TOOL_NAME,
    resource_kind="project_path",
    operations=("apply",),
    side_effect=SideEffectKind.PROJECT_WRITE,
    sandbox_required=True,
)


class BackendFactory(Protocol):
    def __call__(self, project_root: Any) -> ExecutionBackend: ...


ApprovalDecider = Callable[[AuthorizationDecision], AuthorizationDecision]


class _ControlledDecisionError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class ApplyPatchTool:
    name = APPLY_PATCH_TOOL_NAME
    description = "Apply one validated patch proposal through the controlled sandbox chain."

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "patch_id": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
            },
            "required": ["patch_id"],
            "additionalProperties": False,
        }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        del arguments
        return ToolResult(
            success=False,
            content="apply_patch requires controlled sandbox execution",
            error_code="CONTROLLED_EXECUTION_REQUIRED",
        )


def resolve_apply_patch_resource(arguments: Any) -> PolicyResource:
    patch_id = str(arguments.get("patch_id", ""))
    if _PATCH_ID_RE.fullmatch(patch_id) is None:
        raise ValueError("patch_id must be 64 lowercase hex characters")
    return PolicyResource(
        kind="project_path",
        scope=ResourceScope.PROJECT_INTERNAL,
        identifier=f"patch:{patch_id}",
    )


def build_apply_patch_registered_tool() -> RegisteredTool:
    return RegisteredTool(
        ApplyPatchTool(),
        APPLY_PATCH_MANIFEST,
        resolve_apply_patch_resource,
    )


class ControlledPatchExecutor:
    def __init__(
        self,
        downstream: ToolCallExecutor,
        proposal_repository: PatchProposalRepository,
        profile: PermissionProfile,
        policy: PolicyEngine,
        approval: AuthorizationApproval,
        issuer: CapabilityIssuer,
        consumer: CapabilityConsumer,
        ledger: SideEffectLedger,
        *,
        backend_factory: BackendFactory,
        approval_decider: ApprovalDecider | None = None,
        execution_owner_id: str | None = None,
        fault_injector: FaultInjector | None = None,
    ) -> None:
        self._downstream = downstream
        self._proposal_repository = proposal_repository
        self._profile = profile
        self._policy = policy
        self._approval = approval
        self._issuer = issuer
        self._consumer = consumer
        self._ledger = ledger
        self._backend_factory = backend_factory
        self._approval_decider = approval_decider
        self._execution_owner_id = execution_owner_id or str(uuid4())
        self._fault_injector = fault_injector or FaultInjector()

    def policy_request_for(
        self,
        patch: ValidatedPatch,
        context: ToolExecutionContext,
    ) -> PolicyRequest:
        return PolicyRequest(
            profile_version=self._profile.version,
            run_id=context.session_id,
            tool_call_id=context.tool_call_id,
            tool_name=APPLY_PATCH_TOOL_NAME,
            manifest=APPLY_PATCH_MANIFEST,
            resource=resolve_apply_patch_resource({"patch_id": patch.patch_id}),
            operation="apply",
        )

    async def execute(
        self,
        tool: Tool,
        arguments: dict[str, Any],
        context: ToolExecutionContext,
    ) -> ToolResult:
        if not isinstance(tool, ApplyPatchTool):
            return await self._downstream.execute(tool, arguments, context)
        if context.tool_name != APPLY_PATCH_TOOL_NAME:
            return _failure("PATCH_CONTEXT_REQUIRED", "tool context mismatch")
        patch_id = str(arguments.get("patch_id", ""))
        if _PATCH_ID_RE.fullmatch(patch_id) is None:
            return _failure("PATCH_ID_INVALID", "invalid patch_id")
        try:
            patch = await self._proposal_repository.get(context.session_id, patch_id)
        except PatchProposalNotFoundError:
            return _failure("PATCH_NOT_FOUND", "patch proposal not found for run")
        except PatchRepositoryError as exc:
            return _failure(type(exc).__name__, str(exc)[:240])

        request = self.policy_request_for(patch, context)
        outcome = self._policy.decide(self._profile, request)
        existing = await self._ledger.get(
            context.session_id,
            context.tool_call_id,
            context.tool_name,
        )
        if outcome.decision is PolicyDecision.DENY:
            try:
                await self._issuer.issue(request, outcome, None)
            except CapabilityDeniedError:
                return _failure("POLICY_DENIED", outcome.reason_code)
            raise AssertionError("deny outcome unexpectedly issued a capability")

        if existing is not None:
            terminal = await self._reconcile_existing(existing, patch, context)
            if terminal is not None:
                return terminal

        try:
            prepared = prepare_patch(patch, context.root)
            capability = await self._authorize(request, outcome, existing)
        except PatchApplyError as exc:
            return _failure(exc.code, str(exc))
        except _ControlledDecisionError as exc:
            return _failure(exc.code, str(exc))
        except (CapabilityDeniedError, CapabilityMismatchError) as exc:
            return _failure("AUTHORIZATION_REJECTED", str(exc))

        self._fault_injector.hit(CrashPoint.BEFORE_INTENT)
        record = existing
        if record is None:
            record = await self._ledger.prepare(
                SideEffectIntent(
                    operation="apply",
                    resource_key=f"patch:{patch.patch_id}",
                    summary=f"apply patch {patch.patch_id[:12]} to {len(patch.files)} file(s)",
                ),
                context,
                arguments,
            )
            self._fault_injector.hit(CrashPoint.AFTER_INTENT)

        if record.status is not EffectStatus.INTENT_RECORDED:
            raise EffectResolutionRequiredError(
                f"side effect requires reconciliation: {record.status.value}"
            )
        record = await self._ledger.claim(
            record.effect_id,
            EffectStatus.INTENT_RECORDED,
            self._execution_owner_id,
        )
        payload = build_applier_payload(prepared)
        execution_request = ExecutionRequest(
            execution_id=str(uuid4()),
            run_id=context.session_id,
            capability_id=capability.capability_id,
            argv=docker_applier_argv(payload),
            cwd=".",
            mount_mode="project_write",
            stdin=b"",
            timeout_seconds=30,
            max_output_bytes=4096,
        )
        try:
            backend_result = await ContainerRunner(
                self._backend_factory(context.root)
            ).execute(execution_request, capability, request)
        except InjectedCrash:
            raise
        except Exception:
            await self._ledger.mark_unknown(
                record.effect_id,
                self._execution_owner_id,
                "sandbox_execution_exception",
            )
            raise

        self._fault_injector.hit(CrashPoint.AFTER_EXECUTE)
        return await self._resolve_backend_result(
            backend_result,
            prepared,
            record,
            context,
        )

    async def _authorize(
        self,
        request: PolicyRequest,
        outcome: PolicyOutcome,
        existing_effect: SideEffectRecord | None,
    ) -> Capability:
        repository = self._consumer._repository
        existing = await repository.find_capability_for_execution(
            request.run_id,
            request.tool_call_id,
        )
        if existing is not None:
            self._assert_capability_exact(existing, request)
            if existing.consumed_at is None:
                return await self._consumer.consume(existing.capability_id, request)
            if existing_effect is None or existing_effect.status is EffectStatus.INTENT_RECORDED:
                return existing
            raise _ControlledDecisionError("CAPABILITY_REPLAY", "capability already consumed")

        decision: AuthorizationDecision | None = None
        if outcome.decision is PolicyDecision.ASK:
            pending = await self._approval.request(request)
            if self._approval_decider is None:
                raise _ControlledDecisionError("APPROVAL_REQUIRED", "approval is pending")
            decision = self._approval_decider(pending)
            if decision.status is AuthorizationStatus.DENIED:
                try:
                    await self._issuer.issue(request, outcome, decision)
                except CapabilityDeniedError:
                    raise _ControlledDecisionError(
                        "APPROVAL_DENIED",
                        "human denied patch execution",
                    ) from None
        issued = await self._issuer.issue(request, outcome, decision)
        return await self._consumer.consume(issued.capability_id, request)

    async def _reconcile_existing(
        self,
        record: SideEffectRecord,
        patch: ValidatedPatch,
        context: ToolExecutionContext,
    ) -> ToolResult | None:
        if record.status is EffectStatus.COMMITTED:
            verify_applied_patch(patch, context.root)
            if record.result is None:
                raise EffectResolutionRequiredError("committed patch has no result")
            return record.result
        if record.status is EffectStatus.EXECUTING:
            prepared = verify_applied_patch(patch, context.root)
            result = _success_result(prepared)
            owner = record.execution_owner_id
            if owner is None:
                raise EffectResolutionRequiredError("executing patch has no owner")
            committed = await self._ledger.commit(record.effect_id, owner, result)
            return committed.result or result
        if record.status in {
            EffectStatus.UNKNOWN,
            EffectStatus.ROLLED_BACK,
            EffectStatus.FAILED,
        }:
            raise EffectResolutionRequiredError(
                f"side effect requires reconciliation: {record.status.value}"
            )
        return None

    async def _resolve_backend_result(
        self,
        backend_result: ExecutionResult,
        prepared: PreparedPatch,
        record: SideEffectRecord,
        context: ToolExecutionContext,
    ) -> ToolResult:
        status = _backend_status(backend_result)
        if backend_result.exit_code == 0 and status == "applied":
            verify_prepared_patch(prepared, context.root)
            result = _success_result(prepared)
            committed = await self._ledger.commit(
                record.effect_id,
                self._execution_owner_id,
                result,
            )
            self._fault_injector.hit(CrashPoint.AFTER_COMMIT)
            return committed.result or result
        if backend_result.exit_code == 20 and status == "rolled_back":
            result = _failure("PATCH_ROLLED_BACK", "patch failed and was rolled back")
            await mark_effect_rolled_back(
                self._ledger,
                record,
                self._execution_owner_id,
                result,
            )
            return result
        await self._ledger.mark_unknown(
            record.effect_id,
            self._execution_owner_id,
            "patch_backend_unresolved",
        )
        return _failure("PATCH_EFFECT_UNKNOWN", "patch execution requires reconciliation")

    @staticmethod
    def _assert_capability_exact(capability: Capability, request: PolicyRequest) -> None:
        actual = (
            capability.run_id,
            capability.tool_call_id,
            capability.tool_name,
            capability.resource,
            capability.operation,
            capability.profile_version,
        )
        expected = (
            request.run_id,
            request.tool_call_id,
            request.tool_name,
            request.resource,
            request.operation,
            request.profile_version,
        )
        if actual != expected:
            raise CapabilityMismatchError("capability does not match exact patch request")
        consumed_at: datetime | None = capability.consumed_at
        if consumed_at is not None and not (
            capability.issued_at <= consumed_at < capability.expires_at
        ):
            raise CapabilityMismatchError("capability consumption window is invalid")


def _backend_status(result: ExecutionResult) -> str | None:
    try:
        payload = json.loads(result.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    status = payload.get("status")
    return status if isinstance(status, str) else None


def _success_result(prepared: PreparedPatch) -> ToolResult:
    return ToolResult(
        success=True,
        content="patch applied",
        metadata={
            "patch_id": prepared.patch_id,
            "backend": "docker",
            "mount_mode": "project_write",
            "files": [
                {
                    "path": item.path,
                    "operation": item.operation.value,
                    "sha256": item.after_sha256,
                }
                for item in prepared.files
            ],
        },
    )


def _failure(code: str, message: str) -> ToolResult:
    return ToolResult(success=False, content=message[:240], error_code=code)


__all__ = [
    "APPLY_PATCH_MANIFEST",
    "APPLY_PATCH_TOOL_NAME",
    "ApplyPatchTool",
    "ControlledPatchExecutor",
    "build_apply_patch_registered_tool",
    "resolve_apply_patch_resource",
]
