from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from agent_foundations.domain.tool import ToolCall


class Role(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class Message(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: Role
    content: str | None = None
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()
