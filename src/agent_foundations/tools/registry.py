from collections.abc import Iterable, Mapping
from typing import Any, cast

from jsonschema import ValidationError, validate

from agent_foundations.domain._freeze import to_json_value
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

    def validate_call(
        self,
        name: str,
        arguments: Mapping[str, Any],
    ) -> tuple[Tool, dict[str, Any]]:
        tool = self._tools.get(name)
        if tool is None:
            available = ", ".join(sorted(self._tools))
            raise UnknownToolError(f"unknown tool '{name}'; available tools: {available}")
        normalized = cast(dict[str, Any], to_json_value(arguments))
        try:
            validate(instance=normalized, schema=tool.input_schema())
        except ValidationError as exc:
            raise InvalidToolArgumentsError(exc.message) from exc
        return tool, normalized

    async def execute(
        self,
        name: str,
        arguments: Mapping[str, Any],
    ) -> ToolResult:
        tool, normalized = self.validate_call(name, arguments)
        return await tool.execute(normalized)
