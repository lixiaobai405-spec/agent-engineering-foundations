from __future__ import annotations

import asyncio
import importlib.util
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest


def _execution() -> tuple[Any, ...]:
    assert importlib.util.find_spec("agent_foundations.execution") is not None, (
        "Task 14 execution package is missing"
    )
    assert importlib.util.find_spec("agent_foundations.execution.docker") is not None, (
        "Task 14 DockerBackend is missing"
    )
    from agent_foundations.execution.backend import (
        BackendLaunchError,
        BackendUnavailableError,
        ExecutionConflictError,
    )
    from agent_foundations.execution.docker import DockerBackend, DockerCommandBuilder
    from agent_foundations.execution.models import ExecutionRequest

    return (
        DockerCommandBuilder,
        DockerBackend,
        BackendUnavailableError,
        ExecutionConflictError,
        BackendLaunchError,
        ExecutionRequest,
    )


def _request(**changes: object) -> Any:
    *_, ExecutionRequest = _execution()
    values: dict[str, object] = {
        "execution_id": str(uuid4()),
        "run_id": str(uuid4()),
        "capability_id": str(uuid4()),
        "argv": ("python", "-c", "print('ok')"),
        "cwd": ".",
        "mount_mode": "read_only",
        "timeout_seconds": 30,
        "max_output_bytes": 8,
    }
    values.update(changes)
    return ExecutionRequest.model_validate(values)


def test_builder_emits_fixed_security_argv_and_command_after_image(tmp_path: Path) -> None:
    DockerCommandBuilder, *_ = _execution()
    workspace = tmp_path / "project"
    workspace.mkdir()
    request = _request(argv=("--privileged", "value"))
    argv = DockerCommandBuilder(workspace).build(request)

    assert argv[:2] == ("docker", "run")
    assert "--rm" in argv
    assert argv[argv.index("--name") + 1] == f"af-{request.execution_id}"
    assert argv[argv.index("--network") + 1] == "none"
    assert "--read-only" in argv
    assert argv[argv.index("--cap-drop") + 1] == "ALL"
    assert argv[argv.index("--security-opt") + 1] == "no-new-privileges"
    assert argv[argv.index("--user") + 1] == "65532:65532"
    assert argv[argv.index("--pids-limit") + 1] == "64"
    assert argv[argv.index("--memory") + 1] == "512m"
    assert argv[argv.index("--cpus") + 1] == "1.0"
    assert argv[argv.index("--pull") + 1] == "never"
    image_index = argv.index("agent-foundations-sandbox:phase2")
    assert argv[image_index + 1 :] == request.argv
    assert image_index < argv.index("--privileged")
    assert all("docker.sock" not in item.casefold() for item in argv)


def test_builder_uses_one_mount_argument_and_read_only_is_explicit(tmp_path: Path) -> None:
    DockerCommandBuilder, *_ = _execution()
    workspace = tmp_path / "project"
    workspace.mkdir()
    builder = DockerCommandBuilder(workspace)

    readonly = builder.build(_request(mount_mode="read_only"))
    writable = builder.build(_request(mount_mode="project_write"))
    readonly_mount = readonly[readonly.index("--mount") + 1]
    writable_mount = writable[writable.index("--mount") + 1]

    assert readonly.count("--mount") == 1
    assert writable.count("--mount") == 1
    assert f"source={workspace.resolve(strict=True)}" in readonly_mount
    assert "target=/workspace" in readonly_mount
    assert readonly_mount.endswith(",readonly")
    assert ",readonly" not in writable_mount
    assert "-v" not in readonly


@pytest.mark.parametrize("name", ["project,comma", ".ssh", ".aws", ".azure", ".kube"])
def test_builder_rejects_mount_roots_that_can_expose_or_break_mount_syntax(
    tmp_path: Path,
    name: str,
) -> None:
    DockerCommandBuilder, *_ = _execution()
    workspace = tmp_path / name
    workspace.mkdir()
    with pytest.raises(ValueError):
        DockerCommandBuilder(workspace)


def test_builder_rejects_home_root_and_unresolved_workspace() -> None:
    DockerCommandBuilder, *_ = _execution()
    with pytest.raises(ValueError):
        DockerCommandBuilder(Path.home())
    with pytest.raises(ValueError):
        DockerCommandBuilder(Path.home() / f"missing-{uuid4()}")


def test_builder_rejects_cwd_reparse_escape(tmp_path: Path) -> None:
    DockerCommandBuilder, *_ = _execution()
    workspace = tmp_path / "project"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    link = workspace / "escape"
    try:
        os.symlink(outside, link, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is unavailable on this Windows host")

    with pytest.raises(ValueError):
        DockerCommandBuilder(workspace).build(_request(cwd="escape"))


class _Reader:
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks
        self.read_count = 0

    async def read(self, _size: int) -> bytes:
        self.read_count += 1
        return self._chunks.pop(0) if self._chunks else b""


class _Writer:
    def __init__(self) -> None:
        self.data = bytearray()
        self.closed = False

    def write(self, data: bytes) -> None:
        self.data.extend(data)

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


class _BlockingWriter(_Writer):
    def __init__(self) -> None:
        super().__init__()
        self.draining = asyncio.Event()

    async def drain(self) -> None:
        self.draining.set()
        await asyncio.Event().wait()


class _BlockingReader(_Reader):
    def __init__(self) -> None:
        super().__init__([])
        self.reading = asyncio.Event()

    async def read(self, _size: int) -> bytes:
        self.reading.set()
        await asyncio.Event().wait()
        return b""


class _Process:
    def __init__(
        self,
        *,
        stdout: list[bytes] | None = None,
        stderr: list[bytes] | None = None,
        returncode: int = 0,
        blocked: bool = False,
    ) -> None:
        self.stdout = _Reader(stdout or [])
        self.stderr = _Reader(stderr or [])
        self.stdin = _Writer()
        self.returncode: int | None = None if blocked else returncode
        self._final_returncode = returncode
        self._done = asyncio.Event()
        if not blocked:
            self._done.set()
        self.terminated = False
        self.killed = False

    async def wait(self) -> int:
        await self._done.wait()
        if self.returncode is None:
            self.returncode = self._final_returncode
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = -15
        self._done.set()

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9
        self._done.set()


class _Factory:
    def __init__(self, process: _Process | BaseException) -> None:
        self.process = process
        self.argvs: list[tuple[str, ...]] = []
        self.spawned = asyncio.Event()

    async def __call__(self, argv: tuple[str, ...]) -> _Process:
        self.argvs.append(argv)
        self.spawned.set()
        if isinstance(self.process, BaseException):
            raise self.process
        return self.process


class _DelayedFactory:
    def __init__(self, process: _Process) -> None:
        self.process = process
        self.argvs: list[tuple[str, ...]] = []
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def __call__(self, argv: tuple[str, ...]) -> _Process:
        self.argvs.append(argv)
        self.entered.set()
        await self.release.wait()
        return self.process


class _SequenceFactory:
    def __init__(self, outcomes: list[_Process | BaseException]) -> None:
        self.outcomes = outcomes
        self.argvs: list[tuple[str, ...]] = []

    async def __call__(self, argv: tuple[str, ...]) -> _Process:
        self.argvs.append(argv)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


@pytest.mark.asyncio
async def test_backend_bounds_combined_output_but_drains_both_pipes(tmp_path: Path) -> None:
    _Builder, DockerBackend, *_ = _execution()
    workspace = tmp_path / "project"
    workspace.mkdir()
    process = _Process(stdout=[b"123456", b"789"], stderr=[b"abc", b"def"])
    backend = DockerBackend(workspace, process_factory=_Factory(process))

    result = await backend.execute(_request(max_output_bytes=8, stdin=b"input"))

    assert len(result.stdout) + len(result.stderr) == 8
    assert result.output_truncated is True
    assert process.stdout.read_count >= 3
    assert process.stderr.read_count >= 3
    assert bytes(process.stdin.data) == b"input"
    assert process.stdin.closed is True


@pytest.mark.asyncio
async def test_backend_cancel_targets_exact_active_execution_and_duplicate_fails(
    tmp_path: Path,
) -> None:
    _Builder, DockerBackend, _Unavailable, ExecutionConflictError, *_ = _execution()
    workspace = tmp_path / "project"
    workspace.mkdir()
    request = _request()
    process = _Process(blocked=True)
    factory = _Factory(process)
    cleanup_factory = _Factory(_Process())
    backend = DockerBackend(
        workspace,
        process_factory=factory,
        cleanup_factory=cleanup_factory,
    )
    running = asyncio.create_task(backend.execute(request))
    await factory.spawned.wait()

    with pytest.raises(ExecutionConflictError):
        await backend.execute(request)
    await backend.cancel(str(uuid4()))
    assert process.terminated is False
    await backend.cancel(request.execution_id)
    await backend.cancel(request.execution_id)
    result = await running

    assert result.cancelled is True
    assert process.terminated is True
    assert backend.active_execution_ids == ()
    assert all("prune" not in part for argv in factory.argvs for part in argv)
    assert cleanup_factory.argvs == [
        ("docker", "rm", "--force", f"af-{request.execution_id}")
    ]


@pytest.mark.asyncio
async def test_backend_timeout_cleans_only_exact_container(tmp_path: Path) -> None:
    _Builder, DockerBackend, *_ = _execution()
    workspace = tmp_path / "project"
    workspace.mkdir()
    request = _request(timeout_seconds=1)
    process = _Process(blocked=True)
    cleanup_factory = _Factory(_Process())
    backend = DockerBackend(
        workspace,
        process_factory=_Factory(process),
        cleanup_factory=cleanup_factory,
    )

    result = await backend.execute(request)

    assert result.timed_out is True
    assert result.cancelled is False
    assert result.exit_code is None
    assert process.terminated is True
    assert cleanup_factory.argvs == [
        ("docker", "rm", "--force", f"af-{request.execution_id}")
    ]


@pytest.mark.asyncio
async def test_execute_task_cancellation_waits_for_exact_cleanup(tmp_path: Path) -> None:
    _Builder, DockerBackend, *_ = _execution()
    workspace = tmp_path / "project"
    workspace.mkdir()
    request = _request()
    process = _Process(blocked=True)
    process_factory = _Factory(process)
    cleanup_factory = _DelayedFactory(_Process())
    backend = DockerBackend(
        workspace,
        process_factory=process_factory,
        cleanup_factory=cleanup_factory,
    )
    running = asyncio.create_task(backend.execute(request))
    await asyncio.wait_for(process_factory.spawned.wait(), timeout=1)

    running.cancel()
    await asyncio.wait_for(cleanup_factory.entered.wait(), timeout=1)

    assert running.done() is False
    assert backend.active_execution_ids == (request.execution_id,)
    assert process.terminated is True

    cleanup_factory.release.set()
    with pytest.raises(asyncio.CancelledError):
        await running

    assert cleanup_factory.argvs == [
        ("docker", "rm", "--force", f"af-{request.execution_id}")
    ]
    assert backend.active_execution_ids == ()


@pytest.mark.asyncio
async def test_execute_task_cancellation_during_launch_still_cleans_exact_name(
    tmp_path: Path,
) -> None:
    _Builder, DockerBackend, *_ = _execution()
    workspace = tmp_path / "project"
    workspace.mkdir()
    request = _request()
    process = _Process(blocked=True)
    process_factory = _DelayedFactory(process)
    cleanup_factory = _Factory(_Process())
    backend = DockerBackend(
        workspace,
        process_factory=process_factory,
        cleanup_factory=cleanup_factory,
    )
    running = asyncio.create_task(backend.execute(request))
    await asyncio.wait_for(process_factory.entered.wait(), timeout=1)

    running.cancel()
    process_factory.release.set()
    with pytest.raises(asyncio.CancelledError):
        await running

    assert process.terminated is True
    assert cleanup_factory.argvs == [
        ("docker", "rm", "--force", f"af-{request.execution_id}")
    ]
    assert backend.active_execution_ids == ()


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel_point", ["stdin", "stdout"])
async def test_execute_task_cancellation_during_io_cleans_exact_container(
    tmp_path: Path,
    cancel_point: str,
) -> None:
    _Builder, DockerBackend, *_ = _execution()
    workspace = tmp_path / "project"
    workspace.mkdir()
    request = _request(stdin=b"input")
    process = _Process(blocked=cancel_point == "stdin")
    signal: asyncio.Event
    if cancel_point == "stdin":
        writer = _BlockingWriter()
        process.stdin = writer
        signal = writer.draining
    else:
        reader = _BlockingReader()
        process.stdout = reader
        signal = reader.reading
    cleanup_factory = _Factory(_Process())
    backend = DockerBackend(
        workspace,
        process_factory=_Factory(process),
        cleanup_factory=cleanup_factory,
    )
    running = asyncio.create_task(backend.execute(request))
    await asyncio.wait_for(signal.wait(), timeout=1)

    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running

    assert cleanup_factory.argvs == [
        ("docker", "rm", "--force", f"af-{request.execution_id}")
    ]
    assert backend.active_execution_ids == ()


@pytest.mark.asyncio
async def test_explicit_and_task_cancellation_share_one_cleanup(tmp_path: Path) -> None:
    _Builder, DockerBackend, *_ = _execution()
    workspace = tmp_path / "project"
    workspace.mkdir()
    request = _request()
    process = _Process(blocked=True)
    process_factory = _Factory(process)
    cleanup_factory = _DelayedFactory(_Process())
    backend = DockerBackend(
        workspace,
        process_factory=process_factory,
        cleanup_factory=cleanup_factory,
    )
    running = asyncio.create_task(backend.execute(request))
    await asyncio.wait_for(process_factory.spawned.wait(), timeout=1)
    explicit_cancel = asyncio.create_task(backend.cancel(request.execution_id))
    await asyncio.wait_for(cleanup_factory.entered.wait(), timeout=1)

    running.cancel()
    cleanup_factory.release.set()
    await explicit_cancel
    with pytest.raises(asyncio.CancelledError):
        await running

    assert len(cleanup_factory.argvs) == 1
    assert backend.active_execution_ids == ()


@pytest.mark.asyncio
async def test_failed_cleanup_is_observable_and_retryable(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _Builder, DockerBackend, *_ = _execution()
    workspace = tmp_path / "project"
    workspace.mkdir()
    request = _request()
    process = _Process(blocked=True)
    process_factory = _Factory(process)
    cleanup_factory = _SequenceFactory([OSError("cleanup unavailable"), _Process()])
    backend = DockerBackend(
        workspace,
        process_factory=process_factory,
        cleanup_factory=cleanup_factory,
    )
    running = asyncio.create_task(backend.execute(request))
    await asyncio.wait_for(process_factory.spawned.wait(), timeout=1)

    await backend.cancel(request.execution_id)
    await backend.cancel(request.execution_id)
    result = await running

    assert result.cancelled is True
    assert len(cleanup_factory.argvs) == 2
    assert "retrying exact Docker cleanup" in caplog.text


@pytest.mark.asyncio
async def test_backend_daemon_error_is_unavailable_not_normal_nonzero(
    tmp_path: Path,
) -> None:
    _Builder, DockerBackend, BackendUnavailableError, *_ = _execution()
    workspace = tmp_path / "project"
    workspace.mkdir()
    process = _Process(stderr=[b"failed to connect to the docker API"], returncode=125)
    backend = DockerBackend(workspace, process_factory=_Factory(process))

    with pytest.raises(BackendUnavailableError):
        await backend.execute(_request())


@pytest.mark.asyncio
async def test_workload_nonzero_with_docker_like_stderr_is_normal_result(
    tmp_path: Path,
) -> None:
    _Builder, DockerBackend, *_ = _execution()
    workspace = tmp_path / "project"
    workspace.mkdir()
    process = _Process(stderr=[b"no such image"], returncode=7)
    backend = DockerBackend(workspace, process_factory=_Factory(process))

    result = await backend.execute(_request())

    assert result.exit_code == 7
    assert result.stderr == b"no such "


@pytest.mark.asyncio
async def test_unknown_docker_cli_exit_125_is_launch_error(tmp_path: Path) -> None:
    _Builder, DockerBackend, _Unavailable, _Conflict, BackendLaunchError, *_ = (
        _execution()
    )
    workspace = tmp_path / "project"
    workspace.mkdir()
    process = _Process(stderr=[b"docker rejected the request"], returncode=125)
    backend = DockerBackend(workspace, process_factory=_Factory(process))

    with pytest.raises(BackendLaunchError, match="before workload"):
        await backend.execute(_request())


@pytest.mark.asyncio
async def test_backend_missing_docker_is_unavailable_without_host_fallback(
    tmp_path: Path,
) -> None:
    _Builder, DockerBackend, BackendUnavailableError, *_ = _execution()
    workspace = tmp_path / "project"
    workspace.mkdir()
    factory = _Factory(FileNotFoundError("docker missing"))
    request = _request(argv=("python", "-c", "raise SystemExit(99)"))
    backend = DockerBackend(workspace, process_factory=factory)

    with pytest.raises(BackendUnavailableError):
        await backend.execute(request)

    assert len(factory.argvs) == 1
    assert factory.argvs[0][:2] == ("docker", "run")
