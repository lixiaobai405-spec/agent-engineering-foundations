from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from agent_foundations.command_output.models import RetentionStatus
from agent_foundations.command_output.repository import CommandArtifactRepository

if TYPE_CHECKING:
    from agent_foundations.command_output.store import CommandArtifactStore

EXECUTION_OUTPUT_LIMIT_BYTES = 64 * 1024 * 1024
DEFAULT_GLOBAL_CAPACITY_BYTES = 512 * 1024 * 1024
DEFAULT_RETENTION = timedelta(days=7)

Clock = Callable[[], datetime]


class ArtifactCapacityExceeded(RuntimeError):
    code = "ARTIFACT_CAPACITY_EXCEEDED"

    def __init__(self) -> None:
        super().__init__("artifact capacity exceeded")


class ArtifactRetentionSweeper:
    def __init__(
        self,
        store: CommandArtifactStore,
        repository: CommandArtifactRepository,
        *,
        retention: timedelta = DEFAULT_RETENTION,
        global_capacity_bytes: int = DEFAULT_GLOBAL_CAPACITY_BYTES,
        clock: Clock | None = None,
    ) -> None:
        self._store = store
        self._repository = repository
        self._retention = retention
        self._global_capacity_bytes = global_capacity_bytes
        self._clock = clock or (lambda: datetime.now(UTC))

    @property
    def global_capacity_bytes(self) -> int:
        return self._global_capacity_bytes

    @property
    def retention_period(self) -> timedelta:
        return self._retention

    def reserve(self, needed_bytes: int) -> bool:
        while self._repository.used_bytes() + needed_bytes > self._global_capacity_bytes:
            oldest = self._repository.evictable_oldest()
            if oldest is None:
                raise ArtifactCapacityExceeded()
            self._evict(oldest.artifact_id)
        return True

    def sweep_expired(self) -> None:
        cutoff = self._clock().astimezone(UTC) - self._retention
        for artifact_id in self._repository.expired_retained_ids(cutoff):
            self._evict(artifact_id)

    def sweep_pending_delete(self) -> None:
        for artifact_id in self._repository.pending_delete_ids():
            try:
                self._store.delete_directory(artifact_id)
            except OSError:
                self._repository.mark_status(artifact_id, RetentionStatus.DELETE_FAILED)
            else:
                self._repository.mark_status(artifact_id, RetentionStatus.DELETED)

    def _evict(self, artifact_id: str) -> None:
        try:
            self._store.delete_directory(artifact_id)
        except OSError:
            self._repository.mark_status(artifact_id, RetentionStatus.DELETE_FAILED)
            return
        self._repository.mark_status(artifact_id, RetentionStatus.EVICTED)
