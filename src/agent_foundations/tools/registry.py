from collections.abc import Iterable
from typing import Any

from jsonschema import ValidationError, validate

from agent_foundations.domain.errors import InvalidToolArgumentsError, UnknownToolError
from agent_foundations.domain.tool import Tool, ToolDefinition, ToolResult


class ToolRegistry:
    def __init__(self, tools: Iterable[Tool]) -> None:
        self._tools: dict[str, Tool] = {}
        for tool in tools:
            if tool.name in self._tools:
                raise ValueError(f"duplicate tool name: {tool.name}")
            self._tools[tool.name] = tool

    def definitions(self) -> tuple[ToolDefinition, ...]:
        return tuple(
            ToolDefinition(
                name=tool.name,
                description=tool.description,
                parameters=tool.input_schema(),
            )
            for tool in self._tools.values()
        )

    def validate_call(self, name: str, arguments: dict[str, Any]) -> Tool:
        tool = self._tools.get(name)
        if tool is None:
            available = ", ".join(sorted(self._tools))
            raise UnknownToolError(f"unknown tool '{name}'; available tools: {available}")
        try:
            validate(instance=arguments, schema=tool.input_schema())
        except ValidationError as exc:
            raise InvalidToolArgumentsError(exc.message) from exc
        return tool

    async def execute(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        tool = self.validate_call(name, arguments)
        return await tool.execute(arguments)
