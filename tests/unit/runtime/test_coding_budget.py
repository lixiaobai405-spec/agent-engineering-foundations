from __future__ import annotations

import importlib.util
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from agent_foundations.chat.models import PermissionMode
from agent_foundations.context.budget import ContextBudget
from agent_foundations.context.builder import ContextBuilder
from agent_foundations.domain.messages import Message, Role
from agent_foundations.domain.model import ModelResponse
from agent_foundations.domain.tool import Tool, ToolCall, ToolResult
from agent_foundations.providers.fake import FakeModelProvider
from agent_foundations.providers.resilient import RetryPolicy
from agent_foundations.runtime.agent import AgentConfig
from agent_foundations.runtime.loop import AgentLoop, _tool_message_content
from agent_foundations.runtime.recovery import RECOVERY_READ_REQUIRED
from agent_foundations.runtime.redaction import Redactor
from agent_foundations.runtime.sinks import JsonlEventSink
from agent_foundations.runtime.tool_execution import ToolCallExecutor, ToolExecutionContext
from agent_foundations.runtime.trace import InMemoryEventSink
from agent_foundations.security.models import PermissionProfileName
from agent_foundations.tools.command.read_output import ReadCommandOutputTool
from agent_foundations.tools.command.run_command import RunCommandTool
from agent_foundations.tools.command.search_output import SearchCommandOutputTool
from agent_foundations.tools.patch.validate_patch import ValidatePatchTool
from agent_foundations.tools.registry import (
    ToolRegistry,
    build_readonly_filesystem_registered_tools,
)
from tests.unit.tools.registry_helpers import registered_test_tool

FIXTURE_ROOT = Path("tests/fixtures/sample_project").resolve()
SHA = "a" * 64
ARGV = {
    "gate_id": "manifest.python.pytest",
    "target": "tests",
    "flags": ["-q"],
}


def _budget_module() -> Any:
    spec = importlib.util.find_spec("agent_foundations.runtime.coding_budget")
    assert spec is not None
    return importlib.import_module("agent_foundations.runtime.coding_budget")


def _limits() -> Any:
    module = _budget_module()
    return module.CodingBudgetLimits(
        max_patch_repairs=2,
        max_same_argv_command_runs=2,
        max_artifact_reads=2,
    )


def _changes(path: str = "src/auth.py", new_line: str = "return True") -> dict[str, Any]:
    return {
        "changes": [
            {
                "path": path,
                "expected_sha256": SHA,
                "start_line": 1,
                "old_lines": ["return False"],
                "new_lines": [new_line],
            },
        ],
    }


def _assistant(name: str, arguments: Mapping[str, Any], call_id: str) -> Message:
    return Message(
        role=Role.ASSISTANT,
        content=None,
        tool_calls=(ToolCall(id=call_id, name=name, arguments=dict(arguments)),),
    )


def _tool_msg(name: str, call_id: str, result: ToolResult) -> Message:
    return Message(
        role=Role.TOOL,
        name=name,
        tool_call_id=call_id,
        content=_tool_message_content(name, result),
    )


def _failed_patch(code: str = "PATCH_HUNK_FAILED") -> ToolResult:
    return ToolResult(success=False, content="repair failed", error_code=code)


def _append_turn(
    messages: list[Message],
    name: str,
    arguments: Mapping[str, Any],
    result: ToolResult,
    call_id: str,
) -> None:
    messages.append(_assistant(name, arguments, call_id))
    messages.append(_tool_msg(name, call_id, result))


def test_agent_config_default_has_no_layered_budget() -> None:
    config = AgentConfig()
    assert config.max_steps == 10
    assert getattr(config, "coding_budget", None) is None
    assert RetryPolicy().max_attempts == 3


def test_evaluate_budget_blocks_third_failed_patch_on_same_path() -> None:
    module = _budget_module()
    limits = _limits()
    messages: list[Message] = [Message(role=Role.USER, content="fix")]
    _append_turn(messages, "validate_patch", _changes(new_line="a"), _failed_patch(), "p1")
    _append_turn(messages, "validate_patch", _changes(new_line="b"), _failed_patch(), "p2")
    decision = module.evaluate_budget(
        tuple(messages),
        "validate_patch",
        _changes(new_line="c"),
        limits,
    )
    assert decision.allowed is False
    assert decision.error_code == module.BUDGET_PATCH_REPAIRS_EXCEEDED


def test_evaluate_budget_ignores_recovery_intercepts_for_repairs() -> None:
    module = _budget_module()
    limits = _limits()
    messages: list[Message] = [Message(role=Role.USER, content="fix")]
    _append_turn(messages, "validate_patch", _changes(new_line="a"), _failed_patch(), "p1")
    _append_turn(
        messages,
        "validate_patch",
        _changes(new_line="a"),
        ToolResult(
            success=False,
            content="recovery blocked",
            error_code=RECOVERY_READ_REQUIRED,
        ),
        "p2",
    )
    decision = module.evaluate_budget(
        tuple(messages),
        "validate_patch",
        _changes(new_line="c"),
        limits,
    )
    assert decision.allowed is True


def test_evaluate_budget_is_per_path_for_patch_repairs() -> None:
    module = _budget_module()
    limits = _limits()
    messages: list[Message] = [Message(role=Role.USER, content="fix")]
    _append_turn(
        messages,
        "validate_patch",
        _changes(path="src/a.py", new_line="a"),
        _failed_patch(),
        "p1",
    )
    _append_turn(
        messages,
        "validate_patch",
        _changes(path="src/a.py", new_line="b"),
        _failed_patch(),
        "p2",
    )
    blocked = module.evaluate_budget(
        tuple(messages),
        "validate_patch",
        _changes(path="src/a.py", new_line="c"),
        limits,
    )
    allowed = module.evaluate_budget(
        tuple(messages),
        "validate_patch",
        _changes(path="src/b.py", new_line="c"),
        limits,
    )
    assert blocked.allowed is False
    assert allowed.allowed is True


def test_evaluate_budget_blocks_third_same_argv_run_command() -> None:
    module = _budget_module()
    limits = _limits()
    arguments = {**ARGV, "cwd": "."}
    ran = ToolResult(
        success=True,
        content="ran",
        metadata={"exit_code": 1, "failed": 1, "artifact_id": "coa_" + ("b" * 22)},
    )
    messages: list[Message] = [Message(role=Role.USER, content="test")]
    _append_turn(messages, "run_command", arguments, ran, "c1")
    _append_turn(messages, "run_command", arguments, ran, "c2")
    decision = module.evaluate_budget(tuple(messages), "run_command", arguments, limits)
    assert decision.allowed is False
    assert decision.error_code == module.BUDGET_COMMAND_RETRIES_EXCEEDED
    other = module.evaluate_budget(
        tuple(messages),
        "run_command",
        {"gate_id": "manifest.python.mypy", "target": "src", "cwd": "."},
        limits,
    )
    assert other.allowed is True


def test_evaluate_budget_blocks_third_artifact_read() -> None:
    module = _budget_module()
    limits = _limits()
    artifact_id = "coa_" + ("b" * 22)
    read_args = {
        "artifact_id": artifact_id,
        "selector": {"stream": "stdout"},
        "reason": "inspect",
    }
    search_args = {
        "artifact_id": artifact_id,
        "query": "FAILED",
        "reason": "inspect",
    }
    ok = ToolResult(success=True, content="slice", metadata={"artifact_id": artifact_id})
    messages: list[Message] = [Message(role=Role.USER, content="logs")]
    _append_turn(messages, "read_command_output", read_args, ok, "r1")
    _append_turn(messages, "search_command_output", search_args, ok, "r2")
    decision = module.evaluate_budget(
        tuple(messages),
        "read_command_output",
        read_args,
        limits,
    )
    assert decision.allowed is False
    assert decision.error_code == module.BUDGET_ARTIFACT_READS_EXCEEDED


class ScriptedExecutor:
    def __init__(self, results: list[ToolResult]) -> None:
        self._results = list(results)
        self.calls: list[str] = []

    async def execute(
        self,
        tool: Tool,
        arguments: dict[str, Any],
        context: ToolExecutionContext,
    ) -> ToolResult:
        del arguments, context
        self.calls.append(tool.name)
        if not self._results:
            raise AssertionError(f"unexpected extra execute for {tool.name}")
        return self._results.pop(0)


def _loop(
    responses: list[ModelResponse],
    executor: ToolCallExecutor,
    extra_tools: list[Any],
    *,
    config: AgentConfig,
) -> tuple[AgentLoop, FakeModelProvider, InMemoryEventSink]:
    from agent_foundations.tools.filesystem.path_policy import PathPolicy

    policy = PathPolicy(FIXTURE_ROOT)
    registered = list(build_readonly_filesystem_registered_tools(policy))
    registered.extend(extra_tools)
    sink = InMemoryEventSink()
    provider = FakeModelProvider(responses)
    loop = AgentLoop(
        provider=provider,
        registry=ToolRegistry(registered),
        context_builder=ContextBuilder(ContextBudget()),
        event_sink=sink,
        config=config,
        tool_executor=executor,
    )
    return loop, provider, sink


@pytest.mark.asyncio
async def test_loop_does_not_execute_over_budget_validate_patch() -> None:
    assert "coding_budget" in AgentConfig.__dataclass_fields__
    limits = _limits()
    executor = ScriptedExecutor([_failed_patch(), _failed_patch()])
    loop, _, sink = _loop(
        [
            ModelResponse(
                tool_calls=(
                    ToolCall(id="p1", name="validate_patch", arguments=_changes(new_line="a")),
                ),
            ),
            ModelResponse(
                tool_calls=(
                    ToolCall(id="p2", name="validate_patch", arguments=_changes(new_line="b")),
                ),
            ),
            ModelResponse(
                tool_calls=(
                    ToolCall(id="p3", name="validate_patch", arguments=_changes(new_line="c")),
                ),
            ),
            ModelResponse(content="stopped by budget"),
        ],
        executor,
        [registered_test_tool(ValidatePatchTool())],
        config=AgentConfig(max_steps=4, coding_budget=limits),
    )
    result = await loop.run(FIXTURE_ROOT, "fix auth")
    assert result.answer == "stopped by budget"
    assert executor.calls == ["validate_patch", "validate_patch"]
    codes = [
        event.payload.get("result", {}).get("error_code")
        for event in sink.events
        if event.event_type == "tool.call.failed"
    ]
    assert "BUDGET_PATCH_REPAIRS_EXCEEDED" in codes


@pytest.mark.asyncio
async def test_loop_does_not_execute_over_budget_run_command() -> None:
    assert "coding_budget" in AgentConfig.__dataclass_fields__
    limits = _limits()
    arguments = {**ARGV, "cwd": "."}
    ran = ToolResult(success=True, content="ran", metadata={"exit_code": 0, "failed": 0})
    executor = ScriptedExecutor([ran, ran])
    loop, _, sink = _loop(
        [
            ModelResponse(
                tool_calls=(ToolCall(id="c1", name="run_command", arguments=arguments),),
            ),
            ModelResponse(
                tool_calls=(ToolCall(id="c2", name="run_command", arguments=arguments),),
            ),
            ModelResponse(
                tool_calls=(ToolCall(id="c3", name="run_command", arguments=arguments),),
            ),
            ModelResponse(content="command budget"),
        ],
        executor,
        [registered_test_tool(RunCommandTool(), operations=("run",))],
        config=AgentConfig(max_steps=4, coding_budget=limits),
    )
    result = await loop.run(FIXTURE_ROOT, "run tests")
    assert result.answer == "command budget"
    assert executor.calls == ["run_command", "run_command"]
    codes = [
        event.payload.get("result", {}).get("error_code")
        for event in sink.events
        if event.event_type == "tool.call.failed"
    ]
    assert "BUDGET_COMMAND_RETRIES_EXCEEDED" in codes


@pytest.mark.asyncio
async def test_loop_does_not_execute_over_budget_artifact_read() -> None:
    assert "coding_budget" in AgentConfig.__dataclass_fields__
    limits = _limits()
    artifact_id = "coa_" + ("b" * 22)
    read_args = {
        "artifact_id": artifact_id,
        "selector": {"stream": "stdout", "tail_lines": 40},
        "reason": "inspect",
    }
    search_args = {
        "artifact_id": artifact_id,
        "query": "FAILED",
        "reason": "inspect",
    }
    ok = ToolResult(success=True, content="slice")
    executor = ScriptedExecutor([ok, ok])
    loop, _, sink = _loop(
        [
            ModelResponse(
                tool_calls=(
                    ToolCall(id="r1", name="read_command_output", arguments=read_args),
                ),
            ),
            ModelResponse(
                tool_calls=(
                    ToolCall(id="r2", name="search_command_output", arguments=search_args),
                ),
            ),
            ModelResponse(
                tool_calls=(
                    ToolCall(id="r3", name="read_command_output", arguments=read_args),
                ),
            ),
            ModelResponse(content="artifact budget"),
        ],
        executor,
        [
            registered_test_tool(ReadCommandOutputTool(), operations=("read",)),
            registered_test_tool(SearchCommandOutputTool(), operations=("search",)),
        ],
        config=AgentConfig(max_steps=4, coding_budget=limits),
    )
    result = await loop.run(FIXTURE_ROOT, "read logs")
    assert result.answer == "artifact budget"
    assert executor.calls == ["read_command_output", "search_command_output"]
    codes = [
        event.payload.get("result", {}).get("error_code")
        for event in sink.events
        if event.event_type == "tool.call.failed"
    ]
    assert "BUDGET_ARTIFACT_READS_EXCEEDED" in codes


@pytest.mark.asyncio
async def test_chat_runtime_factory_installs_production_coding_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent_foundations.cli import main

    module = _budget_module()
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "README.md").write_text("# fixture\n", encoding="utf-8")
    monkeypatch.setenv("AGENT_API_KEY", "test-placeholder")
    monkeypatch.setenv("AGENT_MODEL", "test-model")
    monkeypatch.setattr(main, "build_provider", lambda: FakeModelProvider([]))

    services = main.build_chat_services(tmp_path)
    await services.repository.initialize()
    conversation = await services.repository.create_conversation(
        title="Budget",
        project_root=project_root,
        permission_profile=PermissionProfileName.ASK_ALWAYS,
        permission_mode=PermissionMode.ASK_FOR_ACCESS,
    )
    executor = services.runner._tool_executor_factory(conversation, str(uuid4()))
    sink = JsonlEventSink(tmp_path / "traces", Redactor(project_root))
    loop = services.runner._runtime_factory(conversation, sink, executor)
    budget = getattr(loop._config, "coding_budget", None)
    assert budget is not None
    assert loop._config.max_steps == module.CHAT_MAX_STEPS
    assert budget == module.CHAT_CODING_BUDGET
    assert 24 <= module.CHAT_MAX_STEPS <= 32
    assert 3 <= module.CHAT_MAX_PATCH_REPAIRS <= 8
    assert 2 <= module.CHAT_MAX_SAME_ARGV_COMMAND_RUNS <= 4
    assert 6 <= module.CHAT_MAX_ARTIFACT_READS <= 16
    assert module.CHAT_MAX_PATCH_REPAIRS < module.CHAT_MAX_STEPS
    assert module.CHAT_MAX_SAME_ARGV_COMMAND_RUNS < module.CHAT_MAX_STEPS
    assert module.CHAT_MAX_ARTIFACT_READS < module.CHAT_MAX_STEPS
    assert AgentConfig().max_steps == 10
    assert AgentConfig().coding_budget is None
