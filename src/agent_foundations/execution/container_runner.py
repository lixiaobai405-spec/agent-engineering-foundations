from __future__ import annotations

from agent_foundations.execution.backend import ExecutionBackend
from agent_foundations.execution.models import ByteStreamSink, ExecutionRequest, ExecutionResult
from agent_foundations.security.capabilities import Capability
from agent_foundations.security.models import PolicyRequest, ResourceScope


class CapabilityBindingError(RuntimeError):
    """A consumed Capability is not bound to the exact execution request."""


class ContainerRunner:
    """Bind an already-consumed Capability to an isolated backend call."""

    def __init__(self, backend: ExecutionBackend) -> None:
        self._backend = backend

    async def execute(
        self,
        request: ExecutionRequest,
        capability: Capability,
        authorization_request: PolicyRequest | None = None,
        *,
        output_sink: ByteStreamSink | None = None,
    ) -> ExecutionResult:
        if request.capability_id != capability.capability_id:
            raise CapabilityBindingError("capability_id does not match execution")
        if request.run_id != capability.run_id:
            raise CapabilityBindingError("run_id does not match execution")
        if capability.consumed_at is None:
            raise CapabilityBindingError("capability must be consumed before execution")
        if not (
            capability.issued_at <= capability.consumed_at < capability.expires_at
        ):
            raise CapabilityBindingError("capability consumption window is invalid")
        if authorization_request is not None:
            expected = (
                authorization_request.run_id,
                authorization_request.tool_call_id,
                authorization_request.tool_name,
                authorization_request.resource,
                authorization_request.operation,
                authorization_request.profile_version,
            )
            actual = (
                capability.run_id,
                capability.tool_call_id,
                capability.tool_name,
                capability.resource,
                capability.operation,
                capability.profile_version,
            )
            if actual != expected:
                raise CapabilityBindingError("capability does not match exact policy request")
        if request.mount_mode == "project_write" and not (
            capability.tool_name == "apply_patch"
            and capability.operation == "apply"
            and capability.resource.kind == "project_path"
            and capability.resource.scope is ResourceScope.PROJECT_INTERNAL
            and authorization_request is not None
        ):
            raise CapabilityBindingError(
                "project_write requires exact controlled apply_patch authorization"
            )
        if request.mount_mode == "snapshot" and not (
            capability.tool_name == "run_command"
            and capability.operation == "run"
            and capability.resource.kind == "sandbox_command"
            and capability.resource.scope is ResourceScope.PROJECT_INTERNAL
            and authorization_request is not None
        ):
            raise CapabilityBindingError(
                "snapshot execution requires exact controlled run_command authorization"
            )
        if output_sink is None:
            return await self._backend.execute(request)
        return await self._backend.execute(request, output_sink=output_sink)

    async def cancel(self, execution_id: str) -> None:
        await self._backend.cancel(execution_id)
