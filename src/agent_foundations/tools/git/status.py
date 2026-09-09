from __future__ import annotations

import json
from typing import Any

from agent_foundations.domain.tool import ToolResult
from agent_foundations.security.models import (
    PolicyResource,
    ResourceScope,
    SideEffectKind,
    ToolManifest,
)
from agent_foundations.tools.git.service import GitReadError, GitReadService

GIT_STATUS_TOOL_NAME = "git_status"

GIT_STATUS_MANIFEST = ToolManifest(
    name=GIT_STATUS_TOOL_NAME,
    resource_kind="project_path",
    operations=("read",),
    side_effect=SideEffectKind.NONE,
    sandbox_required=True,
)


class GitStatusTool:
    name = GIT_STATUS_TOOL_NAME
    description = "Read isolated porcelain git status for the project repository."

    def __init__(self, service: GitReadService) -> None:
        self._service = service

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        del arguments
        try:
            result = await self._service.status()
        except GitReadError as exc:
            return ToolResult(success=False, content=str(exc)[:240], error_code=exc.code)
        payload = result.model_dump(mode="json")
        return ToolResult(
            success=True,
            content=json.dumps(payload, ensure_ascii=False),
            metadata=payload,
        )


def resolve_git_status_resource(arguments: Any) -> PolicyResource:
    del arguments
    return PolicyResource(
        kind="project_path",
        scope=ResourceScope.PROJECT_INTERNAL,
        identifier="repository",
    )
