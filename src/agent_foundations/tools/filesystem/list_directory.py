import json
from pathlib import Path
from typing import Any

from agent_foundations.domain.errors import PathPolicyViolationError
from agent_foundations.domain.tool import ToolResult
from agent_foundations.security.models import SideEffectKind, ToolManifest
from agent_foundations.tools.filesystem.path_policy import PathPolicy

LIST_DIRECTORY_MANIFEST = ToolManifest(
    name="list_directory",
    resource_kind="project_path",
    operations=("list",),
    side_effect=SideEffectKind.NONE,
    sandbox_required=False,
)


class ListDirectoryTool:
    name = "list_directory"
    description = "List direct children of a project-relative directory in stable order."

    def __init__(self, policy: PathPolicy, max_entries: int = 200) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be positive")
        self._policy = policy
        self._max_entries = max_entries

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"path": {"type": "string", "default": "."}},
            "additionalProperties": False,
        }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        path = self._policy.authorize(str(arguments.get("path", ".")))
        if not path.is_dir():
            return ToolResult(
                success=False, content="path is not a directory", error_code="not_directory"
            )
        entries = [
            {"name": child.name, "type": "directory" if child.is_dir() else "file"}
            for child in sorted(
                path.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())
            )
            if self._is_visible(child)
        ]
        truncated = len(entries) > self._max_entries
        payload = {
            "path": self._policy.display_path(path),
            "entries": entries[: self._max_entries],
            "truncated": truncated,
        }
        return ToolResult(success=True, content=json.dumps(payload, ensure_ascii=False))

    def _is_visible(self, path: Path) -> bool:
        try:
            self._policy.authorize(self._policy.display_path(path))
        except (PathPolicyViolationError, ValueError):
            return False
        return True
