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
RUN_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
RUN_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


def _require_spec(name: str, message: str) -> None:
    try:
        spec = importlib.util.find_spec(name)
    except ModuleNotFoundError:
        spec = None
    assert spec is not None, message


def _lifecycle_api() -> Any:
    _require_spec("agent_foundations.command_output.store", "command output store is missing")
    _require_spec(
        "agent_foundations.command_output.repository",
        "command output repository is missing",
    )
    _require_spec(
        "agent_foundations.command_output.retention",
        "command output retention is missing",
    )
    from agent_foundations.command_output.repository import CommandArtifactRepository
    from agent_foundations.command_output.retention import ArtifactRetentionSweeper
    from agent_foundations.command_output.store import CommandArtifactStore

    return CommandArtifactStore, CommandArtifactRepository, ArtifactRetentionSweeper


async def _stack(tmp_path: Path, *, global_capacity: int = 500) -> tuple[Any, ...]:
    store_cls, repo_cls, sweeper_cls = _lifecycle_api()
    db_path = tmp_path / "state.sqlite3"
    durable = DurableRunRepository(db_path)
    await durable.initialize()
    for run_id, name in ((RUN_A, "a"), (RUN_B, "b")):
        await durable.create_run(
            DurableRun(
                run_id=run_id,
                project_root=str(tmp_path / name),
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
        default_run_id=UUID(RUN_A),
        execution_limit_bytes=80,
        global_capacity_bytes=global_capacity,
    )
    sweeper = sweeper_cls(
        store,
        database,
        retention=timedelta(days=7),
        global_capacity_bytes=global_capacity,
        clock=lambda: NOW,
    )
    with database.connect() as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
    assert version == 10
    return store, database, sweeper, durable


@pytest.mark.asyncio
async def test_lifecycle_persists_v9_metadata_without_raw_bytes(tmp_path: Path) -> None:
    store, database, _sweeper, _durable = await _stack(tmp_path)
    artifact = store.write(stdout=b"fixture-secret", stderr=b"failure")
    row = database.fetch_artifact(artifact.artifact_id)
    raw = database.path.read_bytes()
    assert row.stdout_bytes == len(b"fixture-secret")
    assert b"fixture-secret" not in raw
    assert b"failure" not in raw
    assert row.parser_status.value == "pending"
    assert artifact.retention_status.value == "active"


@pytest.mark.asyncio
async def test_delete_run_marks_exact_artifacts_and_sweeper_is_id_scoped(
    tmp_path: Path,
) -> None:
    store, database, sweeper, _durable = await _stack(tmp_path)
    doomed = store.write(
        stdout=b"run-a-log",
        stderr=b"",
        run_id=UUID(RUN_A),
        effect_id=uuid4(),
        execution_id=uuid4(),
    )
    kept = store.write(
        stdout=b"run-b-log",
        stderr=b"",
        run_id=UUID(RUN_B),
        effect_id=uuid4(),
        execution_id=uuid4(),
    )
    pending = database.mark_pending_delete_for_run(RUN_A)
    assert pending == (doomed.artifact_id,)
    sweeper.sweep_pending_delete()
    assert database.fetch_artifact(doomed.artifact_id).retention_status.value == "deleted"
    assert not store.directory_for(doomed.artifact_id).exists()
    assert store.directory_for(kept.artifact_id).exists()
    assert database.fetch_artifact(kept.artifact_id).retention_status.value == "active"


@pytest.mark.asyncio
async def test_quota_matrix_evicts_oldest_completed_before_refusing_capacity(
    tmp_path: Path,
) -> None:
    store, database, sweeper, _durable = await _stack(tmp_path, global_capacity=120)
    first = store.write(stdout=b"x" * 50, stderr=b"", created_at=NOW - timedelta(days=3))
    database.mark_retained(first.artifact_id)
    second = store.write(stdout=b"y" * 50, stderr=b"", created_at=NOW - timedelta(days=1))
    database.mark_retained(second.artifact_id)
    assert sweeper.reserve(50) is True
    assert database.fetch_artifact(first.artifact_id).retention_status.value == "evicted"
    assert database.fetch_artifact(second.artifact_id).retention_status.value == "retained"


@pytest.mark.docker
@pytest.mark.asyncio
async def test_docker_lifecycle_does_not_place_artifacts_in_project(
    tmp_path: Path,
    pytestconfig: pytest.Config,
) -> None:
    if pytestconfig.getoption("-m") != "docker":
        pytest.skip("requires explicit -m docker authorization")
    _require_spec("agent_foundations.command_output.store", "command output store is missing")
    project = tmp_path / "project"
    project.mkdir()
    store, _database, _sweeper, _durable = await _stack(tmp_path)
    assert store.root.is_relative_to(tmp_path)
    assert not store.root.is_relative_to(project)
    assert not (project / "command-output").exists()
