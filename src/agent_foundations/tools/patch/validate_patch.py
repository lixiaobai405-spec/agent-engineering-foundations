from __future__ import annotations

from typing import Any

from agent_foundations.domain.tool import ToolResult
from agent_foundations.security.models import SideEffectKind, ToolManifest

VALIDATE_PATCH_TOOL_NAME = "validate_patch"

VALIDATE_PATCH_MANIFEST = ToolManifest(
    name=VALIDATE_PATCH_TOOL_NAME,
    resource_kind="patch_proposal",
    operations=("validate",),
    side_effect=SideEffectKind.NONE,
    sandbox_required=False,
)


class ValidatePatchTool:
    name = VALIDATE_PATCH_TOOL_NAME
    description = (
        "Validate a unified diff proposal against caller baselines without writing files."
    )

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "diff": {"type": "string"},
                "baselines": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "sha256": {"type": ["string", "null"]},
                        },
                        "required": ["path", "sha256"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["diff", "baselines"],
            "additionalProperties": False,
        }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        return ToolResult(
            success=False,
            content="validate_patch requires durable run context",
            error_code="PATCH_CONTEXT_REQUIRED",
        )
