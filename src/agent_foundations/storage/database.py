from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from agent_foundations.storage.migrations import Migration, validate_migration_sequence


class FutureSchemaVersionError(RuntimeError):
    """Raised when the on-disk schema is newer than this runner supports."""


class SqliteDatabase:
    def __init__(
        self,
        path: Path,
        migrations: tuple[Migration, ...],
    ) -> None:
        self._path = path.resolve()
        self._migrations = validate_migration_sequence(migrations)
        self._latest_version = self._migrations[-1].version

    async def initialize(self) -> None:
        await asyncio.to_thread(self._initialize_sync)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            yield connection
        finally:
            connection.close()

    def _initialize_sync(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            try:
                version = connection.execute("PRAGMA user_version").fetchone()[0]
                if version > self._latest_version:
                    raise FutureSchemaVersionError(
                        f"unsupported schema version: {version}",
                    )
                if version == self._latest_version:
                    connection.commit()
                    return

                for migration in self._migrations:
                    if migration.version <= version:
                        continue
                    if migration.version != version + 1:
                        raise RuntimeError(
                            f"migration version mismatch at version {migration.version}",
                        )
                    for statement in migration.statements:
                        connection.execute(statement)
                    connection.execute(f"PRAGMA user_version = {migration.version}")
                    version = migration.version
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        finally:
            connection.close()
