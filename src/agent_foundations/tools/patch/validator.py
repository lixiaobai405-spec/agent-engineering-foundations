from __future__ import annotations

import hashlib
import os
import stat
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath

from agent_foundations.tools.patch.models import (
    BaselineEntry,
    PatchFile,
    PatchHunk,
    PatchLimits,
    PatchLineKind,
    PatchOperation,
    ValidatedPatch,
    build_validated_patch,
    compute_project_root_fingerprint,
)
from agent_foundations.tools.patch.parser import ParsedPatch, PatchParseError


class PatchValidationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def validate_patch_proposal(
    parsed: ParsedPatch,
    baselines: Sequence[BaselineEntry | Mapping[str, object]],
    project_root: Path,
    limits: PatchLimits | None = None,
) -> ValidatedPatch:
    effective_limits = limits or PatchLimits()
    root = project_root.resolve(strict=True)
    fingerprint = compute_project_root_fingerprint(root)

    baseline_entries = _normalize_baselines(baselines)
    _check_baseline_alignment(parsed.files, baseline_entries)

    validated_files: list[PatchFile] = []
    seen_paths: dict[str, str] = {}

    for file in parsed.files:
        canonical = _authorize_relative_path(root, file.path)
        key = _canonical_path_key(canonical)
        if key in seen_paths:
            raise PatchValidationError("PATCH_PATH_REJECTED", "duplicate path in patch")
        seen_paths[key] = file.path

        baseline = _baseline_for(file.path, baseline_entries)
        _reject_binary_patch_content(file)
        if file.operation == PatchOperation.CREATE:
            if baseline.sha256 is not None:
                raise PatchValidationError(
                    "PATCH_BASELINE_MISMATCH",
                    "create baseline must be null",
                )
            _validate_create_hunks(file.hunks)
            _validate_create_target(root, canonical, effective_limits)
            baseline_sha256 = None
        else:
            if baseline.sha256 is None:
                raise PatchValidationError("PATCH_BASELINE_MISMATCH", "modify baseline required")
            baseline_sha256 = baseline.sha256
            file_bytes = _read_regular_file_bytes(canonical, effective_limits)
            actual_hash = hashlib.sha256(file_bytes).hexdigest()
            if actual_hash != baseline_sha256:
                raise PatchValidationError("PATCH_BASELINE_MISMATCH", "baseline hash mismatch")
            file_lines = _file_lines_for_hunks(file_bytes)
            _validate_modify_hunk_topology(file.hunks, len(file_lines))
            _verify_modify_hunks(file_lines, file.hunks)

        validated_files.append(
            file.model_copy(update={"baseline_sha256": baseline_sha256}),
        )

    return build_validated_patch(fingerprint, tuple(validated_files))


def _reject_binary_patch_content(file: PatchFile) -> None:
    for hunk in file.hunks:
        for patch_line in hunk.lines:
            if "\x00" in patch_line.text:
                raise PatchValidationError("PATCH_VALIDATION_ERROR", "binary content rejected")


def _normalize_baselines(
    baselines: Sequence[BaselineEntry | Mapping[str, object]],
) -> tuple[BaselineEntry, ...]:
    entries: list[BaselineEntry] = []
    seen: set[str] = set()
    for item in baselines:
        entry = (
            item if isinstance(item, BaselineEntry)
            else BaselineEntry.model_validate(item)
        )
        if entry.path in seen:
            raise PatchValidationError("PATCH_BASELINE_MISMATCH", "duplicate baseline path")
        seen.add(entry.path)
        entries.append(entry)
    return tuple(entries)


def _check_baseline_alignment(
    files: tuple[PatchFile, ...],
    baselines: tuple[BaselineEntry, ...],
) -> None:
    file_paths = {file.path for file in files}
    baseline_paths = {entry.path for entry in baselines}
    if file_paths != baseline_paths:
        raise PatchValidationError("PATCH_BASELINE_MISMATCH", "baseline paths mismatch diff")


def _baseline_for(path: str, baselines: tuple[BaselineEntry, ...]) -> BaselineEntry:
    for entry in baselines:
        if entry.path == path:
            return entry
    raise PatchValidationError("PATCH_BASELINE_MISMATCH", "missing baseline")


def _is_path_within_root(candidate: Path, root: Path) -> bool:
    root_abs = root.resolve(strict=True)
    try:
        return candidate.absolute().is_relative_to(root_abs)
    except ValueError:
        return False


def _authorize_relative_path(root: Path, relative_path: str) -> Path:
    if "\\" in relative_path or PurePosixPath(relative_path).is_absolute():
        raise PatchValidationError("PATCH_PATH_REJECTED", "invalid relative path")
    parts = PurePosixPath(relative_path).parts
    if not parts or any(part in {".", ".."} for part in parts):
        raise PatchValidationError("PATCH_PATH_REJECTED", "invalid path traversal")
    if any(":" in part for part in parts):
        raise PatchValidationError("PATCH_PATH_REJECTED", "alternate data stream rejected")
    if any(ord(ch) < 32 or ch in '<>"|?*' for part in parts for ch in part):
        raise PatchValidationError("PATCH_PATH_REJECTED", "control character in path")

    normalized = relative_path.replace("/", "\\") if os.name == "nt" else relative_path
    if normalized.startswith("\\\\"):
        raise PatchValidationError("PATCH_PATH_REJECTED", "unc path rejected")
    if len(relative_path) >= 2 and relative_path[1] == ":":
        raise PatchValidationError("PATCH_PATH_REJECTED", "drive path rejected")

    candidate = root.joinpath(*parts)
    if not _is_path_within_root(candidate, root):
        raise PatchValidationError("PATCH_PATH_REJECTED", "path escapes project root")
    _walk_parents_not_reparse(root, candidate.parent if candidate.name else candidate)
    if candidate.name and candidate.exists() and _is_reparse_point(candidate):
        raise PatchValidationError("PATCH_PATH_REJECTED", "target is reparse point")
    return candidate


def _walk_parents_not_reparse(root: Path, target_parent: Path) -> None:
    current = target_parent
    root_resolved = root.resolve(strict=True)
    while True:
        if _is_reparse_point(current):
            raise PatchValidationError("PATCH_PATH_REJECTED", "reparse point in ancestry")
        if not _is_path_within_root(current, root):
            raise PatchValidationError("PATCH_PATH_REJECTED", "path escapes project root")
        current_abs = current.absolute()
        if current_abs == root_resolved or current == root:
            break
        parent = current.parent
        if parent == current:
            break
        current = parent


def _is_reparse_point(path: Path) -> bool:
    if os.name != "nt":
        return path.is_symlink()
    if path.is_symlink():
        return True
    try:
        import ctypes

        attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
        if attrs == -1:
            return True
        return bool(attrs & 0x400)  # FILE_ATTRIBUTE_REPARSE_POINT
    except (AttributeError, OSError):
        return path.is_symlink()


def _canonical_path_key(path: Path) -> str:
    resolved = path.resolve(strict=False)
    text = resolved.as_posix()
    if os.name == "nt":
        return text.casefold()
    return text


def _validate_create_target(root: Path, target: Path, limits: PatchLimits) -> None:
    if target.exists():
        raise PatchValidationError("PATCH_VALIDATION_ERROR", "create target exists")
    parent = target.parent
    _walk_parents_not_reparse(root, parent)
    if not parent.is_dir():
        raise PatchValidationError("PATCH_VALIDATION_ERROR", "parent directory missing")
    if _is_reparse_point(parent):
        raise PatchValidationError("PATCH_PATH_REJECTED", "parent is reparse point")


def _read_regular_file_bytes(path: Path, limits: PatchLimits) -> bytes:
    if not path.exists():
        raise PatchValidationError("PATCH_VALIDATION_ERROR", "modify target missing")
    if _is_reparse_point(path):
        raise PatchValidationError("PATCH_PATH_REJECTED", "target is reparse point")
    if not path.is_file():
        raise PatchValidationError("PATCH_VALIDATION_ERROR", "target is not a regular file")
    if not stat.S_ISREG(path.stat().st_mode):
        raise PatchValidationError("PATCH_VALIDATION_ERROR", "target is not a regular file")
    with path.open("rb") as stream:
        data = stream.read(limits.max_file_bytes + 1)
    if len(data) > limits.max_file_bytes:
        raise PatchValidationError("PATCH_SIZE_LIMIT", "file exceeds byte limit")
    if b"\x00" in data:
        raise PatchValidationError("PATCH_VALIDATION_ERROR", "binary content rejected")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PatchValidationError("PATCH_VALIDATION_ERROR", "non utf-8 file") from exc
    return data


def _validate_create_hunks(hunks: tuple[PatchHunk, ...]) -> None:
    for hunk in hunks:
        if hunk.old_start != 0 or hunk.old_count != 0:
            raise PatchValidationError(
                "PATCH_VALIDATION_ERROR",
                "create hunk must not reference old file lines",
            )
        for patch_line in hunk.lines:
            if patch_line.kind != PatchLineKind.ADD:
                raise PatchValidationError(
                    "PATCH_VALIDATION_ERROR",
                    "create hunk must only add lines",
                )


def _validate_zero_length_insertion_position(old_start: int, file_line_count: int) -> None:
    if old_start < 0 or old_start > file_line_count:
        raise PatchValidationError(
            "PATCH_VALIDATION_ERROR",
            "invalid insertion position",
        )


def _validate_modify_hunk_topology(
    hunks: tuple[PatchHunk, ...],
    file_line_count: int,
) -> None:
    covered_end = 0
    insertion_positions: set[int] = set()
    for index, hunk in enumerate(hunks):
        if index > 0 and hunk.old_start < hunks[index - 1].old_start:
            raise PatchValidationError("PATCH_VALIDATION_ERROR", "hunks out of order")
        if hunk.old_count == 0:
            _validate_zero_length_insertion_position(hunk.old_start, file_line_count)
            if hunk.old_start in insertion_positions:
                raise PatchValidationError(
                    "PATCH_VALIDATION_ERROR",
                    "duplicate insertion position",
                )
            insertion_positions.add(hunk.old_start)
            if covered_end > 0 and hunk.old_start <= covered_end:
                raise PatchValidationError("PATCH_VALIDATION_ERROR", "overlapping hunk")
            continue
        if hunk.old_start < 1:
            raise PatchValidationError("PATCH_VALIDATION_ERROR", "invalid hunk old start")
        start = hunk.old_start
        end = hunk.old_start + hunk.old_count - 1
        if start <= covered_end:
            raise PatchValidationError("PATCH_VALIDATION_ERROR", "overlapping hunk")
        covered_end = end


def _file_lines_for_hunks(raw: bytes) -> list[tuple[str, bool]]:
    text = raw.decode("utf-8")
    ends_without_newline = not text.endswith("\n") and text != ""
    lines = text.split("\n")
    if ends_without_newline:
        result = [(line, index < len(lines) - 1) for index, line in enumerate(lines)]
        if lines:
            last_text, _ = result[-1]
            result[-1] = (last_text, False)
        return result
    if lines and lines[-1] == "":
        lines = lines[:-1]
    return [(line, True) for line in lines]


def _verify_modify_hunks(
    file_lines: list[tuple[str, bool]],
    hunks: tuple[PatchHunk, ...],
) -> None:
    for hunk in hunks:
        if hunk.old_count == 0:
            continue
        line_index = hunk.old_start - 1
        if line_index < 0:
            raise PatchValidationError("PATCH_VALIDATION_ERROR", "hunk out of bounds")
        for patch_line in hunk.lines:
            if patch_line.kind == PatchLineKind.ADD:
                continue
            if line_index >= len(file_lines):
                raise PatchValidationError("PATCH_VALIDATION_ERROR", "hunk out of bounds")
            actual_text, actual_has_newline = file_lines[line_index]
            if patch_line.text != actual_text:
                raise PatchValidationError("PATCH_VALIDATION_ERROR", "hunk context mismatch")
            expected_missing = not actual_has_newline
            if patch_line.missing_newline != expected_missing:
                raise PatchValidationError("PATCH_VALIDATION_ERROR", "newline state mismatch")
            line_index += 1


def parse_and_validate_patch(
    diff: str,
    baselines: Sequence[BaselineEntry | Mapping[str, object]],
    project_root: Path,
    limits: PatchLimits | None = None,
) -> ValidatedPatch:
    from agent_foundations.tools.patch.parser import parse_unified_diff

    try:
        parsed = parse_unified_diff(diff, limits)
    except PatchParseError as exc:
        raise PatchValidationError(exc.code, str(exc)) from exc
    return validate_patch_proposal(parsed, baselines, project_root, limits)
