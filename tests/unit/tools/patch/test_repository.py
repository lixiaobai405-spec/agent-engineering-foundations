from __future__ import annotations

import importlib.util
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tests.unit.tools.patch_test_helpers import make_tiny_project

RUN_ID = "22222222-2222-4222-8222-222222222222"


@pytest.fixture
def tiny_project(tmp_path: Path) -> Path:
    return make_tiny_project(tmp_path)


def _require_repository() -> None:
    assert importlib.util.find_spec("agent_foundations.tools.patch.repository") is not None


async def _seed_run(repo_path: Path, project_root: Path) -> None:
    from agent_foundations.durable.models import DurableRun, DurableRunStatus
    from agent_foundations.durable.repository import DurableRunRepository

    durable = DurableRunRepository(repo_path)
    await durable.initialize()
    now = datetime(2026, 8, 11, 8, 0, 0, tzinfo=UTC)
    await durable.create_run(
        DurableRun(
            run_id=RUN_ID,
            project_root=str(project_root),
            status=DurableRunStatus.CREATED,
            schema_version=1,
            state_version=0,
            attempt=1,
            created_at=now,
            updated_at=now,
        ),
    )


@pytest.mark.asyncio
async def test_save_is_idempotent(tmp_path: Path, tiny_project: Path) -> None:
    _require_repository()
    from agent_foundations.tools.patch.models import BaselineEntry
    from agent_foundations.tools.patch.repository import PatchProposalRepository
    from agent_foundations.tools.patch.validator import parse_and_validate_patch

    db_path = tmp_path / "app.sqlite3"
    await _seed_run(db_path, tiny_project)
    repo = PatchProposalRepository.from_path(db_path)
    await repo.initialize()
    diff = """diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -1 +1 @@
-# Title
+# Title2
"""
    baseline = BaselineEntry(
        path="README.md",
        sha256=__import__("hashlib").sha256((tiny_project / "README.md").read_bytes()).hexdigest(),
    )
    patch = parse_and_validate_patch(diff, [baseline], tiny_project)
    first = await repo.save(RUN_ID, patch)
    second = await repo.save(RUN_ID, patch)
    assert first.patch_id == second.patch_id


@pytest.mark.asyncio
async def test_conflict_same_patch_id_different_content(
    tmp_path: Path,
    tiny_project: Path,
) -> None:
    _require_repository()
    from agent_foundations.tools.patch.models import (
        BaselineEntry,
        PatchFile,
        PatchHunk,
        PatchLine,
        PatchLineKind,
        PatchOperation,
        build_validated_patch,
        compute_project_root_fingerprint,
    )
    from agent_foundations.tools.patch.repository import (
        PatchProposalConflictError,
        PatchProposalRepository,
    )
    from agent_foundations.tools.patch.validator import parse_and_validate_patch

    db_path = tmp_path / "app.sqlite3"
    await _seed_run(db_path, tiny_project)
    repo = PatchProposalRepository.from_path(db_path)
    await repo.initialize()
    diff = """diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -1 +1 @@
-# Title
+# Title2
"""
    baseline = BaselineEntry(
        path="README.md",
        sha256=__import__("hashlib").sha256((tiny_project / "README.md").read_bytes()).hexdigest(),
    )
    patch = parse_and_validate_patch(diff, [baseline], tiny_project)
    await repo.save(RUN_ID, patch)
    fingerprint = compute_project_root_fingerprint(tiny_project)
    conflicting = build_validated_patch(
        fingerprint,
        (
            PatchFile(
                path="README.md",
                operation=PatchOperation.MODIFY,
                baseline_sha256=baseline.sha256,
                hunks=(
                    PatchHunk(
                        old_start=1,
                        old_count=1,
                        new_start=1,
                        new_count=1,
                        lines=(PatchLine(kind=PatchLineKind.REMOVE, text="# Title"),),
                    ),
                ),
                add_line_count=0,
                remove_line_count=1,
                hunk_count=1,
            ),
        ),
    )
    conflicting = conflicting.model_copy(update={"patch_id": patch.patch_id})
    with pytest.raises(PatchProposalConflictError):
        await repo.save(RUN_ID, conflicting)


@pytest.mark.asyncio
async def test_v5_to_v6_migration_preserves_data(tmp_path: Path) -> None:
    _require_repository()
    from agent_foundations.storage.database import SqliteDatabase
    from agent_foundations.storage.migrations import get_application_migrations
    from agent_foundations.tools.patch.repository import PatchProposalRepository

    path = tmp_path / "migrate.sqlite3"
    migrations = get_application_migrations()
    database = SqliteDatabase(path, migrations[:5])
    await database.initialize()
    await _seed_run(path, tmp_path)
    repo = PatchProposalRepository.from_path(path)
    await repo.initialize()
    with sqlite3.connect(path) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'",
            )
        }
    assert version == 7
    assert "patch_proposals" in tables
    assert "side_effects" in tables
