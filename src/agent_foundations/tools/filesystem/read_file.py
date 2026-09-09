import hashlib
from pathlib import Path
from typing import Any

from agent_foundations.domain.errors import BinaryFileError, FileTooLargeError
from agent_foundations.domain.tool import ToolResult
from agent_foundations.security.models import SideEffectKind, ToolManifest
from agent_foundations.tools.filesystem.path_policy import PathPolicy
from agent_foundations.tools.utf8_lines import utf8_line_texts

READ_FILE_MANIFEST = ToolManifest(
    name="read_file",
    resource_kind="project_path",
    operations=("read",),
    side_effect=SideEffectKind.NONE,
    sandbox_required=False,
)


class ReadFileTool:
    name = "read_file"
    description = (
        "Read a bounded UTF-8 line range from a project-relative text file. "
        "Successful metadata includes sha256, size_bytes, encoding, and truncated; "
        "sha256 is the full-file digest."
    )

    def __init__(self, policy: PathPolicy, max_bytes: int = 256_000) -> None:
        if max_bytes < 1:
            raise ValueError("max_bytes must be positive")
        self._policy = policy
        self._max_bytes = max_bytes

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "start_line": {"type": "integer", "minimum": 1, "default": 1},
                "max_lines": {"type": "integer", "minimum": 1, "maximum": 500, "default": 200},
            },
            "required": ["path"],
            "additionalProperties": False,
        }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        relative_path = str(arguments["path"])
        path = self._policy.authorize(relative_path)
        if not path.is_file():
            return ToolResult(
                success=False,
                content="path is not a file",
                error_code="not_file",
            )
        raw = self._read_raw_bytes(path)
        lines = utf8_line_texts(raw)
        start = int(arguments.get("start_line", 1)) - 1
        maximum = int(arguments.get("max_lines", 200))
        selected = lines[start : start + maximum]
        content = "\n".join(
            f"{number}: {line}"
            for number, line in enumerate(selected, start=start + 1)
        )
        return ToolResult(
            success=True,
            content=content,
            metadata={
                "path": self._policy.display_path(path),
                "start_line": start + 1,
                "returned_lines": len(selected),
                "truncated": start + len(selected) < len(lines),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "size_bytes": len(raw),
                "encoding": "utf-8",
            },
        )

    def read_lines(self, relative_path: str) -> tuple[str, ...]:
        """Load one complete UTF-8 file under the configured byte limit."""
        path = self._policy.authorize(relative_path)
        if not path.is_file():
            raise BinaryFileError("path is not a regular text file")
        raw = self._read_raw_bytes(path)
        return utf8_line_texts(raw)

    def _read_raw_bytes(self, path: Path) -> bytes:
        with path.open("rb") as stream:
            raw = stream.read(self._max_bytes + 1)
        if len(raw) > self._max_bytes:
            raise FileTooLargeError(
                f"file exceeds {self._max_bytes} byte limit"
            )
        if b"\x00" in raw:
            raise BinaryFileError("file contains NUL bytes")
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise BinaryFileError("file is not valid UTF-8 text") from exc
        return raw
