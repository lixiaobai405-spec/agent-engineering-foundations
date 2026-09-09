from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from agent_foundations.execution.fake import FakeBackend
from agent_foundations.execution.models import ExecutionRequest, ExecutionResult
from agent_foundations.runtime.redaction import Redactor
from agent_foundations.tools.filesystem.path_policy import PathPolicy

PLACEHOLDER = "sk-test_placeholder_not_real"
WRITE_TOOLS = {
    "git_add",
    "git_commit",
    "git_push",
    "git_reset",
    "git_checkout",
    "git_clean",
    "git_restore",
    "git_rebase",
    "git_merge",
    "git_submodule_update",
}


def _require_git() -> Any:
    try:
        spec = importlib.util.find_spec("agent_foundations.tools.git.service")
    except ModuleNotFoundError:
        spec = None
    assert spec is not None, "git read service is missing"
    from agent_foundations.cli.main import build_tool_registry
    from agent_foundations.tools.git.service import GitReadService
    from agent_foundations.tools.git.status import GitStatusTool

    return build_tool_registry, GitReadService, GitStatusTool


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


def test_registry_opt_in_exposes_read_tools_only(tmp_path: Path) -> None:
    build_tool_registry, GitReadService, _ = _require_git()
    project = tmp_path / "repo"
    project.mkdir()
    backend = FakeBackend(result_factory=lambda request: _result(request, b""))
    registry = build_tool_registry(
        project,
        include_git_read=True,
        git_backend_factory=lambda _root: backend,
    )
    names = {entry.tool.name for entry in registry.registered_tools()}
    assert {"git_status", "git_diff", "git_log"} <= names
    assert names.isdisjoint(WRITE_TOOLS)
    default_registry = build_tool_registry(project)
    default_names = {entry.tool.name for entry in default_registry.registered_tools()}
    assert default_names.isdisjoint({"git_status", "git_diff", "git_log"})


@pytest.mark.asyncio
async def test_submodule_is_visible_without_update_api(tmp_path: Path) -> None:
    _, GitReadService, GitStatusTool = _require_git()
    project = tmp_path / "repo"
    project.mkdir()
    backend = FakeBackend(
        result_factory=lambda request: _result(request, b" S vendor/lib\0?? extra.txt\0"),
    )
    service = GitReadService(
        project,
        backend,
        PathPolicy(project),
        Redactor(project),
    )
    result = await GitStatusTool(service).execute({})
    assert result.success is True
    payload = json.loads(result.content)
    paths = [entry["path"] for entry in payload["entries"]]
    assert "vendor/lib" in paths
    assert "extra.txt" in payload["untracked"]
    assert "git_submodule_update" not in dir(service)


@pytest.mark.asyncio
async def test_malicious_config_is_not_inherited_from_fake_backend(tmp_path: Path) -> None:
    _, GitReadService, GitStatusTool = _require_git()
    project = tmp_path / "repo"
    project.mkdir()
    backend = FakeBackend(
        result_factory=lambda request: _result(request, b""),
    )
    service = GitReadService(
        project,
        backend,
        PathPolicy(project),
        Redactor(project, secrets=(PLACEHOLDER,)),
    )
    await GitStatusTool(service).execute({})
    env = dict(backend.requests[0].env)
    assert env["GIT_CONFIG_NOSYSTEM"] == "1"
    assert env["HOME"] == "/opt/isolated-home"
    assert env["GIT_CONFIG_GLOBAL"].endswith("gitconfig")
    assert Path.home().as_posix() not in env["HOME"]
    assert "GIT_PAGER" not in env


def _init_temp_repo(project: Path) -> None:
    env = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0"}
    subprocess.run(["git", "init"], cwd=project, check=True, capture_output=True, env=env)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=task21@example.test",
            "-c",
            "user.name=Task21",
            "add",
            "tracked.txt",
        ],
        cwd=project,
        check=True,
        capture_output=True,
        env=env,
    )
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=task21@example.test",
            "-c",
            "user.name=Task21",
            "commit",
            "-m",
            "init",
        ],
        cwd=project,
        check=True,
        capture_output=True,
        env=env,
    )


def _af_residue_names() -> list[str]:
    residue = subprocess.run(
        ["docker", "ps", "-a", "--filter", "name=af-", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    return [line for line in residue.stdout.splitlines() if line.strip()]


@pytest.mark.docker
@pytest.mark.asyncio
async def test_sandbox_readonly_git_smoke(
    tmp_path: Path,
    pytestconfig: pytest.Config,
) -> None:
    if pytestconfig.getoption("-m") != "docker":
        pytest.skip("requires explicit -m docker authorization")
    _require_git()
    from agent_foundations.execution.docker import DockerBackend
    from agent_foundations.tools.git.diff import GitDiffTool
    from agent_foundations.tools.git.log import GitLogTool
    from agent_foundations.tools.git.service import GitReadService
    from agent_foundations.tools.git.status import GitStatusTool

    project = tmp_path / "repo"
    project.mkdir()
    (project / "tracked.txt").write_text("hello\n", encoding="utf-8")
    _init_temp_repo(project)
    (project / "tracked.txt").write_text("hello\nchanged\n", encoding="utf-8")
    before = sorted(path.name for path in project.iterdir())
    service = GitReadService(
        project,
        DockerBackend(project),
        PathPolicy(project),
        Redactor(project),
    )
    result = await GitStatusTool(service).execute({})
    assert result.success is True
    after = sorted(path.name for path in project.iterdir())
    assert after == before
    payload = json.loads(result.content)
    assert any(entry["path"] == "tracked.txt" for entry in payload["entries"])
    diff_result = await GitDiffTool(service).execute({"path": "tracked.txt", "staged": False})
    assert diff_result.success is True
    diff_patch = str((diff_result.metadata or {}).get("patch", diff_result.content))
    assert "changed" in diff_patch
    log_result = await GitLogTool(service).execute({"limit": 5})
    assert log_result.success is True
    log_payload = json.loads(log_result.content)
    assert log_payload["entries"]
    assert log_payload["entries"][0]["subject"] == "init"
    leftover = _af_residue_names()
    assert leftover == [], leftover
    from agent_foundations.execution.docker import DockerCommandBuilder
    from agent_foundations.execution.models import ExecutionRequest
    from agent_foundations.tools.git.service import GIT_ISOLATED_ENV, STATUS_ARGV

    inspect_argv = DockerCommandBuilder(project).build(
        ExecutionRequest(
            execution_id=str(uuid4()),
            run_id=str(uuid4()),
            capability_id=str(uuid4()),
            argv=STATUS_ARGV,
            cwd=".",
            mount_mode="read_only",
            sandbox_profile="legacy_patch",
            timeout_seconds=30,
            max_output_bytes=256000,
            env=GIT_ISOLATED_ENV,
        )
    )
    assert inspect_argv[inspect_argv.index("--user") + 1] == "65532:65532"
    assert inspect_argv[inspect_argv.index("--network") + 1] == "none"
    assert "--read-only" in inspect_argv
    mount = inspect_argv[inspect_argv.index("--mount") + 1]
    assert mount.endswith(",readonly")
    mounts = [
        inspect_argv[index + 1]
        for index, part in enumerate(inspect_argv)
        if part == "--mount"
    ]
    assert mounts == [mount]
    assert "target=/workspace" in mount
    assert "-v" not in inspect_argv
    assert "HOME=/opt/isolated-home" in inspect_argv
    assert dict(GIT_ISOLATED_ENV)["HOME"] == "/opt/isolated-home"
