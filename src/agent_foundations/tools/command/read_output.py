from __future__ import annotations

from typing import Any

from agent_foundations.domain.tool import RegisteredTool, Tool, ToolResult
from agent_foundations.security.models import (
    PolicyResource,
    ResourceScope,
    SideEffectKind,
    ToolManifest,
)

READ_COMMAND_OUTPUT_TOOL_NAME = "read_command_output"

READ_COMMAND_OUTPUT_MANIFEST = ToolManifest(
    name=READ_COMMAND_OUTPUT_TOOL_NAME,
    resource_kind="command_artifact",
    operations=("read",),
    side_effect=SideEffectKind.NONE,
    sandbox_required=False,
)


class ReadCommandOutputTool:
    name = READ_COMMAND_OUTPUT_TOOL_NAME
    description = (
        "Read a bounded sanitized slice of a command output artifact. "
        "Use after a failing run_command together with CommandFeedback.artifact_id. "
        "selector shapes: {diagnostic_id}; {stream, tail_lines}; "
        "{stream, start_line, line_count}."
    )

    def input_schema(self) -> dict[str, Any]:
        selector = {
            "oneOf": [
                {
                    "type": "object",
                    "properties": {"diagnostic_id": {"type": "string"}},
                    "required": ["diagnostic_id"],
                },
                {
                    "type": "object",
                    "properties": {
                        "stream": {"type": "string", "enum": ["stdout", "stderr"]},
                        "tail_lines": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 200,
                        },
                    },
                    "required": ["stream", "tail_lines"],
                },
                {
                    "type": "object",
                    "properties": {
                        "stream": {"type": "string", "enum": ["stdout", "stderr"]},
                        "start_line": {"type": "integer", "minimum": 1},
                        "line_count": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 200,
                        },
                    },
                    "required": ["stream", "start_line"],
                },
            ]
        }
        return {
            "type": "object",
            "properties": {
                "artifact_id": {"type": "string"},
                "selector": selector,
                "reason": {"type": "string"},
            },
            "required": ["artifact_id", "selector", "reason"],
            "additionalProperties": False,
        }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        del arguments
        return ToolResult(
            success=False,
            content="read_command_output requires controlled access execution",
            error_code="CONTROLLED_EXECUTION_REQUIRED",
        )


def resolve_read_command_output_resource(arguments: Any) -> PolicyResource:
    artifact_id = str(arguments.get("artifact_id", "command_artifact"))[:256]
    return PolicyResource(
        kind="command_artifact",
        scope=ResourceScope.PROJECT_INTERNAL,
        identifier=artifact_id,
    )


def build_read_command_output_registered_tool() -> RegisteredTool:
    return RegisteredTool(
        ReadCommandOutputTool(),
        READ_COMMAND_OUTPUT_MANIFEST,
        resolve_read_command_output_resource,
    )


assert isinstance(ReadCommandOutputTool(), Tool)
