from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest

from agent_foundations.durable.models import DurableRun, DurableRunStatus
from agent_foundations.durable.repository import DurableRunRepository

NOW = datetime(2026, 8, 26, 5, 0, tzinfo=UTC)
RUN_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
RUN_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


def _repo_api() -> Any:
    try:
        spec = importlib.util.find_spec("agent_foundations.command_output.repository")
    except ModuleNotFoundError:
        spec = None
    assert spec is not None, "command output repository is missing"
    from agent_foundations.command_output.repository import CommandArtifactRepository
    from agent_foundations.command_output.store import CommandArtifactStore
    from agent_foundations.storage.migrations import get_application_migrations

    return CommandArtifactRepository, CommandArtifactStore, get_application_migrations


async def _stack(tmp_path: Path) -> tuple[Any, Any]:
    repository_cls, store_cls, _migrations = _repo_api()
    db_path = tmp_path / "state.sqlite3"
    durable = DurableRunRepository(db_path)
    await durable.initialize()
    for run_id, name in ((RUN_A, "project-a"), (RUN_B, "project-b")):
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
    database = repository_cls.from_path(db_path)
    await database.initialize()
    store = store_cls(
        tmp_path / "artifacts",
        repository=database,
        default_run_id=UUID(RUN_A),
    )
    return store, database


def test_application_migrations_include_sqlite_v9() -> None:
    _repo, _store, get_application_migrations = _repo_api()
    migrations = get_application_migrations()
    assert migrations[-1].version == 10
    versions = {item.version: item for item in migrations}
    v9 = "\n".join(versions[9].statements)
    v10 = "\n".join(versions[10].statements)
    assert "command_output_artifacts" in v9
    assert "stdout_bytes" in v9
    assert "stderr_bytes" in v9
    assert "command_output_reads" in v10
    assert "BLOB" not in v9.upper()
    assert "BLOB" not in v10.upper()


@pytest.mark.asyncio
async def test_artifact_repository_persists_metadata_not_output(
    tmp_path: Path,
) -> None:
    try:
        spec = importlib.util.find_spec("agent_foundations.command_output.store")
    except ModuleNotFoundError:
        spec = None
    assert spec is not None, "command output store is missing"
    artifact_store, database = await _stack(tmp_path)
    artifact = artifact_store.write(stdout=b"fixture-secret", stderr=b"failure")
    row = database.fetch_artifact(artifact.artifact_id)
    assert row.stdout_bytes == len(b"fixture-secret")
    assert b"fixture-secret" not in database.path.read_bytes()
    assert row.parser_status.value == "pending"
    assert artifact.sha256 == row.sha256


@pytest.mark.asyncio
async def test_pending_delete_is_exact_and_does_not_cross_runs(
    tmp_path: Path,
) -> None:
    artifact_store, database = await _stack(tmp_path)
    first = artifact_store.write(
        stdout=b"run-a-secret",
        stderr=b"",
        run_id=UUID(RUN_A),
        effect_id=uuid4(),
        execution_id=uuid4(),
    )
    second = artifact_store.write(
        stdout=b"run-b-secret",
        stderr=b"",
        run_id=UUID(RUN_B),
        effect_id=uuid4(),
        execution_id=uuid4(),
    )
    pending = database.mark_pending_delete_for_run(RUN_A)
    assert first.artifact_id in pending
    assert second.artifact_id not in pending
    assert database.fetch_artifact(first.artifact_id).retention_status.value == (
        "pending_delete"
    )
    assert database.fetch_artifact(second.artifact_id).retention_status.value != (
        "pending_delete"
    )
    assert b"run-a-secret" not in database.path.read_bytes()
    assert b"run-b-secret" not in database.path.read_bytes()
