from __future__ import annotations

from agent_foundations.execution.backend import ExecutionBackend
from agent_foundations.execution.models import ExecutionRequest, ExecutionResult
from agent_foundations.security.capabilities import Capability


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
        return await self._backend.execute(request)

    async def cancel(self, execution_id: str) -> None:
        await self._backend.cancel(execution_id)
