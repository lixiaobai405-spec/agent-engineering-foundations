from typing import Any

import pytest

from agent_foundations.domain.errors import InvalidToolArgumentsError, UnknownToolError
from agent_foundations.domain.tool import ToolResult
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
