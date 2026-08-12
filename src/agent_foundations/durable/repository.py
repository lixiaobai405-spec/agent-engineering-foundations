from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from agent_foundations.domain.tool import ToolResult
from agent_foundations.durable.models import (
    DurableRun,
    DurableRunStatus,
    EffectStatus,
    RunCheckpoint,
    RunLease,
    RunState,
    SideEffectIntent,
    SideEffectRecord,
)
from agent_foundations.storage.database import SqliteDatabase
from agent_foundations.storage.migrations import get_application_migrations

_RUN_STATE_SCHEMA_VERSION = 1
_CHECKPOINT_SCHEMA_VERSION = 1

_ALLOWED_TRANSITIONS: dict[DurableRunStatus, frozenset[DurableRunStatus]] = {
    DurableRunStatus.CREATED: frozenset({
        DurableRunStatus.RUNNING,
        DurableRunStatus.CANCELLED,
    }),
    DurableRunStatus.PAUSED: frozenset({
        DurableRunStatus.RUNNING,
        DurableRunStatus.CANCELLED,
    }),
    DurableRunStatus.WAITING_APPROVAL: frozenset({
        DurableRunStatus.RUNNING,
        DurableRunStatus.CANCELLED,
    }),
    DurableRunStatus.RUNNING: frozenset({
        DurableRunStatus.PAUSED,
        DurableRunStatus.WAITING_APPROVAL,
        DurableRunStatus.COMPLETED,
        DurableRunStatus.FAILED,
        DurableRunStatus.CANCELLED,
    }),
}

_CANCELABLE_STATUSES = frozenset({
    DurableRunStatus.CREATED,
    DurableRunStatus.RUNNING,
    DurableRunStatus.PAUSED,
    DurableRunStatus.WAITING_APPROVAL,
})


class DurableRepositoryError(RuntimeError):
    """Base durable repository error."""


class DurableRunAlreadyExistsError(DurableRepositoryError):
    """Run ID already exists in durable_runs."""


class DurableRunNotFoundError(DurableRepositoryError):
    """Requested durable run does not exist."""


class CheckpointNotFoundError(DurableRepositoryError):
    """No checkpoint exists for the requested run."""


class StateVersionConflictError(DurableRepositoryError):
    """Expected state_version does not match the database."""


class UnsupportedCheckpointSchemaVersionError(DurableRepositoryError):
    """Checkpoint row or embedded state uses an unsupported schema version."""


class ExecutionFactRunMismatchError(DurableRepositoryError):
    """last_committed_tool_fact.session_id does not match run_id."""


class IdempotencyConflictError(DurableRepositoryError):
    """Side-effect identity conflicts with a different intent digest."""


class EffectNotFoundError(DurableRepositoryError):
    """Requested side-effect record does not exist."""


class EffectStatusConflictError(DurableRepositoryError):
    """Side-effect status does not allow the requested transition."""


class EffectOwnerConflictError(DurableRepositoryError):
    """Side-effect execution owner does not match."""


_ALLOWED_EFFECT_TRANSITIONS: dict[EffectStatus, frozenset[EffectStatus]] = {
    EffectStatus.INTENT_RECORDED: frozenset({EffectStatus.EXECUTING}),
    EffectStatus.EXECUTING: frozenset({
        EffectStatus.COMMITTED,
        EffectStatus.FAILED,
        EffectStatus.UNKNOWN,
    }),
}


class DurableRunStatusConflictError(DurableRepositoryError):
    """Durable run status does not allow the requested transition."""


class InvalidLeaseWriteParametersError(DurableRepositoryError):
    """Lease and checked_at must be provided together for owned writes."""


class LeaseWriteRejectedError(DurableRepositoryError):
    """Lease credentials, expiry, or ownership rejected the write."""


def _serialize_datetime(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _deserialize_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return parsed.astimezone(UTC)


def _coerce_utc_datetime(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        return _deserialize_datetime(value)
    return value.astimezone(UTC)


def _serialize_tool_result(result: ToolResult) -> str:
    return result.model_dump_json()


def _deserialize_tool_result(value: str) -> ToolResult:
    return ToolResult.model_validate_json(value)


def _validate_pending_side_effect_record(
    row: sqlite3.Row,
    target_status: EffectStatus,
    result: ToolResult | None,
    error_code: str | None,
    execution_owner_id: str | None,
    executing_at: datetime | None,
    resolved_at: datetime | None,
    updated_at: datetime,
) -> None:
    """Validate invariants before persisting a side-effect status transition."""
    if target_status == EffectStatus.COMMITTED:
        if result is None or not result.success:
            raise EffectStatusConflictError("COMMITTED requires a successful result")
    elif target_status == EffectStatus.FAILED:
        if result is not None and result.success:
            raise EffectStatusConflictError("FAILED requires an unsuccessful result")
    pending_error_code = error_code
    if target_status in {EffectStatus.COMMITTED, EffectStatus.FAILED} and result is not None:
        pending_error_code = result.error_code or error_code
    try:
        SideEffectRecord(
            effect_id=row["effect_id"],
            run_id=row["run_id"],
            tool_call_id=row["tool_call_id"],
            tool_name=row["tool_name"],
            idempotency_key=row["idempotency_key"],
            intent_digest=row["intent_digest"],
            intent_summary=row["intent_summary"],
            status=target_status,
            result=result,
            error_code=pending_error_code,
            execution_owner_id=execution_owner_id,
            created_at=_deserialize_datetime(row["created_at"]),
            updated_at=updated_at,
            executing_at=executing_at,
            resolved_at=resolved_at,
        )
    except ValidationError as exc:
        raise EffectStatusConflictError(
            f"invalid side effect transition: {exc}",
        ) from exc


def _row_to_side_effect(row: sqlite3.Row) -> SideEffectRecord:
    result: ToolResult | None = None
    if row["result_json"] is not None:
        result = _deserialize_tool_result(row["result_json"])
    executing_at = (
        _deserialize_datetime(row["executing_at"])
        if row["executing_at"] is not None
        else None
    )
    resolved_at = (
        _deserialize_datetime(row["resolved_at"])
        if row["resolved_at"] is not None
        else None
    )
    return SideEffectRecord(
        effect_id=row["effect_id"],
        run_id=row["run_id"],
        tool_call_id=row["tool_call_id"],
        tool_name=row["tool_name"],
        idempotency_key=row["idempotency_key"],
        intent_digest=row["intent_digest"],
        intent_summary=row["intent_summary"],
        status=EffectStatus(row["status"]),
        result=result,
        error_code=row["error_code"],
        execution_owner_id=row["execution_owner_id"],
        created_at=_deserialize_datetime(row["created_at"]),
        updated_at=_deserialize_datetime(row["updated_at"]),
        executing_at=executing_at,
        resolved_at=resolved_at,
    )


def _serialize_run_state(state: RunState) -> str:
    payload = state.model_dump(mode="json")
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _validate_run_state_for_run(run_id: str, state: RunState) -> None:
    if state.schema_version != _RUN_STATE_SCHEMA_VERSION:
        raise UnsupportedCheckpointSchemaVersionError(
            f"unsupported run state schema version: {state.schema_version}",
        )
    fact = state.last_committed_tool_fact
    if fact is not None and fact.session_id != run_id:
        raise ExecutionFactRunMismatchError(
            f"last_committed_tool_fact.session_id must match run_id: "
            f"{fact.session_id} != {run_id}",
        )


def _row_to_durable_run(row: sqlite3.Row) -> DurableRun:
    return DurableRun(
        run_id=row["run_id"],
        project_root=row["project_root"],
        status=DurableRunStatus(row["status"]),
        schema_version=1,
        state_version=int(row["state_version"]),
        attempt=int(row["attempt"]),
        created_at=_deserialize_datetime(row["created_at"]),
        updated_at=_deserialize_datetime(row["updated_at"]),
    )


def _assert_lease_write(
    connection: sqlite3.Connection,
    run_id: str,
    lease: RunLease,
    checked_at: datetime,
) -> None:
    row = connection.execute(
        """
        SELECT owner_id, lease_token, expires_at, released_at
        FROM run_leases
        WHERE run_id = ? AND lease_token = ?
        """,
        (run_id, lease.lease_token),
    ).fetchone()
    if row is None:
        raise LeaseWriteRejectedError("lease record not found")
    if row["released_at"] is not None:
        raise LeaseWriteRejectedError("lease already released")
    if row["owner_id"] != lease.owner_id or row["lease_token"] != lease.lease_token:
        raise LeaseWriteRejectedError("lease credentials do not match")
    expires_at = _deserialize_datetime(row["expires_at"])
    if expires_at <= checked_at:
        raise LeaseWriteRejectedError("lease has expired")


def _assert_status(
    connection: sqlite3.Connection,
    run_id: str,
    expected: DurableRunStatus,
) -> None:
    row = connection.execute(
        "SELECT status FROM durable_runs WHERE run_id = ?",
        (run_id,),
    ).fetchone()
    if row is None:
        raise DurableRunNotFoundError(f"durable run not found: {run_id}")
    current = DurableRunStatus(row["status"])
    if current != expected:
        raise DurableRunStatusConflictError(
            f"status conflict for run {run_id}: expected {expected.value}, got {current.value}",
        )


class DurableRunRepository:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path.resolve()
        self._database = SqliteDatabase(
            self._database_path,
            get_application_migrations(),
        )

    async def initialize(self) -> None:
        await self._database.initialize()

    async def create_run(self, run: DurableRun) -> DurableRun:
        return await asyncio.to_thread(self._create_run_sync, run)

    async def get_run(self, run_id: str) -> DurableRun:
        return await asyncio.to_thread(self._get_run_sync, run_id)

    async def transition_status(
        self,
        run_id: str,
        expected: DurableRunStatus,
        target: DurableRunStatus,
        *,
        lease: RunLease | None = None,
        checked_at: datetime | None = None,
    ) -> DurableRun:
        return await asyncio.to_thread(
            self._transition_status_sync,
            run_id,
            expected,
            target,
            lease,
            checked_at,
        )

    async def save_checkpoint(
        self,
        run_id: str,
        expected_state_version: int,
        state: RunState,
        *,
        lease: RunLease | None = None,
        checked_at: datetime | None = None,
        expected_status: DurableRunStatus | None = None,
    ) -> RunCheckpoint:
        return await asyncio.to_thread(
            self._save_checkpoint_sync,
            run_id,
            expected_state_version,
            state,
            lease,
            checked_at,
            expected_status,
        )

    async def begin_retry(
        self,
        run_id: str,
        expected_state_version: int,
        state: RunState,
        *,
        lease: RunLease,
        checked_at: datetime,
    ) -> RunCheckpoint:
        return await asyncio.to_thread(
            self._begin_retry_sync,
            run_id,
            expected_state_version,
            state,
            lease,
            checked_at,
        )

    async def cancel_run(self, run_id: str) -> DurableRun:
        return await asyncio.to_thread(self._cancel_run_sync, run_id)

    async def load_latest_checkpoint(self, run_id: str) -> RunCheckpoint:
        return await asyncio.to_thread(self._load_latest_checkpoint_sync, run_id)

    async def prepare_side_effect(
        self,
        run_id: str,
        tool_call_id: str,
        tool_name: str,
        intent: SideEffectIntent,
        intent_digest: str,
        idempotency_key: str,
        *,
        checked_at: datetime,
    ) -> SideEffectRecord:
        return await asyncio.to_thread(
            self._prepare_side_effect_sync,
            run_id,
            tool_call_id,
            tool_name,
            intent,
            intent_digest,
            idempotency_key,
            checked_at,
        )

    async def get_side_effect(
        self,
        run_id: str,
        tool_call_id: str,
        tool_name: str,
    ) -> SideEffectRecord | None:
        return await asyncio.to_thread(
            self._get_side_effect_sync,
            run_id,
            tool_call_id,
            tool_name,
        )

    async def transition_side_effect(
        self,
        effect_id: str,
        expected_status: EffectStatus,
        target_status: EffectStatus,
        *,
        execution_owner_id: str | None = None,
        expected_owner_id: str | None = None,
        result: ToolResult | None = None,
        error_code: str | None = None,
        checked_at: datetime | None = None,
    ) -> SideEffectRecord:
        return await asyncio.to_thread(
            self._transition_side_effect_sync,
            effect_id,
            expected_status,
            target_status,
            execution_owner_id,
            expected_owner_id,
            result,
            error_code,
            checked_at or datetime.now(UTC),
        )

    def _create_run_sync(self, run: DurableRun) -> DurableRun:
        if run.state_version != 0:
            raise ValueError("create_run requires initial state_version of 0")
        with self._database.connect() as connection:
            existing = connection.execute(
                "SELECT 1 FROM durable_runs WHERE run_id = ?",
                (run.run_id,),
            ).fetchone()
            if existing is not None:
                raise DurableRunAlreadyExistsError(
                    f"durable run already exists: {run.run_id}",
                )
            connection.execute(
                """
                INSERT INTO durable_runs (
                    run_id,
                    project_root,
                    status,
                    schema_version,
                    state_version,
                    attempt,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.run_id,
                    run.project_root,
                    run.status.value,
                    run.schema_version,
                    run.state_version,
                    run.attempt,
                    _serialize_datetime(run.created_at),
                    _serialize_datetime(run.updated_at),
                ),
            )
            connection.commit()
        return run

    def _get_run_sync(self, run_id: str) -> DurableRun:
        with self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT run_id, project_root, status, state_version, attempt,
                       created_at, updated_at
                FROM durable_runs
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
            if row is None:
                raise DurableRunNotFoundError(f"durable run not found: {run_id}")
        return _row_to_durable_run(row)

    def _transition_status_sync(
        self,
        run_id: str,
        expected: DurableRunStatus,
        target: DurableRunStatus,
        lease: RunLease | None,
        checked_at: datetime | None,
    ) -> DurableRun:
        if lease is not None or checked_at is not None:
            if lease is None or checked_at is None:
                raise InvalidLeaseWriteParametersError(
                    "lease and checked_at must be provided together",
                )
        allowed = _ALLOWED_TRANSITIONS.get(expected, frozenset())
        if target not in allowed:
            raise DurableRunStatusConflictError(
                f"transition {expected.value} -> {target.value} is not allowed",
            )
        now = datetime.now(UTC)
        with self._database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                _assert_status(connection, run_id, expected)
                if lease is not None and checked_at is not None:
                    _assert_lease_write(connection, run_id, lease, checked_at)
                connection.execute(
                    """
                    UPDATE durable_runs
                    SET status = ?, updated_at = ?
                    WHERE run_id = ?
                    """,
                    (target.value, _serialize_datetime(now), run_id),
                )
                row = connection.execute(
                    """
                    SELECT run_id, project_root, status, state_version, attempt,
                           created_at, updated_at
                    FROM durable_runs
                    WHERE run_id = ?
                    """,
                    (run_id,),
                ).fetchone()
                connection.commit()
            except sqlite3.Error:
                connection.rollback()
                raise
            except DurableRepositoryError:
                connection.rollback()
                raise
            except Exception:
                connection.rollback()
                raise
        if row is None:
            raise DurableRunNotFoundError(f"durable run not found: {run_id}")
        return _row_to_durable_run(row)

    def _save_checkpoint_sync(
        self,
        run_id: str,
        expected_state_version: int,
        state: RunState,
        lease: RunLease | None = None,
        checked_at: datetime | None = None,
        expected_status: DurableRunStatus | None = None,
    ) -> RunCheckpoint:
        _validate_run_state_for_run(run_id, state)
        if lease is not None or checked_at is not None:
            if lease is None or checked_at is None:
                raise InvalidLeaseWriteParametersError(
                    "lease and checked_at must be provided together",
                )
        checkpoint_id = str(uuid4())
        now = datetime.now(UTC)
        state_json = _serialize_run_state(state)

        with self._database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    """
                    SELECT state_version, status
                    FROM durable_runs
                    WHERE run_id = ?
                    """,
                    (run_id,),
                ).fetchone()
                if row is None:
                    connection.rollback()
                    raise DurableRunNotFoundError(f"durable run not found: {run_id}")
                if expected_status is not None:
                    current_status = DurableRunStatus(row["status"])
                    if current_status != expected_status:
                        connection.rollback()
                        raise DurableRunStatusConflictError(
                            f"status conflict for run {run_id}: "
                            f"expected {expected_status.value}, got {current_status.value}",
                        )
                if lease is not None and checked_at is not None:
                    _assert_lease_write(connection, run_id, lease, checked_at)
                current_version = int(row["state_version"])
                if current_version != expected_state_version:
                    connection.rollback()
                    raise StateVersionConflictError(
                        f"state_version conflict for run {run_id}: "
                        f"expected {expected_state_version}, got {current_version}",
                    )

                next_sequence_row = connection.execute(
                    """
                    SELECT COALESCE(MAX(sequence), 0) + 1
                    FROM run_checkpoints
                    WHERE run_id = ?
                    """,
                    (run_id,),
                ).fetchone()
                sequence = int(next_sequence_row[0])

                connection.execute(
                    """
                    INSERT INTO run_checkpoints (
                        checkpoint_id,
                        run_id,
                        sequence,
                        schema_version,
                        state_json,
                        created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        checkpoint_id,
                        run_id,
                        sequence,
                        _CHECKPOINT_SCHEMA_VERSION,
                        state_json,
                        _serialize_datetime(now),
                    ),
                )
                connection.execute(
                    """
                    UPDATE durable_runs
                    SET state_version = state_version + 1,
                        attempt = ?,
                        updated_at = ?
                    WHERE run_id = ?
                    """,
                    (state.attempt, _serialize_datetime(now), run_id),
                )
                connection.commit()
            except sqlite3.Error:
                connection.rollback()
                raise
            except DurableRepositoryError:
                connection.rollback()
                raise
            except Exception:
                connection.rollback()
                raise

        return RunCheckpoint(
            checkpoint_id=checkpoint_id,
            run_id=run_id,
            sequence=sequence,
            schema_version=1,
            state=state,
            created_at=now,
        )

    def _begin_retry_sync(
        self,
        run_id: str,
        expected_state_version: int,
        state: RunState,
        lease: RunLease,
        checked_at: datetime,
    ) -> RunCheckpoint:
        _validate_run_state_for_run(run_id, state)
        checkpoint_id = str(uuid4())
        now = datetime.now(UTC)

        with self._database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                _assert_status(connection, run_id, DurableRunStatus.FAILED)
                _assert_lease_write(connection, run_id, lease, checked_at)
                row = connection.execute(
                    """
                    SELECT state_version, attempt
                    FROM durable_runs
                    WHERE run_id = ?
                    """,
                    (run_id,),
                ).fetchone()
                if row is None:
                    connection.rollback()
                    raise DurableRunNotFoundError(f"durable run not found: {run_id}")
                current_version = int(row["state_version"])
                if current_version != expected_state_version:
                    connection.rollback()
                    raise StateVersionConflictError(
                        f"state_version conflict for run {run_id}: "
                        f"expected {expected_state_version}, got {current_version}",
                    )
                current_attempt = int(row["attempt"])
                retry_state = state.model_copy(
                    update={"attempt": current_attempt + 1},
                )
                state_json = _serialize_run_state(retry_state)

                next_sequence_row = connection.execute(
                    """
                    SELECT COALESCE(MAX(sequence), 0) + 1
                    FROM run_checkpoints
                    WHERE run_id = ?
                    """,
                    (run_id,),
                ).fetchone()
                sequence = int(next_sequence_row[0])

                connection.execute(
                    """
                    INSERT INTO run_checkpoints (
                        checkpoint_id,
                        run_id,
                        sequence,
                        schema_version,
                        state_json,
                        created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        checkpoint_id,
                        run_id,
                        sequence,
                        _CHECKPOINT_SCHEMA_VERSION,
                        state_json,
                        _serialize_datetime(now),
                    ),
                )
                connection.execute(
                    """
                    UPDATE durable_runs
                    SET state_version = state_version + 1,
                        attempt = attempt + 1,
                        status = ?,
                        updated_at = ?
                    WHERE run_id = ?
                    """,
                    (
                        DurableRunStatus.RUNNING.value,
                        _serialize_datetime(now),
                        run_id,
                    ),
                )
                connection.commit()
            except sqlite3.Error:
                connection.rollback()
                raise
            except DurableRepositoryError:
                connection.rollback()
                raise
            except Exception:
                connection.rollback()
                raise

        return RunCheckpoint(
            checkpoint_id=checkpoint_id,
            run_id=run_id,
            sequence=sequence,
            schema_version=1,
            state=retry_state,
            created_at=now,
        )

    def _cancel_run_sync(self, run_id: str) -> DurableRun:
        now = datetime.now(UTC)
        with self._database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    """
                    SELECT status
                    FROM durable_runs
                    WHERE run_id = ?
                    """,
                    (run_id,),
                ).fetchone()
                if row is None:
                    connection.rollback()
                    raise DurableRunNotFoundError(f"durable run not found: {run_id}")
                current = DurableRunStatus(row["status"])
                if current not in _CANCELABLE_STATUSES:
                    connection.rollback()
                    raise DurableRunStatusConflictError(
                        f"cannot cancel run in status {current.value}",
                    )
                connection.execute(
                    """
                    UPDATE durable_runs
                    SET status = ?, updated_at = ?
                    WHERE run_id = ?
                    """,
                    (DurableRunStatus.CANCELLED.value, _serialize_datetime(now), run_id),
                )
                updated = connection.execute(
                    """
                    SELECT run_id, project_root, status, state_version, attempt,
                           created_at, updated_at
                    FROM durable_runs
                    WHERE run_id = ?
                    """,
                    (run_id,),
                ).fetchone()
                connection.commit()
            except sqlite3.Error:
                connection.rollback()
                raise
            except DurableRepositoryError:
                connection.rollback()
                raise
            except Exception:
                connection.rollback()
                raise
        if updated is None:
            raise DurableRunNotFoundError(f"durable run not found: {run_id}")
        return _row_to_durable_run(updated)

    def _load_latest_checkpoint_sync(self, run_id: str) -> RunCheckpoint:
        with self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT checkpoint_id, run_id, sequence, schema_version, state_json, created_at
                FROM run_checkpoints
                WHERE run_id = ?
                ORDER BY sequence DESC
                LIMIT 1
                """,
                (run_id,),
            ).fetchone()
            if row is None:
                raise CheckpointNotFoundError(
                    f"no checkpoint found for run: {run_id}",
                )
        return _row_to_checkpoint(row)

    def _prepare_side_effect_sync(
        self,
        run_id: str,
        tool_call_id: str,
        tool_name: str,
        intent: SideEffectIntent,
        intent_digest: str,
        idempotency_key: str,
        checked_at: datetime,
    ) -> SideEffectRecord:
        now = checked_at.astimezone(UTC)
        effect_id = str(uuid4())
        with self._database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    """
                    SELECT effect_id, run_id, tool_call_id, tool_name, idempotency_key,
                           intent_digest, intent_summary, status, result_json, error_code,
                           execution_owner_id, created_at, updated_at, executing_at, resolved_at
                    FROM side_effects
                    WHERE run_id = ? AND tool_call_id = ? AND tool_name = ?
                    """,
                    (run_id, tool_call_id, tool_name),
                ).fetchone()
                if row is not None:
                    if (
                        row["intent_digest"] != intent_digest
                        or row["idempotency_key"] != idempotency_key
                    ):
                        connection.rollback()
                        raise IdempotencyConflictError(
                            "side-effect identity conflicts with different intent",
                        )
                    connection.commit()
                    return _row_to_side_effect(row)
                connection.execute(
                    """
                    INSERT INTO side_effects (
                        effect_id, run_id, tool_call_id, tool_name, idempotency_key,
                        intent_digest, intent_summary, status, result_json, error_code,
                        execution_owner_id, created_at, updated_at, executing_at, resolved_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, ?, ?, NULL, NULL)
                    """,
                    (
                        effect_id,
                        run_id,
                        tool_call_id,
                        tool_name,
                        idempotency_key,
                        intent_digest,
                        intent.summary,
                        EffectStatus.INTENT_RECORDED.value,
                        _serialize_datetime(now),
                        _serialize_datetime(now),
                    ),
                )
                connection.commit()
            except sqlite3.Error:
                connection.rollback()
                raise
            except DurableRepositoryError:
                connection.rollback()
                raise
            except Exception:
                connection.rollback()
                raise
        return SideEffectRecord(
            effect_id=effect_id,
            run_id=run_id,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            idempotency_key=idempotency_key,
            intent_digest=intent_digest,
            intent_summary=intent.summary,
            status=EffectStatus.INTENT_RECORDED,
            result=None,
            error_code=None,
            execution_owner_id=None,
            created_at=now,
            updated_at=now,
            executing_at=None,
            resolved_at=None,
        )

    def _get_side_effect_sync(
        self,
        run_id: str,
        tool_call_id: str,
        tool_name: str,
    ) -> SideEffectRecord | None:
        with self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT effect_id, run_id, tool_call_id, tool_name, idempotency_key,
                       intent_digest, intent_summary, status, result_json, error_code,
                       execution_owner_id, created_at, updated_at, executing_at, resolved_at
                FROM side_effects
                WHERE run_id = ? AND tool_call_id = ? AND tool_name = ?
                """,
                (run_id, tool_call_id, tool_name),
            ).fetchone()
        if row is None:
            return None
        return _row_to_side_effect(row)

    def _transition_side_effect_sync(
        self,
        effect_id: str,
        expected_status: EffectStatus,
        target_status: EffectStatus,
        execution_owner_id: str | None,
        expected_owner_id: str | None,
        result: ToolResult | None,
        error_code: str | None,
        checked_at: datetime,
    ) -> SideEffectRecord:
        allowed = _ALLOWED_EFFECT_TRANSITIONS.get(expected_status, frozenset())
        if target_status not in allowed:
            raise EffectStatusConflictError(
                f"transition {expected_status.value} -> {target_status.value} is not allowed",
            )
        now = checked_at.astimezone(UTC)
        with self._database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    """
                    SELECT effect_id, run_id, tool_call_id, tool_name, idempotency_key,
                           intent_digest, intent_summary, status, result_json, error_code,
                           execution_owner_id, created_at, updated_at, executing_at, resolved_at
                    FROM side_effects
                    WHERE effect_id = ?
                    """,
                    (effect_id,),
                ).fetchone()
                if row is None:
                    connection.rollback()
                    raise EffectNotFoundError(f"side effect not found: {effect_id}")
                current_status = EffectStatus(row["status"])
                if current_status != expected_status:
                    connection.rollback()
                    raise EffectStatusConflictError(
                        f"status conflict: expected {expected_status.value}, "
                        f"got {current_status.value}",
                    )
                current_owner = row["execution_owner_id"]
                if target_status == EffectStatus.EXECUTING:
                    if execution_owner_id is None or not execution_owner_id.strip():
                        connection.rollback()
                        raise EffectOwnerConflictError("execution_owner_id required")
                    new_owner = execution_owner_id
                    new_executing_at = now
                    new_result_json = row["result_json"]
                    new_error_code = row["error_code"]
                    new_resolved_at = None
                elif target_status in {EffectStatus.COMMITTED, EffectStatus.FAILED}:
                    if execution_owner_id is None or current_owner != execution_owner_id:
                        connection.rollback()
                        raise EffectOwnerConflictError("execution owner mismatch")
                    new_owner = current_owner
                    new_executing_at = row["executing_at"]
                    if result is None:
                        connection.rollback()
                        raise ValueError("result required for terminal transition")
                    new_result_json = _serialize_tool_result(result)
                    new_error_code = result.error_code or error_code
                    new_resolved_at = None
                elif target_status == EffectStatus.UNKNOWN:
                    if expected_owner_id is not None and current_owner != expected_owner_id:
                        connection.rollback()
                        raise EffectOwnerConflictError("execution owner mismatch")
                    new_owner = current_owner
                    new_executing_at = row["executing_at"]
                    new_result_json = row["result_json"]
                    new_error_code = error_code
                    new_resolved_at = _serialize_datetime(now)
                else:
                    connection.rollback()
                    raise EffectStatusConflictError(
                        f"unsupported target status: {target_status.value}",
                    )
                _validate_pending_side_effect_record(
                    row,
                    target_status,
                    result,
                    new_error_code,
                    new_owner,
                    _coerce_utc_datetime(new_executing_at),
                    _coerce_utc_datetime(new_resolved_at),
                    now,
                )
                connection.execute(
                    """
                    UPDATE side_effects
                    SET status = ?, result_json = ?, error_code = ?,
                        execution_owner_id = ?, updated_at = ?,
                        executing_at = ?, resolved_at = ?
                    WHERE effect_id = ?
                    """,
                    (
                        target_status.value,
                        new_result_json,
                        new_error_code,
                        new_owner,
                        _serialize_datetime(now),
                        new_executing_at,
                        new_resolved_at,
                        effect_id,
                    ),
                )
                updated = connection.execute(
                    """
                    SELECT effect_id, run_id, tool_call_id, tool_name, idempotency_key,
                           intent_digest, intent_summary, status, result_json, error_code,
                           execution_owner_id, created_at, updated_at, executing_at, resolved_at
                    FROM side_effects
                    WHERE effect_id = ?
                    """,
                    (effect_id,),
                ).fetchone()
                connection.commit()
            except sqlite3.Error:
                connection.rollback()
                raise
            except DurableRepositoryError:
                connection.rollback()
                raise
            except Exception:
                connection.rollback()
                raise
        if updated is None:
            raise EffectNotFoundError(f"side effect not found: {effect_id}")
        return _row_to_side_effect(updated)


def _row_to_checkpoint(row: sqlite3.Row) -> RunCheckpoint:
    row_schema_version = int(row["schema_version"])
    if row_schema_version != _CHECKPOINT_SCHEMA_VERSION:
        raise UnsupportedCheckpointSchemaVersionError(
            f"unsupported checkpoint schema version: {row_schema_version}",
        )
    try:
        state = RunState.model_validate_json(row["state_json"])
    except ValidationError as exc:
        raise UnsupportedCheckpointSchemaVersionError(
            f"invalid checkpoint state_json: {exc}",
        ) from exc
    if state.schema_version != _RUN_STATE_SCHEMA_VERSION:
        raise UnsupportedCheckpointSchemaVersionError(
            f"unsupported run state schema version: {state.schema_version}",
        )
    if row_schema_version != state.schema_version:
        raise UnsupportedCheckpointSchemaVersionError(
            "checkpoint schema_version does not match embedded state schema_version",
        )
    return RunCheckpoint(
        checkpoint_id=row["checkpoint_id"],
        run_id=row["run_id"],
        sequence=int(row["sequence"]),
        schema_version=1,
        state=state,
        created_at=_deserialize_datetime(row["created_at"]),
    )
