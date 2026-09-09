from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID, uuid4

from agent_foundations.command_output.feedback import (
    build_command_feedback,
    feedback_as_metadata,
)
from agent_foundations.command_output.harness import inject_trusted_format
from agent_foundations.command_output.models import ParserStatus, RunCommandRequest
from agent_foundations.command_output.parsers.registry import parser_for
from agent_foundations.command_output.retention import (
    ArtifactCapacityExceeded,
    ArtifactRetentionSweeper,
)
from agent_foundations.command_output.sanitize import sanitize_streams
from agent_foundations.command_output.store import CommandArtifactStore
from agent_foundations.domain.tool import RegisteredTool, Tool, ToolResult
from agent_foundations.durable.effects import EffectResolutionRequiredError, SideEffectLedger
from agent_foundations.durable.faults import CrashPoint, FaultInjector, InjectedCrash
from agent_foundations.durable.models import EffectStatus, SideEffectIntent, SideEffectRecord
from agent_foundations.execution.backend import ExecutionBackend
from agent_foundations.execution.container_runner import ContainerRunner
from agent_foundations.execution.models import ExecutionRequest, ExecutionResult
from agent_foundations.execution.workspace import (
    cleanup_workspace_snapshot,
    create_workspace_snapshot,
)
from agent_foundations.runtime.tool_execution import ToolCallExecutor, ToolExecutionContext
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
from agent_foundations.tools.command.classifier import CommandClassifier
from agent_foundations.tools.command.gate_expand import GateExpandError, expand_gate_argv
from agent_foundations.tools.command.models import (
    CommandClassification,
    CommandSpec,
    ProjectCommandManifest,
)

RUN_COMMAND_TOOL_NAME = "run_command"

RUN_COMMAND_MANIFEST = ToolManifest(
    name=RUN_COMMAND_TOOL_NAME,
    resource_kind="sandbox_command",
    operations=("run",),
    side_effect=SideEffectKind.PROCESS,
    sandbox_required=True,
)

ApprovalDecider = Callable[[AuthorizationDecision], AuthorizationDecision]


class BackendFactory(Protocol):
    def __call__(self, project_root: Path) -> ExecutionBackend: ...


class _ControlledDecisionError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class RunCommandTool:
    name = RUN_COMMAND_TOOL_NAME
    description = (
        "Run one classified project gate command inside the fixed sandbox. "
        "Call with gate_id from the command manifest; do not submit argv. "
        "Exact gates reject target and flags."
    )

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "gate_id": {"type": "string"},
                "target": {"type": "string"},
                "flags": {"type": "array", "items": {"type": "string"}},
                "cwd": {"type": "string", "default": "."},
                "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 300},
            },
            "required": ["gate_id"],
            "additionalProperties": False,
        }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        del arguments
        return ToolResult(
            success=False,
            content="run_command requires controlled sandbox execution",
            error_code="CONTROLLED_EXECUTION_REQUIRED",
        )


def resolve_run_command_resource(arguments: Any) -> PolicyResource:
    gate_id = arguments.get("gate_id")
    if not isinstance(gate_id, str) or not gate_id:
        identifier = "sandbox_command"
    else:
        target = arguments.get("target")
        if isinstance(target, str) and target:
            identifier = f"{gate_id} {target}"
        else:
            identifier = gate_id
    return PolicyResource(
        kind="sandbox_command",
        scope=ResourceScope.PROJECT_INTERNAL,
        identifier=identifier[:256],
    )


def build_run_command_registered_tool() -> RegisteredTool:
    return RegisteredTool(
        RunCommandTool(),
        RUN_COMMAND_MANIFEST,
        resolve_run_command_resource,
    )


class ControlledCommandExecutor:
    def __init__(
        self,
        downstream: ToolCallExecutor,
        profile: PermissionProfile,
        policy: PolicyEngine,
        approval: AuthorizationApproval,
        issuer: CapabilityIssuer,
        consumer: CapabilityConsumer,
        ledger: SideEffectLedger,
        *,
        command_manifest: ProjectCommandManifest,
        artifact_store: CommandArtifactStore,
        retention: ArtifactRetentionSweeper,
        backend_factory: BackendFactory,
        approval_decider: ApprovalDecider | None = None,
        execution_owner_id: str | None = None,
        fault_injector: FaultInjector | None = None,
        fail_artifact_finalize: bool = False,
        controller_root: Path | None = None,
    ) -> None:
        self._downstream = downstream
        self._profile = profile
        self._policy = policy
        self._approval = approval
        self._issuer = issuer
        self._consumer = consumer
        self._ledger = ledger
        self._command_manifest = command_manifest
        self._artifact_store = artifact_store
        self._retention = retention
        self._backend_factory = backend_factory
        self._approval_decider = approval_decider
        self._execution_owner_id = execution_owner_id or str(uuid4())
        self._fault_injector = fault_injector or FaultInjector()
        self._fail_artifact_finalize = fail_artifact_finalize
        self._controller_root = controller_root
        self._runner: ContainerRunner | None = None
        self._active_execution_id: str | None = None

    async def cancel(self, execution_id: str) -> None:
        if self._runner is not None:
            await self._runner.cancel(execution_id)

    async def execute(
        self,
        tool: Tool,
        arguments: dict[str, Any],
        context: ToolExecutionContext,
    ) -> ToolResult:
        if not isinstance(tool, RunCommandTool):
            return await self._downstream.execute(tool, arguments, context)
        try:
            request_model = _parse_request(arguments, self._command_manifest)
        except GateExpandError as exc:
            return _failure(exc.code, str(exc)[:240])
        except Exception as exc:
            return _failure("COMMAND_SPEC_INVALID", str(exc)[:240])

        classifier = CommandClassifier(
            project_fingerprint=self._command_manifest.project_fingerprint,
        )
        classification = classifier.classify(
            CommandSpec(
                argv=request_model.argv,
                cwd=request_model.cwd,
                timeout_seconds=request_model.timeout_seconds,
            ),
            self._command_manifest,
        )
        if classification.hard_denied:
            return _failure(classification.rule_id, "command is hard-denied")
        executed_argv = inject_trusted_format(
            classification.normalized_argv,
            classification.rule_id,
        )

        policy_request = PolicyRequest(
            profile_version=self._profile.version,
            run_id=context.session_id,
            tool_call_id=context.tool_call_id,
            tool_name=RUN_COMMAND_TOOL_NAME,
            manifest=RUN_COMMAND_MANIFEST,
            resource=resolve_run_command_resource(arguments),
            operation="run",
        )
        outcome = self._policy.decide(self._profile, policy_request)
        existing = await self._ledger.get(
            context.session_id,
            context.tool_call_id,
            context.tool_name,
        )
        if outcome.decision is PolicyDecision.DENY:
            try:
                await self._issuer.issue(policy_request, outcome, None)
            except CapabilityDeniedError:
                return _failure("POLICY_DENIED", outcome.reason_code)
            raise AssertionError("deny outcome unexpectedly issued a capability")

        if existing is not None:
            terminal = await self._reconcile_existing(existing)
            if terminal is not None:
                return terminal

        try:
            capability = await self._authorize(policy_request, outcome, existing)
        except _ControlledDecisionError as exc:
            return _failure(exc.code, str(exc))
        except (CapabilityDeniedError, CapabilityMismatchError) as exc:
            return _failure("AUTHORIZATION_REJECTED", str(exc))

        self._fault_injector.hit(CrashPoint.BEFORE_INTENT)
        record = existing
        if record is None:
            record = await self._ledger.prepare(
                SideEffectIntent(
                    operation="run",
                    resource_key=classification.rule_id,
                    summary=f"run {classification.category.value} {classification.rule_id}",
                ),
                context,
                arguments,
            )
            self._fault_injector.hit(CrashPoint.AFTER_INTENT)

        if record.status is not EffectStatus.INTENT_RECORDED:
            raise EffectResolutionRequiredError(
                f"side effect requires reconciliation: {record.status.value}"
            )

        try:
            self._retention.reserve(self._artifact_store._execution_limit_bytes)
        except ArtifactCapacityExceeded:
            return _failure("ARTIFACT_CAPACITY_EXCEEDED", "artifact capacity exceeded")

        record = await self._ledger.claim(
            record.effect_id,
            EffectStatus.INTENT_RECORDED,
            self._execution_owner_id,
        )
        self._fault_injector.hit(CrashPoint.AFTER_CLAIM)

        execution_id = str(uuid4())
        session = self._artifact_store.begin_session(
            run_id=UUID(context.session_id),
            effect_id=UUID(record.effect_id),
            execution_id=UUID(execution_id),
        )
        controller = self._controller_root or context.root.parent / "controller"
        controller.mkdir(parents=True, exist_ok=True)
        snapshot = create_workspace_snapshot(context.root, controller_root=controller)
        runner = ContainerRunner(self._backend_factory(snapshot.root))
        self._runner = runner
        self._active_execution_id = execution_id
        execution_request = ExecutionRequest(
            execution_id=execution_id,
            run_id=context.session_id,
            capability_id=capability.capability_id,
            argv=executed_argv,
            cwd=request_model.cwd,
            mount_mode="snapshot",
            sandbox_profile=classification.sandbox_profile,
            timeout_seconds=request_model.timeout_seconds,
            max_output_bytes=self._artifact_store._execution_limit_bytes,
        )
        try:
            backend_result = await runner.execute(
                execution_request,
                capability,
                policy_request,
                output_sink=session,
            )
        except InjectedCrash:
            raise
        except Exception:
            await self._ledger.mark_unknown(
                record.effect_id,
                self._execution_owner_id,
                "sandbox_execution_exception",
            )
            raise
        finally:
            cleanup_workspace_snapshot(snapshot)
            self._active_execution_id = None

        self._fault_injector.hit(CrashPoint.AFTER_EXECUTE)
        return await self._resolve_backend_result(
            backend_result,
            session,
            record,
            classification=classification,
            argv_display=executed_argv,
            cwd=request_model.cwd,
            project_root=context.root,
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
                        "human denied command execution",
                    ) from None
        issued = await self._issuer.issue(request, outcome, decision)
        return await self._consumer.consume(issued.capability_id, request)

    async def _reconcile_existing(self, record: SideEffectRecord) -> ToolResult | None:
        if record.status is EffectStatus.COMMITTED:
            if record.result is None:
                raise EffectResolutionRequiredError("committed command has no result")
            return record.result
        if record.status is EffectStatus.FAILED:
            if record.result is not None:
                return record.result
            return _failure(record.error_code or "COMMAND_FAILED", "failed command side effect")
        if record.status in {
            EffectStatus.UNKNOWN,
            EffectStatus.ROLLED_BACK,
            EffectStatus.EXECUTING,
        }:
            raise EffectResolutionRequiredError(
                f"side effect requires reconciliation: {record.status.value}"
            )
        return None

    async def _resolve_backend_result(
        self,
        backend_result: ExecutionResult,
        session: Any,
        record: SideEffectRecord,
        *,
        classification: CommandClassification,
        argv_display: tuple[str, ...],
        cwd: str,
        project_root: Path,
    ) -> ToolResult:
        command_exit = backend_result.exit_code
        truncated = backend_result.output_truncated or session.truncated
        metadata_base = {
            "exit_code": command_exit,
            "timed_out": backend_result.timed_out,
            "cancelled": backend_result.cancelled,
            "output_truncated": truncated,
            "parser_status": ParserStatus.PENDING.value,
        }
        if self._fail_artifact_finalize:
            result = ToolResult(
                success=False,
                content="command output artifact could not be finalized",
                error_code="OUTPUT_ARTIFACT_WRITE_FAILED",
                metadata={**metadata_base, "artifact_id": session.artifact_id},
            )
            await self._ledger.fail(record.effect_id, self._execution_owner_id, result)
            return result
        try:
            artifact = session.finalize()
        except Exception:
            result = ToolResult(
                success=False,
                content="command output artifact could not be finalized",
                error_code="OUTPUT_ARTIFACT_WRITE_FAILED",
                metadata={**metadata_base, "artifact_id": session.artifact_id},
            )
            await self._ledger.fail(record.effect_id, self._execution_owner_id, result)
            return result

        metadata = _command_feedback_metadata(
            artifact_store=self._artifact_store,
            artifact=artifact,
            classification=classification,
            argv_display=argv_display,
            cwd=cwd,
            project_root=project_root,
            exit_code=command_exit,
            timed_out=backend_result.timed_out,
            cancelled=backend_result.cancelled,
            output_truncated=truncated,
        )
        if truncated:
            result = ToolResult(
                success=False,
                content="command output exceeded the execution limit",
                error_code="OUTPUT_LIMIT_EXCEEDED",
                metadata=metadata,
            )
            await self._ledger.fail(record.effect_id, self._execution_owner_id, result)
            return result
        if backend_result.timed_out or backend_result.cancelled:
            result = ToolResult(
                success=False,
                content="command interrupted",
                error_code="COMMAND_INTERRUPTED",
                metadata=metadata,
            )
            await self._ledger.fail(record.effect_id, self._execution_owner_id, result)
            return result

        result = ToolResult(
            success=True,
            content="command completed",
            metadata=metadata,
        )
        committed = await self._ledger.commit(
            record.effect_id,
            self._execution_owner_id,
            result,
        )
        self._fault_injector.hit(CrashPoint.AFTER_COMMIT)
        return committed.result or result

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
            raise CapabilityMismatchError("capability does not match exact command request")


def _parse_request(
    arguments: dict[str, Any],
    manifest: ProjectCommandManifest,
) -> RunCommandRequest:
    argv = expand_gate_argv(arguments, manifest)
    payload: dict[str, Any] = {"argv": argv}
    if "cwd" in arguments:
        payload["cwd"] = arguments["cwd"]
    if "timeout_seconds" in arguments:
        payload["timeout_seconds"] = arguments["timeout_seconds"]
    return RunCommandRequest.model_validate(payload)


def _failure(code: str, message: str) -> ToolResult:
    return ToolResult(success=False, content=message[:240], error_code=code)


def _command_feedback_metadata(
    *,
    artifact_store: CommandArtifactStore,
    artifact: Any,
    classification: CommandClassification,
    argv_display: tuple[str, ...],
    cwd: str,
    project_root: Path,
    exit_code: int | None,
    timed_out: bool,
    cancelled: bool,
    output_truncated: bool,
) -> dict[str, Any]:
    directory = artifact_store.directory_for(artifact.artifact_id)
    stdout = (directory / "stdout").read_bytes()
    stderr = (directory / "stderr").read_bytes()
    stdout_text, stderr_text = sanitize_streams(
        stdout=stdout,
        stderr=stderr,
        project_root=project_root,
    )
    outcome = parser_for(classification.rule_id).parse(
        stdout_text,
        stderr_text,
        exit_code=exit_code,
    )
    feedback = build_command_feedback(
        command_category=classification.category,
        argv_display=argv_display,
        cwd=cwd,
        exit_code=exit_code,
        timed_out=timed_out,
        cancelled=cancelled,
        output_truncated=output_truncated,
        passed=outcome.passed,
        failed=outcome.failed,
        skipped=outcome.skipped,
        diagnostics=outcome.diagnostics,
        parser_status=outcome.parser_status,
        unparsed_bytes=outcome.unparsed_bytes,
        unparsed_reason=outcome.unparsed_reason,
        recommended_ranges=outcome.recommended_ranges,
        artifact_id=artifact.artifact_id,
        stdout_bytes=artifact.stdout_bytes,
        stderr_bytes=artifact.stderr_bytes,
        raw_sha256=artifact.sha256,
    )
    repository = artifact_store._repository
    if repository is not None:
        repository.update_parser_status(
            artifact.artifact_id,
            ParserStatus(feedback.parser_status),
        )
    payload = feedback_as_metadata(feedback)
    return {
        "exit_code": feedback.exit_code,
        "timed_out": feedback.timed_out,
        "cancelled": feedback.cancelled,
        "output_truncated": feedback.output_truncated,
        "parser_status": feedback.parser_status,
        "artifact_id": artifact.artifact_id,
        "stdout_bytes": artifact.stdout_bytes,
        "stderr_bytes": artifact.stderr_bytes,
        "sha256": artifact.sha256,
        "retention_status": artifact.retention_status.value,
        **payload,
    }
