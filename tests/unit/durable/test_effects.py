from __future__ import annotations

import importlib.util
import io
import math
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

RUN_ID = "22222222-2222-4222-8222-222222222222"
TOOL_CALL_ID = "call-1"
TOOL_NAME = "fake_effect"
NOW = datetime(2026, 8, 11, 8, 0, 0, tzinfo=UTC)
PROJECT_ROOT = "/tmp/project"


def _require_effects_module() -> None:
    assert importlib.util.find_spec("agent_foundations.durable.effects") is not None


def _require_faults_module() -> None:
    assert importlib.util.find_spec("agent_foundations.durable.faults") is not None


def _require_application_migrations_v5() -> None:
    from agent_foundations.storage.migrations import get_application_migrations

    migrations = get_application_migrations()
    assert len(migrations) == 7
    assert migrations[4].version == 5


def test_effect_status_has_six_stable_values() -> None:
    _require_effects_module()
    from agent_foundations.durable.models import EffectStatus

    assert tuple(EffectStatus) == (
        "intent_recorded",
        "executing",
        "committed",
        "failed",
        "unknown",
        "rolled_back",
    )


def test_side_effect_intent_is_frozen_and_validates_summary_length() -> None:
    _require_effects_module()
    from agent_foundations.durable.models import SideEffectIntent

    intent = SideEffectIntent(
        operation="write",
        resource_key="README.md",
        summary="write README.md",
    )
    with pytest.raises(ValidationError):
        intent.model_copy(update={"summary": "x" * 241})


def test_side_effect_record_committed_requires_success_result() -> None:
    _require_effects_module()
    from agent_foundations.domain.tool import ToolResult
    from agent_foundations.durable.models import EffectStatus, SideEffectRecord

    with pytest.raises(ValidationError, match="result"):
        SideEffectRecord(
            effect_id=str(uuid4()),
            run_id=RUN_ID,
            tool_call_id=TOOL_CALL_ID,
            tool_name=TOOL_NAME,
            idempotency_key="a" * 64,
            intent_digest="b" * 64,
            intent_summary="summary",
            status=EffectStatus.COMMITTED,
            result=ToolResult(success=False, content="fail"),
            error_code=None,
            execution_owner_id="owner",
            created_at=NOW,
            updated_at=NOW,
            executing_at=NOW,
            resolved_at=None,
        )


def test_digest_is_stable_for_dict_key_order() -> None:
    _require_effects_module()
    from agent_foundations.durable.effects import compute_intent_digest

    digest_a = compute_intent_digest(
        RUN_ID,
        TOOL_CALL_ID,
        TOOL_NAME,
        "write",
        "README.md",
        {"path": "README.md", "nested": {"z": 1, "a": 2}},
    )
    digest_b = compute_intent_digest(
        RUN_ID,
        TOOL_CALL_ID,
        TOOL_NAME,
        "write",
        "README.md",
        {"nested": {"a": 2, "z": 1}, "path": "README.md"},
    )
    assert digest_a == digest_b
    assert len(digest_a) == 64


def test_digest_changes_when_arguments_change() -> None:
    _require_effects_module()
    from agent_foundations.durable.effects import compute_intent_digest

    first = compute_intent_digest(
        RUN_ID, TOOL_CALL_ID, TOOL_NAME, "write", "README.md", {"path": "a"}
    )
    second = compute_intent_digest(
        RUN_ID, TOOL_CALL_ID, TOOL_NAME, "write", "README.md", {"path": "b"}
    )
    assert first != second


def test_normalize_arguments_rejects_nan_and_open_handles() -> None:
    _require_effects_module()
    from agent_foundations.durable.effects import normalize_tool_arguments

    with pytest.raises(ValueError):
        normalize_tool_arguments({"value": math.nan})
    with pytest.raises(ValueError):
        normalize_tool_arguments({"handle": io.StringIO("data")})


@pytest.mark.asyncio
async def test_prepare_is_idempotent_for_same_intent(tmp_path: Path) -> None:
    _require_effects_module()
    from agent_foundations.durable.effects import SideEffectLedger
    from agent_foundations.durable.models import EffectStatus, SideEffectIntent
    from agent_foundations.durable.repository import DurableRunRepository
    from agent_foundations.runtime.tool_execution import ToolExecutionContext

    repo = DurableRunRepository(tmp_path / "db.sqlite3")
    await repo.initialize()
    await _seed_run(repo)
    ledger = SideEffectLedger(repo, clock=lambda: NOW)
    intent = SideEffectIntent(
        operation="write",
        resource_key="README.md",
        summary="write README.md",
    )
    context = ToolExecutionContext(
        session_id=RUN_ID,
        root=tmp_path,
        tool_call_id=TOOL_CALL_ID,
        tool_name=TOOL_NAME,
    )
    first = await ledger.prepare(intent, context, {"path": "README.md"})
    second = await ledger.prepare(intent, context, {"path": "README.md"})
    assert first.effect_id == second.effect_id
    assert first.status == EffectStatus.INTENT_RECORDED


@pytest.mark.asyncio
async def test_same_tuple_different_digest_raises_conflict(tmp_path: Path) -> None:
    _require_effects_module()
    from agent_foundations.durable.effects import IdempotencyConflictError, SideEffectLedger
    from agent_foundations.durable.models import SideEffectIntent
    from agent_foundations.durable.repository import DurableRunRepository
    from agent_foundations.runtime.tool_execution import ToolExecutionContext

    repo = DurableRunRepository(tmp_path / "ledger.sqlite3")
    await repo.initialize()
    await _seed_run(repo)
    ledger = SideEffectLedger(repo, clock=lambda: NOW)
    intent = SideEffectIntent(
        operation="write",
        resource_key="README.md",
        summary="write README.md",
    )
    context = ToolExecutionContext(
        session_id=RUN_ID,
        root=tmp_path,
        tool_call_id=TOOL_CALL_ID,
        tool_name=TOOL_NAME,
    )
    await ledger.prepare(intent, context, {"path": "README.md"})
    with pytest.raises(IdempotencyConflictError):
        await ledger.prepare(intent, context, {"path": "OTHER.md"})


@pytest.mark.asyncio
async def test_full_arguments_are_not_persisted(tmp_path: Path) -> None:
    _require_effects_module()
    from agent_foundations.durable.effects import SideEffectLedger
    from agent_foundations.durable.models import SideEffectIntent
    from agent_foundations.durable.repository import DurableRunRepository
    from agent_foundations.runtime.tool_execution import ToolExecutionContext

    repo = DurableRunRepository(tmp_path / "db.sqlite3")
    await repo.initialize()
    await _seed_run(repo)
    ledger = SideEffectLedger(repo, clock=lambda: NOW)
    secret_args = {"path": "README.md", "token": "placeholder-secret-marker"}
    intent = SideEffectIntent(
        operation="write",
        resource_key="README.md",
        summary="write README.md",
    )
    context = ToolExecutionContext(
        session_id=RUN_ID,
        root=tmp_path,
        tool_call_id=TOOL_CALL_ID,
        tool_name=TOOL_NAME,
    )
    await ledger.prepare(intent, context, secret_args)
    with sqlite3.connect(repo._database._path) as connection:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(side_effects)")
        }
        row = connection.execute(
            "SELECT intent_summary, result_json FROM side_effects LIMIT 1",
        ).fetchone()
    assert "arguments" not in columns
    assert "placeholder-secret-marker" not in row[0]
    assert row[1] is None


@pytest.mark.asyncio
async def test_legal_state_transitions(tmp_path: Path) -> None:
    _require_effects_module()
    from agent_foundations.domain.tool import ToolResult
    from agent_foundations.durable.effects import SideEffectLedger
    from agent_foundations.durable.models import EffectStatus, SideEffectIntent
    from agent_foundations.durable.repository import DurableRunRepository
    from agent_foundations.runtime.tool_execution import ToolExecutionContext

    repo = DurableRunRepository(tmp_path / "ledger.sqlite3")
    await repo.initialize()
    await _seed_run(repo)
    ledger = SideEffectLedger(repo, clock=lambda: NOW)
    intent = SideEffectIntent(
        operation="write",
        resource_key="README.md",
        summary="write README.md",
    )
    context = ToolExecutionContext(
        session_id=RUN_ID,
        root=tmp_path,
        tool_call_id=TOOL_CALL_ID,
        tool_name=TOOL_NAME,
    )
    record = await ledger.prepare(intent, context, {"path": "README.md"})
    claimed = await ledger.claim(
        record.effect_id,
        EffectStatus.INTENT_RECORDED,
        "owner-1",
    )
    assert claimed.status == EffectStatus.EXECUTING
    committed = await ledger.commit(
        record.effect_id,
        "owner-1",
        ToolResult(success=True, content="ok"),
    )
    assert committed.status == EffectStatus.COMMITTED
    assert committed.result is not None


@pytest.mark.asyncio
async def test_illegal_transition_and_owner_mismatch_rejected(tmp_path: Path) -> None:
    _require_effects_module()
    from agent_foundations.domain.tool import ToolResult
    from agent_foundations.durable.effects import SideEffectLedger
    from agent_foundations.durable.models import EffectStatus, SideEffectIntent
    from agent_foundations.durable.repository import (
        DurableRunRepository,
        EffectOwnerConflictError,
        EffectStatusConflictError,
    )
    from agent_foundations.runtime.tool_execution import ToolExecutionContext

    repo = DurableRunRepository(tmp_path / "ledger.sqlite3")
    await repo.initialize()
    await _seed_run(repo)
    ledger = SideEffectLedger(repo, clock=lambda: NOW)
    intent = SideEffectIntent(
        operation="write",
        resource_key="README.md",
        summary="write README.md",
    )
    context = ToolExecutionContext(
        session_id=RUN_ID,
        root=tmp_path,
        tool_call_id=TOOL_CALL_ID,
        tool_name=TOOL_NAME,
    )
    record = await ledger.prepare(intent, context, {"path": "README.md"})
    await ledger.claim(record.effect_id, EffectStatus.INTENT_RECORDED, "owner-1")
    with pytest.raises(EffectStatusConflictError):
        await ledger.claim(record.effect_id, EffectStatus.INTENT_RECORDED, "owner-2")
    with pytest.raises(EffectOwnerConflictError):
        await ledger.commit(
            record.effect_id,
            "owner-2",
            ToolResult(success=True, content="ok"),
        )
    committed = await ledger.commit(
        record.effect_id,
        "owner-1",
        ToolResult(success=True, content="ok"),
    )
    with pytest.raises(EffectStatusConflictError):
        await ledger.commit(
            committed.effect_id,
            "owner-1",
            ToolResult(success=True, content="again"),
        )


@pytest.mark.asyncio
async def test_invalid_committed_result_leaves_executing(tmp_path: Path) -> None:
    _require_effects_module()
    import sqlite3

    from agent_foundations.domain.tool import ToolResult
    from agent_foundations.durable.effects import SideEffectLedger
    from agent_foundations.durable.models import EffectStatus, SideEffectIntent
    from agent_foundations.durable.repository import (
        DurableRunRepository,
        EffectStatusConflictError,
    )
    from agent_foundations.runtime.tool_execution import ToolExecutionContext

    repo = DurableRunRepository(tmp_path / "ledger.sqlite3")
    await repo.initialize()
    await _seed_run(repo)
    ledger = SideEffectLedger(repo, clock=lambda: NOW)
    intent = SideEffectIntent(
        operation="write",
        resource_key="README.md",
        summary="write README.md",
    )
    context = ToolExecutionContext(
        session_id=RUN_ID,
        root=tmp_path,
        tool_call_id="call-bad-commit",
        tool_name=TOOL_NAME,
    )
    record = await ledger.prepare(intent, context, {"path": "README.md"})
    await ledger.claim(record.effect_id, EffectStatus.INTENT_RECORDED, "owner-1")
    with pytest.raises(EffectStatusConflictError, match="successful result"):
        await ledger.commit(
            record.effect_id,
            "owner-1",
            ToolResult(success=False, content="boom", error_code="ToolError"),
        )
    with sqlite3.connect(repo._database._path) as connection:
        status = connection.execute(
            "SELECT status FROM side_effects WHERE effect_id = ?",
            (record.effect_id,),
        ).fetchone()[0]
    assert status == EffectStatus.EXECUTING.value


@pytest.mark.asyncio
async def test_invalid_failed_result_leaves_executing(tmp_path: Path) -> None:
    _require_effects_module()
    import sqlite3

    from agent_foundations.domain.tool import ToolResult
    from agent_foundations.durable.effects import SideEffectLedger
    from agent_foundations.durable.models import EffectStatus, SideEffectIntent
    from agent_foundations.durable.repository import (
        DurableRunRepository,
        EffectStatusConflictError,
    )
    from agent_foundations.runtime.tool_execution import ToolExecutionContext

    repo = DurableRunRepository(tmp_path / "ledger.sqlite3")
    await repo.initialize()
    await _seed_run(repo)
    ledger = SideEffectLedger(repo, clock=lambda: NOW)
    intent = SideEffectIntent(
        operation="write",
        resource_key="README.md",
        summary="write README.md",
    )
    context = ToolExecutionContext(
        session_id=RUN_ID,
        root=tmp_path,
        tool_call_id="call-bad-fail",
        tool_name=TOOL_NAME,
    )
    record = await ledger.prepare(intent, context, {"path": "README.md"})
    await ledger.claim(record.effect_id, EffectStatus.INTENT_RECORDED, "owner-1")
    with pytest.raises(EffectStatusConflictError, match="unsuccessful result"):
        await ledger.fail(
            record.effect_id,
            "owner-1",
            ToolResult(success=True, content="ok"),
        )
    with sqlite3.connect(repo._database._path) as connection:
        status = connection.execute(
            "SELECT status FROM side_effects WHERE effect_id = ?",
            (record.effect_id,),
        ).fetchone()[0]
    assert status == EffectStatus.EXECUTING.value


@pytest.mark.asyncio
async def test_fail_and_unknown_transitions(tmp_path: Path) -> None:
    _require_effects_module()
    from agent_foundations.domain.tool import ToolResult
    from agent_foundations.durable.effects import SideEffectLedger
    from agent_foundations.durable.models import EffectStatus, SideEffectIntent
    from agent_foundations.durable.repository import DurableRunRepository
    from agent_foundations.runtime.tool_execution import ToolExecutionContext

    repo = DurableRunRepository(tmp_path / "ledger.sqlite3")
    await repo.initialize()
    await _seed_run(repo)
    ledger = SideEffectLedger(repo, clock=lambda: NOW)
    intent = SideEffectIntent(
        operation="write",
        resource_key="README.md",
        summary="write README.md",
    )
    context = ToolExecutionContext(
        session_id=RUN_ID,
        root=tmp_path,
        tool_call_id="call-fail",
        tool_name=TOOL_NAME,
    )
    record = await ledger.prepare(intent, context, {"path": "README.md"})
    await ledger.claim(record.effect_id, EffectStatus.INTENT_RECORDED, "owner-1")
    failed = await ledger.fail(
        record.effect_id,
        "owner-1",
        ToolResult(success=False, content="boom", error_code="ToolError"),
    )
    assert failed.status == EffectStatus.FAILED

    context_unknown = ToolExecutionContext(
        session_id=RUN_ID,
        root=tmp_path,
        tool_call_id="call-unknown",
        tool_name=TOOL_NAME,
    )
    unknown_record = await ledger.prepare(intent, context_unknown, {"path": "README.md"})
    await ledger.claim(
        unknown_record.effect_id,
        EffectStatus.INTENT_RECORDED,
        "owner-1",
    )
    unknown = await ledger.mark_unknown(
        unknown_record.effect_id,
        "owner-1",
        "crash",
    )
    assert unknown.status == EffectStatus.UNKNOWN
    assert unknown.resolved_at is not None


@pytest.mark.asyncio
async def test_v4_to_v5_migration_preserves_existing_tables(tmp_path: Path) -> None:
    _require_application_migrations_v5()
    from agent_foundations.durable.repository import DurableRunRepository
    from agent_foundations.storage.database import SqliteDatabase
    from agent_foundations.storage.migrations import get_application_migrations

    path = tmp_path / "migrate.sqlite3"
    migrations = get_application_migrations()
    database = SqliteDatabase(path, migrations[:4])
    await database.initialize()
    repo_v4 = DurableRunRepository(path)
    await _seed_run(repo_v4)
    with sqlite3.connect(path) as connection:
        before_tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'",
            )
        }
        before_version = connection.execute("PRAGMA user_version").fetchone()[0]
    database_v5 = SqliteDatabase(path, migrations[:5])
    await database_v5.initialize()
    with sqlite3.connect(path) as connection:
        after_tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'",
            )
        }
        after_version = connection.execute("PRAGMA user_version").fetchone()[0]
        run_count = connection.execute(
            "SELECT COUNT(*) FROM durable_runs",
        ).fetchone()[0]
    assert before_version == 4
    assert after_version == 5
    assert "side_effects" not in before_tables
    assert "side_effects" in after_tables
    assert "durable_runs" in after_tables
    assert run_count == 1


@pytest.mark.asyncio
async def test_user_version_six_is_rejected(tmp_path: Path) -> None:
    from agent_foundations.storage.database import FutureSchemaVersionError, SqliteDatabase
    from agent_foundations.storage.migrations import get_application_migrations

    path = tmp_path / "future.sqlite3"
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA user_version = 8")
    connection.commit()
    connection.close()
    database = SqliteDatabase(path, get_application_migrations())
    with pytest.raises(FutureSchemaVersionError):
        await database.initialize()


async def _seed_run(repository: Any) -> None:
    from agent_foundations.durable.models import DurableRun, DurableRunStatus

    run = DurableRun(
        run_id=RUN_ID,
        project_root=PROJECT_ROOT,
        status=DurableRunStatus.CREATED,
        schema_version=1,
        state_version=0,
        attempt=1,
        created_at=NOW,
        updated_at=NOW,
    )
    await repository.create_run(run)
