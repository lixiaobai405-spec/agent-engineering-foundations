from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, Literal

import pytest

from agent_foundations.execution.fake import FakeBackend
from agent_foundations.execution.models import ExecutionRequest, ExecutionResult
from agent_foundations.runtime.redaction import Redactor
from agent_foundations.tools.command.classifier import CommandClassifier
from agent_foundations.tools.command.config import default_project_command_manifest
from agent_foundations.tools.command.models import CommandSpec
from agent_foundations.tools.filesystem.path_policy import PathPolicy

PLACEHOLDER = "sk-test_placeholder_not_real"


def _require_service() -> Any:
    try:
        spec = importlib.util.find_spec("agent_foundations.tools.git.service")
    except ModuleNotFoundError:
        spec = None
    assert spec is not None, "git read service is missing"
    from agent_foundations.tools.git.service import (
        GIT_ISOLATED_ENV,
        STATUS_ARGV,
        GitReadError,
        GitReadService,
        build_diff_argv,
        build_log_argv,
    )

    return (
        GIT_ISOLATED_ENV,
        STATUS_ARGV,
        GitReadError,
        GitReadService,
        build_diff_argv,
        build_log_argv,
    )


def _result(request: ExecutionRequest, stdout: bytes, *, exit_code: int = 0) -> ExecutionResult:
    return ExecutionResult(
        execution_id=request.execution_id,
        exit_code=exit_code,
        stdout=stdout,
        stderr=b"",
        timed_out=False,
        cancelled=False,
        output_truncated=False,
    )


def _sandbox_manifest() -> Any:
    from agent_foundations.execution.sandbox_manifest import (
        SandboxImageProvenance,
        SandboxManifest,
    )

    def provenance(profile: Literal["python", "node"]) -> SandboxImageProvenance:
        return SandboxImageProvenance(
            profile=profile,
            image_tag=f"agent-foundations-sandbox-{profile}:phase2d",
            base_repo_digest=f"{profile}@sha256:{'a' * 64}",
            lockfile_sha256="b" * 64,
            final_image_id=f"sha256:{'c' * 64}",
            final_repo_digest=f"agent-foundations-sandbox-{profile}@sha256:{'d' * 64}",
        )

    return SandboxManifest(python=provenance("python"), node=provenance("node"))


@pytest.mark.asyncio
async def test_status_uses_fixed_argv_isolated_env_and_readonly_mount(tmp_path: Path) -> None:
    env, status_argv, _, GitReadService, _, _ = _require_service()
    project = tmp_path / "repo"
    project.mkdir()
    backend = FakeBackend(
        result_factory=lambda request: _result(request, b"?? untracked.txt\0M  staged.py\0"),
    )
    service = GitReadService(
        project,
        backend,
        PathPolicy(project),
        Redactor(project, secrets=(PLACEHOLDER,)),
    )
    result = await service.status()
    assert [entry.path for entry in result.entries] == ["untracked.txt", "staged.py"]
    assert result.untracked == ("untracked.txt",)
    assert result.staged == ("staged.py",)
    assert backend.requests[0].argv == ("git", "--version")
    request = backend.requests[1]
    assert request.argv == status_argv
    assert request.mount_mode == "read_only"
    assert request.sandbox_profile == "legacy_patch"
    assert request.env == env
    assert dict(env)["GIT_CONFIG_NOSYSTEM"] == "1"
    assert dict(env)["HOME"] == "/opt/isolated-home"
    assert "--no-pager" in request.argv
    assert "GIT_PAGER" not in dict(env)
    assert "--pretty" not in request.argv


@pytest.mark.asyncio
async def test_diff_and_log_fixed_argv_redaction_and_truncation(tmp_path: Path) -> None:
    _, _, _, GitReadService, build_diff_argv, build_log_argv = _require_service()
    project = tmp_path / "repo"
    project.mkdir()
    (project / "src").mkdir()
    (project / "src" / "a.py").write_text("print(1)\n", encoding="utf-8")
    secret_patch = f"diff --git a/src/a.py b/src/a.py\n+token {PLACEHOLDER}\n".encode()
    backend = FakeBackend(
        result_factory=lambda request: _result(
            request,
            b"git version 2.43.0\n"
            if request.argv == ("git", "--version")
            else secret_patch
            if "diff" in request.argv
            else b"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\tinit\n",
        ),
    )
    service = GitReadService(
        project,
        backend,
        PathPolicy(project),
        Redactor(project, secrets=(PLACEHOLDER,)),
    )
    diff = await service.diff(path="src/a.py", staged=False, max_bytes=200000)
    assert PLACEHOLDER not in diff.patch
    assert "[REDACTED]" in diff.patch
    assert diff.path == "src/a.py"
    assert backend.requests[0].argv == ("git", "--version")
    assert backend.requests[1].argv == build_diff_argv(path="src/a.py", staged=False)
    assert backend.requests[1].argv[-2:] == ("--", "src/a.py")
    log = await service.log(limit=20)
    assert log.entries[0].subject == "init"
    assert backend.requests[2].argv == build_log_argv(20)
    huge = FakeBackend(
        result_factory=lambda request: _result(
            request,
            b"git version 2.43.0\n" if request.argv == ("git", "--version") else b"x" * 50,
        )
    )
    truncated = await GitReadService(
        project,
        huge,
        PathPolicy(project),
        Redactor(project),
    ).diff(path=None, staged=True, max_bytes=16)
    assert truncated.truncated is True
    assert truncated.byte_count == 16
    assert huge.requests[0].argv == ("git", "--version")
    assert "--cached" in huge.requests[1].argv
    assert huge.requests[1].argv == build_diff_argv(path=None, staged=True)


@pytest.mark.asyncio
async def test_diff_rejects_unsafe_paths_and_non_repository(tmp_path: Path) -> None:
    _, _, GitReadError, GitReadService, _, _ = _require_service()
    project = tmp_path / "repo"
    project.mkdir()
    (project / ".env").write_text("SECRET=1\n", encoding="utf-8")
    (project / "id_rsa").write_text("-----BEGIN FAKE PRIVATE KEY-----\n", encoding="utf-8")
    (project / "file.py").write_text("ok\n", encoding="utf-8")
    (project / "subdir").mkdir()
    link = project / "link.py"
    try:
        link.symlink_to(project / "file.py")
        symlink_ok = True
    except OSError:
        symlink_ok = False
    backend = FakeBackend(
        result_factory=lambda request: _result(
            request,
            b"git version 2.43.0\n",
        )
        if request.argv == ("git", "--version")
        else _result(
            request,
            b"fatal: not a git repository\n",
            exit_code=128,
        ),
    )
    service = GitReadService(
        project,
        backend,
        PathPolicy(project),
        Redactor(project),
    )
    with pytest.raises(GitReadError) as not_repo:
        await service.status()
    assert not_repo.value.code == "NOT_A_REPOSITORY"
    with pytest.raises(GitReadError) as env_exc:
        await service.diff(path=".env")
    assert env_exc.value.code in {"SENSITIVE_PATH", "PATH_DENIED"}
    with pytest.raises(GitReadError):
        await service.diff(path="id_rsa")
    with pytest.raises(GitReadError):
        await service.diff(path="../outside.py")
    with pytest.raises(GitReadError):
        await service.diff(path=str(project / "file.py"))
    with pytest.raises(GitReadError):
        await service.diff(path="subdir")
    if symlink_ok:
        with pytest.raises(GitReadError):
            await service.diff(path="link.py")
    with pytest.raises(GitReadError):
        await service.log(limit=0)
    with pytest.raises(GitReadError):
        await service.log(limit=101)
    with pytest.raises(GitReadError):
        await service.diff(path="src/a.py", max_bytes=200001)


def test_diff_and_log_argv_place_isolation_flags_after_subcommand() -> None:
    env, _, _, _, build_diff_argv, build_log_argv = _require_service()
    diff_argv = list(build_diff_argv(path=None, staged=False))
    log_argv = list(build_log_argv(20))
    assert diff_argv.index("--no-ext-diff") > diff_argv.index("diff")
    assert diff_argv.index("--no-textconv") > diff_argv.index("diff")
    assert log_argv.index("--no-ext-diff") > log_argv.index("log")
    assert log_argv.index("--no-textconv") > log_argv.index("log")
    assert diff_argv[:4] == ["git", "--no-pager", "--no-optional-locks", "diff"]
    assert log_argv[:4] == ["git", "--no-pager", "--no-optional-locks", "log"]
    env_map = dict(env)
    assert env_map["GIT_CONFIG_COUNT"] == "2"
    assert "core.autocrlf" in env_map.values()
    assert env_map["GIT_CONFIG_VALUE_1"] == "true"


@pytest.mark.asyncio
async def test_unknown_option_and_timeout_are_not_missing_repository(
    tmp_path: Path,
) -> None:
    _, status_argv, GitReadError, GitReadService, build_diff_argv, _ = _require_service()
    project = tmp_path / "repo"
    project.mkdir()
    version_argv = ("git", "--version")
    diff_l0 = build_diff_argv(path=None, staged=False)
    diff_l1 = ("git", "--no-pager", "diff", "--no-color")

    def unknown_option(request: ExecutionRequest) -> ExecutionResult:
        if request.argv == version_argv:
            return ExecutionResult(
                execution_id=request.execution_id,
                exit_code=0,
                stdout=b"git version 2.43.0\n",
                stderr=b"",
                timed_out=False,
                cancelled=False,
                output_truncated=False,
            )
        return ExecutionResult(
            execution_id=request.execution_id,
            exit_code=129,
            stdout=b"",
            stderr=b"unknown option `no-ext-diff'\n",
            timed_out=False,
            cancelled=False,
            output_truncated=False,
        )

    usage_backend = FakeBackend(result_factory=unknown_option)
    usage_service = GitReadService(
        project,
        usage_backend,
        PathPolicy(project),
        Redactor(project),
    )
    with pytest.raises(GitReadError) as usage:
        await usage_service.diff(path=None, staged=False)
    assert usage.value.code == "GIT_USAGE_ERROR"
    assert usage.value.code != "NOT_A_REPOSITORY"
    assert [request.argv for request in usage_backend.requests] == [
        version_argv,
        diff_l0,
        diff_l1,
    ]

    def timed_out(request: ExecutionRequest) -> ExecutionResult:
        if request.argv == version_argv:
            return ExecutionResult(
                execution_id=request.execution_id,
                exit_code=0,
                stdout=b"git version 2.43.0\n",
                stderr=b"",
                timed_out=False,
                cancelled=False,
                output_truncated=False,
            )
        return ExecutionResult(
            execution_id=request.execution_id,
            exit_code=None,
            stdout=b"",
            stderr=b"",
            timed_out=True,
            cancelled=False,
            output_truncated=False,
        )

    timeout_backend = FakeBackend(result_factory=timed_out)
    timeout_service = GitReadService(
        project,
        timeout_backend,
        PathPolicy(project),
        Redactor(project),
    )
    with pytest.raises(GitReadError) as timeout:
        await timeout_service.status()
    assert timeout.value.code == "GIT_TIMEOUT"
    assert timeout.value.code != "NOT_A_REPOSITORY"
    assert [request.argv for request in timeout_backend.requests] == [
        version_argv,
        status_argv,
    ]


def test_classifier_still_hard_denies_git() -> None:
    _require_service()
    classifier = CommandClassifier(project_fingerprint="a" * 64)
    manifest = default_project_command_manifest(
        project_fingerprint="a" * 64,
        sandbox=_sandbox_manifest(),
    )
    outcome = classifier.classify(CommandSpec(argv=("git", "status"), cwd="."), manifest)
    assert outcome.hard_denied is True
    assert outcome.rule_id == "builtin.command.git-denied"
