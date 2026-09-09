from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from agent_foundations.storage.database import SqliteDatabase


class CommandOutputAuditRepository:
    def __init__(self, database: SqliteDatabase) -> None:
        self._database = database

    def record(
        self,
        *,
        run_id: str,
        artifact_id: str,
        selector_json: str,
        reason: str,
        returned_bytes: int,
        returned_lines: int,
        decision: str,
    ) -> None:
        with self._database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    """
                    INSERT INTO command_output_reads (
                      read_id, run_id, artifact_id, selector_json, reason,
                      returned_bytes, returned_lines, decision, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid4()),
                        run_id,
                        artifact_id,
                        selector_json,
                        reason[:240],
                        returned_bytes,
                        returned_lines,
                        decision,
                        datetime.now(UTC).isoformat(),
                    ),
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def list_for_run(self, run_id: str) -> tuple[dict[str, object], ...]:
        with self._database.connect() as connection:
            rows = connection.execute(
                """
                SELECT read_id, run_id, artifact_id, selector_json, reason,
                       returned_bytes, returned_lines, decision, created_at
                FROM command_output_reads
                WHERE run_id = ?
                ORDER BY created_at ASC
                """,
                (run_id,),
            ).fetchall()
        return tuple(dict(row) for row in rows)
