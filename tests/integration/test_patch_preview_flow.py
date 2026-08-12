from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from agent_foundations.domain.model import ModelResponse
from agent_foundations.domain.tool import ToolCall
from agent_foundations.providers.fake import FakeModelProvider
from agent_foundations.runtime.agent import AgentConfig
from agent_foundations.runtime.loop import AgentLoop
from agent_foundations.runtime.tool_execution import DirectToolCallExecutor
from agent_foundations.runtime.trace import InMemoryEventSink
from tests.unit.tools.patch_test_helpers import (
    SAMPLE_DIFF_SECRET,
    make_tiny_project,
    sha256_bytes,
)

RUN_ID = "22222222-2222-4222-8222-222222222222"


def _snapshot_project_files(project_root: Path) -> dict[Path, bytes]:
    return {
        path: path.read_bytes()
        for path in project_root.rglob("*")
        if path.is_file()
    }


@pytest.fixture
def tiny_project(tmp_path: Path) -> Path:
    return make_tiny_project(tmp_path)


def _require_patch_flow() -> None:
    assert importlib.util.find_spec("agent_foundations.tools.patch.execution") is not None


@pytest.mark.asyncio
async def test_agent_loop_patch_preview_flow(tmp_path: Path, tiny_project: Path) -> None:
    _require_patch_flow()
    from datetime import UTC, datetime

    from agent_foundations.context.budget import ContextBudget
    from agent_foundations.context.builder import ContextBuilder
    from agent_foundations.durable.models import DurableRun, DurableRunStatus
    from agent_foundations.durable.repository import DurableRunRepository
    from agent_foundations.tools.patch.execution import PatchProposalExecutor
    from agent_foundations.tools.patch.repository import PatchProposalRepository
    from tests.unit.tools.registry_helpers import validate_patch_tool_registry

    before = _snapshot_project_files(tiny_project)
    db_path = tmp_path / "app.sqlite3"
    durable = DurableRunRepository(db_path)
    await durable.initialize()
    now = datetime(2026, 8, 11, 8, 0, 0, tzinfo=UTC)
    await durable.create_run(
        DurableRun(
            run_id=RUN_ID,
            project_root=str(tiny_project),
            status=DurableRunStatus.CREATED,
            schema_version=1,
            state_version=0,
            attempt=1,
            created_at=now,
            updated_at=now,
        ),
    )
    patch_repo = PatchProposalRepository.from_path(db_path)
    await patch_repo.initialize()
    registry = validate_patch_tool_registry()
    executor = PatchProposalExecutor(DirectToolCallExecutor(), patch_repo)
    provider = FakeModelProvider(
        [
            ModelResponse(
                content="",
                tool_calls=(
                    ToolCall(
                        id="call-patch",
                        name="validate_patch",
                        arguments={
                            "diff": f"""diff --git a/src/auth.py b/src/auth.py
--- a/src/auth.py
+++ b/src/auth.py
@@ -1,2 +1,2 @@
 def token():
-    return '{SAMPLE_DIFF_SECRET}'
+    return 'changed'
""",
                            "baselines": [
                                {
                                    "path": "src/auth.py",
                                    "sha256": sha256_bytes(
                                        (tiny_project / "src/auth.py").read_bytes(),
                                    ),
                                },
                            ],
                        },
                    ),
                ),
            ),
            ModelResponse(content="preview complete"),
        ],
    )
    sink = InMemoryEventSink()
    loop = AgentLoop(
        provider=provider,
        registry=registry,
        context_builder=ContextBuilder(ContextBudget()),
        event_sink=sink,
        config=AgentConfig(max_steps=5),
        tool_executor=executor,
    )
    result = await loop.run(tiny_project, "preview patch", session_id=RUN_ID)
    assert result.answer

    after = _snapshot_project_files(tiny_project)
    assert before == after

    trace_text = json.dumps([event.model_dump(mode="json") for event in sink.events])
    assert SAMPLE_DIFF_SECRET not in trace_text
    assert "--- a/src" not in trace_text
    assert "+++ b/src" not in trace_text

    completed = next(
        event for event in sink.events if event.event_type == "tool.call.completed"
    )
    patch_id = completed.payload["result"]["metadata"]["patch_id"]
    saved = await patch_repo.get(RUN_ID, patch_id)
    assert saved.patch_id == patch_id

    registry_names = {tool.name for tool in registry.definitions()}
    forbidden = {"apply_patch", "write_file", "delete_file", "run_command", "git_commit"}
    assert forbidden.isdisjoint(registry_names)
