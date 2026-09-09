from __future__ import annotations

import base64
import hashlib
import os
import shutil
import stat
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from uuid import uuid4

from agent_foundations.tools.patch.models import (
    PatchFile,
    PatchLineKind,
    PatchOperation,
    ValidatedPatch,
    canonical_json_dumps,
    compute_patch_id,
    compute_project_root_fingerprint,
)
from agent_foundations.tools.utf8_lines import join_utf8_file_lines, utf8_file_lines, utf8_newline

ReplaceFile = Callable[[Path, Path], None]


class PatchApplyError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class PreparedFile:
    path: str
    operation: PatchOperation
    before_sha256: str | None
    after_sha256: str
    content: bytes


@dataclass(frozen=True)
class PreparedPatch:
    patch_id: str
    project_root_fingerprint: str
    transaction_id: str
    files: tuple[PreparedFile, ...]


def prepare_patch(patch: ValidatedPatch, project_root: Path) -> PreparedPatch:
    root = _strict_project_root(project_root)
    if compute_project_root_fingerprint(root) != patch.project_root_fingerprint:
        raise PatchApplyError("PATCH_ROOT_MISMATCH", "project root fingerprint mismatch")

    prepared: list[PreparedFile] = []
    canonical_paths: set[str] = set()
    for patch_file in patch.files:
        target = _strict_target(root, patch_file.path, patch_file.operation)
        canonical = os.path.normcase(str(target.absolute()))
        if canonical in canonical_paths:
            raise PatchApplyError("PATCH_PATH_REJECTED", "duplicate patch target")
        canonical_paths.add(canonical)
        if patch_file.operation is PatchOperation.MODIFY:
            before = _read_regular_file(target)
            before_sha256 = _sha256(before)
            if before_sha256 != patch_file.baseline_sha256:
                raise PatchApplyError(
                    "PATCH_BASELINE_MISMATCH",
                    "modify target baseline drifted",
                )
            content = _apply_hunks(before, patch_file)
        elif patch_file.operation is PatchOperation.CREATE:
            if patch_file.baseline_sha256 is not None:
                raise PatchApplyError(
                    "PATCH_BASELINE_MISMATCH",
                    "create baseline must be null",
                )
            before_sha256 = None
            content = _apply_hunks(b"", patch_file)
        else:
            raise PatchApplyError("PATCH_OPERATION_REJECTED", "delete and rename are unsupported")
        prepared.append(
            PreparedFile(
                path=patch_file.path,
                operation=patch_file.operation,
                before_sha256=before_sha256,
                after_sha256=_sha256(content),
                content=content,
            )
        )

    if compute_patch_id(patch.project_root_fingerprint, patch.files) != patch.patch_id:
        raise PatchApplyError("PATCH_ID_MISMATCH", "patch identity is not canonical")
    return PreparedPatch(
        patch_id=patch.patch_id,
        project_root_fingerprint=patch.project_root_fingerprint,
        transaction_id=str(uuid4()),
        files=tuple(prepared),
    )


def build_applier_payload(prepared: PreparedPatch) -> bytes:
    payload = {
        "patch_id": prepared.patch_id,
        "transaction_id": prepared.transaction_id,
        "files": [
            {
                "path": item.path,
                "operation": item.operation.value,
                "before_sha256": item.before_sha256,
                "after_sha256": item.after_sha256,
                "content_base64": base64.b64encode(item.content).decode("ascii"),
            }
            for item in prepared.files
        ],
    }
    return canonical_json_dumps(payload).encode("utf-8")


def verify_prepared_patch(prepared: PreparedPatch, project_root: Path) -> None:
    root = _strict_project_root(project_root)
    if compute_project_root_fingerprint(root) != prepared.project_root_fingerprint:
        raise PatchApplyError("PATCH_ROOT_MISMATCH", "verification root mismatch")
    for item in prepared.files:
        target = _strict_target(root, item.path, PatchOperation.MODIFY)
        if _sha256(_read_regular_file(target)) != item.after_sha256:
            raise PatchApplyError("PATCH_VERIFY_FAILED", "verification hash mismatch")


def verify_applied_patch(patch: ValidatedPatch, project_root: Path) -> PreparedPatch:
    """Reconcile a crash-after-execute state without repeating the write."""
    root = _strict_project_root(project_root)
    if compute_project_root_fingerprint(root) != patch.project_root_fingerprint:
        raise PatchApplyError("PATCH_ROOT_MISMATCH", "verification root mismatch")
    verified: list[PreparedFile] = []
    for patch_file in patch.files:
        target = _strict_target(root, patch_file.path, PatchOperation.MODIFY)
        current = _read_regular_file(target)
        if patch_file.operation is PatchOperation.CREATE:
            expected = _apply_hunks(b"", patch_file)
            if current != expected:
                raise PatchApplyError("PATCH_VERIFY_FAILED", "created target hash mismatch")
        elif patch_file.operation is PatchOperation.MODIFY:
            reconstructed = _reverse_hunks(current, patch_file)
            if _sha256(reconstructed) != patch_file.baseline_sha256:
                raise PatchApplyError("PATCH_VERIFY_FAILED", "modified target is not applied patch")
        else:
            raise PatchApplyError("PATCH_OPERATION_REJECTED", "delete and rename are unsupported")
        verified.append(
            PreparedFile(
                path=patch_file.path,
                operation=patch_file.operation,
                before_sha256=patch_file.baseline_sha256,
                after_sha256=_sha256(current),
                content=current,
            )
        )
    return PreparedPatch(
        patch_id=patch.patch_id,
        project_root_fingerprint=patch.project_root_fingerprint,
        transaction_id=str(uuid4()),
        files=tuple(verified),
    )


def apply_prepared_patch_atomically(
    prepared: PreparedPatch,
    project_root: Path,
    *,
    replace_file: ReplaceFile = os.replace,
) -> None:
    """Apply a prepared transaction; production Tool execution uses the Docker script."""
    root = _strict_project_root(project_root)
    if compute_project_root_fingerprint(root) != prepared.project_root_fingerprint:
        raise PatchApplyError("PATCH_ROOT_MISMATCH", "transaction root mismatch")
    transaction = root / f".agent-patch-{prepared.transaction_id}"
    if transaction.exists():
        raise PatchApplyError("PATCH_STAGING_CONFLICT", "staging path already exists")
    staging = transaction / "staging"
    backups = transaction / "backups"
    staging.mkdir(parents=True)
    backups.mkdir()
    applied: list[PreparedFile] = []
    try:
        for index, item in enumerate(prepared.files):
            staged = staging / str(index)
            staged.write_bytes(item.content)
            if _sha256(staged.read_bytes()) != item.after_sha256:
                raise PatchApplyError("PATCH_STAGING_FAILED", "staged hash mismatch")
            if item.operation is PatchOperation.MODIFY:
                target = _strict_target(root, item.path, PatchOperation.MODIFY)
                current = _read_regular_file(target)
                if _sha256(current) != item.before_sha256:
                    raise PatchApplyError("PATCH_BASELINE_MISMATCH", "baseline drifted")
                (backups / str(index)).write_bytes(current)
            else:
                _strict_target(root, item.path, PatchOperation.CREATE)

        for index, item in enumerate(prepared.files):
            target = _strict_target(root, item.path, item.operation)
            replace_file(staging / str(index), target)
            applied.append(item)
            if _sha256(_read_regular_file(target)) != item.after_sha256:
                raise PatchApplyError("PATCH_VERIFY_FAILED", "post-replace hash mismatch")
    except Exception as exc:
        rollback_error: Exception | None = None
        for item in reversed(applied):
            index = prepared.files.index(item)
            target = root.joinpath(*PurePosixPath(item.path).parts)
            try:
                if item.operation is PatchOperation.CREATE:
                    target.unlink(missing_ok=True)
                else:
                    os.replace(backups / str(index), target)
            except Exception as rollback_exc:
                rollback_error = rollback_exc
        if rollback_error is not None:
            raise PatchApplyError(
                "PATCH_ROLLBACK_FAILED",
                "patch failed and rollback could not restore every target",
            ) from rollback_error
        raise PatchApplyError("PATCH_ROLLED_BACK", "patch failed and was rolled back") from exc
    finally:
        shutil.rmtree(transaction, ignore_errors=True)


def docker_applier_argv(payload: bytes) -> tuple[str, ...]:
    encoded = base64.b64encode(_DOCKER_APPLIER_SCRIPT.encode("utf-8")).decode("ascii")
    encoded_payload = base64.b64encode(payload).decode("ascii")
    return (
        "python",
        "-c",
        f"import base64;exec(base64.b64decode('{encoded}'))",
        encoded_payload,
    )


def _strict_project_root(project_root: Path) -> Path:
    try:
        root = project_root.resolve(strict=True)
    except (OSError, ValueError) as exc:
        raise PatchApplyError("PATCH_ROOT_MISMATCH", "project root cannot resolve") from exc
    if not root.is_dir() or _is_reparse(root):
        raise PatchApplyError("PATCH_ROOT_MISMATCH", "project root must be a real directory")
    return root


def _strict_target(root: Path, relative_path: str, operation: PatchOperation) -> Path:
    if not relative_path or relative_path.strip() != relative_path or "\\" in relative_path:
        raise PatchApplyError("PATCH_PATH_REJECTED", "invalid relative patch path")
    pure = PurePosixPath(relative_path)
    if pure.is_absolute() or not pure.parts or any(part in {".", ".."} for part in pure.parts):
        raise PatchApplyError("PATCH_PATH_REJECTED", "patch path escapes project")
    if any(
        ":" in part or any(ord(character) < 32 or ord(character) == 127 for character in part)
        for part in pure.parts
    ):
        raise PatchApplyError("PATCH_PATH_REJECTED", "unsafe patch path syntax")
    target = root.joinpath(*pure.parts)
    parent = target.parent
    try:
        resolved_parent = parent.resolve(strict=True)
    except (OSError, ValueError) as exc:
        raise PatchApplyError("PATCH_PATH_REJECTED", "target parent cannot resolve") from exc
    if not resolved_parent.is_relative_to(root):
        raise PatchApplyError("PATCH_PATH_REJECTED", "target parent escapes project")
    cursor = root
    for part in pure.parts[:-1]:
        cursor /= part
        if _is_reparse(cursor) or not cursor.is_dir():
            raise PatchApplyError("PATCH_PATH_REJECTED", "target parent is unsafe")
    if operation is PatchOperation.CREATE:
        if target.exists() or target.is_symlink():
            raise PatchApplyError("PATCH_BASELINE_MISMATCH", "create target now exists")
    else:
        if _is_reparse(target):
            raise PatchApplyError("PATCH_PATH_REJECTED", "target is a reparse point")
        if not target.exists():
            raise PatchApplyError("PATCH_BASELINE_MISMATCH", "modify target is missing")
    return target


def _is_reparse(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except OSError:
        return False
    attributes = getattr(metadata, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(metadata.st_mode) or bool(attributes & reparse_flag)


def _read_regular_file(path: Path) -> bytes:
    if _is_reparse(path):
        raise PatchApplyError("PATCH_PATH_REJECTED", "target is a reparse point")
    try:
        metadata = path.stat()
    except OSError as exc:
        raise PatchApplyError("PATCH_BASELINE_MISMATCH", "target is unavailable") from exc
    if not stat.S_ISREG(metadata.st_mode):
        raise PatchApplyError("PATCH_PATH_REJECTED", "target is not a regular file")
    try:
        data = path.read_bytes()
        data.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise PatchApplyError("PATCH_VALIDATION_ERROR", "target must be readable UTF-8") from exc
    return data


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _lines(raw: bytes) -> list[tuple[str, bool]]:
    return utf8_file_lines(raw)


def _apply_hunks(raw: bytes, patch_file: PatchFile) -> bytes:
    original = _lines(raw)
    output: list[tuple[str, bool]] = []
    cursor = 0
    for hunk in patch_file.hunks:
        start = hunk.old_start - 1 if hunk.old_count else hunk.old_start
        if start < cursor or start > len(original):
            raise PatchApplyError("PATCH_VALIDATION_ERROR", "hunk position is invalid")
        output.extend(original[cursor:start])
        source_index = start
        for line in hunk.lines:
            has_newline = not line.missing_newline
            if line.kind is PatchLineKind.ADD:
                output.append((line.text, has_newline))
                continue
            if source_index >= len(original) or original[source_index] != (
                line.text,
                has_newline,
            ):
                raise PatchApplyError("PATCH_BASELINE_MISMATCH", "hunk baseline drifted")
            if line.kind is PatchLineKind.CONTEXT:
                output.append(original[source_index])
            source_index += 1
        cursor = source_index
    output.extend(original[cursor:])
    return join_utf8_file_lines(output, newline=utf8_newline(raw))


def _reverse_hunks(raw: bytes, patch_file: PatchFile) -> bytes:
    original = _lines(raw)
    output: list[tuple[str, bool]] = []
    cursor = 0
    for hunk in patch_file.hunks:
        start = hunk.new_start - 1 if hunk.new_count else hunk.new_start
        if start < cursor or start > len(original):
            raise PatchApplyError("PATCH_VERIFY_FAILED", "reverse hunk position is invalid")
        output.extend(original[cursor:start])
        source_index = start
        for line in hunk.lines:
            has_newline = not line.missing_newline
            if line.kind is PatchLineKind.REMOVE:
                output.append((line.text, has_newline))
                continue
            if source_index >= len(original) or original[source_index] != (
                line.text,
                has_newline,
            ):
                raise PatchApplyError("PATCH_VERIFY_FAILED", "applied hunk mismatch")
            if line.kind is PatchLineKind.CONTEXT:
                output.append(original[source_index])
            source_index += 1
        cursor = source_index
    output.extend(original[cursor:])
    return join_utf8_file_lines(output, newline=utf8_newline(raw))


_DOCKER_APPLIER_SCRIPT = r'''
import base64, hashlib, json, os, pathlib, shutil, stat, sys

root = pathlib.Path('/workspace').resolve(strict=True)
payload = json.loads(base64.b64decode(sys.argv[1], validate=True))
tx = root / ('.agent-patch-' + payload['transaction_id'])
staging = tx / 'staging'
backups = tx / 'backups'
applied = []

def digest(data):
    return hashlib.sha256(data).hexdigest()

def target_for(item, create):
    value = item['path']
    if not value or value != value.strip() or '\\' in value:
        raise RuntimeError('unsafe path')
    parts = pathlib.PurePosixPath(value).parts
    if not parts or any(part in ('.', '..') for part in parts):
        raise RuntimeError('unsafe path')
    if any(':' in part or any(ord(ch) < 32 or ord(ch) == 127 for ch in part) for part in parts):
        raise RuntimeError('unsafe path')
    target = root.joinpath(*parts)
    parent = target.parent.resolve(strict=True)
    if not parent.is_relative_to(root):
        raise RuntimeError('path escape')
    cursor = root
    for part in parts[:-1]:
        cursor = cursor / part
        if cursor.is_symlink() or not cursor.is_dir():
            raise RuntimeError('unsafe parent')
    if create:
        if target.exists() or target.is_symlink():
            raise RuntimeError('create drift')
    else:
        mode = target.lstat().st_mode
        if target.is_symlink() or not stat.S_ISREG(mode):
            raise RuntimeError('unsafe target')
    return target

try:
    staging.mkdir(parents=True, exist_ok=False)
    backups.mkdir()
    for index, item in enumerate(payload['files']):
        content = base64.b64decode(item['content_base64'], validate=True)
        if digest(content) != item['after_sha256']:
            raise RuntimeError('payload hash mismatch')
        staged = staging / str(index)
        staged.write_bytes(content)
        if digest(staged.read_bytes()) != item['after_sha256']:
            raise RuntimeError('staging hash mismatch')
        create = item['operation'] == 'create'
        target = target_for(item, create)
        if not create:
            before = target.read_bytes()
            if digest(before) != item['before_sha256']:
                raise RuntimeError('baseline drift')
            (backups / str(index)).write_bytes(before)
    for index, item in enumerate(payload['files']):
        create = item['operation'] == 'create'
        target = target_for(item, create)
        if not create and digest(target.read_bytes()) != item['before_sha256']:
            raise RuntimeError('baseline drift before replace')
        os.replace(staging / str(index), target)
        applied.append((index, item, target))
        if digest(target.read_bytes()) != item['after_sha256']:
            raise RuntimeError('post-replace hash mismatch')
except BaseException as error:
    rollback_failed = False
    for index, item, target in reversed(applied):
        try:
            if item['operation'] == 'create':
                target.unlink(missing_ok=True)
            else:
                os.replace(backups / str(index), target)
        except BaseException:
            rollback_failed = True
    shutil.rmtree(tx, ignore_errors=True)
    status = 'rollback_failed' if rollback_failed else 'rolled_back'
    print(json.dumps({'status': status, 'error': type(error).__name__}))
    raise SystemExit(21 if rollback_failed else 20)
else:
    shutil.rmtree(tx, ignore_errors=True)
    print(json.dumps({'status': 'applied', 'patch_id': payload['patch_id']}))
'''


__all__ = [
    "PatchApplyError",
    "PreparedFile",
    "PreparedPatch",
    "apply_prepared_patch_atomically",
    "build_applier_payload",
    "docker_applier_argv",
    "prepare_patch",
    "verify_prepared_patch",
    "verify_applied_patch",
]
