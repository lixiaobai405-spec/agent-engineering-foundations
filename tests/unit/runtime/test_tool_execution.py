from dataclasses import is_dataclass, replace
from pathlib import Path
from typing import Any

import pytest

from agent_foundations.domain.tool import ToolResult
from agent_foundations.runtime.tool_execution import (
    DirectToolCallExecutor,
    ToolCallExecutor,
    ToolExecutionContext,
)

SESSION_ID = "22222222-2222-4222-8222-222222222222"
FIXTURE_ROOT = Path("tests/fixtures/sample_project").resolve()


def test_tool_execution_context_is_frozen_dataclass() -> None:
    assert is_dataclass(ToolExecutionContext)
    context = ToolExecutionContext(
        session_id=SESSION_ID,
        root=FIXTURE_ROOT,
        tool_call_id="call-1",
        tool_name="read_file",
    )
    assert context.session_id == SESSION_ID
    assert context.root == FIXTURE_ROOT
    assert context.tool_call_id == "call-1"
    assert context.tool_name == "read_file"
    updated = replace(context, tool_name="write_file")
    assert updated.tool_name == "write_file"
    assert context.tool_name == "read_file"


def test_tool_call_executor_is_runtime_checkable_protocol() -> None:
    executor = DirectToolCallExecutor()
    assert isinstance(executor, ToolCallExecutor)


class RecordingTool:
    name = "record"
    description = "Record execute arguments."

    def __init__(self) -> None:
        self.received_arguments: dict[str, Any] | None = None

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        self.received_arguments = arguments
        return ToolResult(success=True, content="recorded")


@pytest.mark.asyncio
async def test_direct_tool_call_executor_delegates_to_tool() -> None:
    tool = RecordingTool()
    executor = DirectToolCallExecutor()
    context = ToolExecutionContext(
        session_id=SESSION_ID,
        root=FIXTURE_ROOT,
        tool_call_id="call-1",
        tool_name=tool.name,
    )
    arguments = {"path": "src"}

    result = await executor.execute(tool, arguments, context)

    assert tool.received_arguments == arguments
    assert result.success is True
    assert result.content == "recorded"
    assert result == ToolResult(success=True, content="recorded")
