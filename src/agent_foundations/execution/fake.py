from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from agent_foundations.execution.backend import ExecutionConflictError
from agent_foundations.execution.models import ByteStreamSink, ExecutionRequest, ExecutionResult

WorkspaceSideEffect = Callable[[Path], None]
ResultFactory = Callable[[ExecutionRequest], ExecutionResult]


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
        result_factory: ResultFactory | None = None,
        workspace_root: Path | None = None,
        workspace_side_effect: WorkspaceSideEffect | None = None,
        honor_timeout: bool = False,
    ) -> None:
        self._results = dict(results or {})
        self._block = block
        self._result_factory = result_factory
        self._workspace_root = workspace_root
        self._workspace_side_effect = workspace_side_effect
        self._honor_timeout = honor_timeout
        self._active: dict[str, _Control] = {}
        self._activation: dict[str, asyncio.Event] = {}
        self._lock = asyncio.Lock()
        self.requests: list[ExecutionRequest] = []

    @property
    def active_execution_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._active))

    async def execute(
        self,
        request: ExecutionRequest,
        *,
        output_sink: ByteStreamSink | None = None,
    ) -> ExecutionResult:
        async with self._lock:
            if request.execution_id in self._active:
                raise ExecutionConflictError("execution_id is already active")
            control = _Control(release=asyncio.Event())
            self._active[request.execution_id] = control
            self.requests.append(request)
            self._activation.setdefault(request.execution_id, asyncio.Event()).set()
        try:
            if self._workspace_root is not None and self._workspace_side_effect is not None:
                self._workspace_side_effect(self._workspace_root)
            if self._block:
                if self._honor_timeout:
                    try:
                        await asyncio.wait_for(
                            control.release.wait(),
                            timeout=request.timeout_seconds,
                        )
                    except TimeoutError:
                        return ExecutionResult(
                            execution_id=request.execution_id,
                            exit_code=None,
                            stdout=b"",
                            stderr=b"",
                            timed_out=True,
                            cancelled=False,
                            output_truncated=False,
                        )
                else:
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
            result = self._resolve_result(request)
            if output_sink is None:
                return result
            truncated = await self._stream(result, output_sink)
            exit_code = result.exit_code
            timed_out = result.timed_out
            cancelled = result.cancelled
            if truncated and not timed_out and not cancelled:
                exit_code = result.exit_code
            return ExecutionResult(
                execution_id=request.execution_id,
                exit_code=exit_code,
                stdout=b"",
                stderr=b"",
                timed_out=timed_out,
                cancelled=cancelled,
                output_truncated=truncated or result.output_truncated,
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

    def _resolve_result(self, request: ExecutionRequest) -> ExecutionResult:
        if self._result_factory is not None:
            return self._result_factory(request)
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

    @staticmethod
    async def _stream(result: ExecutionResult, sink: ByteStreamSink) -> bool:
        truncated = False

        async def pump(name: Literal["stdout", "stderr"], payload: bytes) -> None:
            nonlocal truncated
            if not payload:
                return
            chunk_size = 32
            for offset in range(0, len(payload), chunk_size):
                if truncated:
                    return
                if not sink.feed(name, payload[offset : offset + chunk_size]):
                    truncated = True
                    return
                await asyncio.sleep(0)

        await asyncio.gather(pump("stdout", result.stdout), pump("stderr", result.stderr))
        return truncated
