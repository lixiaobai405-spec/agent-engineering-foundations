from collections.abc import Mapping
from typing import Annotated, Protocol, runtime_checkable

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    PlainValidator,
    WithJsonSchema,
    model_validator,
)

from agent_foundations.domain._freeze import (
    _serialize_frozen,
    _validate_freeze_dict_or_none,
)
from agent_foundations.domain._model import ValidatedCopyModel
from agent_foundations.domain.messages import Message
from agent_foundations.domain.tool import ToolCall, ToolDefinition


class TokenUsage(BaseModel):
    model_config = ConfigDict(frozen=True)

    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)


class ModelRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    messages: tuple[Message, ...]
    tools: tuple[ToolDefinition, ...] = ()


class ModelResponse(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True)

    content: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()
    usage: TokenUsage = TokenUsage()
    raw_response: Annotated[
        Mapping[str, object] | None,
        PlainValidator(_validate_freeze_dict_or_none),
        PlainSerializer(_serialize_frozen, return_type=dict[str, object]),
        WithJsonSchema({"anyOf": [{"type": "object"}, {"type": "null"}]}),
    ] = None

    @model_validator(mode="after")
    def require_content_or_tool_call(self) -> "ModelResponse":
        if not self.content and not self.tool_calls:
            raise ValueError("model response requires content or at least one tool call")
        return self


@runtime_checkable
class ModelProvider(Protocol):
    async def complete(self, request: ModelRequest) -> ModelResponse: ...
