import json
from collections.abc import Iterator
from pathlib import Path, PurePosixPath
from typing import Any

from agent_foundations.domain.errors import (
    BinaryFileError,
    FileTooLargeError,
    PathPolicyViolationError,
)
from agent_foundations.domain.tool import ToolResult
from agent_foundations.tools.filesystem.path_policy import PathPolicy
from agent_foundations.tools.filesystem.read_file import ReadFileTool


class SearchTextTool:
    name = "search_text"
    description = "Search for a literal string in bounded UTF-8 project files."

    def __init__(
        self,
        policy: PathPolicy,
        max_matches: int = 50,
        max_files: int = 1_000,
        max_file_bytes: int = 256_000,
    ) -> None:
        if max_matches < 1:
            raise ValueError("max_matches must be positive")
        if max_files < 1:
            raise ValueError("max_files must be positive")
        self._policy = policy
        self._max_matches = max_matches
        self._max_files = max_files
        self._reader = ReadFileTool(policy, max_bytes=max_file_bytes)

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1},
                "path": {"type": "string", "default": "."},
                "glob": {"type": "string", "minLength": 1, "default": "*"},
            },
            "required": ["query"],
            "additionalProperties": False,
        }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        base = self._policy.authorize(str(arguments.get("path", ".")))
        query = str(arguments["query"])
        folded_query = query.casefold()
        pattern = str(arguments.get("glob", "*"))
        matches: list[dict[str, object]] = []
        scanned_files = 0
        skipped_files = 0
        truncated = False

        for path in self._candidate_files(base):
            try:
                relative = self._policy.display_path(path)
                self._policy.authorize(relative)
            except (PathPolicyViolationError, ValueError):
                skipped_files += 1
                continue
            if not PurePosixPath(relative).match(pattern):
                continue
            if scanned_files == self._max_files:
                truncated = True
                break
            scanned_files += 1
            try:
                lines = self._reader.read_lines(relative)
            except (BinaryFileError, FileTooLargeError, PathPolicyViolationError):
                skipped_files += 1
                continue
            for number, text in enumerate(lines, start=1):
                if folded_query in text.casefold():
                    if len(matches) == self._max_matches:
                        return self._result(
                            query,
                            matches,
                            scanned_files,
                            skipped_files,
                            truncated=True,
                        )
                    matches.append(
                        {"path": relative, "line": number, "text": text}
                    )
        return self._result(
            query,
            matches,
            scanned_files,
            skipped_files,
            truncated,
        )

    def _candidate_files(self, base: Path) -> Iterator[Path]:
        if base.is_file():
            yield base
            return
        for directory, directory_names, file_names in base.walk():
            directory_names.sort(key=str.casefold)
            file_names.sort(key=str.casefold)
            visible_directories: list[str] = []
            for directory_name in directory_names:
                candidate = directory / directory_name
                try:
                    relative = self._policy.display_path(candidate)
                    self._policy.authorize(relative)
                except (PathPolicyViolationError, ValueError):
                    continue
                visible_directories.append(directory_name)
            directory_names[:] = visible_directories
            for file_name in file_names:
                yield directory / file_name

    @staticmethod
    def _result(
        query: str,
        matches: list[dict[str, object]],
        scanned_files: int,
        skipped_files: int,
        truncated: bool,
    ) -> ToolResult:
        payload = {
            "query": query,
            "matches": matches,
            "scanned_files": scanned_files,
            "skipped_files": skipped_files,
            "truncated": truncated,
        }
        return ToolResult(
            success=True,
            content=json.dumps(payload, ensure_ascii=False),
        )
