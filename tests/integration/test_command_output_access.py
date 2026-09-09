from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from agent_foundations.command_output.store import CommandArtifactStore
from agent_foundations.durable.models import DurableRun, DurableRunStatus
from agent_foundations.durable.repository import DurableRunRepository

NOW = datetime(2026, 8, 26, 7, 0, tzinfo=UTC)
RUN_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
RUN_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


def _require_gateway() -> Any:
    try:
        spec = importlib.util.find_spec("agent_foundations.command_output.access")
    except ModuleNotFoundError:
        spec = None
    assert spec is not None, "command output access is missing"
    from agent_foundations.command_output.access import CommandOutputGateway

    return CommandOutputGateway


@pytest.mark.asyncio
async def test_read_command_output_rejects_cross_run_artifact(tmp_path: Path) -> None:
    gateway_cls = _require_gateway()
    store, artifacts, trace_path = await _stack(tmp_path)
    artifact_from_run_a = store.write(
        stdout=b"ok\n",
        stderr=b"fixture-secret\n",
        run_id=UUID(RUN_A),
    )
    output_tool = gateway_cls(store=store, repository=artifacts, trace_path=trace_path)

    class _Run:
        id = RUN_B

    run_b = _Run()
    result = await output_tool.execute(
        current_run_id=run_b.id,
        artifact_id=artifact_from_run_a.artifact_id,
        selector={"stream": "stderr", "tail_lines": 20},
        reason="inspect parser gap",
    )
    assert result.error_code == "ARTIFACT_SCOPE_DENIED"
    assert "fixture-secret" not in trace_path.read_text(encoding="utf-8")
    assert b"fixture-secret" not in artifacts.path.read_bytes()


@pytest.mark.asyncio
async def test_capability_replay_and_search_budget(tmp_path: Path) -> None:
    gateway_cls = _require_gateway()
    store, artifacts, trace_path = await _stack(tmp_path)
    artifact = store.write(
        stdout=b"failed test_id=tests/test_a.py::test_fail\n" * 40,
        stderr=b"",
        run_id=UUID(RUN_A),
    )
    output_tool = gateway_cls(store=store, repository=artifacts, trace_path=trace_path)
    first = await output_tool.execute(
        current_run_id=RUN_A,
        artifact_id=artifact.artifact_id,
        selector={"stream": "stdout", "start_line": 1, "line_count": 10},
        reason="inspect parser gap",
    )
    assert first.success is True
    replay = await output_tool.execute(
        current_run_id=RUN_A,
        artifact_id=artifact.artifact_id,
        selector={"stream": "stdout", "start_line": 1, "line_count": 10},
        reason="inspect parser gap",
    )
    assert replay.error_code == "ARTIFACT_SCOPE_DENIED"
    search = await output_tool.search(
        current_run_id=RUN_A,
        artifact_id=artifact.artifact_id,
        query="test_fail",
        reason="find failing node",
    )
    assert search.success is True
    assert len(search.metadata.get("hits", ())) <= 50
    assert "fixture-secret" not in trace_path.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_v10_audit_table_has_no_output_blob(tmp_path: Path) -> None:
    _require_gateway()
    _store, artifacts, _trace = await _stack(tmp_path)
    with artifacts.connect() as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        names = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert version == 10
    assert "command_output_reads" in names
    ddl = ""
    with artifacts.connect() as connection:
        ddl = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name='command_output_reads'"
        ).fetchone()[0]
    assert "BLOB" not in ddl.upper()
    assert "content" not in ddl.lower()


async def _stack(tmp_path: Path) -> tuple[Any, Any, Path]:
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
    from agent_foundations.command_output.repository import CommandArtifactRepository

    artifacts = CommandArtifactRepository.from_path(db_path)
    await artifacts.initialize()
    store = CommandArtifactStore(tmp_path / "artifacts", repository=artifacts)
    return store, artifacts, tmp_path / "trace.jsonl"
