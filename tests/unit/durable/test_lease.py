from __future__ import annotations

import asyncio
import importlib.util
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest
from pydantic import ValidationError

RUN_ID = "22222222-2222-4222-8222-222222222222"
RUN_ID_UNKNOWN = "55555555-5555-4555-8555-555555555555"
PROJECT_ROOT = "/tmp/project"
NOW = datetime(2026, 8, 2, 12, 0, 0, tzinfo=UTC)
OWNER_A = "worker-a"
OWNER_B = "worker-b"
TTL = timedelta(seconds=30)


class FakeClock:
    def __init__(self, current: datetime) -> None:
        self._current = current.astimezone(UTC)

    def __call__(self) -> datetime:
        return self._current

    def advance(self, delta: timedelta) -> None:
        self._current = self._current + delta


def _require_lease_package() -> None:
    assert importlib.util.find_spec("agent_foundations.durable.lease") is not None


def _require_run_lease_model() -> None:
    spec = importlib.util.find_spec("agent_foundations.durable.models")
    assert spec is not None


def _tables(connection: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'",
        )
    }


async def _open_stack(
    path: Path,
    clock: Callable[[], datetime] | FakeClock,
) -> tuple[Any, Any, Any]:
    from agent_foundations.durable.lease import LeaseManager
    from agent_foundations.durable.repository import DurableRunRepository

    repository = DurableRunRepository(path)
    await repository.initialize()
    manager = LeaseManager(repository, clock=clock)
    return repository, manager, clock


def _sample_durable_run(run_id: str = RUN_ID) -> Any:
    from agent_foundations.durable.models import DurableRun, DurableRunStatus

    return DurableRun(
        run_id=run_id,
        project_root=PROJECT_ROOT,
        status=DurableRunStatus.CREATED,
        schema_version=1,
        state_version=0,
        attempt=1,
        created_at=NOW,
        updated_at=NOW,
    )


def _lease_row(
    connection: sqlite3.Connection,
    lease_token: str,
) -> sqlite3.Row:
    row = connection.execute(
        "SELECT * FROM run_leases WHERE lease_token = ?",
        (lease_token,),
    ).fetchone()
    assert row is not None
    return cast(sqlite3.Row, row)


def test_run_lease_model_is_frozen() -> None:
    _require_run_lease_model()
    from agent_foundations.durable.models import RunLease

    lease = RunLease(
        run_id=RUN_ID,
        owner_id=OWNER_A,
        lease_token=str(uuid4()),
        acquired_at=NOW,
        expires_at=NOW + TTL,
    )
    with pytest.raises(ValidationError):
        lease.owner_id = OWNER_B


def test_run_lease_rejects_invalid_uuid() -> None:
    _require_run_lease_model()
    from agent_foundations.durable.models import RunLease

    with pytest.raises(ValidationError, match="run_id"):
        RunLease(
            run_id="not-a-uuid",
            owner_id=OWNER_A,
            lease_token=str(uuid4()),
            acquired_at=NOW,
            expires_at=NOW + TTL,
        )


def test_run_lease_rejects_blank_owner() -> None:
    _require_run_lease_model()
    from agent_foundations.durable.models import RunLease

    with pytest.raises(ValidationError, match="owner_id"):
        RunLease(
            run_id=RUN_ID,
            owner_id="   ",
            lease_token=str(uuid4()),
            acquired_at=NOW,
            expires_at=NOW + TTL,
        )


def test_run_lease_rejects_naive_datetime() -> None:
    _require_run_lease_model()
    from agent_foundations.durable.models import RunLease

    naive = datetime(2026, 8, 2, 12, 0, 0)
    with pytest.raises(ValidationError, match="timezone-aware"):
        RunLease(
            run_id=RUN_ID,
            owner_id=OWNER_A,
            lease_token=str(uuid4()),
            acquired_at=naive,
            expires_at=NOW + TTL,
        )


def test_run_lease_rejects_expires_at_not_after_acquired_at() -> None:
    _require_run_lease_model()
    from agent_foundations.durable.models import RunLease

    with pytest.raises(ValidationError, match="expires_at"):
        RunLease(
            run_id=RUN_ID,
            owner_id=OWNER_A,
            lease_token=str(uuid4()),
            acquired_at=NOW,
            expires_at=NOW,
        )


def test_run_lease_model_copy_revalidates() -> None:
    _require_run_lease_model()
    from agent_foundations.durable.models import RunLease

    lease = RunLease(
        run_id=RUN_ID,
        owner_id=OWNER_A,
        lease_token=str(uuid4()),
        acquired_at=NOW,
        expires_at=NOW + TTL,
    )
    with pytest.raises(ValidationError, match="owner_id"):
        lease.model_copy(update={"owner_id": "  "})


@pytest.mark.asyncio
async def test_acquire_succeeds_for_known_run(tmp_path: Path) -> None:
    _require_lease_package()
    clock = FakeClock(NOW)
    repository, manager, _ = await _open_stack(tmp_path / "db.sqlite3", clock)
    await repository.create_run(_sample_durable_run())
    lease = await manager.acquire(RUN_ID, OWNER_A, TTL)
    assert lease.run_id == RUN_ID
    assert lease.owner_id == OWNER_A
    assert lease.acquired_at == NOW
    assert lease.expires_at == NOW + TTL
    assert lease.lease_token != RUN_ID


@pytest.mark.asyncio
async def test_acquire_rejects_naive_clock_without_writing_lease(tmp_path: Path) -> None:
    _require_lease_package()
    from agent_foundations.durable.lease import InvalidLeaseClockError

    def naive_clock() -> datetime:
        return datetime(2026, 8, 2, 12, 0, 0)

    repository, manager, _ = await _open_stack(tmp_path / "db.sqlite3", naive_clock)
    await repository.create_run(_sample_durable_run())
    with pytest.raises(InvalidLeaseClockError, match="timezone-aware"):
        await manager.acquire(RUN_ID, OWNER_A, TTL)
    with repository._database.connect() as connection:
        count = connection.execute("SELECT COUNT(*) FROM run_leases").fetchone()[0]
    assert count == 0


@pytest.mark.asyncio
async def test_acquire_rejects_invalid_ttl(tmp_path: Path) -> None:
    _require_lease_package()
    from agent_foundations.durable.lease import InvalidLeaseTTLError

    clock = FakeClock(NOW)
    repository, manager, _ = await _open_stack(tmp_path / "db.sqlite3", clock)
    await repository.create_run(_sample_durable_run())
    with pytest.raises(InvalidLeaseTTLError):
        await manager.acquire(RUN_ID, OWNER_A, timedelta(0))
    with repository._database.connect() as connection:
        count = connection.execute("SELECT COUNT(*) FROM run_leases").fetchone()[0]
    assert count == 0


@pytest.mark.asyncio
async def test_acquire_rejects_unknown_run(tmp_path: Path) -> None:
    _require_lease_package()
    from agent_foundations.durable.repository import DurableRunNotFoundError

    clock = FakeClock(NOW)
    _, manager, _ = await _open_stack(tmp_path / "db.sqlite3", clock)
    with pytest.raises(DurableRunNotFoundError):
        await manager.acquire(RUN_ID_UNKNOWN, OWNER_A, TTL)


@pytest.mark.asyncio
async def test_acquire_conflicts_for_same_owner_twice(tmp_path: Path) -> None:
    _require_lease_package()
    from agent_foundations.durable.lease import LeaseConflictError

    clock = FakeClock(NOW)
    repository, manager, _ = await _open_stack(tmp_path / "db.sqlite3", clock)
    await repository.create_run(_sample_durable_run())
    await manager.acquire(RUN_ID, OWNER_A, TTL)
    with pytest.raises(LeaseConflictError):
        await manager.acquire(RUN_ID, OWNER_A, TTL)


@pytest.mark.asyncio
async def test_acquire_conflicts_for_different_owner(tmp_path: Path) -> None:
    _require_lease_package()
    from agent_foundations.durable.lease import LeaseConflictError

    clock = FakeClock(NOW)
    repository, manager, _ = await _open_stack(tmp_path / "db.sqlite3", clock)
    await repository.create_run(_sample_durable_run())
    await manager.acquire(RUN_ID, OWNER_A, TTL)
    with pytest.raises(LeaseConflictError):
        await manager.acquire(RUN_ID, OWNER_B, TTL)


@pytest.mark.asyncio
async def test_acquire_does_not_takeover_expired_lease_silently(tmp_path: Path) -> None:
    _require_lease_package()
    from agent_foundations.durable.lease import LeaseConflictError

    clock = FakeClock(NOW)
    repository, manager, _ = await _open_stack(tmp_path / "db.sqlite3", clock)
    await repository.create_run(_sample_durable_run())
    first = await manager.acquire(RUN_ID, OWNER_A, TTL)
    clock.advance(TTL)
    with pytest.raises(LeaseConflictError):
        await manager.acquire(RUN_ID, OWNER_B, TTL)
    with repository._database.connect() as connection:
        row = _lease_row(connection, first.lease_token)
    assert row["released_at"] is None


@pytest.mark.asyncio
async def test_concurrent_acquire_only_one_succeeds(tmp_path: Path) -> None:
    _require_lease_package()
    from agent_foundations.durable.lease import LeaseConflictError

    clock = FakeClock(NOW)
    repository, manager_a, _ = await _open_stack(tmp_path / "db.sqlite3", clock)
    manager_b = type(manager_a)(repository, clock=clock)
    await repository.create_run(_sample_durable_run())
    results = await asyncio.gather(
        manager_a.acquire(RUN_ID, OWNER_A, TTL),
        manager_b.acquire(RUN_ID, OWNER_B, TTL),
        return_exceptions=True,
    )
    successes = [r for r in results if not isinstance(r, BaseException)]
    conflicts = [r for r in results if isinstance(r, LeaseConflictError)]
    assert len(successes) == 1
    assert len(conflicts) == 1
    with repository._database.connect() as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM run_leases WHERE run_id = ? AND released_at IS NULL",
            (RUN_ID,),
        ).fetchone()[0]
    assert count == 1


@pytest.mark.asyncio
async def test_renew_extends_expiry_from_now(tmp_path: Path) -> None:
    _require_lease_package()
    clock = FakeClock(NOW)
    repository, manager, _ = await _open_stack(tmp_path / "db.sqlite3", clock)
    await repository.create_run(_sample_durable_run())
    lease = await manager.acquire(RUN_ID, OWNER_A, TTL)
    clock.advance(timedelta(seconds=10))
    renewed = await manager.renew(lease, TTL)
    assert renewed.lease_token == lease.lease_token
    assert renewed.owner_id == OWNER_A
    assert renewed.acquired_at == NOW
    assert renewed.expires_at == clock() + TTL
    with repository._database.connect() as connection:
        row = _lease_row(connection, lease.lease_token)
    assert row["renewal_count"] == 1
    assert row["renewed_at"] is not None


@pytest.mark.asyncio
async def test_renew_rejects_wrong_token(tmp_path: Path) -> None:
    _require_lease_package()
    from agent_foundations.durable.lease import LeaseTokenMismatchError

    clock = FakeClock(NOW)
    repository, manager, _ = await _open_stack(tmp_path / "db.sqlite3", clock)
    await repository.create_run(_sample_durable_run())
    lease = await manager.acquire(RUN_ID, OWNER_A, TTL)
    wrong = lease.model_copy(update={"lease_token": str(uuid4())})
    with pytest.raises(LeaseTokenMismatchError):
        await manager.renew(wrong, TTL)
    with repository._database.connect() as connection:
        row = _lease_row(connection, lease.lease_token)
    assert row["expires_at"] == lease.expires_at.isoformat()


@pytest.mark.asyncio
async def test_renew_rejects_expired_lease(tmp_path: Path) -> None:
    _require_lease_package()
    from agent_foundations.durable.lease import LeaseExpiredError

    clock = FakeClock(NOW)
    repository, manager, _ = await _open_stack(tmp_path / "db.sqlite3", clock)
    await repository.create_run(_sample_durable_run())
    lease = await manager.acquire(RUN_ID, OWNER_A, TTL)
    clock.advance(TTL)
    with pytest.raises(LeaseExpiredError):
        await manager.renew(lease, TTL)


@pytest.mark.asyncio
async def test_renew_rejects_when_expires_at_equals_now(tmp_path: Path) -> None:
    _require_lease_package()
    from agent_foundations.durable.lease import LeaseExpiredError

    clock = FakeClock(NOW)
    repository, manager, _ = await _open_stack(tmp_path / "db.sqlite3", clock)
    await repository.create_run(_sample_durable_run())
    lease = await manager.acquire(RUN_ID, OWNER_A, TTL)
    clock.advance(TTL)
    with pytest.raises(LeaseExpiredError):
        await manager.renew(lease, TTL)


@pytest.mark.asyncio
async def test_release_marks_explicit_release(tmp_path: Path) -> None:
    _require_lease_package()
    clock = FakeClock(NOW)
    repository, manager, _ = await _open_stack(tmp_path / "db.sqlite3", clock)
    await repository.create_run(_sample_durable_run())
    lease = await manager.acquire(RUN_ID, OWNER_A, TTL)
    await manager.release(lease)
    with repository._database.connect() as connection:
        row = _lease_row(connection, lease.lease_token)
    assert row["released_at"] == NOW.isoformat()
    assert row["release_reason"] == "explicit_release"


@pytest.mark.asyncio
async def test_release_allows_expired_lease(tmp_path: Path) -> None:
    _require_lease_package()
    clock = FakeClock(NOW)
    repository, manager, _ = await _open_stack(tmp_path / "db.sqlite3", clock)
    await repository.create_run(_sample_durable_run())
    lease = await manager.acquire(RUN_ID, OWNER_A, TTL)
    clock.advance(TTL)
    await manager.release(lease)
    with repository._database.connect() as connection:
        row = _lease_row(connection, lease.lease_token)
    assert row["release_reason"] == "explicit_release"


@pytest.mark.asyncio
async def test_release_rejects_wrong_token(tmp_path: Path) -> None:
    _require_lease_package()
    from agent_foundations.durable.lease import LeaseTokenMismatchError

    clock = FakeClock(NOW)
    repository, manager, _ = await _open_stack(tmp_path / "db.sqlite3", clock)
    await repository.create_run(_sample_durable_run())
    lease = await manager.acquire(RUN_ID, OWNER_A, TTL)
    wrong = lease.model_copy(update={"lease_token": str(uuid4())})
    with pytest.raises(LeaseTokenMismatchError):
        await manager.release(wrong)
    with repository._database.connect() as connection:
        row = _lease_row(connection, lease.lease_token)
    assert row["released_at"] is None


@pytest.mark.asyncio
async def test_release_rejects_duplicate_release(tmp_path: Path) -> None:
    _require_lease_package()
    from agent_foundations.durable.lease import LeaseConflictError

    clock = FakeClock(NOW)
    repository, manager, _ = await _open_stack(tmp_path / "db.sqlite3", clock)
    await repository.create_run(_sample_durable_run())
    lease = await manager.acquire(RUN_ID, OWNER_A, TTL)
    await manager.release(lease)
    with pytest.raises(LeaseConflictError):
        await manager.release(lease)


@pytest.mark.asyncio
async def test_release_allows_new_acquire(tmp_path: Path) -> None:
    _require_lease_package()
    clock = FakeClock(NOW)
    repository, manager, _ = await _open_stack(tmp_path / "db.sqlite3", clock)
    await repository.create_run(_sample_durable_run())
    lease = await manager.acquire(RUN_ID, OWNER_A, TTL)
    await manager.release(lease)
    new_lease = await manager.acquire(RUN_ID, OWNER_B, TTL)
    assert new_lease.owner_id == OWNER_B
    assert new_lease.lease_token != lease.lease_token


@pytest.mark.asyncio
async def test_takeover_rejects_active_lease(tmp_path: Path) -> None:
    _require_lease_package()
    from agent_foundations.durable.lease import LeaseNotExpiredError

    clock = FakeClock(NOW)
    repository, manager, _ = await _open_stack(tmp_path / "db.sqlite3", clock)
    await repository.create_run(_sample_durable_run())
    await manager.acquire(RUN_ID, OWNER_A, TTL)
    with pytest.raises(LeaseNotExpiredError):
        await manager.takeover_expired(RUN_ID, OWNER_B, TTL)


@pytest.mark.asyncio
async def test_takeover_succeeds_at_expiry_boundary(tmp_path: Path) -> None:
    _require_lease_package()
    clock = FakeClock(NOW)
    repository, manager, _ = await _open_stack(tmp_path / "db.sqlite3", clock)
    await repository.create_run(_sample_durable_run())
    old = await manager.acquire(RUN_ID, OWNER_A, TTL)
    clock.advance(TTL)
    new = await manager.takeover_expired(RUN_ID, OWNER_B, TTL)
    assert new.owner_id == OWNER_B
    assert new.lease_token != old.lease_token
    with repository._database.connect() as connection:
        old_row = _lease_row(connection, old.lease_token)
        new_row = _lease_row(connection, new.lease_token)
    assert old_row["release_reason"] == "expired_takeover"
    assert new_row["predecessor_token"] == old.lease_token


@pytest.mark.asyncio
async def test_takeover_old_token_cannot_renew_or_release_new_owner(tmp_path: Path) -> None:
    _require_lease_package()
    from agent_foundations.durable.lease import (
        LeaseConflictError,
        LeaseTokenMismatchError,
    )

    clock = FakeClock(NOW)
    repository, manager, _ = await _open_stack(tmp_path / "db.sqlite3", clock)
    await repository.create_run(_sample_durable_run())
    old = await manager.acquire(RUN_ID, OWNER_A, TTL)
    clock.advance(TTL)
    new = await manager.takeover_expired(RUN_ID, OWNER_B, TTL)
    with pytest.raises(LeaseTokenMismatchError):
        await manager.renew(old, TTL)
    with pytest.raises(LeaseConflictError):
        await manager.release(old)
    await manager.renew(new, TTL)


@pytest.mark.asyncio
async def test_concurrent_takeover_only_one_succeeds(tmp_path: Path) -> None:
    _require_lease_package()
    from agent_foundations.durable.lease import LeaseConflictError, LeaseNotExpiredError

    clock = FakeClock(NOW)
    repository, manager_a, _ = await _open_stack(tmp_path / "db.sqlite3", clock)
    manager_b = type(manager_a)(repository, clock=clock)
    owner_c = "worker-c"
    await repository.create_run(_sample_durable_run())
    await manager_a.acquire(RUN_ID, OWNER_A, TTL)
    clock.advance(TTL)
    results = await asyncio.gather(
        manager_a.takeover_expired(RUN_ID, OWNER_B, TTL),
        manager_b.takeover_expired(RUN_ID, owner_c, TTL),
        return_exceptions=True,
    )
    successes = [r for r in results if not isinstance(r, BaseException)]
    failures = [
        r
        for r in results
        if isinstance(r, (LeaseConflictError, LeaseNotExpiredError))
    ]
    assert len(successes) == 1
    assert len(failures) == 1


@pytest.mark.asyncio
async def test_failed_v4_migration_rolls_back_to_v3(
    tmp_path: Path,
) -> None:
    _require_lease_package()
    from agent_foundations.durable.schema import RUN_LEASE_MIGRATION
    from agent_foundations.storage.database import SqliteDatabase
    from agent_foundations.storage.migrations import Migration, get_application_migrations

    path = tmp_path / "db.sqlite3"
    migrations = get_application_migrations()
    v3_database = SqliteDatabase(path, migrations[:3])
    await v3_database.initialize()
    from agent_foundations.durable.repository import DurableRunRepository

    repository = DurableRunRepository(path)
    await repository.create_run(_sample_durable_run())
    with repository._database.connect() as connection:
        preserved_runs = [
            tuple(row)
            for row in connection.execute("SELECT * FROM durable_runs ORDER BY rowid")
        ]
    broken_v4 = Migration(
        version=RUN_LEASE_MIGRATION.version,
        statements=(
            "CREATE TABLE run_leases (lease_token TEXT PRIMARY KEY)",
            "CREATE TABLE run_leases (lease_token TEXT PRIMARY KEY)",
        ),
    )
    broken_database = SqliteDatabase(path, (*migrations[:3], broken_v4))
    with pytest.raises(sqlite3.OperationalError):
        await broken_database.initialize()
    with repository._database.connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 3
        assert "run_leases" not in _tables(connection)
        runs_after = [
            tuple(row)
            for row in connection.execute("SELECT * FROM durable_runs ORDER BY rowid")
        ]
    assert runs_after == preserved_runs
