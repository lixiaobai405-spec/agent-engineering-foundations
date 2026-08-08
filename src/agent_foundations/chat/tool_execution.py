from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_foundations.chat.approvals import ApprovalCoordinator
from agent_foundations.chat.models import (
    AccessDecision,
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
from agent_foundations.domain.tool import Tool, ToolResult
from agent_foundations.runtime.tool_execution import ToolExecutionContext
from agent_foundations.tools.filesystem.list_directory import ListDirectoryTool
from agent_foundations.tools.filesystem.path_policy import PathPolicy
from agent_foundations.tools.filesystem.read_file import ReadFileTool
from agent_foundations.tools.filesystem.search_text import SearchTextTool

_EXTERNAL_READ_TOOLS = frozenset({"read_file", "list_directory", "search_text"})


class FilesystemAccessController:
    """Classify one filesystem read without executing or persisting anything."""

    def decide(
        self,
        conversation: Conversation,
        raw_path: str,
    ) -> AccessDecision:
        project_policy = PathPolicy(Path(conversation.project_root))
        if _is_absolute_request(raw_path):
            canonical = PathPolicy.resolve_external_read_target(raw_path)
        else:
            canonical = project_policy.authorize(raw_path)

        project_root = project_policy.root
        if canonical.is_relative_to(project_root):
            scope = AccessScope.PROJECT
            decision = PolicyDecision.ALLOW
        else:
            scope = AccessScope.EXTERNAL_EXACT_PATH
            decision = (
                PolicyDecision.ASK
                if conversation.permission_mode is PermissionMode.ASK_FOR_ACCESS
                else PolicyDecision.DENY
            )
        return AccessDecision(
            resource=ResourceKind.FILESYSTEM,
            operation=AccessOperation.READ,
            scope=scope,
            decision=decision,
            canonical_path=str(canonical),
        )


class ApprovalAwareToolExecutor:
    def __init__(
        self,
        conversation: Conversation,
        coordinator: ApprovalCoordinator,
    ) -> None:
        self._conversation = conversation
        self._coordinator = coordinator
        self._controller = FilesystemAccessController()

    async def execute(
        self,
        tool: Tool,
        arguments: dict[str, Any],
        context: ToolExecutionContext,
    ) -> ToolResult:
        self._validate_context(tool, context)
        if "path" not in arguments:
            return await tool.execute(arguments)

        raw_path = str(arguments["path"])
        access = self._controller.decide(self._conversation, raw_path)
        if access.scope is AccessScope.PROJECT:
            if not _is_absolute_request(raw_path):
                return await tool.execute(arguments)
            rewritten = dict(arguments)
            rewritten["path"] = self._project_relative_path(access.canonical_path)
            return await tool.execute(rewritten)

        if access.decision is PolicyDecision.DENY:
            raise PathPolicyViolationError("external read access is denied")
        if tool.name not in _EXTERNAL_READ_TOOLS:
            raise PathPolicyViolationError("tool cannot receive external read access")

        request = ApprovalRequest(
            conversation_id=self._conversation.conversation_id,
            session_id=context.session_id,
            tool_call_id=context.tool_call_id,
            tool_name=tool.name,
            canonical_path=access.canonical_path,
            operation=AccessOperation.READ,
            status=ApprovalStatus.PENDING,
        )
        approval_status = await self._coordinator.request(request)
        if approval_status is ApprovalStatus.DENIED:
            return ToolResult(
                success=False,
                content="access denied",
                error_code="access_denied",
            )
        if approval_status is not ApprovalStatus.APPROVED:
            raise PathPolicyViolationError("external read approval is unavailable")

        resolved = PathPolicy.resolve_external_read_target(raw_path)
        if str(resolved) != access.canonical_path:
            raise PathPolicyViolationError("approved external target changed")
        prepared = self._prepare_scoped_execution(tool.name, resolved, arguments)
        if isinstance(prepared, ToolResult):
            return prepared
        scoped_tool, rewritten = prepared
        return await scoped_tool.execute(rewritten)

    def _validate_context(self, tool: Tool, context: ToolExecutionContext) -> None:
        if context.tool_name != tool.name:
            raise PathPolicyViolationError("tool execution context mismatch")
        try:
            context_root = context.root.resolve(strict=True)
            conversation_root = Path(self._conversation.project_root).resolve(strict=True)
        except (OSError, ValueError) as exc:
            raise PathPolicyViolationError("tool execution root is invalid") from exc
        if context_root != conversation_root:
            raise PathPolicyViolationError("tool execution root mismatch")

    def _project_relative_path(self, canonical_path: str) -> str:
        project_root = Path(self._conversation.project_root).resolve(strict=True)
        return Path(canonical_path).relative_to(project_root).as_posix()

    def _prepare_scoped_execution(
        self,
        tool_name: str,
        target: Path,
        arguments: dict[str, Any],
    ) -> tuple[Tool, dict[str, Any]] | ToolResult:
        rewritten = dict(arguments)
        if tool_name == "read_file":
            policy = PathPolicy(target.parent)
            rewritten["path"] = target.name
            return ReadFileTool(policy), rewritten
        if tool_name == "list_directory":
            if not target.is_dir():
                return ToolResult(
                    success=False,
                    content="path is not a directory",
                    error_code="not_directory",
                )
            policy = PathPolicy(target)
            rewritten["path"] = "."
            return ListDirectoryTool(policy), rewritten
        if tool_name == "search_text":
            if target.is_dir():
                policy = PathPolicy(target)
                rewritten["path"] = "."
            else:
                policy = PathPolicy(target.parent)
                rewritten["path"] = target.name
            return SearchTextTool(policy), rewritten
        raise PathPolicyViolationError("tool cannot receive external read access")


def _is_absolute_request(raw_path: str) -> bool:
    normalized = raw_path.replace("/", "\\")
    if normalized.startswith("\\\\"):
        return True
    try:
        path = Path(raw_path)
    except (TypeError, ValueError) as exc:
        raise PathPolicyViolationError("invalid path syntax") from exc
    return path.is_absolute() or bool(path.drive)
