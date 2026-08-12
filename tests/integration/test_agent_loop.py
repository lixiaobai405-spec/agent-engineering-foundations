import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from agent_foundations.context.budget import ContextBudget
from agent_foundations.context.builder import ContextBuilder
from agent_foundations.domain.errors import (
    ContextBudgetExceededError,
    FakeModelExhaustedError,
    InvalidModelResponseError,
    MaxStepsExceededError,
)
from agent_foundations.domain.messages import Message, Role
from agent_foundations.domain.model import ModelProvider, ModelRequest, ModelResponse
from agent_foundations.domain.tool import ToolCall, ToolResult
from agent_foundations.planning.tools import build_planning_registered_tools
from agent_foundations.providers.fake import FakeModelProvider
from agent_foundations.runtime.agent import AgentConfig, PlanningMode
from agent_foundations.runtime.loop import AgentLoop
from agent_foundations.runtime.tool_execution import (
    DirectToolCallExecutor,
    ToolCallExecutor,
    ToolExecutionContext,
)
from agent_foundations.runtime.trace import InMemoryEventSink
from agent_foundations.tools.filesystem.path_policy import PathPolicy
from agent_foundations.tools.registry import (
    ToolRegistry,
    build_readonly_filesystem_registered_tools,
)
from tests.unit.tools.registry_helpers import readonly_tool_registry, registered_test_tool

FIXTURE_ROOT = Path("tests/fixtures/sample_project").resolve()
FIXTURE_SESSION_ID = "22222222-2222-4222-8222-222222222222"


def build_loop(
    responses: list[ModelResponse],
    max_steps: int = 10,
    budget: ContextBudget | None = None,
    registry: ToolRegistry | None = None,
    tool_executor: ToolCallExecutor | None = None,
    planning_required: bool = False,
) -> tuple[AgentLoop, InMemoryEventSink, FakeModelProvider]:
    from agent_foundations.planning.controller import PlanController
    from agent_foundations.planning.execution import ExecutionFactJournal
    from agent_foundations.planning.tools import PlanningToolExecutor, build_planning_tools

    sink = InMemoryEventSink()
    provider = FakeModelProvider(responses)
    plan_controller: PlanController | None = None
    config = AgentConfig(max_steps=max_steps)
    effective_executor = tool_executor
    effective_registry = registry or readonly_tool_registry(FIXTURE_ROOT)
    if registry is None:
        policy = PathPolicy(FIXTURE_ROOT)
        registered = list(build_readonly_filesystem_registered_tools(policy))
        if planning_required:
            plan_controller = PlanController()
            journal = ExecutionFactJournal()
            planning_tools = build_planning_tools(plan_controller, journal)
            registered.extend(build_planning_registered_tools(plan_controller, journal))
            if tool_executor is None:
                effective_executor = PlanningToolExecutor(
                    DirectToolCallExecutor(),
                    plan_controller,
                    journal,
                    {tool.name: tool for tool in planning_tools},
                )
            config = AgentConfig(
                max_steps=max_steps,
                planning_mode=PlanningMode.REQUIRED,
            )
        effective_registry = ToolRegistry(registered)
    elif planning_required:
        plan_controller = PlanController()
        config = AgentConfig(
            max_steps=max_steps,
            planning_mode=PlanningMode.REQUIRED,
        )

    loop = AgentLoop(
        provider=provider,
        registry=effective_registry,
        context_builder=ContextBuilder(budget or ContextBudget()),
        event_sink=sink,
        config=config,
        tool_executor=effective_executor,
        plan_controller=plan_controller,
    )
    return loop, sink, provider


@pytest.mark.asyncio
async def test_agent_executes_tool_then_returns_final_answer() -> None:
    loop, sink, provider = build_loop([
        ModelResponse(
            tool_calls=(
                ToolCall(id="c1", name="list_directory", arguments={"path": "."}),
            ),
        ),
        ModelResponse(content="The project contains source code and a README."),
    ])
    result = await loop.run(FIXTURE_ROOT, "Summarize the project")
    assert result.answer.startswith("The project")
    assert result.steps == 2
    assert len(provider.requests) == 2
    assert [event.event_type for event in sink.events] == [
        "session.started",
        "user.message",
        "model.request.started",
        "model.response.received",
        "tool.call.requested",
        "tool.call.validated",
        "tool.call.completed",
        "model.request.started",
        "model.response.received",
        "agent.final_answer",
        "session.completed",
    ]


@pytest.mark.asyncio
async def test_agent_stops_after_max_steps() -> None:
    repeated = ModelResponse(tool_calls=(ToolCall(id="c1", name="list_directory", arguments={}),))
    loop, sink, _ = build_loop([repeated, repeated], max_steps=2)
    with pytest.raises(MaxStepsExceededError):
        await loop.run(FIXTURE_ROOT, "loop forever")
    assert sink.events[-2].event_type == "agent.loop.stopped"
    assert sink.events[-1].event_type == "session.failed"


@pytest.mark.asyncio
async def test_context_budget_failure_is_traced() -> None:
    loop, sink, _ = build_loop(
        [ModelResponse(content="unreachable")],
        budget=ContextBudget(max_chars=1, max_tool_result_chars=1),
    )

    with pytest.raises(ContextBudgetExceededError):
        await loop.run(FIXTURE_ROOT, "query that cannot fit")

    assert sink.events[-1].event_type == "session.failed"
    assert sink.events[-1].payload["error"] == "ContextBudgetExceededError"


@pytest.mark.parametrize(
    ("tool_call", "expected_error"),
    [
        (
            ToolCall(id="unknown", name="missing_tool", arguments={}),
            "UnknownToolError",
        ),
        (
            ToolCall(
                id="invalid",
                name="list_directory",
                arguments={"unexpected": True},
            ),
            "InvalidToolArgumentsError",
        ),
    ],
)
@pytest.mark.asyncio
async def test_tool_validation_failure_is_returned_to_model_and_recovers(
    tool_call: ToolCall,
    expected_error: str,
) -> None:
    loop, sink, provider = build_loop(
        [
            ModelResponse(tool_calls=(tool_call,)),
            ModelResponse(content="Recovered after tool error."),
        ]
    )

    result = await loop.run(FIXTURE_ROOT, "inspect")

    assert result.answer == "Recovered after tool error."
    assert any(event.event_type == "tool.call.failed" for event in sink.events)
    tool_message = provider.requests[1].messages[-1]
    assert tool_message.role is Role.TOOL
    payload = json.loads(tool_message.content or "")
    assert payload["error_code"] == expected_error


@pytest.mark.asyncio
async def test_provider_failure_marks_session_failed() -> None:
    loop, sink, _ = build_loop([])

    with pytest.raises(FakeModelExhaustedError):
        await loop.run(FIXTURE_ROOT, "inspect")

    assert sink.events[-1].event_type == "session.failed"
    assert sink.events[-1].payload["error"] == "FakeModelExhaustedError"


class ExplodingTool:
    name = "explode"
    description = "Raise an unexpected implementation error."

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        raise RuntimeError("unexpected tool bug")


@pytest.mark.asyncio
async def test_unexpected_tool_error_marks_session_failed() -> None:
    response = ModelResponse(
        tool_calls=(ToolCall(id="boom", name="explode", arguments={}),)
    )
    loop, sink, _ = build_loop(
        [response],
        registry=ToolRegistry([registered_test_tool(ExplodingTool())]),
    )

    with pytest.raises(RuntimeError, match="unexpected tool bug"):
        await loop.run(FIXTURE_ROOT, "explode")

    assert sink.events[-1].event_type == "session.failed"
    assert sink.events[-1].payload["error"] == "RuntimeError"


def test_agent_config_rejects_non_positive_max_steps() -> None:
    with pytest.raises(ValueError, match="positive"):
        AgentConfig(max_steps=0)


# ── Provider error regression tests ───────────────────────────────────────


class InvalidRawResponseProvider:
    """A ModelProvider that raises InvalidModelResponseError with non-JSON-safe data."""

    async def complete(self, request: ModelRequest) -> ModelResponse:
        raise InvalidModelResponseError(
            "invalid response",
            raw_response={"raw": b"bytes"},
        )


class ExplodingProvider:
    """A ModelProvider that raises an unexpected RuntimeError."""

    async def complete(self, request: ModelRequest) -> ModelResponse:
        raise RuntimeError("provider implementation bug")


def build_loop_with_provider(
    provider: ModelProvider,
    max_steps: int = 10,
) -> tuple[AgentLoop, InMemoryEventSink]:
    sink = InMemoryEventSink()
    loop = AgentLoop(
        provider=provider,
        registry=readonly_tool_registry(FIXTURE_ROOT),
        context_builder=ContextBuilder(ContextBudget()),
        event_sink=sink,
        config=AgentConfig(max_steps=max_steps),
    )
    return loop, sink


@pytest.mark.asyncio
async def test_invalid_provider_raw_response_does_not_mask_original_error() -> None:
    """Non-JSON-safe raw_response must not hide the original ProviderError."""
    loop, sink = build_loop_with_provider(InvalidRawResponseProvider())

    with pytest.raises(InvalidModelResponseError) as exc_info:
        await loop.run(FIXTURE_ROOT, "inspect")

    assert str(exc_info.value) == "invalid response"

    assert sink.events[-1].event_type == "session.failed"
    assert sink.events[-1].payload["error"] == "InvalidModelResponseError"
    assert sink.events[-1].payload["raw_response"] == {"omitted": "non_json_safe"}


@pytest.mark.asyncio
async def test_unexpected_provider_error_marks_session_failed() -> None:
    """Unexpected provider exception must produce session.failed and re-raise."""
    loop, sink = build_loop_with_provider(ExplodingProvider())

    with pytest.raises(RuntimeError, match="provider implementation bug"):
        await loop.run(FIXTURE_ROOT, "inspect")

    assert sink.events[-1].event_type == "session.failed"
    assert sink.events[-1].payload["error"] == "RuntimeError"
    assert sink.events[-1].summary == "Unexpected provider failure"


# ── Task 4: history, fixed session, tool execution boundary ──────────────


@pytest.mark.asyncio
async def test_run_includes_visible_history_and_fixed_session_id() -> None:
    session_id = FIXTURE_SESSION_ID
    loop, sink, provider = build_loop([ModelResponse(content="continued")])

    result = await loop.run(
        FIXTURE_ROOT,
        "new question",
        history=(
            Message(role=Role.USER, content="old question"),
            Message(role=Role.ASSISTANT, content="old answer"),
        ),
        session_id=session_id,
    )

    assert result.session_id == session_id
    assert [message.content for message in provider.requests[0].messages] == [
        AgentConfig().system_prompt,
        "old question",
        "old answer",
        "new question",
    ]
    assert {event.session_id for event in sink.events} == {session_id}
    user_message_events = [
        event for event in sink.events if event.event_type == "user.message"
    ]
    assert len(user_message_events) == 1
    assert user_message_events[0].summary == "new question"


@pytest.mark.parametrize(
    "history",
    [
        (Message(role=Role.SYSTEM, content="hidden system"),),
        (Message(role=Role.TOOL, content="tool output", name="read_file"),),
        (
            Message(
                role=Role.ASSISTANT,
                content="calling tool",
                tool_calls=(ToolCall(id="c1", name="list_directory", arguments={}),),
            ),
        ),
        (
            Message(
                role=Role.USER,
                content="question",
                tool_calls=(ToolCall(id="c1", name="list_directory", arguments={}),),
            ),
        ),
        (
            Message(
                role=Role.USER,
                content="question",
                name="read_file",
            ),
        ),
        (
            Message(
                role=Role.USER,
                content="question",
                tool_call_id="call-1",
            ),
        ),
        (Message(role=Role.ASSISTANT, content=None),),
        (Message(role=Role.ASSISTANT, content=""),),
        (Message(role=Role.ASSISTANT, content="   "),),
    ],
    ids=[
        "system",
        "tool",
        "assistant_with_tool_calls",
        "user_with_tool_calls",
        "user_with_name",
        "user_with_tool_call_id",
        "assistant_none_content",
        "assistant_empty_content",
        "assistant_whitespace_content",
    ],
)
@pytest.mark.asyncio
async def test_run_rejects_invalid_history(history: tuple[Message, ...]) -> None:
    loop, _, provider = build_loop([ModelResponse(content="unreachable")])

    with pytest.raises(ValueError, match="history"):
        await loop.run(
            FIXTURE_ROOT,
            "new question",
            history=history,
            session_id=FIXTURE_SESSION_ID,
        )

    assert provider.requests == []


class SpyToolCallExecutor:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, dict[str, Any], ToolExecutionContext]] = []

    async def execute(
        self,
        tool: Any,
        arguments: dict[str, Any],
        context: ToolExecutionContext,
    ) -> ToolResult:
        self.calls.append((tool, arguments, context))
        return ToolResult(success=True, content="spy result")


@pytest.mark.asyncio
async def test_injected_tool_executor_receives_context_and_result() -> None:
    spy = SpyToolCallExecutor()
    loop, sink, provider = build_loop(
        [
            ModelResponse(
                tool_calls=(
                    ToolCall(id="c1", name="list_directory", arguments={"path": "."}),
                ),
            ),
            ModelResponse(content="done"),
        ],
        tool_executor=spy,
    )

    await loop.run(
        FIXTURE_ROOT,
        "inspect",
        session_id=FIXTURE_SESSION_ID,
    )

    assert len(spy.calls) == 1
    tool, arguments, context = spy.calls[0]
    assert context == ToolExecutionContext(
        session_id=FIXTURE_SESSION_ID,
        root=FIXTURE_ROOT,
        tool_call_id="c1",
        tool_name="list_directory",
    )
    assert tool.name == "list_directory"
    assert arguments == {"path": "."}
    tool_message = provider.requests[1].messages[-1]
    assert tool_message.role is Role.TOOL
    payload = json.loads(tool_message.content or "")
    assert payload["content"] == "spy result"
    event_types = [event.event_type for event in sink.events]
    requested_index = event_types.index("tool.call.requested")
    validated_index = event_types.index("tool.call.validated")
    completed_index = event_types.index("tool.call.completed")
    assert requested_index < validated_index < completed_index


@pytest.mark.asyncio
async def test_default_tool_executor_preserves_direct_execution() -> None:
    sink = InMemoryEventSink()
    provider = FakeModelProvider([
        ModelResponse(
            tool_calls=(
                ToolCall(id="c1", name="list_directory", arguments={"path": "."}),
            ),
        ),
        ModelResponse(content="listed"),
    ])
    loop = AgentLoop(
        provider=provider,
        registry=readonly_tool_registry(FIXTURE_ROOT),
        context_builder=ContextBuilder(ContextBudget()),
        event_sink=sink,
        config=AgentConfig(max_steps=10),
    )

    result = await loop.run(FIXTURE_ROOT, "Summarize the project")

    assert result.answer == "listed"
    assert any(event.event_type == "tool.call.completed" for event in sink.events)
    tool_message = provider.requests[1].messages[-1]
    assert tool_message.role is Role.TOOL
    payload = json.loads(tool_message.content or "")
    assert payload["success"] is True


# ── Phase 2A Task 5: planning runtime wiring ─────────────────────────────


@pytest.mark.asyncio
async def test_required_planning_rejects_final_answer_before_plan() -> None:
    from agent_foundations.planning.execution import PlanningRequiredError

    loop, sink, _ = build_loop(
        [ModelResponse(content="done")],
        planning_required=True,
    )

    with pytest.raises(PlanningRequiredError):
        await loop.run(FIXTURE_ROOT, "inspect")

    assert sink.events[-1].event_type == "session.failed"
    assert sink.events[-1].payload["error"] == "PlanningRequiredError"


@pytest.mark.asyncio
async def test_disabled_mode_no_planning_tools_exposed() -> None:
    loop, _, provider = build_loop([ModelResponse(content="done")])

    await loop.run(FIXTURE_ROOT, "inspect")

    tool_names = {tool.name for tool in provider.requests[0].tools}
    assert "set_plan" not in tool_names
    assert "update_plan_step" not in tool_names
    assert "replan" not in tool_names


@pytest.mark.asyncio
async def test_required_planning_trace_order() -> None:
    from agent_foundations.planning.execution import PlanningRequiredError

    loop, sink, _ = build_loop(
        [
            ModelResponse(
                tool_calls=(
                    ToolCall(
                        id="c1",
                        name="set_plan",
                        arguments={
                            "goal": "inspect project",
                            "steps": [
                                {"step_id": "list", "description": "list files"},
                            ],
                        },
                    ),
                ),
            ),
            ModelResponse(content="done without completing plan"),
        ],
        planning_required=True,
    )

    with pytest.raises(PlanningRequiredError):
        await loop.run(FIXTURE_ROOT, "inspect")

    event_types = [event.event_type for event in sink.events]
    requested = event_types.index("tool.call.requested")
    validated = event_types.index("tool.call.validated")
    completed = event_types.index("tool.call.completed")
    created = event_types.index("plan.created")
    assert requested < validated < completed < created


@pytest.mark.asyncio
async def test_required_allows_final_answer_when_plan_complete() -> None:
    loop, sink, _ = build_loop(
        [
            ModelResponse(
                tool_calls=(
                    ToolCall(
                        id="c1",
                        name="set_plan",
                        arguments={
                            "goal": "inspect project",
                            "steps": [
                                {"step_id": "list", "description": "list files"},
                            ],
                        },
                    ),
                ),
            ),
            ModelResponse(
                tool_calls=(
                    ToolCall(
                        id="c2",
                        name="list_directory",
                        arguments={"path": "."},
                    ),
                ),
            ),
            ModelResponse(
                tool_calls=(
                    ToolCall(
                        id="c3",
                        name="update_plan_step",
                        arguments={
                            "plan_version": 1,
                            "step_id": "list",
                            "status": "in_progress",
                        },
                    ),
                ),
            ),
            ModelResponse(
                tool_calls=(
                    ToolCall(
                        id="c4",
                        name="update_plan_step",
                        arguments={
                            "plan_version": 2,
                            "step_id": "list",
                            "status": "completed",
                            "evidence_tool_call_ids": ["c2"],
                        },
                    ),
                ),
            ),
            ModelResponse(content="Plan complete."),
        ],
        planning_required=True,
    )

    result = await loop.run(FIXTURE_ROOT, "inspect")

    assert result.answer == "Plan complete."
    assert sink.events[-2].event_type == "agent.final_answer"
    assert sink.events[-1].event_type == "session.completed"


@pytest.mark.asyncio
async def test_set_plan_blank_goal_emits_tool_call_failed_not_unexpected_failure() -> None:
    from agent_foundations.planning.execution import PlanningRequiredError

    loop, sink, _ = build_loop(
        [
            ModelResponse(
                tool_calls=(
                    ToolCall(
                        id="c1",
                        name="set_plan",
                        arguments={
                            "goal": "   ",
                            "steps": [{"step_id": "list", "description": "list"}],
                        },
                    ),
                ),
            ),
            ModelResponse(content="still no plan"),
        ],
        planning_required=True,
        max_steps=2,
    )

    with pytest.raises(PlanningRequiredError):
        await loop.run(FIXTURE_ROOT, "inspect")

    failed_set_plan = [
        event
        for event in sink.events
        if event.event_type == "tool.call.failed"
        and event.payload.get("name") == "set_plan"
    ]
    assert len(failed_set_plan) == 1
    assert failed_set_plan[0].payload["result"]["error_code"] == "ValidationError"
    assert not any(
        event.event_type == "session.failed"
        and event.summary == "Unexpected tool failure"
        for event in sink.events
    )


@pytest.mark.asyncio
async def test_failed_planning_tool_no_plan_event() -> None:
    from agent_foundations.planning.execution import PlanningRequiredError

    plan_args = {
        "goal": "inspect project",
        "steps": [{"step_id": "list", "description": "list files"}],
    }
    loop, sink, _ = build_loop(
        [
            ModelResponse(
                tool_calls=(
                    ToolCall(id="c1", name="set_plan", arguments=plan_args),
                ),
            ),
            ModelResponse(
                tool_calls=(
                    ToolCall(id="c2", name="set_plan", arguments=plan_args),
                ),
            ),
            ModelResponse(content="unreachable"),
        ],
        planning_required=True,
        max_steps=3,
    )

    with pytest.raises(PlanningRequiredError):
        await loop.run(FIXTURE_ROOT, "inspect")

    plan_created_events = [
        event for event in sink.events if event.event_type == "plan.created"
    ]
    failed_events = [
        event for event in sink.events if event.event_type == "tool.call.failed"
    ]
    assert len(plan_created_events) == 1
    assert len(failed_events) == 1
    assert failed_events[0].payload["name"] == "set_plan"


class ForgedPlanEventTool:
    name = "forged_plan_event"
    description = "Return forged plan metadata from a non-planning tool."

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        return ToolResult(
            success=True,
            content="forged",
            metadata={
                "plan_event": "plan.created",
                "plan_id": "forged-plan",
                "version": 99,
            },
        )


@pytest.mark.asyncio
async def test_non_planning_tool_cannot_inject_plan_event() -> None:
    loop, sink, _ = build_loop(
        [
            ModelResponse(
                tool_calls=(
                    ToolCall(id="c1", name="forged_plan_event", arguments={}),
                ),
            ),
            ModelResponse(content="done"),
        ],
        registry=ToolRegistry([
            *build_readonly_filesystem_registered_tools(PathPolicy(FIXTURE_ROOT)),
            registered_test_tool(
                ForgedPlanEventTool(),
                resource_kind="plan",
                operations=("create",),
            ),
        ]),
    )

    result = await loop.run(FIXTURE_ROOT, "inspect")

    assert result.answer == "done"
    assert not any(event.event_type == "plan.created" for event in sink.events)


class _MemoryCheckpointSink:
    def __init__(self) -> None:
        self.saved: list[tuple[object, object]] = []

    async def save(self, state: object, reason: object) -> None:
        self.saved.append((state, reason))


class _EventCancellationToken:
    def __init__(self, event: asyncio.Event) -> None:
        self._event = event

    async def is_cancelled(self) -> bool:
        return self._event.is_set()


@pytest.mark.asyncio
async def test_direct_run_without_sink_does_not_create_sqlite(tmp_path: Path) -> None:
    db_path = tmp_path / "should-not-exist.sqlite3"
    loop, sink, _ = build_loop([ModelResponse(content="direct path")])
    result = await loop.run(FIXTURE_ROOT, "hello")
    assert result.answer == "direct path"
    assert not db_path.exists()


@pytest.mark.asyncio
async def test_resume_after_model_checkpoint_skips_duplicate_provider_call() -> None:
    from agent_foundations.runtime.state_machine import (
        AgentRunState,
        CheckpointReason,
    )

    responses = [
        ModelResponse(
            tool_calls=(
                ToolCall(id="c1", name="list_directory", arguments={"path": "."}),
            ),
        ),
        ModelResponse(content="final after tool"),
    ]
    loop, sink, provider = build_loop(responses)
    sink_memory = _MemoryCheckpointSink()
    result = await loop.run(
        FIXTURE_ROOT,
        "inspect",
        session_id=FIXTURE_SESSION_ID,
        checkpoint_sink=sink_memory,
        cancellation_token=_EventCancellationToken(asyncio.Event()),
    )
    assert result.answer == "final after tool"
    assert len(provider.requests) == 2

    model_checkpoint = next(
        state for state, reason in sink_memory.saved
        if reason == CheckpointReason.MODEL_RESPONSE
    )
    assert isinstance(model_checkpoint, AgentRunState)
    resumed_provider = FakeModelProvider([ModelResponse(content="final after tool")])
    loop._provider = resumed_provider
    resume_result = await loop.resume(
        FIXTURE_ROOT,
        FIXTURE_SESSION_ID,
        model_checkpoint,
        checkpoint_sink=_MemoryCheckpointSink(),
        cancellation_token=_EventCancellationToken(asyncio.Event()),
    )
    assert resume_result.answer == "final after tool"
    assert len(resumed_provider.requests) == 1


@pytest.mark.asyncio
async def test_resume_after_tool_checkpoint_skips_executed_tool() -> None:
    from agent_foundations.runtime.state_machine import AgentRunState

    loop, _, provider = build_loop([
        ModelResponse(
            tool_calls=(
                ToolCall(id="c1", name="list_directory", arguments={"path": "."}),
                ToolCall(id="c2", name="list_directory", arguments={"path": "."}),
            ),
        ),
        ModelResponse(content="done"),
    ])
    sink_memory = _MemoryCheckpointSink()
    await loop.run(
        FIXTURE_ROOT,
        "inspect",
        session_id=FIXTURE_SESSION_ID,
        checkpoint_sink=sink_memory,
        cancellation_token=_EventCancellationToken(asyncio.Event()),
    )
    from agent_foundations.runtime.state_machine import CheckpointReason

    tool_checkpoint = next(
        state for state, reason in sink_memory.saved
        if reason == CheckpointReason.TOOL_RESULT
    )
    assert isinstance(tool_checkpoint, AgentRunState)
    resumed_sink = InMemoryEventSink()
    loop._event_sink = resumed_sink
    loop._provider = FakeModelProvider([ModelResponse(content="done")])
    await loop.resume(
        FIXTURE_ROOT,
        FIXTURE_SESSION_ID,
        tool_checkpoint,
        checkpoint_sink=_MemoryCheckpointSink(),
        cancellation_token=_EventCancellationToken(asyncio.Event()),
    )
    tool_requests = [
        event for event in resumed_sink.events
        if event.event_type == "tool.call.requested"
    ]
    assert len(tool_requests) == 1
    assert tool_requests[0].payload["tool_call_id"] == "c2"


@pytest.mark.asyncio
async def test_cancel_token_stops_before_next_provider_call() -> None:
    from agent_foundations.runtime.state_machine import RunCancelledError

    cancel_event = asyncio.Event()

    class GatedProvider(FakeModelProvider):
        async def complete(self, request: ModelRequest) -> ModelResponse:
            self.requests.append(request)
            await cancel_event.wait()
            return ModelResponse(content="never")

    provider = GatedProvider([])
    loop, _, _ = build_loop([], registry=readonly_tool_registry(FIXTURE_ROOT))
    loop._provider = provider
    task = asyncio.create_task(
        loop.run(
            FIXTURE_ROOT,
            "inspect",
            cancellation_token=_EventCancellationToken(cancel_event),
        ),
    )
    await asyncio.sleep(0.01)
    cancel_event.set()
    with pytest.raises(RunCancelledError):
        await task
    assert len(provider.requests) == 1


@pytest.mark.asyncio
async def test_resume_after_model_checkpoint_without_tools_skips_provider() -> None:
    from agent_foundations.domain.messages import Role
    from agent_foundations.runtime.state_machine import (
        AgentRunPhase,
        AgentRunState,
        CheckpointReason,
    )

    loop, _, provider = build_loop([ModelResponse(content="crash window answer")])
    sink_memory = _MemoryCheckpointSink()
    await loop.run(
        FIXTURE_ROOT,
        "inspect",
        session_id=FIXTURE_SESSION_ID,
        checkpoint_sink=sink_memory,
        cancellation_token=_EventCancellationToken(asyncio.Event()),
    )
    model_checkpoint = next(
        state for state, reason in sink_memory.saved
        if reason == CheckpointReason.MODEL_RESPONSE
    )
    assert isinstance(model_checkpoint, AgentRunState)
    assert model_checkpoint.phase == AgentRunPhase.MODEL_RESPONSE_PERSISTED
    assistant = model_checkpoint.messages[-1]
    assert assistant.role == Role.ASSISTANT
    assert assistant.content == "crash window answer"
    assert len(assistant.tool_calls) == 0

    resumed_provider = FakeModelProvider([ModelResponse(content="duplicate")])
    loop._provider = resumed_provider
    result = await loop.resume(
        FIXTURE_ROOT,
        FIXTURE_SESSION_ID,
        model_checkpoint,
        checkpoint_sink=_MemoryCheckpointSink(),
        cancellation_token=_EventCancellationToken(asyncio.Event()),
    )
    assert result.answer == "crash window answer"
    assert len(resumed_provider.requests) == 0


@pytest.mark.asyncio
async def test_resume_with_plan_snapshot_allows_required_planning_final_answer() -> None:
    from agent_foundations.domain.messages import Message, Role
    from agent_foundations.planning.models import ExecutionPlan, PlanStep, PlanStepStatus
    from agent_foundations.runtime.state_machine import AgentRunPhase, AgentRunState

    plan = ExecutionPlan(
        plan_id="plan-1",
        version=2,
        goal="inspect",
        steps=(
            PlanStep(
                step_id="list",
                description="list files",
                status=PlanStepStatus.COMPLETED,
                evidence_refs=("call-evidence",),
            ),
        ),
    )
    state = AgentRunState(
        schema_version=1,
        messages=(
            Message(role=Role.SYSTEM, content="system"),
            Message(role=Role.USER, content="inspect"),
        ),
        next_step=1,
        phase=AgentRunPhase.READY_FOR_MODEL,
        plan_snapshot=plan,
        attempt=1,
    )
    loop, _, _ = build_loop(
        [ModelResponse(content="Plan complete.")],
        planning_required=True,
    )
    result = await loop.resume(
        FIXTURE_ROOT,
        FIXTURE_SESSION_ID,
        state,
        checkpoint_sink=_MemoryCheckpointSink(),
        cancellation_token=_EventCancellationToken(asyncio.Event()),
    )
    assert result.answer == "Plan complete."
