from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from agent_foundations.domain.tool import ToolResult
from agent_foundations.security.models import (
    PolicyResource,
    ResourceScope,
    SideEffectKind,
    ToolManifest,
)
from agent_foundations.tools.filesystem.path_policy import PathPolicy
from agent_foundations.tools.git.models import DEFAULT_DIFF_MAX_BYTES
from agent_foundations.tools.git.service import GitReadError, GitReadService

GIT_DIFF_TOOL_NAME = "git_diff"

GIT_DIFF_MANIFEST = ToolManifest(
    name=GIT_DIFF_TOOL_NAME,
    resource_kind="project_path",
    operations=("read",),
    side_effect=SideEffectKind.NONE,
    sandbox_required=True,
)


class GitDiffTool:
    name = GIT_DIFF_TOOL_NAME
    description = "Read a bounded isolated git diff for the project repository."

    def __init__(self, service: GitReadService) -> None:
        self._service = service

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": ["string", "null"], "default": None},
                "staged": {"type": "boolean", "default": False},
                "max_bytes": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": DEFAULT_DIFF_MAX_BYTES,
                    "default": DEFAULT_DIFF_MAX_BYTES,
                },
            },
            "additionalProperties": False,
        }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        path = arguments.get("path")
        staged = bool(arguments.get("staged", False))
        max_bytes = int(arguments.get("max_bytes", DEFAULT_DIFF_MAX_BYTES))
        try:
            result = await self._service.diff(
                path=None if path in {None, ""} else str(path),
                staged=staged,
                max_bytes=max_bytes,
            )
        except GitReadError as exc:
            return ToolResult(success=False, content=str(exc)[:240], error_code=exc.code)
        payload = result.model_dump(mode="json")
        return ToolResult(
            success=True,
            content=json.dumps(payload, ensure_ascii=False)[:240],
            metadata=payload,
        )


def resolve_git_diff_resource(
    arguments: Mapping[str, Any],
    policy: PathPolicy,
) -> PolicyResource:
    path = arguments.get("path")
    if path in {None, ""}:
        identifier = "repository"
    else:
        authorized = policy.authorize(str(path))
        identifier = policy.display_path(authorized)[:256]
    return PolicyResource(
        kind="project_path",
        scope=ResourceScope.PROJECT_INTERNAL,
        identifier=identifier,
    )
