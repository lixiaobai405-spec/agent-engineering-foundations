from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

from agent_foundations.execution.fake import FakeBackend
from agent_foundations.execution.models import ExecutionRequest, ExecutionResult
from agent_foundations.runtime.redaction import Redactor
from agent_foundations.tools.filesystem.path_policy import PathPolicy

VERSION_ARGV = ("git", "--version")
STATUS_L1 = ("git", "--no-pager", "status", "--porcelain", "-z")
MODERN_VERSION = b"git version 2.43.0\n"
OLD_VERSION = b"git version 2.14.1.windows.1\n"
PORCELAIN = b" M tracked.txt\0"


def _probe_module() -> Any:
    spec = importlib.util.find_spec("agent_foundations.tools.git.probe")
    assert spec is not None
    return importlib.import_module("agent_foundations.tools.git.probe")


def _service() -> Any:
    from agent_foundations.tools.git.service import (
        STATUS_ARGV,
        GitReadError,
        GitReadService,
        build_diff_argv,
        build_log_argv,
    )

    return STATUS_ARGV, GitReadError, GitReadService, build_diff_argv, build_log_argv


def _result(
    request: ExecutionRequest,
    stdout: bytes,
    *,
    exit_code: int = 0,
    stderr: bytes = b"",
    timed_out: bool = False,
) -> ExecutionResult:
    return ExecutionResult(
        execution_id=request.execution_id,
        exit_code=None if timed_out else exit_code,
        stdout=stdout,
        stderr=stderr,
        timed_out=timed_out,
        cancelled=False,
        output_truncated=False,
    )


def _service_with(tmp_path: Path, factory: Any) -> Any:
    _, _, GitReadService, _, _ = _service()
    project = tmp_path / "repo"
    project.mkdir(exist_ok=True)
    backend = FakeBackend(result_factory=factory)
    service = GitReadService(
        project,
        backend,
        PathPolicy(project),
        Redactor(project),
    )
    return service, backend


def test_parse_git_version_locked_shapes() -> None:
    module = _probe_module()
    assert module.parse_git_version(b"git version 2.43.0\n") == (2, 43, 0)
    assert module.parse_git_version(b"git version 2.14.1.windows.1") == (2, 14, 1)
    assert module.parse_git_version(b"git version 2.15\n") == (2, 15, 0)
    assert module.parse_git_version(b"git version 1.8.3.1\n") == (1, 8, 3)
    assert module.parse_git_version(b"not a version banner") is None


@pytest.mark.asyncio
async def test_l0_usage_falls_back_to_l1_once(tmp_path: Path) -> None:
    status_argv, _, _, _, _ = _service()

    def factory(request: ExecutionRequest) -> ExecutionResult:
        if request.argv == VERSION_ARGV:
            return _result(request, MODERN_VERSION)
        if request.argv == status_argv:
            return _result(
                request,
                b"",
                exit_code=129,
                stderr=b"unknown option `no-optional-locks'\n",
            )
        if request.argv == STATUS_L1:
            return _result(request, PORCELAIN)
        raise AssertionError(f"unexpected argv: {request.argv}")

    service, backend = _service_with(tmp_path, factory)
    result = await service.status()
    assert [entry.path for entry in result.entries] == ["tracked.txt"]
    assert [request.argv for request in backend.requests] == [
        VERSION_ARGV,
        status_argv,
        STATUS_L1,
    ]


@pytest.mark.asyncio
async def test_not_a_repository_does_not_send_l1(tmp_path: Path) -> None:
    status_argv, GitReadError, _, _, _ = _service()

    def factory(request: ExecutionRequest) -> ExecutionResult:
        if request.argv == VERSION_ARGV:
            return _result(request, MODERN_VERSION)
        if request.argv == status_argv:
            return _result(
                request,
                b"",
                exit_code=128,
                stderr=b"fatal: not a git repository (or any of the parent directories): .git\n",
            )
        raise AssertionError(f"L1 must not run: {request.argv}")

    service, backend = _service_with(tmp_path, factory)
    with pytest.raises(GitReadError) as not_repo:
        await service.status()
    assert not_repo.value.code == "NOT_A_REPOSITORY"
    assert [request.argv for request in backend.requests] == [VERSION_ARGV, status_argv]


@pytest.mark.asyncio
async def test_git_version_is_probed_once_per_instance(tmp_path: Path) -> None:
    status_argv, _, _, _, _ = _service()

    def factory(request: ExecutionRequest) -> ExecutionResult:
        if request.argv == VERSION_ARGV:
            return _result(request, MODERN_VERSION)
        if request.argv == status_argv:
            return _result(request, PORCELAIN)
        raise AssertionError(request.argv)

    service, backend = _service_with(tmp_path, factory)
    await service.status()
    await service.status()
    version_calls = [request for request in backend.requests if request.argv == VERSION_ARGV]
    assert len(version_calls) == 1
    assert len(backend.requests) == 3


@pytest.mark.asyncio
async def test_old_git_skips_l0_and_uses_l1(tmp_path: Path) -> None:
    status_argv, _, _, _, _ = _service()

    def factory(request: ExecutionRequest) -> ExecutionResult:
        if request.argv == VERSION_ARGV:
            return _result(request, OLD_VERSION)
        if request.argv == STATUS_L1:
            return _result(request, PORCELAIN)
        raise AssertionError(f"L0 must be skipped for old git: {request.argv}")

    service, backend = _service_with(tmp_path, factory)
    result = await service.status()
    assert result.entries[0].path == "tracked.txt"
    assert status_argv not in [request.argv for request in backend.requests]
    assert [request.argv for request in backend.requests] == [VERSION_ARGV, STATUS_L1]


@pytest.mark.asyncio
async def test_unparseable_version_still_tries_l0(tmp_path: Path) -> None:
    status_argv, _, _, _, _ = _service()

    def factory(request: ExecutionRequest) -> ExecutionResult:
        if request.argv == VERSION_ARGV:
            return _result(request, b"git version mystery\n")
        if request.argv == status_argv:
            return _result(request, PORCELAIN)
        raise AssertionError(request.argv)

    service, backend = _service_with(tmp_path, factory)
    await service.status()
    assert [request.argv for request in backend.requests] == [VERSION_ARGV, status_argv]


@pytest.mark.asyncio
async def test_version_nonzero_or_timeout_skips_git_ops(tmp_path: Path) -> None:
    _, GitReadError, _, _, _ = _service()

    def failed_version(request: ExecutionRequest) -> ExecutionResult:
        if request.argv == VERSION_ARGV:
            return _result(request, b"", exit_code=1, stderr=b"git: command failed\n")
        raise AssertionError(f"ops must not run: {request.argv}")

    failed_service, failed_backend = _service_with(tmp_path, failed_version)
    with pytest.raises(GitReadError) as failed:
        await failed_service.status()
    assert failed.value.code == "GIT_FAILED"
    assert [request.argv for request in failed_backend.requests] == [VERSION_ARGV]

    def timed_version(request: ExecutionRequest) -> ExecutionResult:
        if request.argv == VERSION_ARGV:
            return _result(request, b"", timed_out=True)
        raise AssertionError(f"ops must not run: {request.argv}")

    timeout_service, timeout_backend = _service_with(tmp_path, timed_version)
    with pytest.raises(GitReadError) as timeout:
        await timeout_service.diff(path=None)
    assert timeout.value.code == "GIT_TIMEOUT"
    assert [request.argv for request in timeout_backend.requests] == [VERSION_ARGV]
