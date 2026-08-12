from __future__ import annotations

import asyncio
import importlib.util
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from agent_foundations.domain.tool import Tool, ToolResult
from agent_foundations.runtime.tool_execution import (
    DirectToolCallExecutor,
    ToolExecutionContext,
)

RUN_ID = "22222222-2222-4222-8222-222222222222"
TOOL_CALL_ID = "call-1"
TOOL_NAME = "fake_effect"
SECRET_MARKER = "placeholder-secret-marker-not-real"
FIXTURE_ROOT = Path("tests/fixtures/sample_project").resolve()
FIXTURE_SESSION_ID = "22222222-2222-4222-8222-222222222222"


def _require_idempotent_executor() -> None:
    assert importlib.util.find_spec("agent_foundations.runtime.tool_execution") is not None
    from agent_foundations.runtime.tool_execution import IdempotentToolCallExecutor

    assert IdempotentToolCallExecutor is not None


@dataclass
class FakeCounterTool:
    name: str = TOOL_NAME
    description: str = "fake side effect"
    count: int = 0

    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {"path": {"type": "string"}}}

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        self.count += 1
        return ToolResult(
            success=True,
            content=f"ok:{arguments.get('path', '')}",
            metadata={"secret": SECRET_MARKER},
        )


class FakeSideEffectClassifier:
    def describe(
        self,
        tool: Tool,
        arguments: Mapping[str, Any],
        context: ToolExecutionContext,
    ) -> Any:
        from agent_foundations.durable.models import SideEffectIntent

        path = str(arguments.get("path", "resource"))
        return SideEffectIntent(
            operation="write",
            resource_key=path,
            summary=f"write {path}",
        )


class NoSideEffectClassifier:
    def describe(
        self,
        tool: Tool,
        arguments: Mapping[str, Any],
        context: ToolExecutionContext,
    ) -> None:
        return None


@dataclass
class RecordingObserver:
    events: list[dict[str, Any]] = field(default_factory=list)

    def on_effect_event(self, event: Mapping[str, Any]) -> None:
        self.events.append(dict(event))


async def _open_stack(tmp_path: Path) -> tuple[Any, Any]:
    from datetime import UTC, datetime

    from agent_foundations.durable.effects import SideEffectLedger
    from agent_foundations.durable.repository import DurableRunRepository

    now = datetime(2026, 8, 11, 8, 0, 0, tzinfo=UTC)
    repo = DurableRunRepository(tmp_path / "ledger.sqlite3")
    await repo.initialize()
    from agent_foundations.durable.models import DurableRun, DurableRunStatus

    await repo.create_run(
        DurableRun(
            run_id=RUN_ID,
            project_root=str(tmp_path),
            status=DurableRunStatus.CREATED,
            schema_version=1,
            state_version=0,
            attempt=1,
            created_at=now,
            updated_at=now,
        ),
    )
    ledger = SideEffectLedger(repo, clock=lambda: now)
    return repo, ledger


def _context(tmp_path: Path, tool_call_id: str = TOOL_CALL_ID) -> ToolExecutionContext:
    return ToolExecutionContext(
        session_id=RUN_ID,
        root=tmp_path,
        tool_call_id=tool_call_id,
        tool_name=TOOL_NAME,
    )


@pytest.mark.asyncio
async def test_classifier_none_skips_ledger(tmp_path: Path) -> None:
    _require_idempotent_executor()
    from agent_foundations.runtime.tool_execution import IdempotentToolCallExecutor

    _, ledger = await _open_stack(tmp_path)
    tool = FakeCounterTool()
    executor = IdempotentToolCallExecutor(
        DirectToolCallExecutor(),
        NoSideEffectClassifier(),
        ledger,
    )
    result = await executor.execute(tool, {"path": "README.md"}, _context(tmp_path))
    assert result.success
    assert tool.count == 1
    assert await ledger.get(RUN_ID, TOOL_CALL_ID, TOOL_NAME) is None


@pytest.mark.asyncio
async def test_committed_duplicate_executes_once(tmp_path: Path) -> None:
    _require_idempotent_executor()
    from agent_foundations.runtime.tool_execution import IdempotentToolCallExecutor

    _, ledger = await _open_stack(tmp_path)
    tool = FakeCounterTool()
    executor = IdempotentToolCallExecutor(
        DirectToolCallExecutor(),
        FakeSideEffectClassifier(),
        ledger,
        execution_owner_id="owner-1",
    )
    context = _context(tmp_path)
    first = await executor.execute(tool, {"path": "README.md"}, context)
    second = await executor.execute(tool, {"path": "README.md"}, context)
    assert first.content == second.content
    assert tool.count == 1


@pytest.mark.asyncio
async def test_failed_duplicate_does_not_reexecute(tmp_path: Path) -> None:
    _require_idempotent_executor()
    from agent_foundations.runtime.tool_execution import IdempotentToolCallExecutor

    class FailingTool(FakeCounterTool):
        async def execute(self, arguments: dict[str, Any]) -> ToolResult:
            self.count += 1
            return ToolResult(success=False, content="boom", error_code="ToolError")

    _, ledger = await _open_stack(tmp_path)
    tool = FailingTool()
    executor = IdempotentToolCallExecutor(
        DirectToolCallExecutor(),
        FakeSideEffectClassifier(),
        ledger,
        execution_owner_id="owner-1",
    )
    context = _context(tmp_path)
    first = await executor.execute(tool, {"path": "README.md"}, context)
    second = await executor.execute(tool, {"path": "README.md"}, context)
    assert not first.success
    assert first.error_code == second.error_code
    assert tool.count == 1


@pytest.mark.asyncio
async def test_concurrent_calls_execute_downstream_once(tmp_path: Path) -> None:
    _require_idempotent_executor()
    from agent_foundations.runtime.tool_execution import IdempotentToolCallExecutor

    _, ledger = await _open_stack(tmp_path)
    tool = FakeCounterTool()
    executor = IdempotentToolCallExecutor(
        DirectToolCallExecutor(),
        FakeSideEffectClassifier(),
        ledger,
        execution_owner_id="owner-1",
    )
    context = _context(tmp_path)

    results = await asyncio.gather(
        executor.execute(tool, {"path": "README.md"}, context),
        executor.execute(tool, {"path": "README.md"}, context),
        executor.execute(tool, {"path": "README.md"}, context),
    )
    assert all(result.success for result in results)
    assert tool.count == 1


@pytest.mark.asyncio
async def test_crash_after_claim_recovery_is_unknown_with_zero_effects(tmp_path: Path) -> None:
    _require_idempotent_executor()
    from agent_foundations.durable.effects import EffectResolutionRequiredError
    from agent_foundations.durable.faults import CrashPoint, InjectedCrash, PointFaultInjector
    from agent_foundations.runtime.tool_execution import IdempotentToolCallExecutor

    _, ledger = await _open_stack(tmp_path)
    tool = FakeCounterTool()
    injector = PointFaultInjector(crash_at=CrashPoint.AFTER_CLAIM)
    executor = IdempotentToolCallExecutor(
        DirectToolCallExecutor(),
        FakeSideEffectClassifier(),
        ledger,
        execution_owner_id="owner-1",
        fault_injector=injector,
    )
    context = _context(tmp_path)
    with pytest.raises(InjectedCrash):
        await executor.execute(tool, {"path": "README.md"}, context)
    assert tool.count == 0

    recovery = IdempotentToolCallExecutor(
        DirectToolCallExecutor(),
        FakeSideEffectClassifier(),
        ledger,
        execution_owner_id="owner-2",
    )
    with pytest.raises(EffectResolutionRequiredError):
        await recovery.execute(tool, {"path": "README.md"}, context)
    assert tool.count == 0


@pytest.mark.asyncio
async def test_observer_events_exclude_arguments_and_secrets(tmp_path: Path) -> None:
    _require_idempotent_executor()
    from agent_foundations.runtime.tool_execution import IdempotentToolCallExecutor

    _, ledger = await _open_stack(tmp_path)
    tool = FakeCounterTool()
    observer = RecordingObserver()
    executor = IdempotentToolCallExecutor(
        DirectToolCallExecutor(),
        FakeSideEffectClassifier(),
        ledger,
        execution_owner_id="owner-1",
        observer=observer,
    )
    await executor.execute(
        tool,
        {"path": "README.md", "token": SECRET_MARKER},
        _context(tmp_path),
    )
    payload = " ".join(str(event) for event in observer.events)
    assert SECRET_MARKER not in payload
    assert "arguments" not in payload.lower()
    assert "result_json" not in payload.lower()


async def _crash_recovery_executor(
    tmp_path: Path,
    crash_at: Any,
    *,
    execution_owner_id: str = "owner-1",
) -> tuple[Any, Any, FakeCounterTool, ToolExecutionContext, Any]:
    from agent_foundations.durable.faults import PointFaultInjector
    from agent_foundations.runtime.tool_execution import IdempotentToolCallExecutor

    _, ledger = await _open_stack(tmp_path)
    tool = FakeCounterTool()
    injector = PointFaultInjector(crash_at=crash_at)
    executor = IdempotentToolCallExecutor(
        DirectToolCallExecutor(),
        FakeSideEffectClassifier(),
        ledger,
        execution_owner_id=execution_owner_id,
        fault_injector=injector,
    )
    context = _context(tmp_path)
    return executor, ledger, tool, context, injector


@pytest.mark.asyncio
async def test_crash_before_intent_recovery_executes_once(tmp_path: Path) -> None:
    _require_idempotent_executor()
    from agent_foundations.durable.faults import CrashPoint, InjectedCrash
    from agent_foundations.runtime.tool_execution import IdempotentToolCallExecutor

    executor, ledger, tool, context, _ = await _crash_recovery_executor(
        tmp_path,
        CrashPoint.BEFORE_INTENT,
    )
    with pytest.raises(InjectedCrash):
        await executor.execute(tool, {"path": "README.md"}, context)
    assert tool.count == 0

    recovery = IdempotentToolCallExecutor(
        DirectToolCallExecutor(),
        FakeSideEffectClassifier(),
        ledger,
        execution_owner_id="owner-2",
    )
    result = await recovery.execute(tool, {"path": "README.md"}, context)
    assert result.success
    assert tool.count == 1


@pytest.mark.asyncio
async def test_crash_after_intent_recovery_executes_once(tmp_path: Path) -> None:
    _require_idempotent_executor()
    from agent_foundations.durable.faults import CrashPoint, InjectedCrash
    from agent_foundations.runtime.tool_execution import IdempotentToolCallExecutor

    executor, ledger, tool, context, _ = await _crash_recovery_executor(
        tmp_path,
        CrashPoint.AFTER_INTENT,
    )
    with pytest.raises(InjectedCrash):
        await executor.execute(tool, {"path": "README.md"}, context)
    assert tool.count == 0

    recovery = IdempotentToolCallExecutor(
        DirectToolCallExecutor(),
        FakeSideEffectClassifier(),
        ledger,
        execution_owner_id="owner-2",
    )
    result = await recovery.execute(tool, {"path": "README.md"}, context)
    assert result.success
    assert tool.count == 1


@pytest.mark.asyncio
async def test_crash_after_execute_recovery_is_unknown_with_one_effect(tmp_path: Path) -> None:
    _require_idempotent_executor()
    from agent_foundations.durable.effects import EffectResolutionRequiredError
    from agent_foundations.durable.faults import CrashPoint, InjectedCrash
    from agent_foundations.runtime.tool_execution import IdempotentToolCallExecutor

    executor, ledger, tool, context, _ = await _crash_recovery_executor(
        tmp_path,
        CrashPoint.AFTER_EXECUTE,
    )
    with pytest.raises(InjectedCrash):
        await executor.execute(tool, {"path": "README.md"}, context)
    assert tool.count == 1

    recovery = IdempotentToolCallExecutor(
        DirectToolCallExecutor(),
        FakeSideEffectClassifier(),
        ledger,
        execution_owner_id="owner-2",
    )
    with pytest.raises(EffectResolutionRequiredError):
        await recovery.execute(tool, {"path": "README.md"}, context)
    assert tool.count == 1


@pytest.mark.asyncio
async def test_crash_after_commit_recovery_returns_saved_result(tmp_path: Path) -> None:
    _require_idempotent_executor()
    from agent_foundations.durable.faults import CrashPoint, InjectedCrash
    from agent_foundations.runtime.tool_execution import IdempotentToolCallExecutor

    executor, ledger, tool, context, _ = await _crash_recovery_executor(
        tmp_path,
        CrashPoint.AFTER_COMMIT,
    )
    with pytest.raises(InjectedCrash):
        await executor.execute(tool, {"path": "README.md"}, context)
    assert tool.count == 1

    recovery = IdempotentToolCallExecutor(
        DirectToolCallExecutor(),
        FakeSideEffectClassifier(),
        ledger,
        execution_owner_id="owner-2",
    )
    result = await recovery.execute(tool, {"path": "README.md"}, context)
    assert result.success
    assert tool.count == 1


@pytest.mark.asyncio
async def test_downstream_exception_marks_unknown_and_requires_resolution(
    tmp_path: Path,
) -> None:
    _require_idempotent_executor()
    from agent_foundations.durable.effects import EffectResolutionRequiredError
    from agent_foundations.runtime.tool_execution import IdempotentToolCallExecutor

    class ExplodingTool(FakeCounterTool):
        async def execute(self, arguments: dict[str, Any]) -> ToolResult:
            self.count += 1
            raise RuntimeError("boom")

    _, ledger = await _open_stack(tmp_path)
    tool = ExplodingTool()
    executor = IdempotentToolCallExecutor(
        DirectToolCallExecutor(),
        FakeSideEffectClassifier(),
        ledger,
        execution_owner_id="owner-1",
    )
    context = _context(tmp_path)
    with pytest.raises(RuntimeError, match="boom"):
        await executor.execute(tool, {"path": "README.md"}, context)
    assert tool.count == 1

    recovery = IdempotentToolCallExecutor(
        DirectToolCallExecutor(),
        FakeSideEffectClassifier(),
        ledger,
        execution_owner_id="owner-2",
    )
    with pytest.raises(EffectResolutionRequiredError):
        await recovery.execute(tool, {"path": "README.md"}, context)
    assert tool.count == 1


@pytest.mark.asyncio
async def test_unknown_and_rolled_back_do_not_auto_retry(tmp_path: Path) -> None:
    _require_idempotent_executor()
    from agent_foundations.durable.effects import EffectResolutionRequiredError
    from agent_foundations.durable.models import EffectStatus
    from agent_foundations.runtime.tool_execution import IdempotentToolCallExecutor

    repo, ledger = await _open_stack(tmp_path)
    tool = FakeCounterTool()
    executor = IdempotentToolCallExecutor(
        DirectToolCallExecutor(),
        FakeSideEffectClassifier(),
        ledger,
        execution_owner_id="owner-1",
    )
    context = _context(tmp_path, tool_call_id="call-unknown")
    await executor.execute(tool, {"path": "README.md"}, context)
    assert tool.count == 1

    with repo._database.connect() as connection:
        connection.execute(
            "UPDATE side_effects SET status = ?, resolved_at = updated_at "
            "WHERE run_id = ? AND tool_call_id = ?",
            (EffectStatus.UNKNOWN.value, RUN_ID, "call-unknown"),
        )
        connection.commit()

    with pytest.raises(EffectResolutionRequiredError):
        await executor.execute(tool, {"path": "README.md"}, context)
    assert tool.count == 1

    context_rolled = _context(tmp_path, tool_call_id="call-rolled")
    await executor.execute(tool, {"path": "README.md"}, context_rolled)
    assert tool.count == 2
    with repo._database.connect() as connection:
        connection.execute(
            "UPDATE side_effects SET status = ?, resolved_at = updated_at "
            "WHERE run_id = ? AND tool_call_id = ?",
            (EffectStatus.ROLLED_BACK.value, RUN_ID, "call-rolled"),
        )
        connection.commit()
    with pytest.raises(EffectResolutionRequiredError):
        await executor.execute(tool, {"path": "README.md"}, context_rolled)
    assert tool.count == 2


@pytest.mark.asyncio
async def test_same_call_id_with_changed_arguments_conflicts(tmp_path: Path) -> None:
    _require_idempotent_executor()
    from agent_foundations.durable.repository import IdempotencyConflictError
    from agent_foundations.runtime.tool_execution import IdempotentToolCallExecutor

    _, ledger = await _open_stack(tmp_path)
    tool = FakeCounterTool()
    executor = IdempotentToolCallExecutor(
        DirectToolCallExecutor(),
        FakeSideEffectClassifier(),
        ledger,
        execution_owner_id="owner-1",
    )
    context = _context(tmp_path)
    await executor.execute(tool, {"path": "README.md"}, context)
    with pytest.raises(IdempotencyConflictError):
        await executor.execute(tool, {"path": "OTHER.md"}, context)


@pytest.mark.asyncio
async def test_agent_loop_readonly_path_unaffected_with_wrapper(tmp_path: Path) -> None:
    _require_idempotent_executor()
    from agent_foundations.context.budget import ContextBudget
    from agent_foundations.context.builder import ContextBuilder
    from agent_foundations.domain.model import ModelResponse
    from agent_foundations.domain.tool import ToolCall
    from agent_foundations.durable.effects import SideEffectLedger
    from agent_foundations.durable.repository import DurableRunRepository
    from agent_foundations.providers.fake import FakeModelProvider
    from agent_foundations.runtime.agent import AgentConfig
    from agent_foundations.runtime.loop import AgentLoop
    from agent_foundations.runtime.tool_execution import IdempotentToolCallExecutor
    from agent_foundations.runtime.trace import InMemoryEventSink

    fixture_root = FIXTURE_ROOT
    repo = DurableRunRepository(tmp_path / "loop.sqlite3")
    await repo.initialize()
    ledger = SideEffectLedger(repo)
    wrapped = IdempotentToolCallExecutor(
        DirectToolCallExecutor(),
        NoSideEffectClassifier(),
        ledger,
    )
    provider = FakeModelProvider(
        [
            ModelResponse(
                content="",
                tool_calls=(
                    ToolCall(
                        id="call-list",
                        name="list_directory",
                        arguments={"path": "."},
                    ),
                ),
            ),
            ModelResponse(content="done"),
        ],
    )
    from tests.unit.tools.registry_helpers import readonly_tool_registry

    loop = AgentLoop(
        provider=provider,
        registry=readonly_tool_registry(fixture_root),
        context_builder=ContextBuilder(ContextBudget()),
        event_sink=InMemoryEventSink(),
        config=AgentConfig(max_steps=10),
        tool_executor=wrapped,
    )
    result = await loop.run(
        fixture_root,
        "list files",
        session_id=FIXTURE_SESSION_ID,
    )
    assert result.answer
    assert len(provider.requests) == 2
