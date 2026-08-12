from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass

from agent_foundations.execution.backend import ExecutionConflictError
from agent_foundations.execution.models import ExecutionRequest, ExecutionResult


@dataclass
class _Control:
    release: asyncio.Event
    cancelled: bool = False


class FakeBackend:
    """Deterministic, side-effect-free execution boundary for upper-layer tests."""

    def __init__(
        self,
        *,
        results: Mapping[str, ExecutionResult] | None = None,
        block: bool = False,
    ) -> None:
        self._results = dict(results or {})
        self._block = block
        self._active: dict[str, _Control] = {}
        self._activation: dict[str, asyncio.Event] = {}
        self._lock = asyncio.Lock()
        self.requests: list[ExecutionRequest] = []

    @property
    def active_execution_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._active))

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        async with self._lock:
            if request.execution_id in self._active:
                raise ExecutionConflictError("execution_id is already active")
            control = _Control(release=asyncio.Event())
            self._active[request.execution_id] = control
            self.requests.append(request)
            self._activation.setdefault(request.execution_id, asyncio.Event()).set()
        try:
            if self._block:
                await control.release.wait()
            if control.cancelled:
                return ExecutionResult(
                    execution_id=request.execution_id,
                    exit_code=None,
                    stdout=b"",
                    stderr=b"",
                    timed_out=False,
                    cancelled=True,
                    output_truncated=False,
                )
            return self._results.get(
                request.execution_id,
                ExecutionResult(
                    execution_id=request.execution_id,
                    exit_code=0,
                    stdout=b"",
                    stderr=b"",
                    timed_out=False,
                    cancelled=False,
                    output_truncated=False,
                ),
            )
        finally:
            async with self._lock:
                self._active.pop(request.execution_id, None)

    async def cancel(self, execution_id: str) -> None:
        async with self._lock:
            control = self._active.get(execution_id)
            if control is not None:
                control.cancelled = True
                control.release.set()

    def release(self, execution_id: str) -> None:
        control = self._active.get(execution_id)
        if control is not None:
            control.release.set()

    async def wait_until_active(self, execution_id: str) -> None:
        signal = self._activation.setdefault(execution_id, asyncio.Event())
        await signal.wait()
