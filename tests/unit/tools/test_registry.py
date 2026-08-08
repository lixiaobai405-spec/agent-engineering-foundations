from typing import Any

import pytest

from agent_foundations.domain.errors import InvalidToolArgumentsError, UnknownToolError
from agent_foundations.domain.tool import ToolCall, ToolResult
from agent_foundations.tools.registry import ToolRegistry


class EchoTool:
    name = "echo"
    description = "Echo a string"

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
            "additionalProperties": False,
        }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, content=str(arguments["text"]))


class CaptureTool(EchoTool):
    def __init__(self) -> None:
        self.received: dict[str, Any] | None = None

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "options": {
                    "type": "object",
                    "properties": {
                        "tags": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["tags"],
                    "additionalProperties": False,
                },
            },
            "required": ["text", "options"],
            "additionalProperties": False,
        }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        self.received = arguments
        return ToolResult(success=True, content=str(arguments["text"]))


def test_registry_exports_model_independent_definitions() -> None:
    registry = ToolRegistry([EchoTool()])
    assert registry.definitions()[0].name == "echo"


@pytest.mark.asyncio
async def test_registry_validates_before_execution() -> None:
    registry = ToolRegistry([EchoTool()])
    with pytest.raises(InvalidToolArgumentsError, match="'text' is a required property"):
        await registry.execute("echo", {})


@pytest.mark.asyncio
async def test_registry_rejects_unknown_tool() -> None:
    registry = ToolRegistry([EchoTool()])
    with pytest.raises(UnknownToolError, match="available tools: echo"):
        await registry.execute("missing", {})


@pytest.mark.asyncio
async def test_registry_thaws_tool_call_arguments_before_validation_and_execution() -> None:
    tool = CaptureTool()
    registry = ToolRegistry([tool])
    call = ToolCall(
        id="c1",
        name="echo",
        arguments={"text": "hello", "options": {"tags": ["a", "b"]}},
    )

    result = await registry.execute(call.name, call.arguments)

    assert result.success is True
    assert tool.received == {
        "text": "hello",
        "options": {"tags": ["a", "b"]},
    }
    assert isinstance(tool.received, dict)
    assert isinstance(tool.received["options"], dict)
    assert isinstance(tool.received["options"]["tags"], list)
