from __future__ import annotations

import asyncio
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from agent_foundations.storage.database import SqliteDatabase
from agent_foundations.storage.migrations import get_application_migrations
from agent_foundations.tools.patch.models import (
    ValidatedPatch,
    compute_project_root_fingerprint,
)


class PatchRepositoryError(RuntimeError):
    """Base patch proposal repository error."""


class PatchProposalNotFoundError(PatchRepositoryError):
    """Patch proposal not found for run."""


class PatchProposalConflictError(PatchRepositoryError):
    """Stored patch proposal conflicts with incoming content."""


class PatchRunNotFoundError(PatchRepositoryError):
    """Durable run not found."""


class PatchRootMismatchError(PatchRepositoryError):
    """Patch root fingerprint does not match durable run."""


def _serialize_datetime(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


class PatchProposalRepository:
    def __init__(self, database: SqliteDatabase) -> None:
        self._database = database

    @classmethod
    def from_path(cls, path: Path) -> PatchProposalRepository:
        return cls(SqliteDatabase(path, get_application_migrations()))

    async def initialize(self) -> None:
        await self._database.initialize()

    async def save(self, run_id: str, patch: ValidatedPatch) -> ValidatedPatch:
        return await asyncio.to_thread(self._save_sync, run_id, patch)

    async def get(self, run_id: str, patch_id: str) -> ValidatedPatch:
        return await asyncio.to_thread(self._get_sync, run_id, patch_id)

    def _save_sync(self, run_id: str, patch: ValidatedPatch) -> ValidatedPatch:
        now = datetime.now(UTC)
        with self._database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    "SELECT project_root FROM durable_runs WHERE run_id = ?",
                    (run_id,),
                ).fetchone()
                if row is None:
                    connection.rollback()
                    raise PatchRunNotFoundError(f"run not found: {run_id}")
                expected = compute_project_root_fingerprint(Path(row["project_root"]))
                if expected != patch.project_root_fingerprint:
                    connection.rollback()
                    raise PatchRootMismatchError("project root fingerprint mismatch")

                existing = connection.execute(
                    """
                    SELECT patch_json FROM patch_proposals
                    WHERE run_id = ? AND patch_id = ?
                    """,
                    (run_id, patch.patch_id),
                ).fetchone()
                patch_json = patch.model_dump_json()
                if existing is not None:
                    if existing["patch_json"] != patch_json:
                        connection.rollback()
                        raise PatchProposalConflictError(
                            "patch_id already exists with different content",
                        )
                    connection.commit()
                    return patch

                connection.execute(
                    """
                    INSERT INTO patch_proposals (
                        run_id, patch_id, project_root_fingerprint, patch_json, created_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        patch.patch_id,
                        patch.project_root_fingerprint,
                        patch_json,
                        _serialize_datetime(now),
                    ),
                )
                connection.commit()
            except sqlite3.Error:
                connection.rollback()
                raise
            except PatchRepositoryError:
                connection.rollback()
                raise
        return patch

    def _get_sync(self, run_id: str, patch_id: str) -> ValidatedPatch:
        with self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT patch_json FROM patch_proposals
                WHERE run_id = ? AND patch_id = ?
                """,
                (run_id, patch_id),
            ).fetchone()
        if row is None:
            raise PatchProposalNotFoundError(
                f"patch proposal not found: {run_id}/{patch_id}",
            )
        try:
            return ValidatedPatch.model_validate_json(row["patch_json"])
        except ValidationError as exc:
            raise PatchRepositoryError("stored patch_json is invalid") from exc
