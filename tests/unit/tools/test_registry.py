from __future__ import annotations

import importlib.util
from typing import Any, cast

import pytest

from agent_foundations.domain.errors import InvalidToolArgumentsError, UnknownToolError
from agent_foundations.domain.tool import ToolCall, ToolResult


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


def _require_registry_contract() -> None:
    try:
        spec = importlib.util.find_spec("agent_foundations.security.models")
    except ModuleNotFoundError:
        spec = None
    assert spec is not None, "agent_foundations.security.models is not implemented"


def _echo_registered() -> Any:
    _require_registry_contract()
    from agent_foundations.domain.tool import RegisteredTool
    from agent_foundations.security.models import SideEffectKind, ToolManifest
    from agent_foundations.security.resources import resolve_echo_resource

    manifest = ToolManifest(
        name="echo",
        resource_kind="project_path",
        operations=("read",),
        side_effect=SideEffectKind.NONE,
        sandbox_required=False,
    )
    return RegisteredTool(EchoTool(), manifest, resolve_echo_resource)


def test_registry_exports_model_independent_definitions() -> None:
    from agent_foundations.tools.registry import ToolRegistry

    registry = ToolRegistry([_echo_registered()])
    assert registry.definitions()[0].name == "echo"


@pytest.mark.asyncio
async def test_registry_validates_before_execution() -> None:
    from agent_foundations.tools.registry import ToolRegistry

    registry = ToolRegistry([_echo_registered()])
    with pytest.raises(InvalidToolArgumentsError, match="'text' is a required property"):
        await registry.execute("echo", {})


@pytest.mark.asyncio
async def test_registry_rejects_unknown_tool() -> None:
    from agent_foundations.tools.registry import ToolRegistry

    registry = ToolRegistry([_echo_registered()])
    with pytest.raises(UnknownToolError, match="available tools: echo"):
        await registry.execute("missing", {})


@pytest.mark.asyncio
async def test_registry_thaws_tool_call_arguments_before_validation_and_execution() -> None:
    from agent_foundations.tools.registry import ToolRegistry

    tool = CaptureTool()
    _require_registry_contract()
    from agent_foundations.domain.tool import RegisteredTool
    from agent_foundations.security.models import SideEffectKind, ToolManifest
    from agent_foundations.security.resources import resolve_echo_resource

    manifest = ToolManifest(
        name="echo",
        resource_kind="project_path",
        operations=("read",),
        side_effect=SideEffectKind.NONE,
        sandbox_required=False,
    )
    registry = ToolRegistry([RegisteredTool(tool, manifest, resolve_echo_resource)])
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


def test_registry_rejects_tool_without_manifest() -> None:
    from agent_foundations.tools.registry import ToolRegistry

    with pytest.raises(TypeError, match="RegisteredTool"):
        ToolRegistry([cast(Any, EchoTool())])


def test_registry_rejects_name_only_pseudo_manifest() -> None:
    _require_registry_contract()
    from agent_foundations.domain.tool import RegisteredTool
    from agent_foundations.security.resources import resolve_echo_resource
    from agent_foundations.tools.registry import ToolRegistry

    class NameOnlyManifest:
        name = "echo"

    registered = RegisteredTool(
        EchoTool(),
        cast(Any, NameOnlyManifest()),
        resolve_echo_resource,
    )
    with pytest.raises(TypeError, match="ToolManifest"):
        ToolRegistry([registered])


def test_registry_rejects_manifest_name_mismatch() -> None:
    _require_registry_contract()
    from agent_foundations.domain.tool import RegisteredTool
    from agent_foundations.security.models import SideEffectKind, ToolManifest
    from agent_foundations.security.resources import resolve_echo_resource
    from agent_foundations.tools.registry import ToolRegistry

    manifest = ToolManifest(
        name="wrong",
        resource_kind="project_path",
        operations=("read",),
        side_effect=SideEffectKind.NONE,
        sandbox_required=False,
    )
    with pytest.raises(ValueError, match="manifest.name must match tool.name"):
        ToolRegistry([RegisteredTool(EchoTool(), manifest, resolve_echo_resource)])


def test_registry_rejects_duplicate_tool_names() -> None:
    from agent_foundations.tools.registry import ToolRegistry

    with pytest.raises(ValueError, match="duplicate tool name"):
        ToolRegistry([_echo_registered(), _echo_registered()])


def test_registry_resource_resolver_is_structured_without_raw_diff() -> None:
    _require_registry_contract()
    from agent_foundations.security.models import ResourceScope
    from agent_foundations.tools.registry import ToolRegistry

    registry = ToolRegistry([_echo_registered()])
    resource = registry.resolve_resource("echo", {"text": "hello"})
    assert resource.scope is ResourceScope.PROJECT_INTERNAL
    assert "diff" not in resource.identifier.lower()
    assert len(resource.identifier) <= 256
