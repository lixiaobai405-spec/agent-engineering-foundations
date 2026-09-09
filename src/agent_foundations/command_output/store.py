from __future__ import annotations

import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from agent_foundations.command_output.models import (
    ARTIFACT_ID_PATTERN,
    CommandArtifactMetadata,
    ParserStatus,
    RetentionStatus,
    compute_artifact_sha256,
    generate_artifact_id,
)
from agent_foundations.command_output.permissions import apply_owner_only, is_reparse_point
from agent_foundations.command_output.repository import CommandArtifactRepository
from agent_foundations.command_output.retention import (
    DEFAULT_GLOBAL_CAPACITY_BYTES,
    EXECUTION_OUTPUT_LIMIT_BYTES,
)

__all__ = (
    "DEFAULT_GLOBAL_CAPACITY_BYTES",
    "EXECUTION_OUTPUT_LIMIT_BYTES",
)

Clock = Callable[[], datetime]


class ArtifactRootError(ValueError):
    """Artifact root is outside the allowed local application-data boundary."""


class UnsafeArtifactIdError(ValueError):
    """Artifact identifier is not an opaque store-internal directory name."""


class OutputLimitExceeded(RuntimeError):
    code = "OUTPUT_LIMIT_EXCEEDED"


def default_artifact_root() -> Path:
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA")
        base = Path(local) if local else Path.home() / "AppData" / "Local"
        return (base / "AgentFoundations" / "command-output").resolve()
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return (Path(xdg) / "AgentFoundations" / "command-output").resolve()
    return (Path.home() / ".local" / "share" / "AgentFoundations" / "command-output").resolve()


class CommandArtifactStore:
    def __init__(
        self,
        root: Path,
        *,
        repository: CommandArtifactRepository | None = None,
        default_run_id: UUID | None = None,
        execution_limit_bytes: int = EXECUTION_OUTPUT_LIMIT_BYTES,
        global_capacity_bytes: int = DEFAULT_GLOBAL_CAPACITY_BYTES,
        clock: Clock | None = None,
    ) -> None:
        self.root = _validated_root(root)
        self.root.mkdir(parents=True, exist_ok=True)
        apply_owner_only(self.root)
        self._repository = repository
        self._default_run_id = default_run_id
        self._execution_limit_bytes = execution_limit_bytes
        self._global_capacity_bytes = global_capacity_bytes
        self._clock = clock or (lambda: datetime.now(UTC))

    def directory_for(self, artifact_id: str) -> Path:
        if ARTIFACT_ID_PATTERN.fullmatch(artifact_id) is None:
            raise UnsafeArtifactIdError("artifact_id is not an opaque store directory")
        if ":" in artifact_id or any(ord(character) < 32 for character in artifact_id):
            raise UnsafeArtifactIdError("artifact_id contains unsafe path syntax")
        directory = self.root / artifact_id
        if directory.parent != self.root or directory.name != artifact_id:
            raise UnsafeArtifactIdError("artifact_id escaped the artifact root")
        return directory

    def write(
        self,
        *,
        stdout: bytes,
        stderr: bytes,
        run_id: UUID | None = None,
        effect_id: UUID | None = None,
        execution_id: UUID | None = None,
        created_at: datetime | None = None,
    ) -> CommandArtifactMetadata:
        if len(stdout) + len(stderr) > self._execution_limit_bytes:
            raise OutputLimitExceeded("command output exceeded the execution limit")
        artifact_id = generate_artifact_id()
        directory = self.directory_for(artifact_id)
        directory.mkdir(mode=0o700, exist_ok=False)
        apply_owner_only(directory)
        _atomic_write(directory / "stdout", stdout)
        _atomic_write(directory / "stderr", stderr)
        metadata = CommandArtifactMetadata(
            artifact_id=artifact_id,
            run_id=run_id or self._default_run_id or uuid4(),
            effect_id=effect_id or uuid4(),
            execution_id=execution_id or uuid4(),
            stdout_bytes=len(stdout),
            stderr_bytes=len(stderr),
            sha256=compute_artifact_sha256(stdout, stderr),
            created_at=(created_at or self._clock()).astimezone(UTC),
            retention_status=RetentionStatus.ACTIVE,
            parser_status=ParserStatus.PENDING,
        )
        if self._repository is not None:
            self._repository.persist_metadata(metadata)
        return metadata

    def begin_session(
        self,
        *,
        run_id: UUID,
        effect_id: UUID,
        execution_id: UUID,
    ) -> StreamingArtifactSession:
        artifact_id = generate_artifact_id()
        directory = self.directory_for(artifact_id)
        directory.mkdir(mode=0o700, exist_ok=False)
        apply_owner_only(directory)
        return StreamingArtifactSession(
            store=self,
            artifact_id=artifact_id,
            directory=directory,
            run_id=run_id,
            effect_id=effect_id,
            execution_id=execution_id,
            execution_limit_bytes=self._execution_limit_bytes,
            created_at=self._clock().astimezone(UTC),
        )

    def delete_directory(self, artifact_id: str) -> None:
        directory = self.directory_for(artifact_id)
        if not directory.exists():
            return
        for child in directory.iterdir():
            child.unlink()
        directory.rmdir()


class StreamingArtifactSession:
    def __init__(
        self,
        *,
        store: CommandArtifactStore,
        artifact_id: str,
        directory: Path,
        run_id: UUID,
        effect_id: UUID,
        execution_id: UUID,
        execution_limit_bytes: int,
        created_at: datetime,
    ) -> None:
        self.artifact_id = artifact_id
        self._store = store
        self._directory = directory
        self._run_id = run_id
        self._effect_id = effect_id
        self._execution_id = execution_id
        self._limit = execution_limit_bytes
        self._created_at = created_at
        self._stdout = bytearray()
        self._stderr = bytearray()
        self._stdout_file = (directory / "stdout.tmp").open("wb")
        self._stderr_file = (directory / "stderr.tmp").open("wb")
        self.truncated = False

    def feed(self, stream: Literal["stdout", "stderr"], chunk: bytes) -> bool:
        if self.truncated:
            return False
        remaining = self._limit - (len(self._stdout) + len(self._stderr))
        if remaining <= 0:
            self.truncated = True
            return False
        accepted = chunk[:remaining]
        overflow = len(chunk) > remaining
        target = self._stdout if stream == "stdout" else self._stderr
        handle = self._stdout_file if stream == "stdout" else self._stderr_file
        target.extend(accepted)
        handle.write(accepted)
        handle.flush()
        if overflow:
            self.truncated = True
            return False
        return True

    def finalize(self) -> CommandArtifactMetadata:
        self._stdout_file.flush()
        os.fsync(self._stdout_file.fileno())
        self._stdout_file.close()
        self._stderr_file.flush()
        os.fsync(self._stderr_file.fileno())
        self._stderr_file.close()
        stdout_final = self._directory / "stdout"
        stderr_final = self._directory / "stderr"
        os.replace(self._directory / "stdout.tmp", stdout_final)
        os.replace(self._directory / "stderr.tmp", stderr_final)
        apply_owner_only(stdout_final)
        apply_owner_only(stderr_final)
        stdout = bytes(self._stdout)
        stderr = bytes(self._stderr)
        metadata = CommandArtifactMetadata(
            artifact_id=self.artifact_id,
            run_id=self._run_id,
            effect_id=self._effect_id,
            execution_id=self._execution_id,
            stdout_bytes=len(stdout),
            stderr_bytes=len(stderr),
            sha256=compute_artifact_sha256(stdout, stderr),
            created_at=self._created_at,
            retention_status=RetentionStatus.ACTIVE,
            parser_status=ParserStatus.PENDING,
        )
        if self._store._repository is not None:
            self._store._repository.persist_metadata(metadata)
        return metadata

    def abort(self) -> None:
        for handle in (self._stdout_file, self._stderr_file):
            if not handle.closed:
                handle.close()


def _atomic_write(path: Path, data: bytes) -> None:
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    apply_owner_only(path)


def validate_artifact_root(root: Path) -> Path:
    return _validated_root(root)


def _validated_root(root: Path) -> Path:
    if not root.is_absolute():
        raise ArtifactRootError("artifact root must be an absolute path")
    resolved = root.resolve()
    if resolved.exists() and is_reparse_point(resolved):
        raise ArtifactRootError("artifact root must not be a reparse point")
    if _is_git_worktree(resolved):
        raise ArtifactRootError("artifact root must not be a Git worktree or project directory")
    return resolved


def _is_git_worktree(path: Path) -> bool:
    current = path
    while True:
        if (current / ".git").exists():
            return True
        if current.parent == current:
            return False
        current = current.parent
