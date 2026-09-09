from __future__ import annotations

import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest

from agent_foundations.durable.models import DurableRun, DurableRunStatus
from agent_foundations.durable.repository import DurableRunRepository

NOW = datetime(2026, 8, 26, 5, 0, tzinfo=UTC)
RUN_ID = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"


def _retention_api() -> Any:
    try:
        spec = importlib.util.find_spec("agent_foundations.command_output.retention")
    except ModuleNotFoundError:
        spec = None
    assert spec is not None, "command output retention is missing"
    from agent_foundations.command_output.models import (
        ParserStatus,
        RetentionStatus,
    )
    from agent_foundations.command_output.repository import CommandArtifactRepository
    from agent_foundations.command_output.retention import (
        DEFAULT_GLOBAL_CAPACITY_BYTES,
        DEFAULT_RETENTION,
        EXECUTION_OUTPUT_LIMIT_BYTES,
        ArtifactCapacityExceeded,
        ArtifactRetentionSweeper,
    )
    from agent_foundations.command_output.store import CommandArtifactStore

    return (
        CommandArtifactStore,
        CommandArtifactRepository,
        ArtifactRetentionSweeper,
        ArtifactCapacityExceeded,
        EXECUTION_OUTPUT_LIMIT_BYTES,
        DEFAULT_GLOBAL_CAPACITY_BYTES,
        DEFAULT_RETENTION,
        RetentionStatus,
        ParserStatus,
    )


async def _stack(
    tmp_path: Path,
    *,
    execution_limit: int = 64,
    global_capacity: int = 200,
    retention: timedelta = timedelta(days=7),
) -> tuple[Any, ...]:
    (
        store_cls,
        repo_cls,
        sweeper_cls,
        *_rest,
    ) = _retention_api()
    db_path = tmp_path / "state.sqlite3"
    durable = DurableRunRepository(db_path)
    await durable.initialize()
    await durable.create_run(
        DurableRun(
            run_id=RUN_ID,
            project_root=str(tmp_path / "project"),
            status=DurableRunStatus.CREATED,
            schema_version=1,
            state_version=0,
            attempt=1,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    database = repo_cls.from_path(db_path)
    await database.initialize()
    store = store_cls(
        tmp_path / "artifacts",
        repository=database,
        default_run_id=UUID(RUN_ID),
        execution_limit_bytes=execution_limit,
        global_capacity_bytes=global_capacity,
    )
    sweeper = sweeper_cls(
        store,
        database,
        retention=retention,
        global_capacity_bytes=global_capacity,
        clock=lambda: NOW,
    )
    return store, database, sweeper


def test_default_limits_are_64mib_512mib_7days() -> None:
    (
        _store,
        _repo,
        _sweeper,
        _capacity,
        execution_limit,
        global_capacity,
        retention,
        *_rest,
    ) = _retention_api()
    assert execution_limit == 64 * 1024 * 1024
    assert global_capacity == 512 * 1024 * 1024
    assert global_capacity != 1024 * 1024 * 1024
    assert retention == timedelta(days=7)


def test_store_imports_capacity_constant_from_retention() -> None:
    import inspect

    from agent_foundations.command_output import retention as retention_mod
    from agent_foundations.command_output import store as store_mod

    assert store_mod.DEFAULT_GLOBAL_CAPACITY_BYTES == 512 * 1024 * 1024
    assert store_mod.DEFAULT_GLOBAL_CAPACITY_BYTES is retention_mod.DEFAULT_GLOBAL_CAPACITY_BYTES
    assert store_mod.EXECUTION_OUTPUT_LIMIT_BYTES is retention_mod.EXECUTION_OUTPUT_LIMIT_BYTES
    store_source = inspect.getsource(store_mod)
    assert "DEFAULT_GLOBAL_CAPACITY_BYTES = 512" not in store_source
    assert "DEFAULT_GLOBAL_CAPACITY_BYTES = 1024" not in store_source


@pytest.mark.asyncio
async def test_sweeper_exposes_readonly_capacity_and_retention(tmp_path: Path) -> None:
    _store, _database, sweeper = await _stack(
        tmp_path,
        global_capacity=512 * 1024 * 1024,
        retention=timedelta(days=7),
    )
    assert getattr(sweeper, "global_capacity_bytes", None) == 512 * 1024 * 1024
    assert getattr(sweeper, "retention_period", None) == timedelta(days=7)
    period = getattr(sweeper, "retention_period", None)
    assert period is not None
    assert int(period.total_seconds()) == 604800


@pytest.mark.asyncio
async def test_quota_reservation_evicts_oldest_retained_not_active(
    tmp_path: Path,
) -> None:
    store, database, sweeper = await _stack(
        tmp_path,
        execution_limit=40,
        global_capacity=90,
    )
    oldest = store.write(stdout=b"a" * 40, stderr=b"", created_at=NOW - timedelta(days=2))
    database.mark_retained(oldest.artifact_id)
    active = store.write(stdout=b"b" * 20, stderr=b"", created_at=NOW - timedelta(hours=1))
    reserved = sweeper.reserve(40)
    assert reserved is True
    assert database.fetch_artifact(oldest.artifact_id).retention_status.value == "evicted"
    assert not store.directory_for(oldest.artifact_id).exists()
    assert database.fetch_artifact(active.artifact_id).retention_status.value == "active"
    assert store.directory_for(active.artifact_id).exists()


@pytest.mark.asyncio
async def test_capacity_exceeded_before_start_when_active_cannot_be_evicted(
    tmp_path: Path,
) -> None:
    (
        _store_cls,
        _repo_cls,
        _sweeper_cls,
        capacity_error,
        *_rest,
    ) = _retention_api()
    store, _database, sweeper = await _stack(
        tmp_path,
        execution_limit=80,
        global_capacity=100,
    )
    store.write(stdout=b"c" * 80, stderr=b"")
    with pytest.raises(capacity_error) as caught:
        sweeper.reserve(80)
    assert caught.value.code == "ARTIFACT_CAPACITY_EXCEEDED"


@pytest.mark.asyncio
async def test_expired_retained_artifacts_are_evicted_after_seven_days(
    tmp_path: Path,
) -> None:
    store, database, sweeper = await _stack(tmp_path, execution_limit=20, global_capacity=200)
    expired = store.write(
        stdout=b"old",
        stderr=b"",
        created_at=NOW - timedelta(days=8),
    )
    database.mark_retained(expired.artifact_id)
    fresh = store.write(stdout=b"new", stderr=b"", created_at=NOW)
    database.mark_retained(fresh.artifact_id)
    sweeper.sweep_expired()
    assert database.fetch_artifact(expired.artifact_id).retention_status.value == "evicted"
    assert database.fetch_artifact(fresh.artifact_id).retention_status.value == "retained"


@pytest.mark.asyncio
async def test_pending_delete_sweeper_is_exact_and_records_delete_failed(
    tmp_path: Path,
) -> None:
    store, database, sweeper = await _stack(tmp_path, execution_limit=20, global_capacity=200)
    artifact = store.write(stdout=b"doomed", stderr=b"")
    other = store.write(stdout=b"kept", stderr=b"", effect_id=uuid4(), execution_id=uuid4())
    database.mark_pending_delete(artifact.artifact_id)
    sweeper.sweep_pending_delete()
    assert database.fetch_artifact(artifact.artifact_id).retention_status.value == "deleted"
    assert not store.directory_for(artifact.artifact_id).exists()
    assert store.directory_for(other.artifact_id).exists()
