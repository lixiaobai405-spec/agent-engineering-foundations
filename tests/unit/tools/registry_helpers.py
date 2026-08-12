from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from agent_foundations.domain.tool import RegisteredTool, Tool
from agent_foundations.planning.controller import PlanController
from agent_foundations.planning.execution import ExecutionFactJournal
from agent_foundations.planning.tools import build_planning_registered_tools
from agent_foundations.security.models import (
    PolicyResource,
    ResourceScope,
    SideEffectKind,
    ToolManifest,
)
from agent_foundations.security.resources import resolve_validate_patch_resource
from agent_foundations.tools.filesystem.path_policy import PathPolicy
from agent_foundations.tools.patch.validate_patch import VALIDATE_PATCH_MANIFEST, ValidatePatchTool
from agent_foundations.tools.registry import (
    ToolRegistry,
    build_readonly_filesystem_registered_tools,
)


def _default_resolver(
    resource_kind: str,
    identifier: str,
) -> Any:
    def resolve(_arguments: Mapping[str, Any]) -> PolicyResource:
        return PolicyResource(
            kind=resource_kind,
            scope=ResourceScope.PROJECT_INTERNAL,
            identifier=identifier,
        )

    return resolve


def registered_test_tool(
    tool: Tool,
    *,
    resource_kind: str = "project_path",
    operations: tuple[str, ...] = ("read",),
    side_effect: SideEffectKind = SideEffectKind.NONE,
    identifier: str | None = None,
) -> RegisteredTool:
    manifest = ToolManifest(
        name=tool.name,
        resource_kind=resource_kind,
        operations=operations,
        side_effect=side_effect,
        sandbox_required=side_effect is SideEffectKind.PROCESS,
    )
    return RegisteredTool(
        tool,
        manifest,
        _default_resolver(resource_kind, identifier or tool.name),
    )


def readonly_tool_registry(root: Path) -> ToolRegistry:
    policy = PathPolicy(root)
    return ToolRegistry(build_readonly_filesystem_registered_tools(policy))


def planning_tool_registry(
    controller: PlanController,
    journal: ExecutionFactJournal,
    root: Path | None = None,
) -> ToolRegistry:
    registered = list(
        build_planning_registered_tools(controller, journal),
    )
    if root is not None:
        policy = PathPolicy(root)
        registered = list(build_readonly_filesystem_registered_tools(policy)) + registered
    return ToolRegistry(registered)


def validate_patch_tool_registry() -> ToolRegistry:
    return ToolRegistry(
        [
            RegisteredTool(
                ValidatePatchTool(),
                VALIDATE_PATCH_MANIFEST,
                resolve_validate_patch_resource,
            ),
        ],
    )
