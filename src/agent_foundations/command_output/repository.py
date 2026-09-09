from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from agent_foundations.command_output.models import (
    CommandArtifactMetadata,
    ParserStatus,
    RetentionStatus,
)
from agent_foundations.storage.database import SqliteDatabase
from agent_foundations.storage.migrations import get_application_migrations


class CommandArtifactNotFoundError(LookupError):
    """Requested command artifact metadata does not exist."""


class CommandArtifactRepository:
    def __init__(self, database: SqliteDatabase) -> None:
        self._database = database

    @classmethod
    def from_path(cls, path: Path) -> CommandArtifactRepository:
        return cls(SqliteDatabase(path, get_application_migrations()))

    @property
    def path(self) -> Path:
        return self._database._path

    async def initialize(self) -> None:
        await self._database.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        with self._database.connect() as connection:
            yield connection

    def persist_metadata(self, metadata: CommandArtifactMetadata) -> None:
        with self._database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    """
                    INSERT INTO command_output_artifacts (
                      artifact_id, run_id, effect_id, execution_id,
                      stdout_bytes, stderr_bytes, sha256, created_at,
                      retention_status, parser_status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        metadata.artifact_id,
                        str(metadata.run_id),
                        str(metadata.effect_id),
                        str(metadata.execution_id),
                        metadata.stdout_bytes,
                        metadata.stderr_bytes,
                        metadata.sha256,
                        metadata.created_at.astimezone(UTC).isoformat(),
                        metadata.retention_status.value,
                        metadata.parser_status.value,
                    ),
                )
                connection.commit()
            except sqlite3.Error:
                connection.rollback()
                raise

    def fetch_artifact(self, artifact_id: str) -> CommandArtifactMetadata:
        with self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT artifact_id, run_id, effect_id, execution_id,
                       stdout_bytes, stderr_bytes, sha256, created_at,
                       retention_status, parser_status
                FROM command_output_artifacts
                WHERE artifact_id = ?
                """,
                (artifact_id,),
            ).fetchone()
        if row is None:
            raise CommandArtifactNotFoundError(artifact_id)
        return _row_to_metadata(row)

    def mark_retained(self, artifact_id: str) -> None:
        self._set_status(artifact_id, RetentionStatus.RETAINED)

    def mark_pending_delete(self, artifact_id: str) -> None:
        self._set_status(artifact_id, RetentionStatus.PENDING_DELETE)

    def mark_status(self, artifact_id: str, status: RetentionStatus) -> None:
        self._set_status(artifact_id, status)

    def update_parser_status(self, artifact_id: str, status: ParserStatus) -> None:
        if status is ParserStatus.PENDING:
            raise ValueError("parser_status cannot be reverted to pending")
        with self._database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                cursor = connection.execute(
                    """
                    UPDATE command_output_artifacts
                    SET parser_status = ?
                    WHERE artifact_id = ?
                    """,
                    (status.value, artifact_id),
                )
                if cursor.rowcount != 1:
                    connection.rollback()
                    raise CommandArtifactNotFoundError(artifact_id)
                connection.commit()
            except sqlite3.Error:
                connection.rollback()
                raise

    def mark_pending_delete_for_run(self, run_id: str) -> tuple[str, ...]:
        with self._database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                rows = connection.execute(
                    """
                    SELECT artifact_id FROM command_output_artifacts
                    WHERE run_id = ? AND retention_status NOT IN ('deleted', 'evicted')
                    ORDER BY created_at ASC
                    """,
                    (run_id,),
                ).fetchall()
                artifact_ids = tuple(row["artifact_id"] for row in rows)
                if artifact_ids:
                    connection.execute(
                        f"""
                        UPDATE command_output_artifacts
                        SET retention_status = ?
                        WHERE artifact_id IN ({",".join("?" for _ in artifact_ids)})
                        """,
                        (RetentionStatus.PENDING_DELETE.value, *artifact_ids),
                    )
                connection.commit()
            except sqlite3.Error:
                connection.rollback()
                raise
        return artifact_ids

    def pending_delete_ids(self) -> tuple[str, ...]:
        with self._database.connect() as connection:
            rows = connection.execute(
                """
                SELECT artifact_id FROM command_output_artifacts
                WHERE retention_status = ?
                ORDER BY created_at ASC
                """,
                (RetentionStatus.PENDING_DELETE.value,),
            ).fetchall()
        return tuple(row["artifact_id"] for row in rows)

    def expired_retained_ids(self, cutoff: datetime) -> tuple[str, ...]:
        with self._database.connect() as connection:
            rows = connection.execute(
                """
                SELECT artifact_id FROM command_output_artifacts
                WHERE retention_status = ? AND created_at <= ?
                ORDER BY created_at ASC
                """,
                (RetentionStatus.RETAINED.value, cutoff.astimezone(UTC).isoformat()),
            ).fetchall()
        return tuple(row["artifact_id"] for row in rows)

    def evictable_oldest(self) -> CommandArtifactMetadata | None:
        with self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT artifact_id, run_id, effect_id, execution_id,
                       stdout_bytes, stderr_bytes, sha256, created_at,
                       retention_status, parser_status
                FROM command_output_artifacts
                WHERE retention_status IN ('retained')
                ORDER BY created_at ASC
                LIMIT 1
                """
            ).fetchone()
        if row is None:
            return None
        return _row_to_metadata(row)

    def used_bytes(self) -> int:
        with self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT COALESCE(SUM(stdout_bytes + stderr_bytes), 0) AS total
                FROM command_output_artifacts
                WHERE retention_status IN ('active', 'retained', 'pending_delete', 'delete_failed')
                """
            ).fetchone()
        return int(row["total"])

    def _set_status(self, artifact_id: str, status: RetentionStatus) -> None:
        with self._database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                cursor = connection.execute(
                    """
                    UPDATE command_output_artifacts
                    SET retention_status = ?
                    WHERE artifact_id = ?
                    """,
                    (status.value, artifact_id),
                )
                if cursor.rowcount != 1:
                    connection.rollback()
                    raise CommandArtifactNotFoundError(artifact_id)
                connection.commit()
            except sqlite3.Error:
                connection.rollback()
                raise


def _row_to_metadata(row: sqlite3.Row) -> CommandArtifactMetadata:
    created_at = datetime.fromisoformat(row["created_at"])
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    return CommandArtifactMetadata(
        artifact_id=row["artifact_id"],
        run_id=UUID(row["run_id"]),
        effect_id=UUID(row["effect_id"]),
        execution_id=UUID(row["execution_id"]),
        stdout_bytes=row["stdout_bytes"],
        stderr_bytes=row["stderr_bytes"],
        sha256=row["sha256"],
        created_at=created_at,
        retention_status=RetentionStatus(row["retention_status"]),
        parser_status=ParserStatus(row["parser_status"]),
    )
