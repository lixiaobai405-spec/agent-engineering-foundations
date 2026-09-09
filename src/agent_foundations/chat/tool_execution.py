from __future__ import annotations

from collections.abc import Callable
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
    PolicyDecision,
    ResourceKind,
    utc_now,
)
from agent_foundations.domain.errors import PathPolicyViolationError
from agent_foundations.domain.tool import Tool, ToolResult
from agent_foundations.runtime.tool_execution import ToolCallExecutor, ToolExecutionContext
from agent_foundations.security.approvals import (
    AuthorizationDecision,
    AuthorizationStatus,
)
from agent_foundations.security.models import (
    PermissionProfile,
    PermissionProfileName,
    PolicyOutcome,
    PolicyRequest,
    PolicyResource,
    ResourceScope,
    ToolManifest,
    default_allowed_tools,
)
from agent_foundations.security.policy import PolicyEngine
from agent_foundations.tools.command.run_command import (
    RUN_COMMAND_MANIFEST,
    resolve_run_command_resource,
)
from agent_foundations.tools.filesystem.list_directory import (
    LIST_DIRECTORY_MANIFEST,
    ListDirectoryTool,
)
from agent_foundations.tools.filesystem.path_policy import PathPolicy
from agent_foundations.tools.filesystem.read_file import READ_FILE_MANIFEST, ReadFileTool
from agent_foundations.tools.filesystem.search_text import (
    SEARCH_TEXT_MANIFEST,
    SearchTextTool,
)
from agent_foundations.tools.patch.apply_patch import (
    APPLY_PATCH_MANIFEST,
    ApplyPatchTool,
    resolve_apply_patch_resource,
)

_EXTERNAL_READ_TOOLS = frozenset({"read_file", "list_directory", "search_text"})
_EXTERNAL_POLICY_METADATA = {
    "read_file": (READ_FILE_MANIFEST, "read"),
    "list_directory": (LIST_DIRECTORY_MANIFEST, "list"),
    "search_text": (SEARCH_TEXT_MANIFEST, "search"),
}

ControlledPatchFactory = Callable[
    [Callable[[AuthorizationDecision], AuthorizationDecision] | None],
    ToolCallExecutor,
]


class ChatControlledToolExecutor:
    """Bridge persisted Chat approval to the controlled patch executor."""

    def __init__(
        self,
        downstream: ToolCallExecutor,
        conversation: Conversation,
        coordinator: ApprovalCoordinator,
        controlled_patch_factory: ControlledPatchFactory,
        *,
        controlled_command_factory: ControlledPatchFactory | None = None,
        output_executor: ToolCallExecutor | None = None,
    ) -> None:
        self._downstream = downstream
        self._conversation = conversation
        self._coordinator = coordinator
        self._controlled_patch_factory = controlled_patch_factory
        self._controlled_command_factory = controlled_command_factory
        self._output_executor = output_executor

    async def execute(
        self,
        tool: Tool,
        arguments: dict[str, Any],
        context: ToolExecutionContext,
    ) -> ToolResult:
        from agent_foundations.tools.command.read_output import ReadCommandOutputTool
        from agent_foundations.tools.command.run_command import RunCommandTool
        from agent_foundations.tools.command.search_output import SearchCommandOutputTool

        if isinstance(tool, (ReadCommandOutputTool, SearchCommandOutputTool)):
            if self._output_executor is None:
                return await tool.execute(arguments)
            return await self._output_executor.execute(tool, arguments, context)

        if isinstance(tool, RunCommandTool):
            if self._controlled_command_factory is None:
                return await tool.execute(arguments)
            initial = await self._controlled_command_factory(None).execute(
                tool,
                arguments,
                context,
            )
            if initial.error_code != "APPROVAL_REQUIRED":
                return initial
            request = ApprovalRequest(
                conversation_id=self._conversation.conversation_id,
                session_id=context.session_id,
                tool_call_id=context.tool_call_id,
                tool_name="run_command",
                canonical_path="command:run_command",
                operation=AccessOperation.READ,
            )
            policy_request, outcome = self._manifest_policy_request(
                context,
                tool_name="run_command",
                manifest=RUN_COMMAND_MANIFEST,
                resource=resolve_run_command_resource(arguments),
                operation="run",
            )
            status = await self._coordinator.request(request, policy_request, outcome)

            def decide_command(pending: AuthorizationDecision) -> AuthorizationDecision:
                target = (
                    AuthorizationStatus.APPROVED
                    if status is ApprovalStatus.APPROVED
                    else AuthorizationStatus.DENIED
                )
                return pending.model_copy(
                    update={"status": target, "decided_at": utc_now()},
                )

            return await self._controlled_command_factory(decide_command).execute(
                tool,
                arguments,
                context,
            )

        if not isinstance(tool, ApplyPatchTool):
            return await self._downstream.execute(tool, arguments, context)

        initial = await self._controlled_patch_factory(None).execute(
            tool,
            arguments,
            context,
        )
        if initial.error_code != "APPROVAL_REQUIRED":
            return initial

        patch_id = str(arguments.get("patch_id", ""))
        request = ApprovalRequest(
            conversation_id=self._conversation.conversation_id,
            session_id=context.session_id,
            tool_call_id=context.tool_call_id,
            tool_name="apply_patch",
            canonical_path=f"patch:{patch_id}",
            operation=AccessOperation.APPLY,
        )
        try:
            resource = resolve_apply_patch_resource(arguments)
        except ValueError:
            resource = PolicyResource(
                kind=APPLY_PATCH_MANIFEST.resource_kind,
                scope=ResourceScope.PROJECT_INTERNAL,
                identifier=(f"patch:{patch_id}" if patch_id else "project_path")[:256],
            )
        policy_request, outcome = self._manifest_policy_request(
            context,
            tool_name="apply_patch",
            manifest=APPLY_PATCH_MANIFEST,
            resource=resource,
            operation="apply",
        )
        status = await self._coordinator.request(request, policy_request, outcome)

        def decide(pending: AuthorizationDecision) -> AuthorizationDecision:
            target = (
                AuthorizationStatus.APPROVED
                if status is ApprovalStatus.APPROVED
                else AuthorizationStatus.DENIED
            )
            return pending.model_copy(
                update={"status": target, "decided_at": utc_now()},
            )

        return await self._controlled_patch_factory(decide).execute(
            tool,
            arguments,
            context,
        )

    def _manifest_policy_request(
        self,
        context: ToolExecutionContext,
        *,
        tool_name: str,
        manifest: ToolManifest,
        resource: PolicyResource,
        operation: str,
    ) -> tuple[PolicyRequest, PolicyOutcome]:
        profile = PermissionProfile(
            name=self._conversation.permission_profile,
            version=self._conversation.profile_version,
            allowed_tools=default_allowed_tools(
                self._conversation.permission_profile,
            ),
        )
        policy_request = PolicyRequest(
            profile_version=profile.version,
            run_id=context.session_id,
            tool_call_id=context.tool_call_id,
            tool_name=tool_name,
            manifest=manifest,
            resource=resource,
            operation=operation,
        )
        return policy_request, PolicyEngine().decide(profile, policy_request)


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
                if conversation.permission_profile is PermissionProfileName.ASK_ALWAYS
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
        policy_request, outcome = self._external_policy_request(
            tool.name,
            context,
            access.canonical_path,
        )
        request_capability = getattr(self._coordinator, "request_capability", None)
        capability = None
        if request_capability is None:
            approval_status = await self._coordinator.request(
                request,
                policy_request,
                outcome,
            )
        else:
            capability = await request_capability(request, policy_request, outcome)
            approval_status = (
                ApprovalStatus.APPROVED
                if capability is not None
                else ApprovalStatus.DENIED
            )
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
        if capability is not None:
            await self._coordinator.consume_capability(
                capability.capability_id,
                policy_request,
            )
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

    def _external_policy_request(
        self,
        tool_name: str,
        context: ToolExecutionContext,
        canonical_path: str,
    ) -> tuple[PolicyRequest, PolicyOutcome]:
        metadata = _EXTERNAL_POLICY_METADATA.get(tool_name)
        if metadata is None:
            raise PathPolicyViolationError("tool cannot receive external read access")
        manifest, operation = metadata
        profile = PermissionProfile(
            name=self._conversation.permission_profile,
            version=self._conversation.profile_version,
            allowed_tools=default_allowed_tools(
                self._conversation.permission_profile,
            ),
        )
        request = PolicyRequest(
            profile_version=profile.version,
            run_id=context.session_id,
            tool_call_id=context.tool_call_id,
            tool_name=tool_name,
            manifest=manifest,
            resource=PolicyResource(
                kind="project_path",
                scope=ResourceScope.EXTERNAL_EXACT_PATH,
                identifier=canonical_path,
            ),
            operation=operation,
        )
        return request, PolicyEngine().decide(profile, request)


def _is_absolute_request(raw_path: str) -> bool:
    normalized = raw_path.replace("/", "\\")
    if normalized.startswith("\\\\"):
        return True
    try:
        path = Path(raw_path)
    except (TypeError, ValueError) as exc:
        raise PathPolicyViolationError("invalid path syntax") from exc
    return path.is_absolute() or bool(path.drive)
