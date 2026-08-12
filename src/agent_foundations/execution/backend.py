from __future__ import annotations

from typing import Protocol

from agent_foundations.execution.models import ExecutionRequest, ExecutionResult


class ExecutionBackendError(RuntimeError):
    """Base error for execution infrastructure."""


class ExecutionConflictError(ExecutionBackendError):
    """An execution identifier is already active."""


class BackendUnavailableError(ExecutionBackendError):
    """The configured isolated backend is unavailable."""


class BackendLaunchError(ExecutionBackendError):
    """The configured backend could not launch the isolated request."""


class ExecutionBackend(Protocol):
    async def execute(self, request: ExecutionRequest) -> ExecutionResult: ...

    async def cancel(self, execution_id: str) -> None: ...
