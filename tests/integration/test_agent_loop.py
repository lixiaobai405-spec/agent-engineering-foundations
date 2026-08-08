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
from agent_foundations.providers.fake import FakeModelProvider
from agent_foundations.runtime.agent import AgentConfig
from agent_foundations.runtime.loop import AgentLoop
from agent_foundations.runtime.tool_execution import ToolCallExecutor, ToolExecutionContext
from agent_foundations.runtime.trace import InMemoryEventSink
from agent_foundations.tools.filesystem.list_directory import ListDirectoryTool
from agent_foundations.tools.filesystem.path_policy import PathPolicy
from agent_foundations.tools.registry import ToolRegistry

FIXTURE_ROOT = Path("tests/fixtures/sample_project").resolve()
FIXTURE_SESSION_ID = "22222222-2222-4222-8222-222222222222"


def build_loop(
    responses: list[ModelResponse],
    max_steps: int = 10,
    budget: ContextBudget | None = None,
    registry: ToolRegistry | None = None,
    tool_executor: ToolCallExecutor | None = None,
) -> tuple[AgentLoop, InMemoryEventSink, FakeModelProvider]:
    sink = InMemoryEventSink()
    provider = FakeModelProvider(responses)
    loop = AgentLoop(
        provider=provider,
        registry=registry or ToolRegistry([ListDirectoryTool(PathPolicy(FIXTURE_ROOT))]),
        context_builder=ContextBuilder(budget or ContextBudget()),
        event_sink=sink,
        config=AgentConfig(max_steps=max_steps),
        tool_executor=tool_executor,
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
        registry=ToolRegistry([ExplodingTool()]),
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
        registry=ToolRegistry([ListDirectoryTool(PathPolicy(FIXTURE_ROOT))]),
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
        registry=ToolRegistry([ListDirectoryTool(PathPolicy(FIXTURE_ROOT))]),
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
