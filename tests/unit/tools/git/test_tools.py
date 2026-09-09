from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from agent_foundations.domain.tool import ToolResult
from agent_foundations.execution.fake import FakeBackend
from agent_foundations.execution.models import ExecutionRequest, ExecutionResult
from agent_foundations.runtime.redaction import Redactor
from agent_foundations.runtime.tool_execution import DirectToolCallExecutor, ToolExecutionContext
from agent_foundations.security.models import SideEffectKind, default_allowed_tools
from agent_foundations.tools.command.run_command import RunCommandTool
from agent_foundations.tools.filesystem.path_policy import PathPolicy
from agent_foundations.tools.patch.apply_patch import ApplyPatchTool

WRITE_TOOLS = (
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
)


def _require_tools() -> Any:
    try:
        spec = importlib.util.find_spec("agent_foundations.tools.git.status")
    except ModuleNotFoundError:
        spec = None
    assert spec is not None, "git_status tool is missing"
    from agent_foundations.tools.git.diff import GIT_DIFF_MANIFEST, GitDiffTool
    from agent_foundations.tools.git.log import GIT_LOG_MANIFEST, GitLogTool
    from agent_foundations.tools.git.service import GitReadService
    from agent_foundations.tools.git.status import GIT_STATUS_MANIFEST, GitStatusTool
    from agent_foundations.tools.registry import build_git_read_registered_tools

    return (
        GIT_STATUS_MANIFEST,
        GIT_DIFF_MANIFEST,
        GIT_LOG_MANIFEST,
        GitStatusTool,
        GitDiffTool,
        GitLogTool,
        GitReadService,
        build_git_read_registered_tools,
    )


def _result(request: ExecutionRequest, stdout: bytes) -> ExecutionResult:
    return ExecutionResult(
        execution_id=request.execution_id,
        exit_code=0,
        stdout=stdout,
        stderr=b"",
        timed_out=False,
        cancelled=False,
        output_truncated=False,
    )


def test_git_tool_manifests_and_no_write_api(tmp_path: Path) -> None:
    (
        status_manifest,
        diff_manifest,
        log_manifest,
        status_cls,
        diff_cls,
        log_cls,
        GitReadService,
        build_registered,
    ) = _require_tools()
    for manifest, name in (
        (status_manifest, "git_status"),
        (diff_manifest, "git_diff"),
        (log_manifest, "git_log"),
    ):
        assert manifest.name == name
        assert manifest.resource_kind == "project_path"
        assert manifest.operations == ("read",)
        assert manifest.side_effect is SideEffectKind.NONE
        assert manifest.sandbox_required is True
    project = tmp_path / "repo"
    project.mkdir()
    backend = FakeBackend(result_factory=lambda request: _result(request, b""))
    service = GitReadService(
        project,
        backend,
        PathPolicy(project),
        Redactor(project),
    )
    registered = build_registered(service, PathPolicy(project))
    names = {entry.tool.name for entry in registered}
    assert names == {"git_status", "git_diff", "git_log"}
    assert names.isdisjoint(WRITE_TOOLS)
    from agent_foundations.security.models import PermissionProfileName

    allowed = default_allowed_tools(PermissionProfileName.PROJECT_READ_ONLY)
    assert {"git_status", "git_diff", "git_log"} <= set(allowed)
    status_schema = status_cls(service).input_schema()
    assert status_schema["additionalProperties"] is False
    assert status_schema["properties"] == {}
    diff_schema = diff_cls(service).input_schema()
    assert set(diff_schema["properties"]) == {"path", "staged", "max_bytes"}
    assert "ref" not in diff_schema["properties"]
    assert "format" not in diff_schema["properties"]
    log_schema = log_cls(service).input_schema()
    assert set(log_schema["properties"]) == {"limit"}
    assert log_schema["properties"]["limit"]["maximum"] == 100


@pytest.mark.asyncio
async def test_direct_executor_runs_git_tools_via_backend_not_host_git(
    tmp_path: Path,
) -> None:
    *_, status_cls, diff_cls, log_cls, GitReadService, _ = _require_tools()
    project = tmp_path / "repo"
    project.mkdir()
    (project / "a.py").write_text("x\n", encoding="utf-8")
    backend = FakeBackend(
        result_factory=lambda request: _result(
            request,
            b"?? a.py\0" if "status" in request.argv else b"",
        ),
    )
    service = GitReadService(
        project,
        backend,
        PathPolicy(project),
        Redactor(project),
    )
    executor = DirectToolCallExecutor()
    context = ToolExecutionContext(
        session_id=str(uuid4()),
        root=project,
        tool_call_id="call-git",
        tool_name="git_status",
    )
    status_result = await executor.execute(status_cls(service), {}, context)
    assert isinstance(status_result, ToolResult)
    assert status_result.success is True
    assert backend.requests[0].argv[0] == "git"
    patch = await executor.execute(ApplyPatchTool(), {"path": "x"}, context)
    assert patch.error_code == "CONTROLLED_EXECUTION_REQUIRED"
    command = await executor.execute(RunCommandTool(), {"argv": ["git", "status"]}, context)
    assert command.error_code == "CONTROLLED_EXECUTION_REQUIRED"
    diff_result = await executor.execute(
        diff_cls(service),
        {"path": "a.py", "staged": False, "max_bytes": 200000},
        context,
    )
    log_result = await executor.execute(log_cls(service), {"limit": 5}, context)
    assert diff_result.success is True
    assert log_result.success is True
    assert all("create_subprocess" not in repr(request.argv) for request in backend.requests)
