from collections.abc import Mapping
from typing import Annotated, Any, Protocol, runtime_checkable

from pydantic import (
    ConfigDict,
    Field,
    PlainSerializer,
    PlainValidator,
    WithJsonSchema,
)

from agent_foundations.domain._freeze import (
    FrozenJSON,
    _serialize_frozen,
    _validate_freeze_dict,
)
from agent_foundations.domain._model import ValidatedCopyModel


class ToolCall(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    arguments: Annotated[
        Mapping[str, Any],
        PlainValidator(_validate_freeze_dict),
        PlainSerializer(_serialize_frozen, return_type=dict[str, Any]),
        WithJsonSchema({"type": "object"}),
    ]


class ToolDefinition(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    parameters: Annotated[
        Mapping[str, Any],
        PlainValidator(_validate_freeze_dict),
        PlainSerializer(_serialize_frozen, return_type=dict[str, Any]),
        WithJsonSchema({"type": "object"}),
    ]


class ToolResult(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True)

    success: bool
    content: str
    error_code: str | None = None
    metadata: Annotated[
        Mapping[str, Any],
        PlainValidator(_validate_freeze_dict),
        PlainSerializer(_serialize_frozen, return_type=dict[str, Any]),
        WithJsonSchema({"type": "object"}),
    ] = Field(default_factory=lambda: FrozenJSON({}))


@runtime_checkable
class Tool(Protocol):
    name: str
    description: str

    def input_schema(self) -> dict[str, Any]: ...

    async def execute(self, arguments: dict[str, Any]) -> ToolResult: ...
