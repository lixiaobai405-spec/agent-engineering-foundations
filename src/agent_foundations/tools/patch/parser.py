from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath

from agent_foundations.tools.patch.models import (
    PatchFile,
    PatchHunk,
    PatchLimits,
    PatchLine,
    PatchLineKind,
    PatchOperation,
)

_HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
_DIFF_GIT = re.compile(r"^diff --git a/(.*) b/(.*)$")
_NO_NEWLINE = "\\ No newline at end of file"


class PatchParseError(ValueError):
    """Raised when unified diff input is malformed or unsupported."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class ParsedPatch:
    files: tuple[PatchFile, ...]


def parse_unified_diff(diff: str, limits: PatchLimits | None = None) -> ParsedPatch:
    effective_limits = limits or PatchLimits()
    raw = diff if diff.endswith("\n") else diff + "\n"
    patch_bytes = len(raw.encode("utf-8"))
    if patch_bytes > effective_limits.max_patch_bytes:
        raise PatchParseError("PATCH_SIZE_LIMIT", "patch exceeds byte limit")

    lines = raw.splitlines()
    files: list[PatchFile] = []
    index = 0

    while index < len(lines):
        line = lines[index]
        if line == "":
            index += 1
            continue
        if not line.startswith("diff --git "):
            raise PatchParseError("PATCH_PARSE_ERROR", "expected diff header")

        match = _DIFF_GIT.match(line)
        if match is None:
            raise PatchParseError("PATCH_PARSE_ERROR", "malformed diff header")
        old_path_raw, new_path_raw = match.group(1), match.group(2)
        _ = old_path_raw, new_path_raw
        index += 1

        is_new_file = False
        saw_mode_change = False
        while index < len(lines) and not lines[index].startswith("--- "):
            meta = lines[index]
            if meta.startswith("new file mode "):
                mode = meta[len("new file mode ") :].strip()
                if mode != "100644":
                    raise PatchParseError("PATCH_PARSE_ERROR", "unsupported file mode")
                is_new_file = True
            elif meta.startswith("deleted file mode "):
                raise PatchParseError("PATCH_PARSE_ERROR", "delete not supported")
            elif meta.startswith("old mode ") or meta.startswith("new mode "):
                saw_mode_change = True
            elif meta.startswith("rename from ") or meta.startswith("rename to "):
                raise PatchParseError("PATCH_PARSE_ERROR", "rename not supported")
            elif meta.startswith("copy from ") or meta.startswith("copy to "):
                raise PatchParseError("PATCH_PARSE_ERROR", "copy not supported")
            elif meta.startswith("similarity index "):
                pass
            elif meta.startswith("dissimilarity index "):
                pass
            elif meta.startswith("index "):
                pass
            elif meta.startswith("Binary files "):
                raise PatchParseError("PATCH_PARSE_ERROR", "binary patch not supported")
            elif meta.startswith("GIT binary patch"):
                raise PatchParseError("PATCH_PARSE_ERROR", "binary patch not supported")
            else:
                raise PatchParseError("PATCH_PARSE_ERROR", "unexpected metadata line")
            index += 1

        if saw_mode_change and not is_new_file:
            raise PatchParseError("PATCH_PARSE_ERROR", "mode change not supported")

        if index >= len(lines) or not lines[index].startswith("--- "):
            raise PatchParseError("PATCH_PARSE_ERROR", "missing old file header")
        old_header = lines[index][4:]
        index += 1
        if index >= len(lines) or not lines[index].startswith("+++ "):
            raise PatchParseError("PATCH_PARSE_ERROR", "missing new file header")
        new_header = lines[index][4:]
        index += 1

        operation, rel_path, old_rel = _resolve_paths(old_header, new_header, is_new_file)
        hunks: list[PatchHunk] = []
        while index < len(lines) and lines[index].startswith("@@ "):
            hunk, index = _parse_hunk(lines, index)
            hunks.append(hunk)

        if not hunks:
            raise PatchParseError("PATCH_PARSE_ERROR", "file has no hunks")

        add_count = sum(
            1 for hunk in hunks for line in hunk.lines if line.kind == PatchLineKind.ADD
        )
        remove_count = sum(
            1 for hunk in hunks for line in hunk.lines if line.kind == PatchLineKind.REMOVE
        )
        files.append(
            PatchFile(
                path=rel_path,
                operation=operation,
                baseline_sha256=None,
                hunks=tuple(hunks),
                old_path=old_rel,
                add_line_count=add_count,
                remove_line_count=remove_count,
                hunk_count=len(hunks),
            ),
        )
        if len(files) > effective_limits.max_files:
            raise PatchParseError("PATCH_SIZE_LIMIT", "too many files in patch")

    if not files:
        raise PatchParseError("PATCH_PARSE_ERROR", "patch contains no files")

    total_hunks = sum(file.hunk_count for file in files)
    if total_hunks > effective_limits.max_hunks:
        raise PatchParseError("PATCH_SIZE_LIMIT", "too many hunks in patch")

    return ParsedPatch(files=tuple(files))


def _resolve_paths(
    old_header: str,
    new_header: str,
    is_new_file: bool,
) -> tuple[PatchOperation, str, str | None]:
    old_path = _normalize_header_path(old_header)
    new_path = _normalize_header_path(new_header)

    if new_path == "dev/null":
        raise PatchParseError("PATCH_PARSE_ERROR", "invalid new path")

    if is_new_file or old_path == "dev/null":
        if old_path != "dev/null":
            raise PatchParseError("PATCH_PARSE_ERROR", "create path mismatch")
        return PatchOperation.CREATE, new_path, "dev/null"

    if old_path != new_path:
        raise PatchParseError("PATCH_PARSE_ERROR", "modify path mismatch")
    return PatchOperation.MODIFY, new_path, old_path


def _normalize_header_path(header: str) -> str:
    value = header.strip()
    if value.startswith("a/") or value.startswith("b/"):
        value = value[2:]
    if value == "/dev/null":
        return "dev/null"
    if value.startswith("/"):
        raise PatchParseError("PATCH_PATH_REJECTED", "absolute path rejected")
    if "\\" in value:
        raise PatchParseError("PATCH_PATH_REJECTED", "backslash path rejected")
    parts = PurePosixPath(value).parts
    if not parts or any(part in {".", ".."} for part in parts):
        raise PatchParseError("PATCH_PATH_REJECTED", "invalid path component")
    if any(":" in part for part in parts):
        raise PatchParseError("PATCH_PATH_REJECTED", "alternate data stream rejected")
    return "/".join(parts)


def _parse_hunk(lines: list[str], index: int) -> tuple[PatchHunk, int]:
    header = lines[index]
    match = _HUNK_HEADER.match(header)
    if match is None:
        raise PatchParseError("PATCH_PARSE_ERROR", "malformed hunk header")

    old_start = int(match.group(1))
    old_count = int(match.group(2) or "1")
    new_start = int(match.group(3))
    new_count = int(match.group(4) or "1")
    index += 1

    hunk_lines: list[PatchLine] = []
    old_seen = 0
    new_seen = 0

    while index < len(lines):
        line = lines[index]
        if line.startswith("@@ ") or line.startswith("diff --git "):
            break
        if line == "":
            raise PatchParseError("PATCH_PARSE_ERROR", "blank line inside hunk")
        prefix = line[0]
        body = line[1:]
        missing_newline = False
        if body.endswith(_NO_NEWLINE):
            body = body[: -len(_NO_NEWLINE)]
            missing_newline = True
        if prefix == " ":
            kind = PatchLineKind.CONTEXT
            old_seen += 1
            new_seen += 1
        elif prefix == "-":
            kind = PatchLineKind.REMOVE
            old_seen += 1
        elif prefix == "+":
            kind = PatchLineKind.ADD
            new_seen += 1
        else:
            raise PatchParseError("PATCH_PARSE_ERROR", "invalid hunk line prefix")
        hunk_lines.append(
            PatchLine(kind=kind, text=body, missing_newline=missing_newline),
        )
        index += 1
        if index < len(lines) and lines[index] == _NO_NEWLINE:
            last = hunk_lines[-1]
            hunk_lines[-1] = PatchLine(
                kind=last.kind,
                text=last.text,
                missing_newline=True,
            )
            index += 1
        continue

    if old_seen != old_count or new_seen != new_count:
        raise PatchParseError("PATCH_PARSE_ERROR", "hunk count mismatch")

    return (
        PatchHunk(
            old_start=old_start,
            old_count=old_count,
            new_start=new_start,
            new_count=new_count,
            lines=tuple(hunk_lines),
        ),
        index,
    )
