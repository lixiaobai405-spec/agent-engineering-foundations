from __future__ import annotations

from typing import Any

from agent_foundations.domain.tool import RegisteredTool, Tool, ToolResult
from agent_foundations.security.models import (
    PolicyResource,
    ResourceScope,
    SideEffectKind,
    ToolManifest,
)

SEARCH_COMMAND_OUTPUT_TOOL_NAME = "search_command_output"

SEARCH_COMMAND_OUTPUT_MANIFEST = ToolManifest(
    name=SEARCH_COMMAND_OUTPUT_TOOL_NAME,
    resource_kind="command_artifact",
    operations=("search",),
    side_effect=SideEffectKind.NONE,
    sandbox_required=False,
)


class SearchCommandOutputTool:
    name = SEARCH_COMMAND_OUTPUT_TOOL_NAME
    description = "Search a sanitized command output artifact for a literal query."

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "artifact_id": {"type": "string"},
                "query": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["artifact_id", "query", "reason"],
            "additionalProperties": False,
        }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        del arguments
        return ToolResult(
            success=False,
            content="search_command_output requires controlled access execution",
            error_code="CONTROLLED_EXECUTION_REQUIRED",
        )


def resolve_search_command_output_resource(arguments: Any) -> PolicyResource:
    artifact_id = str(arguments.get("artifact_id", "command_artifact"))[:256]
    return PolicyResource(
        kind="command_artifact",
        scope=ResourceScope.PROJECT_INTERNAL,
        identifier=artifact_id,
    )


def build_search_command_output_registered_tool() -> RegisteredTool:
    return RegisteredTool(
        SearchCommandOutputTool(),
        SEARCH_COMMAND_OUTPUT_MANIFEST,
        resolve_search_command_output_resource,
    )


assert isinstance(SearchCommandOutputTool(), Tool)
