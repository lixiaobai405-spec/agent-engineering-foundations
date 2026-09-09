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
        "Validate a patch proposal without writing files. "
        "Prefer changes with expected_sha256 from read_file; Runtime compiles unified diff. "
        "The diff+baselines path remains valid. Do not guess hashes."
    )

    def input_schema(self) -> dict[str, Any]:
        baseline_items = {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "sha256": {"type": ["string", "null"]},
            },
            "required": ["path", "sha256"],
            "additionalProperties": False,
        }
        change_items = {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "expected_sha256": {
                    "type": "string",
                    "pattern": "^[a-f0-9]{64}$",
                    "description": (
                        "Full-file sha256 returned by read_file. Do not guess hashes."
                    ),
                },
                "start_line": {"type": "integer", "minimum": 1},
                "old_lines": {"type": "array", "items": {"type": "string"}},
                "new_lines": {"type": "array", "items": {"type": "string"}},
            },
            "required": [
                "path",
                "expected_sha256",
                "start_line",
                "old_lines",
                "new_lines",
            ],
            "additionalProperties": False,
        }
        return {
            "type": "object",
            "properties": {
                "diff": {
                    "type": "string",
                    "description": "Unified diff; remains valid when sent with baselines.",
                },
                "baselines": {
                    "type": "array",
                    "items": baseline_items,
                    "description": "Per-path sha256 baselines for the unified diff path.",
                },
                "changes": {
                    "type": "array",
                    "minItems": 1,
                    "items": change_items,
                    "description": (
                        "Prefer structured changes with expected_sha256 from read_file; "
                        "Runtime compiles a unified diff."
                    ),
                },
            },
            "additionalProperties": False,
            "oneOf": [
                {
                    "required": ["diff", "baselines"],
                    "not": {"required": ["changes"]},
                },
                {
                    "required": ["changes"],
                    "not": {"anyOf": [{"required": ["diff"]}, {"required": ["baselines"]}]},
                },
            ],
        }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        return ToolResult(
            success=False,
            content="validate_patch requires durable run context",
            error_code="PATCH_CONTEXT_REQUIRED",
        )
