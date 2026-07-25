import json
from collections.abc import Mapping
from typing import Any

import pytest
from pydantic import ValidationError

from agent_foundations.domain.messages import Message, Role
from agent_foundations.domain.model import ModelRequest, ModelResponse, TokenUsage
from agent_foundations.domain.tool import ToolCall, ToolDefinition, ToolResult

type JsonFieldModel = ToolCall | ToolDefinition | ToolResult | ModelResponse

JSON_FIELD_NAMES = ("arguments", "parameters", "metadata", "raw_response")
NON_FINITE_FLOATS = (
    pytest.param(float("nan"), id="nan"),
    pytest.param(float("inf"), id="positive-infinity"),
    pytest.param(float("-inf"), id="negative-infinity"),
)
FINITE_FLOATS = (0.0, -1.5, 1e20)


def _build_json_field_model(field_name: str, value: dict[str, Any]) -> JsonFieldModel:
    if field_name == "arguments":
        return ToolCall(id="c1", name="read", arguments=value)
    if field_name == "parameters":
        return ToolDefinition(name="read", description="Read a file", parameters=value)
    if field_name == "metadata":
        return ToolResult(success=True, content="ok", metadata=value)
    if field_name == "raw_response":
        return ModelResponse(content="ok", raw_response=value)
    raise AssertionError(f"unknown JSON field: {field_name}")


def _set_item(target: Any, key: str, value: Any) -> None:
    target[key] = value


def _append_item(target: Any, value: Any) -> None:
    target.append(value)


def test_message_preserves_tool_call_relationship() -> None:
    message = Message(
        role=Role.TOOL,
        content='{"entries": ["src"]}',
        name="list_directory",
        tool_call_id="call-1",
    )
    assert message.tool_call_id == "call-1"


def test_model_response_requires_content_or_tool_call() -> None:
    with pytest.raises(ValidationError):
        ModelResponse()


def test_request_contains_model_independent_tool_schema() -> None:
    tool = ToolDefinition(
        name="read_file",
        description="Read a UTF-8 text file",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
    )
    request = ModelRequest(
        messages=(Message(role=Role.USER, content="Inspect the project"),),
        tools=(tool,),
    )
    response = ModelResponse(
        tool_calls=(ToolCall(id="call-1", name="read_file", arguments={"path": "README.md"}),),
        usage=TokenUsage(input_tokens=10, output_tokens=5),
    )
    assert request.tools[0].name == response.tool_calls[0].name


# ---- deep immutability ----


def test_tool_call_arguments_are_deeply_immutable() -> None:
    call = ToolCall(id="c1", name="read", arguments={"path": "a.txt", "opts": {"dry": True}})

    # nested mapping mutation must fail
    args: Any = call.arguments
    with pytest.raises(TypeError):
        args["opts"]["dry"] = False

    # top-level mapping mutation must fail
    with pytest.raises(TypeError):
        args["path"] = "b.txt"


def test_tool_definition_parameters_are_deeply_immutable() -> None:
    td = ToolDefinition(
        name="search",
        description="search",
        parameters={
            "type": "object",
            "properties": {"q": {"type": "string"}},
        },
    )
    params: Any = td.parameters

    with pytest.raises(TypeError):
        params["properties"]["q"]["type"] = "number"


def test_tool_result_metadata_are_deeply_immutable() -> None:
    result = ToolResult(success=True, content="ok", metadata={"hits": [1, 2, 3]})

    # nested list mutation must fail (list is frozen to tuple)
    meta: Any = result.metadata
    with pytest.raises(AttributeError):
        meta["hits"].append(4)


def test_model_response_raw_response_is_deeply_immutable() -> None:
    response = ModelResponse(
        content="done",
        raw_response={"choices": [{"index": 0, "delta": {"role": "assistant"}}]},
    )
    assert response.raw_response is not None
    raw: Any = response.raw_response

    with pytest.raises(TypeError):
        raw["choices"][0]["delta"]["role"] = "system"


def test_original_input_mutation_does_not_affect_model() -> None:
    original_args: dict[str, Any] = {"path": "a.txt", "tags": ["urgent"]}
    call = ToolCall(id="c1", name="read", arguments=original_args)

    original_args["path"] = "b.txt"
    original_args["tags"].append("later")

    assert call.arguments["path"] == "a.txt"
    assert call.arguments["tags"] == ("urgent",)


def test_model_dump_json_produces_plain_json_structure() -> None:
    call = ToolCall(id="c1", name="read", arguments={"path": "a.txt"})
    result = ToolResult(success=True, content="ok", metadata={"pages": 3})

    dumped_call = call.model_dump(mode="json")
    dumped_result = result.model_dump(mode="json")

    assert isinstance(dumped_call["arguments"], dict)
    assert isinstance(dumped_result["metadata"], dict)
    assert dumped_call["arguments"]["path"] == "a.txt"
    assert dumped_result["metadata"]["pages"] == 3
    assert json.loads(call.model_dump_json())["arguments"] == {"path": "a.txt"}
    assert json.loads(result.model_dump_json())["metadata"] == {"pages": 3}


# ---- default metadata ----


def test_default_metadata_is_immutable() -> None:
    result = ToolResult(success=True, content="ok")

    assert isinstance(result.metadata, Mapping)
    meta: Any = result.metadata
    with pytest.raises(TypeError):
        meta["new"] = "value"


# ---- validated copy paths ----


def test_model_validate_freezes_input_data() -> None:
    """model_validate is the standard validated construction path."""
    call = ToolCall.model_validate(
        {"id": "c1", "name": "read", "arguments": {"path": "a.txt"}}
    )
    args: Any = call.arguments
    assert args["path"] == "a.txt"
    with pytest.raises(TypeError):
        args["path"] = "c.txt"


def test_model_validate_roundtrip_preserves_immutability() -> None:
    """model_validate(model_dump()) round-trip must re-freeze."""
    original = ToolCall(
        id="c1", name="read",
        arguments={"nested": {"key": "val"}},
    )
    dumped = original.model_dump(mode="json")
    reloaded = ToolCall.model_validate(dumped)

    reloaded_args: Any = reloaded.arguments
    with pytest.raises(TypeError):
        reloaded_args["nested"]["key"] = "changed"


def test_model_copy_deep_preserves_immutability() -> None:
    call = ToolCall(id="c1", name="read", arguments={"path": "a.txt", "opts": {"dry": True}})
    deep = call.model_copy(deep=True)

    assert deep is not call
    assert deep == call
    assert deep.arguments == call.arguments

    deep_args: Any = deep.arguments
    with pytest.raises(TypeError):
        deep_args["opts"]["dry"] = False


@pytest.mark.parametrize("field_name", JSON_FIELD_NAMES)
@pytest.mark.parametrize("deep", [False, True], ids=["shallow", "deep"])
def test_model_copy_update_revalidates_json_fields(field_name: str, deep: bool) -> None:
    original = _build_json_field_model(
        field_name,
        {"outer": {"items": [{"name": "original"}]}},
    )
    update_value: dict[str, Any] = {
        "outer": {
            "items": [
                {"name": "first"},
                {"name": "second"},
            ]
        }
    }

    copied = original.model_copy(update={field_name: update_value}, deep=deep)

    frozen: Any = getattr(copied, field_name)
    assert isinstance(frozen, Mapping)
    assert isinstance(frozen["outer"], Mapping)
    assert isinstance(frozen["outer"]["items"], tuple)
    assert isinstance(frozen["outer"]["items"][0], Mapping)

    with pytest.raises(TypeError):
        _set_item(frozen, "new", "value")
    with pytest.raises(TypeError):
        _set_item(frozen["outer"]["items"][0], "name", "changed")
    with pytest.raises(AttributeError):
        _append_item(frozen["outer"]["items"], {"name": "third"})

    original_value: Any = getattr(original, field_name)
    assert original_value["outer"]["items"][0]["name"] == "original"

    update_value["outer"]["items"][0]["name"] = "mutated input"
    assert frozen["outer"]["items"][0]["name"] == "first"


@pytest.mark.parametrize("field_name", JSON_FIELD_NAMES)
@pytest.mark.parametrize("deep", [False, True], ids=["shallow", "deep"])
def test_model_copy_update_rejects_non_json_values(field_name: str, deep: bool) -> None:
    original = _build_json_field_model(field_name, {"valid": True})

    with pytest.raises(ValidationError):
        original.model_copy(update={field_name: {"bad": {1, 2, 3}}}, deep=deep)


def test_model_copy_update_preserves_explicit_field_set() -> None:
    original = ToolResult(success=True, content="ok")

    copied = original.model_copy(update={"content": "changed"})

    assert copied.model_fields_set == {"success", "content"}
    assert copied.model_dump(exclude_unset=True) == {
        "success": True,
        "content": "changed",
    }


def test_model_copy_update_respects_shallow_and_deep_copy() -> None:
    usage = TokenUsage(input_tokens=1)
    original = ModelResponse(content="ok", usage=usage)

    shallow = original.model_copy(update={"content": "shallow"}, deep=False)
    deep = original.model_copy(update={"content": "deep"}, deep=True)

    assert original.usage is usage
    assert shallow.usage is usage
    assert deep.usage is not usage
    assert deep.usage == usage


# ---- finite JSON numbers ----


@pytest.mark.parametrize("field_name", JSON_FIELD_NAMES)
@pytest.mark.parametrize("value", NON_FINITE_FLOATS)
@pytest.mark.parametrize("nested", [False, True], ids=["top-level", "nested"])
def test_rejects_non_finite_float_during_validation(
    field_name: str,
    value: float,
    nested: bool,
) -> None:
    json_value = (
        {"outer": {"items": [{"number": value}]}}
        if nested
        else {"number": value}
    )

    with pytest.raises(ValidationError, match="finite JSON number"):
        _build_json_field_model(field_name, json_value)


@pytest.mark.parametrize("field_name", JSON_FIELD_NAMES)
@pytest.mark.parametrize("value", NON_FINITE_FLOATS)
def test_model_copy_update_rejects_non_finite_float(
    field_name: str,
    value: float,
) -> None:
    original = _build_json_field_model(field_name, {"number": 0.0})

    with pytest.raises(ValidationError, match="finite JSON number"):
        original.model_copy(
            update={
                field_name: {
                    "outer": {
                        "items": [{"number": value}],
                    }
                }
            }
        )


@pytest.mark.parametrize("field_name", JSON_FIELD_NAMES)
@pytest.mark.parametrize("value", FINITE_FLOATS)
def test_accepts_finite_float(field_name: str, value: float) -> None:
    model = _build_json_field_model(
        field_name,
        {"outer": {"items": [{"number": value}]}},
    )

    frozen: Any = getattr(model, field_name)
    assert frozen["outer"]["items"][0]["number"] == value


# ---- non-JSON value rejection ----


def test_rejects_tuple_in_arguments() -> None:
    with pytest.raises(ValidationError):
        ToolCall(id="c1", name="read", arguments={"items": (1, 2, 3)})


def test_rejects_set_in_metadata() -> None:
    with pytest.raises(ValidationError):
        ToolResult(success=True, content="ok", metadata={"tags": {"a", "b"}})


def test_rejects_bytes_in_raw_response() -> None:
    with pytest.raises(ValidationError):
        ModelResponse(content="ok", raw_response={"data": b"binary"})


def test_rejects_bytearray_in_value() -> None:
    with pytest.raises(ValidationError):
        ToolCall(id="c1", name="read", arguments={"buf": bytearray(b"data")})


# ---- JSON Schema ----


def test_model_json_schema_includes_object_type() -> None:
    tc_schema = ToolCall.model_json_schema()
    td_schema = ToolDefinition.model_json_schema()
    tr_schema = ToolResult.model_json_schema()
    mr_schema = ModelResponse.model_json_schema()

    assert tc_schema["properties"]["arguments"]["type"] == "object"
    assert td_schema["properties"]["parameters"]["type"] == "object"
    assert tr_schema["properties"]["metadata"]["type"] == "object"

    raw_schema = mr_schema["properties"]["raw_response"]
    assert raw_schema["anyOf"] == [{"type": "object"}, {"type": "null"}]


# ---- public API is Mapping, not dict ----


def test_public_fields_expose_mapping_not_dict() -> None:
    call = ToolCall(id="c1", name="read", arguments={"path": "a.txt"})
    td = ToolDefinition(
        name="s", description="d",
        parameters={"type": "object", "properties": {}, "additionalProperties": False},
    )
    result = ToolResult(success=True, content="ok")
    response = ModelResponse(content="ok", raw_response={"key": "val"})

    assert isinstance(call.arguments, Mapping)
    assert not isinstance(call.arguments, dict)

    assert isinstance(td.parameters, Mapping)
    assert not isinstance(td.parameters, dict)

    assert isinstance(result.metadata, Mapping)
    assert not isinstance(result.metadata, dict)

    assert response.raw_response is not None
    assert isinstance(response.raw_response, Mapping)
    assert not isinstance(response.raw_response, dict)
