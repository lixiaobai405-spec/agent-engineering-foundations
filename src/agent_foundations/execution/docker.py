from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from agent_foundations.execution.backend import (
    BackendLaunchError,
    BackendUnavailableError,
    ExecutionConflictError,
)
from agent_foundations.execution.models import ExecutionRequest, ExecutionResult

SANDBOX_IMAGE = "agent-foundations-sandbox:phase2"
logger = logging.getLogger(__name__)
_CONTAINER_PREFIX = "af-"
_CREDENTIAL_PARTS = frozenset(
    {".ssh", ".aws", ".azure", ".kube", ".git", "credentials", "secrets"}
)
_UNAVAILABLE_MARKERS = (
    b"failed to connect",
    b"cannot connect to the docker daemon",
    b"is the docker daemon running",
    b"no such image",
    b"unable to find image",
    b"pull access denied",
)


class _Readable(Protocol):
    async def read(self, size: int) -> bytes: ...


class _Writable(Protocol):
    def write(self, data: bytes) -> None: ...

    async def drain(self) -> None: ...

    def close(self) -> None: ...


class _Process(Protocol):
    @property
    def stdin(self) -> _Writable | None: ...

    @property
    def stdout(self) -> _Readable | None: ...

    @property
    def stderr(self) -> _Readable | None: ...

    @property
    def returncode(self) -> int | None: ...

    async def wait(self) -> int: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...


ProcessFactory = Callable[[tuple[str, ...]], Awaitable[_Process]]


class _AsyncioProcess:
    def __init__(self, process: asyncio.subprocess.Process) -> None:
        self._process = process

    @property
    def stdin(self) -> _Writable | None:
        return self._process.stdin

    @property
    def stdout(self) -> _Readable | None:
        return self._process.stdout

    @property
    def stderr(self) -> _Readable | None:
        return self._process.stderr

    @property
    def returncode(self) -> int | None:
        return self._process.returncode

    async def wait(self) -> int:
        return await self._process.wait()

    def terminate(self) -> None:
        self._process.terminate()

    def kill(self) -> None:
        self._process.kill()


async def _spawn_docker(argv: tuple[str, ...]) -> _Process:
    process = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={},
    )
    return _AsyncioProcess(process)


class DockerCommandBuilder:
    def __init__(self, workspace_root: Path, *, docker_executable: str = "docker") -> None:
        try:
            resolved = workspace_root.resolve(strict=True)
        except (OSError, ValueError) as exc:
            raise ValueError("workspace root must resolve strictly") from exc
        if not resolved.is_dir():
            raise ValueError("workspace root must be a directory")
        if resolved == Path(resolved.anchor):
            raise ValueError("workspace root must not be a drive root")
        if resolved == Path.home().resolve(strict=True):
            raise ValueError("workspace root must not be the user home")
        self._validate_mount_source(resolved)
        self.workspace_root = resolved
        self._docker_executable = docker_executable

    def build(self, request: ExecutionRequest) -> tuple[str, ...]:
        cwd = self._resolve_cwd(request.cwd)
        relative = cwd.relative_to(self.workspace_root)
        container_cwd = "/workspace"
        if relative.parts:
            container_cwd += "/" + relative.as_posix()
        mount = f"type=bind,source={self.workspace_root},target=/workspace"
        if request.mount_mode == "read_only":
            mount += ",readonly"
        return (
            self._docker_executable,
            "run",
            "--rm",
            "--name",
            container_name(request.execution_id),
            "--pull",
            "never",
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--user",
            "65532:65532",
            "--pids-limit",
            "64",
            "--memory",
            "512m",
            "--cpus",
            "1.0",
            "--mount",
            mount,
            "--workdir",
            container_cwd,
            SANDBOX_IMAGE,
            *request.argv,
        )

    def _resolve_cwd(self, relative_cwd: str) -> Path:
        try:
            resolved = (self.workspace_root / relative_cwd).resolve(strict=True)
        except (OSError, ValueError) as exc:
            raise ValueError("cwd must resolve within the workspace") from exc
        if not resolved.is_dir() or not resolved.is_relative_to(self.workspace_root):
            raise ValueError("cwd must be a workspace directory")
        return resolved

    @staticmethod
    def _validate_mount_source(path: Path) -> None:
        value = str(path)
        normalized = value.replace("/", "\\")
        if normalized.startswith(("\\\\", "\\?\\", "\\.\\")):
            raise ValueError("UNC and device mount sources are blocked")
        if "," in value or any(ord(character) < 32 for character in value):
            raise ValueError("mount source contains unsafe syntax")
        remainder = value[2:] if len(value) > 1 and value[1] == ":" else value
        if ":" in remainder:
            raise ValueError("alternate data stream mount source is blocked")
        if any(part.casefold() in _CREDENTIAL_PARTS for part in path.parts):
            raise ValueError("credential-bearing mount source is blocked")


def container_name(execution_id: str) -> str:
    return f"{_CONTAINER_PREFIX}{execution_id}"


@dataclass
class _ActiveExecution:
    launch_task: asyncio.Future[_Process] | None = None
    process: _Process | None = None
    cancelled: bool = False
    cleanup_task: asyncio.Task[None] | None = None
    drain_tasks: tuple[asyncio.Task[None], ...] = ()


@dataclass
class _OutputBudget:
    remaining: int
    truncated: bool = False


class DockerBackend:
    def __init__(
        self,
        workspace_root: Path,
        *,
        process_factory: ProcessFactory = _spawn_docker,
        cleanup_factory: ProcessFactory = _spawn_docker,
    ) -> None:
        self._builder = DockerCommandBuilder(workspace_root)
        self._process_factory = process_factory
        self._cleanup_factory = cleanup_factory
        self._active: dict[str, _ActiveExecution] = {}
        self._lock = asyncio.Lock()

    @property
    def active_execution_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._active))

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        argv = self._builder.build(request)
        active = _ActiveExecution()
        async with self._lock:
            if request.execution_id in self._active:
                raise ExecutionConflictError("execution_id is already active")
            self._active[request.execution_id] = active
        try:
            launch_task = asyncio.ensure_future(self._process_factory(argv))
            active.launch_task = launch_task
            try:
                process = await asyncio.shield(launch_task)
            except FileNotFoundError as exc:
                raise BackendUnavailableError("docker executable is unavailable") from exc
            except OSError as exc:
                raise BackendLaunchError("docker CLI launch failed") from exc
            active.process = process
            if active.cancelled:
                await self._abort_and_cleanup(request.execution_id, active)
                return self._cancelled_result(request.execution_id)
            await self._write_stdin(process, request.stdin)
            budget = _OutputBudget(request.max_output_bytes)
            stdout = bytearray()
            stderr = bytearray()
            stderr_probe = bytearray()
            active.drain_tasks = (
                asyncio.create_task(self._drain(process.stdout, stdout, budget)),
                asyncio.create_task(
                    self._drain(
                        process.stderr,
                        stderr,
                        budget,
                        diagnostic_probe=stderr_probe,
                    )
                ),
            )
            timed_out = False
            try:
                exit_code = await asyncio.wait_for(
                    process.wait(),
                    timeout=request.timeout_seconds,
                )
            except TimeoutError:
                timed_out = True
                await self._abort_and_cleanup(request.execution_id, active)
                exit_code = None
            await asyncio.gather(*active.drain_tasks)
            cancelled = active.cancelled and not timed_out
            if cancelled:
                await self._cleanup_exact(request.execution_id, active)
                exit_code = None
            stderr_bytes = bytes(stderr)
            if not timed_out and not cancelled and exit_code == 125:
                diagnostic = bytes(stderr_probe).lower()
                if any(marker in diagnostic for marker in _UNAVAILABLE_MARKERS):
                    raise BackendUnavailableError(
                        "docker daemon or sandbox image is unavailable"
                    )
                raise BackendLaunchError("docker failed before workload execution")
            return ExecutionResult(
                execution_id=request.execution_id,
                exit_code=exit_code,
                stdout=bytes(stdout),
                stderr=stderr_bytes,
                timed_out=timed_out,
                cancelled=cancelled,
                output_truncated=budget.truncated,
            )
        except asyncio.CancelledError:
            active.cancelled = True
            cleanup = asyncio.create_task(
                self._finish_cancelled_execution(request.execution_id, active)
            )
            try:
                await self._await_despite_cancellation(cleanup)
            except Exception as exc:
                logger.error(
                    "exact Docker cleanup failed after task cancellation for %s: %s",
                    request.execution_id,
                    type(exc).__name__,
                )
            raise
        finally:
            async with self._lock:
                self._active.pop(request.execution_id, None)

    async def cancel(self, execution_id: str) -> None:
        async with self._lock:
            active = self._active.get(execution_id)
            if active is None:
                return
            active.cancelled = True
        await self._abort_and_cleanup(execution_id, active)

    async def _finish_cancelled_execution(
        self,
        execution_id: str,
        active: _ActiveExecution,
    ) -> None:
        await self._abort_and_cleanup(execution_id, active)
        for task in active.drain_tasks:
            if not task.done():
                task.cancel()
        if active.drain_tasks:
            await asyncio.gather(*active.drain_tasks, return_exceptions=True)

    async def _abort_and_cleanup(
        self,
        execution_id: str,
        active: _ActiveExecution,
    ) -> None:
        process = await self._resolve_launched_process(active)
        if process is not None:
            await self._terminate(process)
        await self._cleanup_exact(execution_id, active)

    @staticmethod
    async def _resolve_launched_process(active: _ActiveExecution) -> _Process | None:
        if active.process is not None:
            return active.process
        launch_task = active.launch_task
        if launch_task is None:
            return None
        try:
            process = await asyncio.shield(launch_task)
        except (FileNotFoundError, OSError):
            return None
        active.process = process
        return process

    async def _cleanup_exact(
        self,
        execution_id: str,
        active: _ActiveExecution,
    ) -> None:
        cleanup_task = active.cleanup_task
        if cleanup_task is None:
            cleanup_task = asyncio.create_task(self._run_exact_cleanup(execution_id))
            active.cleanup_task = cleanup_task
        try:
            await asyncio.shield(cleanup_task)
        except Exception:
            if active.cleanup_task is cleanup_task:
                active.cleanup_task = None
            raise

    async def _run_exact_cleanup(self, execution_id: str) -> None:
        for attempt in range(2):
            try:
                await self._run_exact_cleanup_attempt(execution_id)
            except BackendLaunchError:
                if attempt == 1:
                    raise
                logger.warning(
                    "retrying exact Docker cleanup for %s after failure",
                    execution_id,
                )
            else:
                return

    async def _run_exact_cleanup_attempt(self, execution_id: str) -> None:
        argv = ("docker", "rm", "--force", container_name(execution_id))
        try:
            cleanup = await self._cleanup_factory(argv)
        except (FileNotFoundError, OSError) as exc:
            raise BackendLaunchError("exact Docker cleanup could not launch") from exc
        stdout, stderr, exit_code = await asyncio.gather(
            self._read_prefix(cleanup.stdout),
            self._read_prefix(cleanup.stderr),
            cleanup.wait(),
        )
        diagnostic = (stdout + stderr).lower()
        if exit_code != 0 and b"no such container" not in diagnostic:
            raise BackendLaunchError(
                f"exact Docker cleanup failed with exit code {exit_code}"
            )

    @staticmethod
    async def _await_despite_cancellation(task: asyncio.Task[None]) -> None:
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
        task.result()

    @staticmethod
    def _cancelled_result(execution_id: str) -> ExecutionResult:
        return ExecutionResult(
            execution_id=execution_id,
            exit_code=None,
            stdout=b"",
            stderr=b"",
            timed_out=False,
            cancelled=True,
            output_truncated=False,
        )

    @staticmethod
    async def _write_stdin(process: _Process, data: bytes) -> None:
        writer = process.stdin
        if writer is None:
            if data:
                raise BackendLaunchError("docker stdin pipe is unavailable")
            return
        try:
            if data:
                writer.write(data)
                await writer.drain()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            writer.close()

    @staticmethod
    async def _drain(
        reader: _Readable | None,
        target: bytearray,
        budget: _OutputBudget,
        *,
        diagnostic_probe: bytearray | None = None,
    ) -> None:
        if reader is None:
            return
        while True:
            chunk = await reader.read(65536)
            if not chunk:
                return
            if diagnostic_probe is not None and len(diagnostic_probe) < 4096:
                remaining_probe = 4096 - len(diagnostic_probe)
                diagnostic_probe.extend(chunk[:remaining_probe])
            keep = min(len(chunk), budget.remaining)
            if keep:
                target.extend(chunk[:keep])
                budget.remaining -= keep
            if keep < len(chunk):
                budget.truncated = True

    @staticmethod
    async def _discard(reader: _Readable | None) -> None:
        if reader is None:
            return
        while await reader.read(65536):
            pass

    @staticmethod
    async def _read_prefix(reader: _Readable | None) -> bytes:
        if reader is None:
            return b""
        prefix = bytearray()
        while True:
            chunk = await reader.read(65536)
            if not chunk:
                return bytes(prefix)
            if len(prefix) < 4096:
                prefix.extend(chunk[: 4096 - len(prefix)])

    @staticmethod
    async def _terminate(process: _Process) -> None:
        if process.returncode is not None:
            return
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=1.0)
        except TimeoutError:
            process.kill()
            await process.wait()
