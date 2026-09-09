from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import tempfile
from pathlib import Path

from pydantic import ConfigDict, Field

from agent_foundations.domain._model import ValidatedCopyModel
from agent_foundations.domain.errors import PathPolicyViolationError
from agent_foundations.tools.filesystem.path_policy import PathPolicy
from agent_foundations.tools.patch.models import DigestHex

_SNAPSHOT_PREFIX = "agent-foundations-snapshot-"
_REPARSE_POINT = 0x400
_EXCLUDED_PARTS = frozenset(
    {
        ".agent-foundations",
        ".agents",
        ".aws",
        ".azure",
        ".cache",
        ".docker",
        ".gate-backup",
        ".git",
        ".kube",
        ".mypy_cache",
        ".npm",
        ".pytest_cache",
        ".ruff_cache",
        ".ssh",
        ".venv",
        "__pycache__",
        "artifacts",
        "build",
        "coverage",
        "dist",
        "logs",
        "node_modules",
        "traces",
        "venv",
    }
)
_EXCLUDED_PREFIXES = ((".config", "pip"),)
_SENSITIVE_NAMES = frozenset(
    {
        "auth.json",
        "credentials",
        "credentials.json",
        "id_dsa",
        "id_ecdsa",
        "id_ed25519",
        "id_rsa",
        "pip.conf",
        "pip.ini",
        "private.key",
        "token.txt",
    }
)
_SENSITIVE_SUFFIXES = (
    ".db",
    ".key",
    ".log",
    ".pem",
    ".pfx",
    ".sqlite",
    ".sqlite3",
)


class WorkspaceSnapshotError(RuntimeError):
    """Raised when a filtered snapshot cannot be constructed safely."""


class WorkspaceLimits(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    max_files: int = Field(default=10_000, ge=1)
    max_file_bytes: int = Field(default=10 * 1024 * 1024, ge=1)
    max_total_bytes: int = Field(default=100 * 1024 * 1024, ge=1)


class WorkspaceFile(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    path: str
    size_bytes: int = Field(ge=0)
    sha256: DigestHex


class WorkspaceSnapshot(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    root: Path
    controller_root: Path
    project_root: Path
    files: tuple[WorkspaceFile, ...]
    total_bytes: int = Field(ge=0)
    fingerprint: DigestHex


def create_workspace_snapshot(
    project_root: Path,
    *,
    controller_root: Path,
    limits: WorkspaceLimits | None = None,
) -> WorkspaceSnapshot:
    limits = limits or WorkspaceLimits()
    project = _resolve_directory(project_root, label="project")
    controller = _resolve_directory(controller_root, label="controller")
    if controller == project or controller.is_relative_to(project):
        raise WorkspaceSnapshotError("controller root must be outside project")

    snapshot_root = Path(tempfile.mkdtemp(prefix=_SNAPSHOT_PREFIX, dir=controller))
    entries: list[WorkspaceFile] = []
    total_bytes = 0
    path_policy = PathPolicy(project)
    try:
        for discovered in _regular_project_files(project):
            relative = discovered.relative_to(project)
            try:
                source = path_policy.authorize(relative.as_posix())
            except PathPolicyViolationError:
                continue
            if source != discovered.resolve(strict=True):
                raise WorkspaceSnapshotError(
                    f"source changed during snapshot: {relative.as_posix()}"
                )
            if len(entries) >= limits.max_files:
                raise WorkspaceSnapshotError("workspace file-count limit exceeded")
            before = _stable_metadata(source)
            size = before[2]
            if size > limits.max_file_bytes:
                raise WorkspaceSnapshotError("workspace single-file limit exceeded")
            total_bytes += size
            if total_bytes > limits.max_total_bytes:
                raise WorkspaceSnapshotError("workspace total-bytes limit exceeded")

            parent_state = _parent_metadata(project, source.parent)
            destination = snapshot_root.joinpath(*relative.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            digest = _copy_file_contents(source, destination)
            after = _stable_metadata(source)
            if before != after or parent_state != _parent_metadata(project, source.parent):
                raise WorkspaceSnapshotError(
                    f"source changed during snapshot: {relative.as_posix()}"
                )
            if destination.stat().st_size != size:
                raise WorkspaceSnapshotError(
                    f"source changed during snapshot: {relative.as_posix()}"
                )
            entries.append(
                WorkspaceFile(
                    path=relative.as_posix(),
                    size_bytes=size,
                    sha256=digest,
                )
            )

        ordered = tuple(sorted(entries, key=lambda entry: entry.path))
        fingerprint = _snapshot_fingerprint(ordered)
        return WorkspaceSnapshot(
            root=snapshot_root.resolve(strict=True),
            controller_root=controller,
            project_root=project,
            files=ordered,
            total_bytes=total_bytes,
            fingerprint=fingerprint,
        )
    except Exception:
        _cleanup_exact(snapshot_root, controller)
        raise


def cleanup_workspace_snapshot(snapshot: WorkspaceSnapshot) -> None:
    _cleanup_exact(snapshot.root, snapshot.controller_root)


def _resolve_directory(path: Path, *, label: str) -> Path:
    try:
        resolved = path.resolve(strict=True)
    except (OSError, ValueError) as exc:
        raise WorkspaceSnapshotError(f"{label} root must resolve strictly") from exc
    if not resolved.is_dir():
        raise WorkspaceSnapshotError(f"{label} root must be a directory")
    if _is_reparse(resolved.lstat()):
        raise WorkspaceSnapshotError(f"{label} root must not be a reparse point")
    return resolved


def _regular_project_files(root: Path) -> tuple[Path, ...]:
    files: list[Path] = []
    stack = [root]
    while stack:
        directory = stack.pop()
        try:
            children = tuple(os.scandir(directory))
        except OSError as exc:
            raise WorkspaceSnapshotError("workspace enumeration failed closed") from exc
        for child in children:
            relative = Path(child.path).relative_to(root)
            if _is_excluded(relative):
                continue
            try:
                metadata = child.stat(follow_symlinks=False)
            except OSError as exc:
                raise WorkspaceSnapshotError("workspace metadata changed during scan") from exc
            if child.is_symlink() or _is_reparse(metadata):
                continue
            path = Path(child.path)
            if stat.S_ISDIR(metadata.st_mode):
                stack.append(path)
            elif stat.S_ISREG(metadata.st_mode):
                files.append(path)
    return tuple(sorted(files, key=lambda path: path.relative_to(root).as_posix()))


def _is_excluded(relative: Path) -> bool:
    lowered = tuple(part.casefold() for part in relative.parts)
    if any(part in _EXCLUDED_PARTS for part in lowered):
        return True
    if any(lowered[: len(prefix)] == prefix for prefix in _EXCLUDED_PREFIXES):
        return True
    name = lowered[-1]
    return (
        name == ".env"
        or name.startswith(".env.")
        or name in _SENSITIVE_NAMES
        or "credential" in name
        or "secret" in name
        or name.endswith(_SENSITIVE_SUFFIXES)
    )


def _is_reparse(metadata: os.stat_result) -> bool:
    return bool(getattr(metadata, "st_file_attributes", 0) & _REPARSE_POINT)


def _stable_metadata(path: Path) -> tuple[int, int, int, int, int]:
    try:
        metadata = path.stat(follow_symlinks=False)
    except OSError as exc:
        raise WorkspaceSnapshotError("source changed during snapshot") from exc
    if not stat.S_ISREG(metadata.st_mode) or _is_reparse(metadata):
        raise WorkspaceSnapshotError("source changed during snapshot")
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        getattr(metadata, "st_file_attributes", 0),
    )


def _parent_metadata(root: Path, parent: Path) -> tuple[tuple[str, int, int, int], ...]:
    states: list[tuple[str, int, int, int]] = []
    current = root
    for part in parent.relative_to(root).parts:
        current /= part
        try:
            metadata = current.stat(follow_symlinks=False)
        except OSError as exc:
            raise WorkspaceSnapshotError("parent changed during snapshot") from exc
        if not stat.S_ISDIR(metadata.st_mode) or _is_reparse(metadata):
            raise WorkspaceSnapshotError("parent changed during snapshot")
        states.append((part, metadata.st_dev, metadata.st_ino, metadata.st_mtime_ns))
    return tuple(states)


def _copy_file_contents(source: Path, destination: Path) -> str:
    digest = hashlib.sha256()
    try:
        with source.open("rb") as reader, destination.open("xb") as writer:
            while chunk := reader.read(64 * 1024):
                digest.update(chunk)
                writer.write(chunk)
    except OSError as exc:
        raise WorkspaceSnapshotError("workspace file copy failed closed") from exc
    return digest.hexdigest()


def _snapshot_fingerprint(files: tuple[WorkspaceFile, ...]) -> str:
    payload = [
        {"path": entry.path, "sha256": entry.sha256, "size_bytes": entry.size_bytes}
        for entry in files
    ]
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _cleanup_exact(snapshot_root: Path, controller_root: Path) -> None:
    controller = controller_root.resolve(strict=True)
    try:
        candidate = snapshot_root.resolve(strict=False)
    except (OSError, ValueError) as exc:
        raise WorkspaceSnapshotError("snapshot cleanup target is invalid") from exc
    if candidate.parent != controller or not candidate.name.startswith(_SNAPSHOT_PREFIX):
        raise WorkspaceSnapshotError("refusing broad snapshot cleanup")
    if candidate.exists():
        shutil.rmtree(candidate)
