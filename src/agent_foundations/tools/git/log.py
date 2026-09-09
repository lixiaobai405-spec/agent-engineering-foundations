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
from agent_foundations.tools.git.models import DEFAULT_LOG_LIMIT, MAX_LOG_LIMIT
from agent_foundations.tools.git.service import GitReadError, GitReadService

GIT_LOG_TOOL_NAME = "git_log"

GIT_LOG_MANIFEST = ToolManifest(
    name=GIT_LOG_TOOL_NAME,
    resource_kind="project_path",
    operations=("read",),
    side_effect=SideEffectKind.NONE,
    sandbox_required=True,
)


class GitLogTool:
    name = GIT_LOG_TOOL_NAME
    description = "Read a bounded isolated git log for the project repository."

    def __init__(self, service: GitReadService) -> None:
        self._service = service

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": MAX_LOG_LIMIT,
                    "default": DEFAULT_LOG_LIMIT,
                },
            },
            "additionalProperties": False,
        }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        limit = int(arguments.get("limit", DEFAULT_LOG_LIMIT))
        try:
            result = await self._service.log(limit=limit)
        except GitReadError as exc:
            return ToolResult(success=False, content=str(exc)[:240], error_code=exc.code)
        payload = result.model_dump(mode="json")
        return ToolResult(
            success=True,
            content=json.dumps(payload, ensure_ascii=False),
            metadata=payload,
        )


def resolve_git_log_resource(arguments: Any) -> PolicyResource:
    del arguments
    return PolicyResource(
        kind="project_path",
        scope=ResourceScope.PROJECT_INTERNAL,
        identifier="repository",
    )
