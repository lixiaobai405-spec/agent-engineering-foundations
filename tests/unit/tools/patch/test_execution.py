from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from agent_foundations.domain.tool import ToolResult
from agent_foundations.runtime.tool_execution import DirectToolCallExecutor, ToolExecutionContext
from tests.unit.tools.patch_test_helpers import make_tiny_project, sha256_bytes


@pytest.fixture
def tiny_project(tmp_path: Path) -> Path:
    return make_tiny_project(tmp_path)


def _require_execution() -> None:
    assert importlib.util.find_spec("agent_foundations.tools.patch.execution") is not None


@pytest.mark.asyncio
async def test_direct_executor_requires_context(tiny_project: Path) -> None:
    _require_execution()
    from agent_foundations.tools.patch.validate_patch import ValidatePatchTool

    tool = ValidatePatchTool()
    result = await tool.execute({"diff": "", "baselines": []})
    assert not result.success
    assert result.error_code == "PATCH_CONTEXT_REQUIRED"


@pytest.mark.asyncio
async def test_patch_executor_delegates_other_tools(tiny_project: Path) -> None:
    _require_execution()
    from dataclasses import dataclass
    from typing import Any

    from agent_foundations.tools.patch.execution import PatchProposalExecutor
    from agent_foundations.tools.patch.repository import PatchProposalRepository

    @dataclass
    class DummyTool:
        name: str = "dummy"
        description: str = "dummy"

        def input_schema(self) -> dict[str, Any]:
            return {"type": "object", "additionalProperties": False}

        async def execute(self, arguments: dict[str, Any]) -> ToolResult:
            return ToolResult(success=True, content="ok")

    repo = PatchProposalRepository.from_path(tiny_project / "unused.sqlite3")
    executor = PatchProposalExecutor(DirectToolCallExecutor(), repo)
    context = ToolExecutionContext(
        session_id="22222222-2222-4222-8222-222222222222",
        root=tiny_project,
        tool_call_id="c1",
        tool_name="dummy",
    )
    result = await executor.execute(DummyTool(), {}, context)
    assert result.success


@pytest.mark.asyncio
async def test_success_result_excludes_diff_and_secrets(
    tiny_project: Path,
    tmp_path: Path,
) -> None:
    _require_execution()
    from datetime import UTC, datetime

    from agent_foundations.durable.models import DurableRun, DurableRunStatus
    from agent_foundations.durable.repository import DurableRunRepository
    from agent_foundations.tools.patch.execution import PatchProposalExecutor
    from agent_foundations.tools.patch.repository import PatchProposalRepository
    from agent_foundations.tools.patch.validate_patch import ValidatePatchTool
    from tests.unit.tools.patch_test_helpers import SAMPLE_DIFF_SECRET

    run_id = "22222222-2222-4222-8222-222222222222"
    db_path = tmp_path / "app.sqlite3"
    durable = DurableRunRepository(db_path)
    await durable.initialize()
    now = datetime(2026, 8, 11, 8, 0, 0, tzinfo=UTC)
    await durable.create_run(
        DurableRun(
            run_id=run_id,
            project_root=str(tiny_project),
            status=DurableRunStatus.CREATED,
            schema_version=1,
            state_version=0,
            attempt=1,
            created_at=now,
            updated_at=now,
        ),
    )
    repo = PatchProposalRepository.from_path(db_path)
    await repo.initialize()
    executor = PatchProposalExecutor(DirectToolCallExecutor(), repo)
    tool = ValidatePatchTool()
    secret_diff = f"""diff --git a/src/auth.py b/src/auth.py
--- a/src/auth.py
+++ b/src/auth.py
@@ -1,2 +1,2 @@
 def token():
-    return '{SAMPLE_DIFF_SECRET}'
+    return 'changed'
"""
    context = ToolExecutionContext(
        session_id=run_id,
        root=tiny_project,
        tool_call_id="call-1",
        tool_name=tool.name,
    )
    baselines = [{
        "path": "src/auth.py",
        "sha256": sha256_bytes((tiny_project / "src/auth.py").read_bytes()),
    }]
    result = await executor.execute(
        tool,
        {"diff": secret_diff, "baselines": baselines},
        context,
    )
    assert result.success
    payload = str(result.model_dump(mode="json"))
    assert SAMPLE_DIFF_SECRET not in payload
    assert "diff" not in payload.lower()


@pytest.mark.asyncio
async def test_invalid_baseline_sha256_returns_tool_result_not_exception(
    tiny_project: Path,
    tmp_path: Path,
) -> None:
    _require_execution()
    from datetime import UTC, datetime

    from agent_foundations.durable.models import DurableRun, DurableRunStatus
    from agent_foundations.durable.repository import DurableRunRepository
    from agent_foundations.tools.patch.execution import PatchProposalExecutor
    from agent_foundations.tools.patch.repository import PatchProposalRepository
    from agent_foundations.tools.patch.validate_patch import ValidatePatchTool

    run_id = "22222222-2222-4222-8222-222222222222"
    db_path = tmp_path / "app.sqlite3"
    durable = DurableRunRepository(db_path)
    await durable.initialize()
    now = datetime(2026, 8, 11, 8, 0, 0, tzinfo=UTC)
    await durable.create_run(
        DurableRun(
            run_id=run_id,
            project_root=str(tiny_project),
            status=DurableRunStatus.CREATED,
            schema_version=1,
            state_version=0,
            attempt=1,
            created_at=now,
            updated_at=now,
        ),
    )
    repo = PatchProposalRepository.from_path(db_path)
    await repo.initialize()
    executor = PatchProposalExecutor(DirectToolCallExecutor(), repo)
    tool = ValidatePatchTool()
    context = ToolExecutionContext(
        session_id=run_id,
        root=tiny_project,
        tool_call_id="call-bad-hash",
        tool_name=tool.name,
    )
    result = await executor.execute(
        tool,
        {
            "diff": """diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -1 +1 @@
-# Title
+# changed
""",
            "baselines": [{"path": "README.md", "sha256": "not-a-valid-hash"}],
        },
        context,
    )
    assert not result.success
    assert result.error_code == "PATCH_BASELINE_MISMATCH"
