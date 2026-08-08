from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest

from agent_foundations.chat.approvals import ApprovalCoordinator
from agent_foundations.chat.models import (
    AccessOperation,
    AccessScope,
    ApprovalRequest,
    ApprovalStatus,
    Conversation,
    PermissionMode,
    PolicyDecision,
    ResourceKind,
)
from agent_foundations.domain.errors import PathPolicyViolationError
from agent_foundations.domain.tool import ToolResult
from agent_foundations.runtime.tool_execution import ToolExecutionContext
from agent_foundations.tools.filesystem.list_directory import ListDirectoryTool
from agent_foundations.tools.filesystem.path_policy import PathPolicy
from agent_foundations.tools.filesystem.read_file import ReadFileTool
from agent_foundations.tools.filesystem.search_text import SearchTextTool

SESSION_ID = "22222222-2222-4222-8222-222222222222"


def _require_task9_components() -> tuple[Any, Any]:
    try:
        from agent_foundations.chat.tool_execution import (
            ApprovalAwareToolExecutor,
            FilesystemAccessController,
        )
    except ImportError as exc:
        raise AssertionError(f"Task 9 tool execution module missing: {exc}") from exc
    return FilesystemAccessController, ApprovalAwareToolExecutor


def _conversation(root: Path, mode: PermissionMode) -> Conversation:
    return Conversation(
        title="Tool execution study",
        project_root=str(root),
        permission_mode=mode,
    )


def _context(root: Path, tool_name: str, *, tool_call_id: str = "call-1") -> ToolExecutionContext:
    return ToolExecutionContext(
        session_id=SESSION_ID,
        root=root,
        tool_call_id=tool_call_id,
        tool_name=tool_name,
    )


class RecordingCoordinator:
    def __init__(
        self,
        decision: ApprovalStatus,
        on_request: Callable[[], None] | None = None,
    ) -> None:
        self.decision = decision
        self.on_request = on_request
        self.requests: list[ApprovalRequest] = []

    async def request(self, request: ApprovalRequest) -> ApprovalStatus:
        self.requests.append(request)
        if self.on_request is not None:
            self.on_request()
        return self.decision


class RecordingTool:
    description = "Record calls"

    def __init__(self, name: str) -> None:
        self.name = name
        self.calls: list[dict[str, Any]] = []

    def input_schema(self) -> dict[str, Any]:
        return {"type": "object"}

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        self.calls.append(dict(arguments))
        return ToolResult(success=True, content="original tool called")


@pytest.mark.parametrize(
    ("mode", "path_kind", "expected_scope", "expected_decision"),
    [
        (
            PermissionMode.PROJECT_READ_ONLY,
            "relative",
            AccessScope.PROJECT,
            PolicyDecision.ALLOW,
        ),
        (
            PermissionMode.PROJECT_READ_ONLY,
            "project-absolute",
            AccessScope.PROJECT,
            PolicyDecision.ALLOW,
        ),
        (
            PermissionMode.PROJECT_READ_ONLY,
            "external",
            AccessScope.EXTERNAL_EXACT_PATH,
            PolicyDecision.DENY,
        ),
        (
            PermissionMode.ASK_FOR_ACCESS,
            "relative",
            AccessScope.PROJECT,
            PolicyDecision.ALLOW,
        ),
        (
            PermissionMode.ASK_FOR_ACCESS,
            "project-absolute",
            AccessScope.PROJECT,
            PolicyDecision.ALLOW,
        ),
        (
            PermissionMode.ASK_FOR_ACCESS,
            "external",
            AccessScope.EXTERNAL_EXACT_PATH,
            PolicyDecision.ASK,
        ),
    ],
)
def test_filesystem_access_controller_decision_matrix(
    tmp_path: Path,
    mode: PermissionMode,
    path_kind: str,
    expected_scope: AccessScope,
    expected_decision: PolicyDecision,
) -> None:
    FilesystemAccessController, _ = _require_task9_components()
    project = tmp_path / "project"
    project.mkdir()
    project_file = project / "inside.txt"
    project_file.write_text("inside", encoding="utf-8")
    external = tmp_path / "external.txt"
    external.write_text("outside", encoding="utf-8")
    raw_path = {
        "relative": "inside.txt",
        "project-absolute": str(project_file),
        "external": str(external),
    }[path_kind]

    decision = FilesystemAccessController().decide(
        _conversation(project, mode),
        raw_path,
    )

    assert decision.resource is ResourceKind.FILESYSTEM
    assert decision.operation is AccessOperation.READ
    assert decision.scope is expected_scope
    assert decision.decision is expected_decision
    assert Path(decision.canonical_path) == (
        project_file.resolve() if path_kind != "external" else external.resolve()
    )


@pytest.mark.parametrize(
    "raw_path_factory",
    [
        pytest.param(lambda root: str(root / ".env"), id="sensitive"),
        pytest.param(lambda root: str(root / "missing.txt"), id="missing"),
        pytest.param(lambda root: str(root / "notes.txt") + ":secret", id="ads"),
        pytest.param(lambda root: r"\\server\share\notes.txt", id="unc"),
        pytest.param(lambda root: r"\\?\C:\notes.txt", id="device"),
    ],
)
@pytest.mark.parametrize("mode", list(PermissionMode))
def test_filesystem_access_controller_hard_rejects_invalid_targets(
    tmp_path: Path,
    raw_path_factory: Callable[[Path], str],
    mode: PermissionMode,
) -> None:
    FilesystemAccessController, _ = _require_task9_components()
    project = tmp_path / "project"
    project.mkdir()

    with pytest.raises(PathPolicyViolationError):
        FilesystemAccessController().decide(
            _conversation(project, mode),
            raw_path_factory(tmp_path),
        )


@pytest.mark.asyncio
async def test_executor_without_path_calls_original_tool(tmp_path: Path) -> None:
    _, ApprovalAwareToolExecutor = _require_task9_components()
    project = tmp_path / "project"
    project.mkdir()
    coordinator = RecordingCoordinator(ApprovalStatus.APPROVED)
    executor = ApprovalAwareToolExecutor(
        _conversation(project, PermissionMode.ASK_FOR_ACCESS),
        cast(ApprovalCoordinator, coordinator),
    )
    tool = RecordingTool("no_path_tool")
    arguments = {"query": "needle"}

    result = await executor.execute(
        tool,
        arguments,
        _context(project, tool.name),
    )

    assert result.success
    assert tool.calls == [arguments]
    assert coordinator.requests == []


@pytest.mark.asyncio
async def test_executor_relative_project_path_calls_original_tool(
    tmp_path: Path,
) -> None:
    _, ApprovalAwareToolExecutor = _require_task9_components()
    project = tmp_path / "project"
    project.mkdir()
    (project / "inside.txt").write_text("inside", encoding="utf-8")
    coordinator = RecordingCoordinator(ApprovalStatus.APPROVED)
    executor = ApprovalAwareToolExecutor(
        _conversation(project, PermissionMode.ASK_FOR_ACCESS),
        cast(ApprovalCoordinator, coordinator),
    )
    tool = RecordingTool("read_file")
    arguments = {"path": "inside.txt", "start_line": 2}

    await executor.execute(tool, arguments, _context(project, tool.name))

    assert tool.calls == [arguments]
    assert coordinator.requests == []


@pytest.mark.asyncio
async def test_executor_project_absolute_path_rewrites_without_mutating_input(
    tmp_path: Path,
) -> None:
    _, ApprovalAwareToolExecutor = _require_task9_components()
    project = tmp_path / "project"
    project.mkdir()
    inside = project / "nested" / "inside.txt"
    inside.parent.mkdir()
    inside.write_text("inside", encoding="utf-8")
    coordinator = RecordingCoordinator(ApprovalStatus.APPROVED)
    executor = ApprovalAwareToolExecutor(
        _conversation(project, PermissionMode.ASK_FOR_ACCESS),
        cast(ApprovalCoordinator, coordinator),
    )
    tool = RecordingTool("read_file")
    arguments = {"path": str(inside), "start_line": 2}
    original = dict(arguments)

    await executor.execute(tool, arguments, _context(project, tool.name))

    assert arguments == original
    assert tool.calls == [{"path": "nested/inside.txt", "start_line": 2}]
    assert coordinator.requests == []


@pytest.mark.asyncio
async def test_project_read_only_external_path_is_denied_without_approval(
    tmp_path: Path,
) -> None:
    _, ApprovalAwareToolExecutor = _require_task9_components()
    project = tmp_path / "project"
    project.mkdir()
    external = tmp_path / "external.txt"
    external.write_text("outside", encoding="utf-8")
    coordinator = RecordingCoordinator(ApprovalStatus.APPROVED)
    executor = ApprovalAwareToolExecutor(
        _conversation(project, PermissionMode.PROJECT_READ_ONLY),
        cast(ApprovalCoordinator, coordinator),
    )
    tool = ReadFileTool(PathPolicy(project))

    with pytest.raises(PathPolicyViolationError):
        await executor.execute(
            tool,
            {"path": str(external)},
            _context(project, tool.name),
        )
    assert coordinator.requests == []


@pytest.mark.asyncio
async def test_external_denial_returns_stable_result_without_execution(
    tmp_path: Path,
) -> None:
    _, ApprovalAwareToolExecutor = _require_task9_components()
    project = tmp_path / "project"
    project.mkdir()
    external = tmp_path / "external.txt"
    external.write_text("outside", encoding="utf-8")
    coordinator = RecordingCoordinator(ApprovalStatus.DENIED)
    conversation = _conversation(project, PermissionMode.ASK_FOR_ACCESS)
    executor = ApprovalAwareToolExecutor(
        conversation,
        cast(ApprovalCoordinator, coordinator),
    )
    tool = ReadFileTool(PathPolicy(project))

    result = await executor.execute(
        tool,
        {"path": str(external)},
        _context(project, tool.name),
    )

    assert result == ToolResult(
        success=False,
        content="access denied",
        error_code="access_denied",
    )
    assert str(external) not in result.content
    assert len(coordinator.requests) == 1
    request = coordinator.requests[0]
    assert request.conversation_id == conversation.conversation_id
    assert request.session_id == SESSION_ID
    assert request.tool_call_id == "call-1"
    assert request.tool_name == "read_file"
    assert request.canonical_path == str(external.resolve())
    assert request.operation is AccessOperation.READ


@pytest.mark.asyncio
async def test_approved_external_read_file_uses_fresh_scoped_tool(
    tmp_path: Path,
) -> None:
    _, ApprovalAwareToolExecutor = _require_task9_components()
    project = tmp_path / "project"
    project.mkdir()
    external = tmp_path / "external.txt"
    external.write_text("one\ntwo\nthree\n", encoding="utf-8")
    coordinator = RecordingCoordinator(ApprovalStatus.APPROVED)
    executor = ApprovalAwareToolExecutor(
        _conversation(project, PermissionMode.ASK_FOR_ACCESS),
        cast(ApprovalCoordinator, coordinator),
    )
    original_tool = RecordingTool("read_file")

    result = await executor.execute(
        original_tool,
        {"path": str(external), "start_line": 2, "max_lines": 1},
        _context(project, original_tool.name),
    )

    assert result.success
    assert result.content == "2: two"
    assert original_tool.calls == []
    assert result.metadata["path"] == "external.txt"


@pytest.mark.asyncio
async def test_approved_external_list_directory_filters_sensitive_children(
    tmp_path: Path,
) -> None:
    _, ApprovalAwareToolExecutor = _require_task9_components()
    project = tmp_path / "project"
    project.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    (external / "visible.txt").write_text("visible", encoding="utf-8")
    (external / ".env").write_text("placeholder", encoding="utf-8")
    coordinator = RecordingCoordinator(ApprovalStatus.APPROVED)
    executor = ApprovalAwareToolExecutor(
        _conversation(project, PermissionMode.ASK_FOR_ACCESS),
        cast(ApprovalCoordinator, coordinator),
    )
    tool = ListDirectoryTool(PathPolicy(project))

    result = await executor.execute(
        tool,
        {"path": str(external)},
        _context(project, tool.name),
    )

    payload = json.loads(result.content)
    assert result.success
    assert payload["path"] == "."
    assert payload["entries"] == [{"name": "visible.txt", "type": "file"}]


@pytest.mark.asyncio
async def test_approved_external_list_directory_rejects_file_target(
    tmp_path: Path,
) -> None:
    _, ApprovalAwareToolExecutor = _require_task9_components()
    project = tmp_path / "project"
    project.mkdir()
    external = tmp_path / "external.txt"
    external.write_text("outside", encoding="utf-8")
    coordinator = RecordingCoordinator(ApprovalStatus.APPROVED)
    executor = ApprovalAwareToolExecutor(
        _conversation(project, PermissionMode.ASK_FOR_ACCESS),
        cast(ApprovalCoordinator, coordinator),
    )
    tool = ListDirectoryTool(PathPolicy(project))

    result = await executor.execute(
        tool,
        {"path": str(external)},
        _context(project, tool.name),
    )

    assert result == ToolResult(
        success=False,
        content="path is not a directory",
        error_code="not_directory",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("target_kind", ["file", "directory"])
async def test_approved_external_search_preserves_query_and_glob(
    tmp_path: Path,
    target_kind: str,
) -> None:
    _, ApprovalAwareToolExecutor = _require_task9_components()
    project = tmp_path / "project"
    project.mkdir()
    external_dir = tmp_path / "external"
    external_dir.mkdir()
    external_file = external_dir / "notes.txt"
    external_file.write_text("Needle here\n", encoding="utf-8")
    target = external_file if target_kind == "file" else external_dir
    coordinator = RecordingCoordinator(ApprovalStatus.APPROVED)
    executor = ApprovalAwareToolExecutor(
        _conversation(project, PermissionMode.ASK_FOR_ACCESS),
        cast(ApprovalCoordinator, coordinator),
    )
    tool = SearchTextTool(PathPolicy(project))

    result = await executor.execute(
        tool,
        {"path": str(target), "query": "needle", "glob": "*.txt"},
        _context(project, tool.name),
    )

    payload = json.loads(result.content)
    assert result.success
    assert payload["query"] == "needle"
    assert payload["matches"] == [
        {"path": "notes.txt", "line": 1, "text": "Needle here"},
    ]


@pytest.mark.asyncio
async def test_repeated_external_access_creates_distinct_approvals(
    tmp_path: Path,
) -> None:
    _, ApprovalAwareToolExecutor = _require_task9_components()
    project = tmp_path / "project"
    project.mkdir()
    external = tmp_path / "external.txt"
    external.write_text("outside", encoding="utf-8")
    coordinator = RecordingCoordinator(ApprovalStatus.APPROVED)
    executor = ApprovalAwareToolExecutor(
        _conversation(project, PermissionMode.ASK_FOR_ACCESS),
        cast(ApprovalCoordinator, coordinator),
    )
    tool = ReadFileTool(PathPolicy(project))

    await executor.execute(
        tool,
        {"path": str(external)},
        _context(project, tool.name, tool_call_id="call-1"),
    )
    await executor.execute(
        tool,
        {"path": str(external)},
        _context(project, tool.name, tool_call_id="call-2"),
    )

    assert len(coordinator.requests) == 2
    assert coordinator.requests[0].approval_id != coordinator.requests[1].approval_id
    assert {request.tool_call_id for request in coordinator.requests} == {
        "call-1",
        "call-2",
    }


@pytest.mark.asyncio
async def test_external_access_rejects_context_or_tool_name_mismatch(
    tmp_path: Path,
) -> None:
    _, ApprovalAwareToolExecutor = _require_task9_components()
    project = tmp_path / "project"
    project.mkdir()
    external = tmp_path / "external.txt"
    external.write_text("outside", encoding="utf-8")
    coordinator = RecordingCoordinator(ApprovalStatus.APPROVED)
    executor = ApprovalAwareToolExecutor(
        _conversation(project, PermissionMode.ASK_FOR_ACCESS),
        cast(ApprovalCoordinator, coordinator),
    )

    with pytest.raises(PathPolicyViolationError):
        await executor.execute(
            RecordingTool("read_file"),
            {"path": str(external)},
            _context(project, "search_text"),
        )
    with pytest.raises(PathPolicyViolationError):
        await executor.execute(
            RecordingTool("unsupported_reader"),
            {"path": str(external)},
            _context(project, "unsupported_reader"),
        )
    assert coordinator.requests == []


@pytest.mark.asyncio
async def test_approved_external_access_rejects_changed_symlink_target(
    tmp_path: Path,
) -> None:
    _, ApprovalAwareToolExecutor = _require_task9_components()
    project = tmp_path / "project"
    project.mkdir()
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text("first", encoding="utf-8")
    second.write_text("second", encoding="utf-8")
    link = tmp_path / "external-link.txt"
    try:
        link.symlink_to(first)
    except OSError:
        pytest.skip("creating symlinks is not permitted on this Windows host")

    def replace_target() -> None:
        link.unlink()
        link.symlink_to(second)

    coordinator = RecordingCoordinator(
        ApprovalStatus.APPROVED,
        on_request=replace_target,
    )
    executor = ApprovalAwareToolExecutor(
        _conversation(project, PermissionMode.ASK_FOR_ACCESS),
        cast(ApprovalCoordinator, coordinator),
    )
    tool = RecordingTool("read_file")

    with pytest.raises(PathPolicyViolationError, match="changed"):
        await executor.execute(
            tool,
            {"path": str(link)},
            _context(project, tool.name),
        )
    assert tool.calls == []


@pytest.mark.asyncio
async def test_approved_external_access_rejects_disappeared_target(
    tmp_path: Path,
) -> None:
    _, ApprovalAwareToolExecutor = _require_task9_components()
    project = tmp_path / "project"
    project.mkdir()
    external = tmp_path / "external.txt"
    external.write_text("outside", encoding="utf-8")
    coordinator = RecordingCoordinator(
        ApprovalStatus.APPROVED,
        on_request=external.unlink,
    )
    executor = ApprovalAwareToolExecutor(
        _conversation(project, PermissionMode.ASK_FOR_ACCESS),
        cast(ApprovalCoordinator, coordinator),
    )
    tool = RecordingTool("read_file")

    with pytest.raises(PathPolicyViolationError, match="cannot be resolved"):
        await executor.execute(
            tool,
            {"path": str(external)},
            _context(project, tool.name),
        )
    assert tool.calls == []
