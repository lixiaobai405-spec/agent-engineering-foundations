from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator

from agent_foundations.domain._model import ValidatedCopyModel
from agent_foundations.domain.errors import PathPolicyViolationError
from agent_foundations.tools.filesystem.path_policy import PathPolicy
from agent_foundations.tools.patch.models import BaselineEntry, DigestHex
from agent_foundations.tools.patch.validator import PatchValidationError
from agent_foundations.tools.utf8_lines import utf8_file_lines, utf8_line_texts


class StructuredChange(ValidatedCopyModel):
    path: str
    expected_sha256: DigestHex
    start_line: int = Field(ge=1)
    old_lines: tuple[str, ...]
    new_lines: tuple[str, ...]

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        if not value or value.strip() != value:
            raise ValueError("path must not be blank or padded")
        if "\\" in value:
            raise ValueError("path must be relative POSIX")
        return value

    @field_validator("old_lines", "new_lines")
    @classmethod
    def validate_line_texts(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for line in value:
            if "\n" in line or "\r" in line:
                raise ValueError("line texts must not contain newline characters")
        return value


def compile_structured_changes(
    changes: Sequence[Mapping[str, Any] | StructuredChange],
    project_root: Path,
) -> tuple[str, tuple[BaselineEntry, ...]]:
    if len(changes) < 1:
        raise PatchValidationError("PATCH_INVALID_ARGUMENTS", "changes must not be empty")
    parsed = tuple(
        item if isinstance(item, StructuredChange) else StructuredChange.model_validate(item)
        for item in changes
    )
    policy = PathPolicy(project_root)
    by_path: dict[str, list[StructuredChange]] = {}
    order: list[str] = []
    for change in parsed:
        if change.path not in by_path:
            by_path[change.path] = []
            order.append(change.path)
        by_path[change.path].append(change)

    diff_parts: list[str] = []
    baselines: list[BaselineEntry] = []
    for relative_path in order:
        try:
            authorized = policy.authorize(relative_path)
        except PathPolicyViolationError as exc:
            raise PatchValidationError("PATCH_PATH_REJECTED", str(exc)) from exc
        raw = authorized.read_bytes()
        actual = hashlib.sha256(raw).hexdigest()
        for change in by_path[relative_path]:
            if change.expected_sha256 != actual:
                raise PatchValidationError("PATCH_BASELINE_MISMATCH", "baseline hash mismatch")
        original_rows = utf8_file_lines(raw)
        original = [text for text, _has_newline in original_rows]
        ended_with_newline = bool(original_rows) and original_rows[-1][1]
        updated = list(original)
        for change in sorted(
            by_path[relative_path],
            key=lambda item: item.start_line,
            reverse=True,
        ):
            updated = _apply_change(updated, change)
        display = policy.display_path(authorized)
        diff_parts.append(
            _unified_diff(
                display,
                original,
                updated,
                original_ended_with_newline=ended_with_newline,
                updated_ended_with_newline=ended_with_newline,
            )
        )
        baselines.append(BaselineEntry(path=display, sha256=actual))
    return "".join(diff_parts), tuple(baselines)


def _line_texts(raw: bytes) -> list[str]:
    return list(utf8_line_texts(raw))


def _apply_change(lines: list[str], change: StructuredChange) -> list[str]:
    index = change.start_line - 1
    old = list(change.old_lines)
    if index < 0 or index > len(lines):
        raise PatchValidationError("PATCH_VALIDATION_ERROR", "old_lines mismatch")
    if index == len(lines) and old:
        raise PatchValidationError("PATCH_VALIDATION_ERROR", "old_lines mismatch")
    actual = lines[index : index + len(old)]
    if actual != old:
        raise PatchValidationError("PATCH_VALIDATION_ERROR", "old_lines mismatch")
    return lines[:index] + list(change.new_lines) + lines[index + len(old) :]


def _unified_diff(
    path: str,
    original: list[str],
    updated: list[str],
    *,
    original_ended_with_newline: bool,
    updated_ended_with_newline: bool,
) -> str:
    if original == updated:
        raise PatchValidationError("PATCH_VALIDATION_ERROR", "changes produced an empty diff")
    start = 0
    while start < len(original) and start < len(updated) and original[start] == updated[start]:
        start += 1
    old_end = len(original)
    new_end = len(updated)
    while old_end > start and new_end > start and original[old_end - 1] == updated[new_end - 1]:
        old_end -= 1
        new_end -= 1
    old_slice = original[start:old_end]
    new_slice = updated[start:new_end]
    old_count = len(old_slice)
    new_count = len(new_slice)
    if old_count == 0:
        old_start = start
    else:
        old_start = start + 1
    new_start = 1 if new_count == 0 and start == 0 else start + 1
    hunk_lines: list[str] = [f"-{line}" for line in old_slice]
    if old_count and old_end == len(original) and original and not original_ended_with_newline:
        hunk_lines.append("\\ No newline at end of file")
    hunk_lines.extend(f"+{line}" for line in new_slice)
    if new_count and new_end == len(updated) and updated and not updated_ended_with_newline:
        hunk_lines.append("\\ No newline at end of file")
    header = f"@@ -{old_start},{old_count} +{new_start},{new_count} @@"
    return (
        f"diff --git a/{path} b/{path}\n"
        f"--- a/{path}\n"
        f"+++ b/{path}\n"
        f"{header}\n"
        + "\n".join(hunk_lines)
        + "\n"
    )
