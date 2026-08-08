from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from agent_foundations.domain.tool import Tool, ToolResult


@dataclass(frozen=True)
class ToolExecutionContext:
    session_id: str
    root: Path
    tool_call_id: str
    tool_name: str


@runtime_checkable
class ToolCallExecutor(Protocol):
    async def execute(
        self,
        tool: Tool,
        arguments: dict[str, Any],
        context: ToolExecutionContext,
    ) -> ToolResult: ...


class DirectToolCallExecutor:
    async def execute(
        self,
        tool: Tool,
        arguments: dict[str, Any],
        context: ToolExecutionContext,
    ) -> ToolResult:
        return await tool.execute(arguments)
