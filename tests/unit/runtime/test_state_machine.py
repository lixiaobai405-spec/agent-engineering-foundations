from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from agent_foundations.domain.messages import Message, Role
from agent_foundations.domain.tool import ToolCall
from agent_foundations.planning.models import ExecutionPlan, PlanStep
from agent_foundations.runtime.state_machine import (
    AgentRunPhase,
    AgentRunState,
    CheckpointReason,
    RunCancelledError,
)

RUN_ID = "22222222-2222-4222-8222-222222222222"
NOW = datetime(2026, 8, 2, 12, 0, 0, tzinfo=UTC)
FIXTURE_ROOT = Path("tests/fixtures/sample_project").resolve()


class _NoOpSink:
    async def save(self, state: AgentRunState, reason: CheckpointReason) -> None:
        return None


class _NoOpToken:
    async def is_cancelled(self) -> bool:
        return False


def _require_state_machine() -> None:
    spec = importlib.util.find_spec("agent_foundations.runtime.state_machine")
    assert spec is not None


def _assistant_with_tools(count: int = 1) -> Message:
    calls = tuple(
        ToolCall(id=f"call-{index}", name="list_directory", arguments={"path": "."})
        for index in range(count)
    )
    return Message(role=Role.ASSISTANT, content=None, tool_calls=calls)


def _base_state(**updates: Any) -> AgentRunState:
    messages = updates.pop("messages", (Message(role=Role.USER, content="hello"),))
    return AgentRunState(
        schema_version=1,
        messages=messages,
        next_step=updates.pop("next_step", 1),
        phase=updates.pop("phase", AgentRunPhase.READY_FOR_MODEL),
        next_tool_index=updates.pop("next_tool_index", 0),
        plan_snapshot=updates.pop("plan_snapshot", None),
        attempt=updates.pop("attempt", 1),
        last_committed_tool_fact=updates.pop("last_committed_tool_fact", None),
        final_answer=updates.pop("final_answer", None),
    )


def test_agent_run_state_is_frozen_and_round_trips() -> None:
    _require_state_machine()
    state = _base_state()
    restored = AgentRunState.model_validate_json(state.model_dump_json())
    assert restored == state
    with pytest.raises(ValidationError):
        state.next_step = 2


def test_legacy_run_state_json_defaults_phase_and_tool_index() -> None:
    _require_state_machine()
    from agent_foundations.durable.models import RunState

    legacy = {
        "schema_version": 1,
        "messages": [{"role": "user", "content": "hello"}],
        "next_step": 1,
        "attempt": 1,
    }
    state = RunState.model_validate(legacy)
    assert state.phase == AgentRunPhase.READY_FOR_MODEL
    assert state.next_tool_index == 0
    assert state.final_answer is None


def test_checkpoint_reason_order_is_stable() -> None:
    _require_state_machine()
    assert tuple(CheckpointReason) == (
        "model_response",
        "tool_result",
        "plan_update",
        "finalizing",
        "retry_started",
    )


def test_finalizing_requires_final_answer() -> None:
    _require_state_machine()
    with pytest.raises(ValidationError, match="final_answer"):
        _base_state(phase=AgentRunPhase.FINALIZING, final_answer=None)


def test_ready_for_model_requires_zero_tool_index() -> None:
    _require_state_machine()
    with pytest.raises(ValidationError, match="next_tool_index"):
        _base_state(next_tool_index=1)


def test_model_response_phase_requires_valid_tool_index() -> None:
    _require_state_machine()
    with pytest.raises(ValidationError, match="next_tool_index"):
        _base_state(
            messages=(_assistant_with_tools(1),),
            phase=AgentRunPhase.MODEL_RESPONSE_PERSISTED,
            next_tool_index=2,
        )


@pytest.mark.asyncio
async def test_cancel_token_blocks_before_provider() -> None:
    _require_state_machine()

    class Token:
        async def is_cancelled(self) -> bool:
            return True

    from agent_foundations.runtime.state_machine import CancellationToken

    token: CancellationToken = Token()
    if await token.is_cancelled():
        with pytest.raises(RunCancelledError):
            raise RunCancelledError("run cancelled")


@pytest.mark.asyncio
async def test_resume_from_model_response_skips_provider() -> None:

    from agent_foundations.context.budget import ContextBudget
    from agent_foundations.context.builder import ContextBuilder
    from agent_foundations.domain.model import ModelResponse
    from agent_foundations.providers.fake import FakeModelProvider
    from agent_foundations.runtime.agent import AgentConfig
    from agent_foundations.runtime.loop import AgentLoop
    from agent_foundations.runtime.trace import InMemoryEventSink
    from tests.unit.tools.registry_helpers import readonly_tool_registry

    fixture_root = FIXTURE_ROOT
    provider = FakeModelProvider([ModelResponse(content="done after tool")])
    sink = InMemoryEventSink()
    loop = AgentLoop(
        provider=provider,
        registry=readonly_tool_registry(fixture_root),
        context_builder=ContextBuilder(ContextBudget()),
        event_sink=sink,
        config=AgentConfig(max_steps=3),
    )
    state = _base_state(
        messages=(
            Message(role=Role.SYSTEM, content="system"),
            Message(role=Role.USER, content="query"),
            _assistant_with_tools(1),
        ),
        next_step=1,
        phase=AgentRunPhase.MODEL_RESPONSE_PERSISTED,
        next_tool_index=0,
    )
    result = await loop.resume(
        fixture_root,
        RUN_ID,
        state,
        checkpoint_sink=_NoOpSink(),
        cancellation_token=_NoOpToken(),
    )
    assert "done" in result.answer
    assert len(provider.requests) == 1
    assert any(event.event_type == "tool.call.completed" for event in sink.events)


@pytest.mark.asyncio
async def test_resume_after_first_tool_skips_first_tool() -> None:

    from agent_foundations.context.budget import ContextBudget
    from agent_foundations.context.builder import ContextBuilder
    from agent_foundations.domain.model import ModelResponse
    from agent_foundations.domain.tool import ToolCall
    from agent_foundations.providers.fake import FakeModelProvider
    from agent_foundations.runtime.agent import AgentConfig
    from agent_foundations.runtime.loop import AgentLoop
    from agent_foundations.runtime.trace import InMemoryEventSink
    from tests.unit.tools.registry_helpers import readonly_tool_registry

    fixture_root = FIXTURE_ROOT
    provider = FakeModelProvider([
        ModelResponse(content="done after second tool"),
    ])
    sink = InMemoryEventSink()
    loop = AgentLoop(
        provider=provider,
        registry=readonly_tool_registry(fixture_root),
        context_builder=ContextBuilder(ContextBudget()),
        event_sink=sink,
        config=AgentConfig(max_steps=3),
    )
    assistant = Message(
        role=Role.ASSISTANT,
        tool_calls=(
            ToolCall(id="call-1", name="list_directory", arguments={"path": "."}),
            ToolCall(id="call-2", name="list_directory", arguments={"path": "."}),
        ),
    )
    state = _base_state(
        messages=(
            Message(role=Role.SYSTEM, content="system"),
            Message(role=Role.USER, content="query"),
            assistant,
            Message(
                role=Role.TOOL,
                name="list_directory",
                tool_call_id="call-1",
                content='{"success":true,"content":"ok"}',
            ),
        ),
        next_step=1,
        phase=AgentRunPhase.TOOL_RESULT_PERSISTED,
        next_tool_index=1,
    )
    result = await loop.resume(
        fixture_root,
        RUN_ID,
        state,
        checkpoint_sink=_NoOpSink(),
        cancellation_token=_NoOpToken(),
    )
    assert "done" in result.answer
    tool_requests = [
        event for event in sink.events if event.event_type == "tool.call.requested"
    ]
    assert len(tool_requests) == 1
    assert tool_requests[0].payload["tool_call_id"] == "call-2"


@pytest.mark.asyncio
async def test_resume_from_finalizing_completes_without_provider_or_tool() -> None:

    from agent_foundations.context.budget import ContextBudget
    from agent_foundations.context.builder import ContextBuilder
    from agent_foundations.domain.model import ModelResponse
    from agent_foundations.providers.fake import FakeModelProvider
    from agent_foundations.runtime.agent import AgentConfig
    from agent_foundations.runtime.loop import AgentLoop
    from agent_foundations.runtime.trace import InMemoryEventSink
    from agent_foundations.tools.registry import ToolRegistry

    fixture_root = FIXTURE_ROOT
    provider = FakeModelProvider([ModelResponse(content="unused")])
    sink = InMemoryEventSink()
    loop = AgentLoop(
        provider=provider,
        registry=ToolRegistry([]),
        context_builder=ContextBuilder(ContextBudget()),
        event_sink=sink,
        config=AgentConfig(max_steps=3),
    )
    state = _base_state(
        messages=(
            Message(role=Role.SYSTEM, content="system"),
            Message(role=Role.USER, content="query"),
            Message(role=Role.ASSISTANT, content="final"),
        ),
        next_step=1,
        phase=AgentRunPhase.FINALIZING,
        final_answer="final",
    )
    result = await loop.resume(
        fixture_root,
        RUN_ID,
        state,
        checkpoint_sink=_NoOpSink(),
        cancellation_token=_NoOpToken(),
    )
    assert result.answer == "final"
    assert len(provider.requests) == 0
    assert not any(
        event.event_type.startswith("tool.call") for event in sink.events
    )


@pytest.mark.asyncio
async def test_resume_from_model_response_without_tools_finalizes_without_provider() -> None:
    from agent_foundations.context.budget import ContextBudget
    from agent_foundations.context.builder import ContextBuilder
    from agent_foundations.domain.model import ModelResponse
    from agent_foundations.providers.fake import FakeModelProvider
    from agent_foundations.runtime.agent import AgentConfig
    from agent_foundations.runtime.loop import AgentLoop
    from agent_foundations.runtime.trace import InMemoryEventSink
    from agent_foundations.tools.registry import ToolRegistry

    provider = FakeModelProvider([ModelResponse(content="final only")])
    sink = InMemoryEventSink()
    loop = AgentLoop(
        provider=provider,
        registry=ToolRegistry([]),
        context_builder=ContextBuilder(ContextBudget()),
        event_sink=sink,
        config=AgentConfig(max_steps=3),
    )
    state = _base_state(
        messages=(
            Message(role=Role.SYSTEM, content="system"),
            Message(role=Role.USER, content="query"),
            Message(role=Role.ASSISTANT, content="final only"),
        ),
        next_step=1,
        phase=AgentRunPhase.MODEL_RESPONSE_PERSISTED,
        next_tool_index=0,
    )
    resumed_provider = FakeModelProvider([ModelResponse(content="should not run")])
    loop._provider = resumed_provider
    result = await loop.resume(
        FIXTURE_ROOT,
        RUN_ID,
        state,
        checkpoint_sink=_NoOpSink(),
        cancellation_token=_NoOpToken(),
    )
    assert result.answer == "final only"
    assert len(resumed_provider.requests) == 0


@pytest.mark.asyncio
async def test_model_response_persisted_with_no_tools_does_not_advance_step() -> None:
    from agent_foundations.context.budget import ContextBudget
    from agent_foundations.context.builder import ContextBuilder
    from agent_foundations.domain.model import ModelResponse
    from agent_foundations.providers.fake import FakeModelProvider
    from agent_foundations.runtime.agent import AgentConfig
    from agent_foundations.runtime.loop import AgentLoop
    from agent_foundations.runtime.trace import InMemoryEventSink
    from agent_foundations.tools.registry import ToolRegistry

    provider = FakeModelProvider([ModelResponse(content="final only")])
    sink = InMemoryEventSink()
    loop = AgentLoop(
        provider=provider,
        registry=ToolRegistry([]),
        context_builder=ContextBuilder(ContextBudget()),
        event_sink=sink,
        config=AgentConfig(max_steps=3),
    )
    state = _base_state(
        messages=(
            Message(role=Role.SYSTEM, content="system"),
            Message(role=Role.USER, content="query"),
            Message(role=Role.ASSISTANT, content="final only"),
        ),
        next_step=1,
        phase=AgentRunPhase.MODEL_RESPONSE_PERSISTED,
        next_tool_index=0,
    )
    session = __import__(
        "agent_foundations.runtime.session",
        fromlist=["AgentSession"],
    ).AgentSession(root=FIXTURE_ROOT, session_id=RUN_ID)
    session.messages.extend(list(state.messages))
    finalized = await loop._execute_next_tool(
        session,
        state,
        checkpoint_sink=None,
        cancellation_token=None,
    )
    assert finalized.phase == AgentRunPhase.FINALIZING
    assert finalized.final_answer == "final only"
    assert finalized.next_step == 1


def test_plan_snapshot_restore_on_controller() -> None:
    from agent_foundations.planning.controller import PlanController

    controller = PlanController(plan_id_factory=lambda: "plan-1")
    plan = ExecutionPlan(
        plan_id="plan-1",
        version=2,
        goal="goal",
        steps=(PlanStep(step_id="read", description="read"),),
    )
    controller.restore(plan)
    assert controller.current_plan == plan
