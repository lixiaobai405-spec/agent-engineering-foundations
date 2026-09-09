from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from agent_foundations.context.budget import ContextBudget
from agent_foundations.context.builder import ContextBuilder
from agent_foundations.domain.messages import Message, Role
from agent_foundations.domain.model import ModelResponse
from agent_foundations.domain.tool import Tool, ToolCall, ToolResult
from agent_foundations.providers.fake import FakeModelProvider
from agent_foundations.runtime.agent import AgentConfig
from agent_foundations.runtime.loop import AgentLoop, _tool_message_content
from agent_foundations.runtime.recovery import (
    RECOVERY_FEEDBACK_READ_REQUIRED,
    RECOVERY_IDENTICAL_PAYLOAD_BLOCKED,
    RECOVERY_READ_REQUIRED,
    RECOVERY_RETRY_BLOCKED,
    evaluate_tool_call,
    should_request_model,
)
from agent_foundations.runtime.tool_execution import ToolCallExecutor, ToolExecutionContext
from agent_foundations.runtime.trace import InMemoryEventSink
from agent_foundations.tools.command.read_output import ReadCommandOutputTool
from agent_foundations.tools.command.run_command import RunCommandTool
from agent_foundations.tools.command.search_output import SearchCommandOutputTool
from agent_foundations.tools.patch.apply_patch import ApplyPatchTool
from agent_foundations.tools.registry import (
    ToolRegistry,
    build_readonly_filesystem_registered_tools,
)
from tests.unit.tools.registry_helpers import registered_test_tool

FIXTURE_ROOT = Path("tests/fixtures/sample_project").resolve()
SHA = "a" * 64
ARTIFACT_ID = "coa_" + ("b" * 22)
PATCH_ID = "c" * 64


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


def _diff_args(path: str = "src/auth.py") -> dict[str, Any]:
    return {
        "diff": (
            f"diff --git a/{path} b/{path}\n"
            f"--- a/{path}\n"
            f"+++ b/{path}\n"
            "@@ -1 +1 @@\n"
            "-old\n"
            "+new\n"
        ),
        "baselines": [{"path": path, "sha256": SHA}],
    }


def _tool_message(name: str, call_id: str, result: ToolResult) -> Message:
    return Message(
        role=Role.TOOL,
        name=name,
        tool_call_id=call_id,
        content=_tool_message_content(name, result),
    )


def _assistant(name: str, arguments: Mapping[str, Any], call_id: str = "c1") -> Message:
    return Message(
        role=Role.ASSISTANT,
        content=None,
        tool_calls=(ToolCall(id=call_id, name=name, arguments=dict(arguments)),),
    )


def _transcript(
    name: str,
    arguments: Mapping[str, Any],
    result: ToolResult,
    *,
    call_id: str = "c1",
) -> tuple[Message, ...]:
    return (
        Message(role=Role.USER, content="fix it"),
        _assistant(name, arguments, call_id),
        _tool_message(name, call_id, result),
    )


def _stale_result() -> ToolResult:
    return ToolResult(
        success=False,
        content="baseline hash mismatch",
        error_code="PATCH_BASELINE_MISMATCH",
    )


def _failed_command_result(*, failed: int = 1, exit_code: int = 1) -> ToolResult:
    return ToolResult(
        success=True,
        content="tests failed",
        metadata={
            "artifact_id": ARTIFACT_ID,
            "exit_code": exit_code,
            "timed_out": False,
            "failed": failed,
            "argv_display": ["python", "-m", "pytest", "-q"],
        },
    )


def test_stale_blocks_validate_until_matching_read_file() -> None:
    arguments = _changes()
    messages = _transcript("validate_patch", arguments, _stale_result())
    blocked = evaluate_tool_call(messages, "validate_patch", arguments)
    assert blocked.allowed is False
    assert blocked.error_code == RECOVERY_READ_REQUIRED

    also_apply = evaluate_tool_call(messages, "apply_patch", {"patch_id": PATCH_ID})
    assert also_apply.allowed is False
    assert also_apply.error_code == RECOVERY_READ_REQUIRED

    after_other_path = list(messages) + [
        _assistant("read_file", {"path": "README.md", "start_line": 1}, "c2"),
        _tool_message(
            "read_file",
            "c2",
            ToolResult(success=True, content="readme", metadata={"path": "README.md"}),
        ),
    ]
    still = evaluate_tool_call(tuple(after_other_path), "validate_patch", arguments)
    assert still.allowed is False
    assert still.error_code == RECOVERY_READ_REQUIRED

    after_read = list(messages) + [
        _assistant("read_file", {"path": "src/auth.py", "start_line": 1}, "c3"),
        _tool_message(
            "read_file",
            "c3",
            ToolResult(success=True, content="code", metadata={"path": "src/auth.py"}),
        ),
    ]
    allowed = evaluate_tool_call(tuple(after_read), "validate_patch", arguments)
    assert allowed.allowed is True
    assert allowed.error_code is None


def test_parse_blocks_identical_validate_payload_only() -> None:
    arguments = _changes()
    messages = _transcript(
        "validate_patch",
        arguments,
        ToolResult(success=False, content="bad diff", error_code="PATCH_PARSE_ERROR"),
    )
    blocked = evaluate_tool_call(messages, "validate_patch", arguments)
    assert blocked.allowed is False
    assert blocked.error_code == RECOVERY_IDENTICAL_PAYLOAD_BLOCKED

    different = evaluate_tool_call(messages, "validate_patch", _changes(new_line="return 1"))
    assert different.allowed is True

    also_diff = evaluate_tool_call(messages, "validate_patch", _diff_args())
    assert also_diff.allowed is True


def test_hard_stop_blocks_identical_tool_payload_not_the_run() -> None:
    arguments = _changes(path="secret.env")
    messages = _transcript(
        "validate_patch",
        arguments,
        ToolResult(success=False, content="rejected", error_code="PATCH_PATH_REJECTED"),
    )
    blocked = evaluate_tool_call(messages, "validate_patch", arguments)
    assert blocked.allowed is False
    assert blocked.error_code == RECOVERY_RETRY_BLOCKED

    other = evaluate_tool_call(messages, "validate_patch", _changes(path="src/auth.py"))
    assert other.allowed is True

    policy_args = {"path": "src/auth.py"}
    policy_messages = _transcript(
        "read_file",
        policy_args,
        ToolResult(success=False, content="denied", error_code="POLICY_DENIED"),
    )
    policy_blocked = evaluate_tool_call(policy_messages, "read_file", policy_args)
    assert policy_blocked.allowed is False
    assert policy_blocked.error_code == RECOVERY_RETRY_BLOCKED


def test_command_feedback_blocks_same_argv_until_artifact_read() -> None:
    arguments = {
        "gate_id": "manifest.python.pytest",
        "target": "tests",
        "flags": ["-q"],
        "cwd": ".",
    }
    messages = _transcript("run_command", arguments, _failed_command_result())
    blocked = evaluate_tool_call(messages, "run_command", arguments)
    assert blocked.allowed is False
    assert blocked.error_code == RECOVERY_FEEDBACK_READ_REQUIRED

    other_argv = evaluate_tool_call(
        messages,
        "run_command",
        {"gate_id": "manifest.python.mypy", "target": "src", "cwd": "."},
    )
    assert other_argv.allowed is True

    after_read = list(messages) + [
        _assistant(
            "read_command_output",
            {"artifact_id": ARTIFACT_ID, "selector": {"stream": "stdout"}, "reason": "tests"},
            "c2",
        ),
        _tool_message(
            "read_command_output",
            "c2",
            ToolResult(
                success=True,
                content="failure slice",
                metadata={"artifact_id": ARTIFACT_ID},
            ),
        ),
    ]
    allowed = evaluate_tool_call(tuple(after_read), "run_command", arguments)
    assert allowed.allowed is True


def test_command_feedback_uses_metadata_not_tool_success() -> None:
    arguments = {
        "gate_id": "manifest.python.pytest",
        "target": "tests",
        "flags": ["-q"],
    }
    result = _failed_command_result(failed=2, exit_code=1)
    assert result.success is True
    messages = _transcript("run_command", arguments, result)
    blocked = evaluate_tool_call(messages, "run_command", arguments)
    assert blocked.allowed is False
    assert blocked.error_code == RECOVERY_FEEDBACK_READ_REQUIRED


def test_awaiting_approval_forbids_model_complete() -> None:
    messages = _transcript(
        "apply_patch",
        {"patch_id": PATCH_ID},
        ToolResult(success=False, content="approval is pending", error_code="APPROVAL_REQUIRED"),
    )
    assert should_request_model(messages) is False
    assert should_request_model((), run_status="waiting_approval") is False
    assert should_request_model(()) is True


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
        config=AgentConfig(max_steps=8),
        tool_executor=executor,
    )
    return loop, provider, sink


def _failed_codes(sink: InMemoryEventSink) -> list[str | None]:
    codes: list[str | None] = []
    for event in sink.events:
        if event.event_type != "tool.call.failed":
            continue
        payload = event.payload
        result = payload.get("result") if isinstance(payload, Mapping) else None
        if isinstance(result, Mapping):
            code = result.get("error_code")
            codes.append(str(code) if code is not None else None)
    return codes


@pytest.mark.asyncio
async def test_loop_stale_does_not_call_executor_until_read_file() -> None:
    apply_args = {"patch_id": PATCH_ID}
    stale_apply = ToolResult(
        success=False,
        content="baseline drifted",
        error_code="PATCH_BASELINE_MISMATCH",
        metadata={"files": [{"path": "src/auth.py"}]},
    )
    executor = ScriptedExecutor(
        [
            stale_apply,
            ToolResult(success=True, content="file body", metadata={"path": "src/auth.py"}),
            ToolResult(success=True, content="applied"),
        ],
    )
    loop, provider, sink = _loop(
        [
            ModelResponse(
                tool_calls=(ToolCall(id="a1", name="apply_patch", arguments=apply_args),),
            ),
            ModelResponse(
                tool_calls=(ToolCall(id="a2", name="apply_patch", arguments=apply_args),),
            ),
            ModelResponse(
                tool_calls=(
                    ToolCall(
                        id="r1",
                        name="read_file",
                        arguments={"path": "src/auth.py", "start_line": 1},
                    ),
                ),
            ),
            ModelResponse(
                tool_calls=(ToolCall(id="a3", name="apply_patch", arguments=apply_args),),
            ),
            ModelResponse(content="done"),
        ],
        executor,
        [registered_test_tool(ApplyPatchTool(), operations=("apply",))],
    )
    result = await loop.run(FIXTURE_ROOT, "fix auth")
    assert result.answer == "done"
    assert executor.calls == ["apply_patch", "read_file", "apply_patch"]
    assert RECOVERY_READ_REQUIRED in _failed_codes(sink)
    assert len(provider.requests) == 5


@pytest.mark.asyncio
async def test_loop_parse_blocks_identical_payload_without_executor() -> None:
    apply_args = {"patch_id": PATCH_ID}
    executor = ScriptedExecutor(
        [
            ToolResult(success=False, content="bad args", error_code="PATCH_INVALID_ARGUMENTS"),
            ToolResult(success=True, content="applied"),
        ],
    )
    other_args = {"patch_id": "d" * 64}
    loop, _, sink = _loop(
        [
            ModelResponse(
                tool_calls=(ToolCall(id="a1", name="apply_patch", arguments=apply_args),),
            ),
            ModelResponse(
                tool_calls=(ToolCall(id="a2", name="apply_patch", arguments=apply_args),),
            ),
            ModelResponse(
                tool_calls=(ToolCall(id="a3", name="apply_patch", arguments=other_args),),
            ),
            ModelResponse(content="ok"),
        ],
        executor,
        [registered_test_tool(ApplyPatchTool(), operations=("apply",))],
    )
    result = await loop.run(FIXTURE_ROOT, "fix auth")
    assert result.answer == "ok"
    assert executor.calls == ["apply_patch", "apply_patch"]
    assert RECOVERY_IDENTICAL_PAYLOAD_BLOCKED in _failed_codes(sink)


@pytest.mark.asyncio
async def test_loop_approval_required_does_not_call_complete_again() -> None:
    executor = ScriptedExecutor(
        [
            ToolResult(
                success=False,
                content="approval is pending",
                error_code="APPROVAL_REQUIRED",
            ),
        ],
    )
    loop, provider, _sink = _loop(
        [
            ModelResponse(
                tool_calls=(
                    ToolCall(id="a1", name="apply_patch", arguments={"patch_id": PATCH_ID}),
                ),
            ),
            ModelResponse(content="should not be requested"),
        ],
        executor,
        [registered_test_tool(ApplyPatchTool(), operations=("apply",))],
    )
    result = await loop.run(FIXTURE_ROOT, "apply it")
    assert len(provider.requests) == 1
    assert result.answer
    assert executor.calls == ["apply_patch"]


@pytest.mark.asyncio
async def test_loop_command_feedback_blocks_identical_argv() -> None:
    argv_args = {
        "gate_id": "manifest.python.pytest",
        "target": "tests",
        "flags": ["-q"],
        "cwd": ".",
    }
    executor = ScriptedExecutor(
        [
            _failed_command_result(),
            ToolResult(
                success=True,
                content="slice",
                metadata={"artifact_id": ARTIFACT_ID},
            ),
            ToolResult(success=True, content="pass", metadata={"exit_code": 0, "failed": 0}),
        ],
    )
    loop, _, sink = _loop(
        [
            ModelResponse(
                tool_calls=(ToolCall(id="c1", name="run_command", arguments=argv_args),),
            ),
            ModelResponse(
                tool_calls=(ToolCall(id="c2", name="run_command", arguments=argv_args),),
            ),
            ModelResponse(
                tool_calls=(
                    ToolCall(
                        id="c3",
                        name="read_command_output",
                        arguments={
                            "artifact_id": ARTIFACT_ID,
                            "selector": {"stream": "stdout", "tail_lines": 40},
                            "reason": "read failures",
                        },
                    ),
                ),
            ),
            ModelResponse(
                tool_calls=(ToolCall(id="c4", name="run_command", arguments=argv_args),),
            ),
            ModelResponse(content="green"),
        ],
        executor,
        [
            registered_test_tool(RunCommandTool(), operations=("execute",)),
            registered_test_tool(ReadCommandOutputTool()),
            registered_test_tool(SearchCommandOutputTool()),
        ],
    )
    result = await loop.run(FIXTURE_ROOT, "run tests")
    assert result.answer == "green"
    assert executor.calls == ["run_command", "read_command_output", "run_command"]
    assert RECOVERY_FEEDBACK_READ_REQUIRED in _failed_codes(sink)
