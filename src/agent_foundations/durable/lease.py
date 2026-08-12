from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import uuid4

from agent_foundations.durable.models import RunLease
from agent_foundations.durable.repository import (
    DurableRepositoryError,
    DurableRunNotFoundError,
    DurableRunRepository,
    _deserialize_datetime,
    _serialize_datetime,
)

Clock = Callable[[], datetime]

_RELEASE_EXPLICIT = "explicit_release"
_RELEASE_TAKEOVER = "expired_takeover"


class LeaseError(DurableRepositoryError):
    """Base lease manager error."""


class LeaseConflictError(LeaseError):
    """Active lease already exists or lease already released."""


class LeaseNotFoundError(LeaseError):
    """No matching unreleased lease record exists."""


class LeaseTokenMismatchError(LeaseError):
    """Lease credentials do not match the active record."""


class LeaseExpiredError(LeaseError):
    """Lease has expired and cannot be renewed."""


class LeaseNotExpiredError(LeaseError):
    """Lease is still active and cannot be taken over."""


class InvalidLeaseTTLError(LeaseError):
    """Lease TTL must be strictly positive."""


class InvalidLeaseClockError(LeaseError):
    """Injected clock returned a naive datetime."""


def _utc_now(clock: Clock) -> datetime:
    value = clock()
    if value.tzinfo is None or value.utcoffset() is None:
        raise InvalidLeaseClockError("clock must return a timezone-aware datetime")
    return value.astimezone(UTC)


def _validate_ttl(ttl: timedelta) -> None:
    if ttl <= timedelta(0):
        raise InvalidLeaseTTLError("lease ttl must be strictly positive")


def _row_to_run_lease(row: sqlite3.Row) -> RunLease:
    return RunLease(
        run_id=row["run_id"],
        owner_id=row["owner_id"],
        lease_token=row["lease_token"],
        acquired_at=_deserialize_datetime(row["acquired_at"]),
        expires_at=_deserialize_datetime(row["expires_at"]),
    )


class LeaseManager:
    def __init__(
        self,
        repository: DurableRunRepository,
        *,
        clock: Clock | None = None,
    ) -> None:
        self._repository = repository
        self._clock: Clock = clock or (lambda: datetime.now(UTC))

    async def acquire(
        self,
        run_id: str,
        owner_id: str,
        ttl: timedelta,
    ) -> RunLease:
        return await asyncio.to_thread(
            self._acquire_sync,
            run_id,
            owner_id,
            ttl,
        )

    async def renew(self, lease: RunLease, ttl: timedelta) -> RunLease:
        return await asyncio.to_thread(self._renew_sync, lease, ttl)

    async def release(self, lease: RunLease) -> None:
        await asyncio.to_thread(self._release_sync, lease)

    async def takeover_expired(
        self,
        run_id: str,
        owner_id: str,
        ttl: timedelta,
    ) -> RunLease:
        return await asyncio.to_thread(
            self._takeover_expired_sync,
            run_id,
            owner_id,
            ttl,
        )

    def _acquire_sync(
        self,
        run_id: str,
        owner_id: str,
        ttl: timedelta,
    ) -> RunLease:
        _validate_ttl(ttl)
        now = _utc_now(self._clock)
        lease_token = str(uuid4())
        expires_at = now + ttl

        with self._repository._database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                if not self._run_exists(connection, run_id):
                    connection.rollback()
                    raise DurableRunNotFoundError(f"durable run not found: {run_id}")
                if self._active_lease_row(connection, run_id) is not None:
                    connection.rollback()
                    raise LeaseConflictError(
                        f"active lease already exists for run: {run_id}",
                    )
                connection.execute(
                    """
                    INSERT INTO run_leases (
                        lease_token,
                        run_id,
                        owner_id,
                        acquired_at,
                        expires_at,
                        renewal_count
                    ) VALUES (?, ?, ?, ?, ?, 0)
                    """,
                    (
                        lease_token,
                        run_id,
                        owner_id,
                        _serialize_datetime(now),
                        _serialize_datetime(expires_at),
                    ),
                )
                connection.commit()
            except sqlite3.Error:
                connection.rollback()
                raise
            except (DurableRepositoryError, LeaseError):
                raise
            except Exception:
                connection.rollback()
                raise

        return RunLease(
            run_id=run_id,
            owner_id=owner_id,
            lease_token=lease_token,
            acquired_at=now,
            expires_at=expires_at,
        )

    def _renew_sync(self, lease: RunLease, ttl: timedelta) -> RunLease:
        _validate_ttl(ttl)
        now = _utc_now(self._clock)
        new_expires_at = now + ttl

        with self._repository._database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._active_lease_row(connection, lease.run_id)
                if row is None:
                    connection.rollback()
                    raise LeaseNotFoundError(
                        f"no active lease for run: {lease.run_id}",
                    )
                if row["owner_id"] != lease.owner_id or row["lease_token"] != lease.lease_token:
                    connection.rollback()
                    raise LeaseTokenMismatchError("lease credentials do not match")
                expires_at = _deserialize_datetime(row["expires_at"])
                if expires_at <= now:
                    connection.rollback()
                    raise LeaseExpiredError("lease has expired")
                connection.execute(
                    """
                    UPDATE run_leases
                    SET expires_at = ?,
                        renewed_at = ?,
                        renewal_count = renewal_count + 1
                    WHERE lease_token = ?
                    """,
                    (
                        _serialize_datetime(new_expires_at),
                        _serialize_datetime(now),
                        lease.lease_token,
                    ),
                )
                connection.commit()
            except sqlite3.Error:
                connection.rollback()
                raise
            except (DurableRepositoryError, LeaseError):
                raise
            except Exception:
                connection.rollback()
                raise

        return RunLease(
            run_id=lease.run_id,
            owner_id=lease.owner_id,
            lease_token=lease.lease_token,
            acquired_at=_deserialize_datetime(row["acquired_at"]),
            expires_at=new_expires_at,
        )

    def _release_sync(self, lease: RunLease) -> None:
        now = _utc_now(self._clock)

        with self._repository._database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    """
                    SELECT lease_token, released_at
                    FROM run_leases
                    WHERE run_id = ? AND owner_id = ? AND lease_token = ?
                    """,
                    (lease.run_id, lease.owner_id, lease.lease_token),
                ).fetchone()
                if row is None:
                    connection.rollback()
                    raise self._release_lookup_error(connection, lease)
                if row["released_at"] is not None:
                    connection.rollback()
                    raise LeaseConflictError("lease already released")
                connection.execute(
                    """
                    UPDATE run_leases
                    SET released_at = ?, release_reason = ?
                    WHERE lease_token = ?
                    """,
                    (
                        _serialize_datetime(now),
                        _RELEASE_EXPLICIT,
                        lease.lease_token,
                    ),
                )
                connection.commit()
            except sqlite3.Error:
                connection.rollback()
                raise
            except (DurableRepositoryError, LeaseError):
                raise
            except Exception:
                connection.rollback()
                raise

    def _takeover_expired_sync(
        self,
        run_id: str,
        owner_id: str,
        ttl: timedelta,
    ) -> RunLease:
        _validate_ttl(ttl)
        now = _utc_now(self._clock)
        new_token = str(uuid4())
        new_expires_at = now + ttl

        with self._repository._database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                if not self._run_exists(connection, run_id):
                    connection.rollback()
                    raise DurableRunNotFoundError(f"durable run not found: {run_id}")
                row = self._active_lease_row(connection, run_id)
                if row is None:
                    connection.rollback()
                    raise LeaseNotFoundError(f"no active lease for run: {run_id}")
                expires_at = _deserialize_datetime(row["expires_at"])
                if expires_at > now:
                    connection.rollback()
                    raise LeaseNotExpiredError("lease has not expired")
                old_token = row["lease_token"]
                connection.execute(
                    """
                    UPDATE run_leases
                    SET released_at = ?, release_reason = ?
                    WHERE lease_token = ?
                    """,
                    (
                        _serialize_datetime(now),
                        _RELEASE_TAKEOVER,
                        old_token,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO run_leases (
                        lease_token,
                        run_id,
                        owner_id,
                        acquired_at,
                        expires_at,
                        renewal_count,
                        predecessor_token
                    ) VALUES (?, ?, ?, ?, ?, 0, ?)
                    """,
                    (
                        new_token,
                        run_id,
                        owner_id,
                        _serialize_datetime(now),
                        _serialize_datetime(new_expires_at),
                        old_token,
                    ),
                )
                connection.commit()
            except sqlite3.Error:
                connection.rollback()
                raise
            except (DurableRepositoryError, LeaseError):
                raise
            except Exception:
                connection.rollback()
                raise

        return RunLease(
            run_id=run_id,
            owner_id=owner_id,
            lease_token=new_token,
            acquired_at=now,
            expires_at=new_expires_at,
        )

    def _run_exists(self, connection: sqlite3.Connection, run_id: str) -> bool:
        row = connection.execute(
            "SELECT 1 FROM durable_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        return row is not None

    def _active_lease_row(
        self,
        connection: sqlite3.Connection,
        run_id: str,
    ) -> sqlite3.Row | None:
        return cast(
            "sqlite3.Row | None",
            connection.execute(
                """
                SELECT lease_token, run_id, owner_id, acquired_at, expires_at, released_at
                FROM run_leases
                WHERE run_id = ? AND released_at IS NULL
                """,
                (run_id,),
            ).fetchone(),
        )

    def _release_lookup_error(
        self,
        connection: sqlite3.Connection,
        lease: RunLease,
    ) -> LeaseError:
        active = self._active_lease_row(connection, lease.run_id)
        if active is not None:
            return LeaseTokenMismatchError("lease credentials do not match")
        return LeaseNotFoundError(f"lease not found: {lease.lease_token}")
