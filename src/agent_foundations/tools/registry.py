from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any, cast

from jsonschema import ValidationError, validate

from agent_foundations.domain._freeze import to_json_value
from agent_foundations.domain.errors import InvalidToolArgumentsError, UnknownToolError
from agent_foundations.domain.tool import (
    RegisteredTool,
    Tool,
    ToolDefinition,
    ToolResult,
)
from agent_foundations.planning.tools import build_planning_registered_tools
from agent_foundations.security.models import PolicyResource, ToolManifest
from agent_foundations.security.resources import (
    resolve_list_directory_resource,
    resolve_read_file_resource,
    resolve_search_text_resource,
)
from agent_foundations.tools.filesystem.list_directory import (
    LIST_DIRECTORY_MANIFEST,
    ListDirectoryTool,
)
from agent_foundations.tools.filesystem.path_policy import PathPolicy
from agent_foundations.tools.filesystem.read_file import READ_FILE_MANIFEST, ReadFileTool
from agent_foundations.tools.filesystem.search_text import (
    SEARCH_TEXT_MANIFEST,
    SearchTextTool,
)
from agent_foundations.tools.patch.validate_patch import (
    VALIDATE_PATCH_MANIFEST,
    ValidatePatchTool,
)


def _validate_registered(entry: RegisteredTool) -> RegisteredTool:
    if not isinstance(entry.manifest, ToolManifest):
        raise TypeError("RegisteredTool manifest must be a ToolManifest")
    if entry.tool.name != entry.manifest.name:
        raise ValueError(
            f"manifest.name must match tool.name: {entry.manifest.name!r} != {entry.tool.name!r}",
        )
    return entry


class ToolRegistry:
    def __init__(self, tools: Iterable[RegisteredTool]) -> None:
        self._tools: dict[str, RegisteredTool] = {}
        for entry in tools:
            if not isinstance(entry, RegisteredTool):
                raise TypeError("ToolRegistry requires RegisteredTool entries with manifest")
            validated = _validate_registered(entry)
            if validated.tool.name in self._tools:
                raise ValueError(f"duplicate tool name: {validated.tool.name}")
            self._tools[validated.tool.name] = validated

    def registered_tools(self) -> tuple[RegisteredTool, ...]:
        return tuple(self._tools[name] for name in sorted(self._tools))

    def get_registered(self, name: str) -> RegisteredTool:
        entry = self._tools.get(name)
        if entry is None:
            available = ", ".join(sorted(self._tools))
            raise UnknownToolError(f"unknown tool '{name}'; available tools: {available}")
        return entry

    def definitions(self) -> tuple[ToolDefinition, ...]:
        return tuple(
            ToolDefinition(
                name=entry.tool.name,
                description=entry.tool.description,
                parameters=entry.tool.input_schema(),
            )
            for entry in self._tools.values()
        )

    def resolve_resource(self, name: str, arguments: Mapping[str, Any]) -> PolicyResource:
        tool, normalized = self.validate_call(name, arguments)
        del tool
        entry = self.get_registered(name)
        return entry.resource_resolver(normalized)

    def validate_call(
        self,
        name: str,
        arguments: Mapping[str, Any],
    ) -> tuple[Tool, dict[str, Any]]:
        entry = self.get_registered(name)
        normalized = cast(dict[str, Any], to_json_value(arguments))
        try:
            validate(instance=normalized, schema=entry.tool.input_schema())
        except ValidationError as exc:
            raise InvalidToolArgumentsError(exc.message) from exc
        return entry.tool, normalized

    async def execute(
        self,
        name: str,
        arguments: Mapping[str, Any],
    ) -> ToolResult:
        tool, normalized = self.validate_call(name, arguments)
        return await tool.execute(normalized)


def build_readonly_filesystem_registered_tools(
    policy: PathPolicy,
) -> tuple[RegisteredTool, ...]:
    return (
        RegisteredTool(
            ListDirectoryTool(policy),
            LIST_DIRECTORY_MANIFEST,
            lambda arguments: resolve_list_directory_resource(arguments, policy),
        ),
        RegisteredTool(
            ReadFileTool(policy),
            READ_FILE_MANIFEST,
            lambda arguments: resolve_read_file_resource(arguments, policy),
        ),
        RegisteredTool(
            SearchTextTool(policy),
            SEARCH_TEXT_MANIFEST,
            lambda arguments: resolve_search_text_resource(arguments, policy),
        ),
    )


def build_standard_registered_tools(
    policy: PathPolicy,
    *,
    controller: Any | None = None,
    journal: Any | None = None,
    include_validate_patch: bool = False,
) -> tuple[RegisteredTool, ...]:
    tools: list[RegisteredTool] = list(build_readonly_filesystem_registered_tools(policy))
    if controller is not None and journal is not None:
        tools.extend(build_planning_registered_tools(controller, journal))
    if include_validate_patch:
        tools.append(
            RegisteredTool(
                ValidatePatchTool(),
                VALIDATE_PATCH_MANIFEST,
                _validate_patch_resolver(),
            ),
        )
    return tuple(tools)


def build_replay_registered_tools(
    policy: PathPolicy,
    *,
    planning_required: bool,
    controller: Any,
    journal: Any,
) -> tuple[RegisteredTool, ...]:
    registered = list(build_readonly_filesystem_registered_tools(policy))
    if planning_required:
        registered.extend(build_planning_registered_tools(controller, journal))
    return tuple(registered)


def _validate_patch_resolver() -> Callable[[Mapping[str, Any]], PolicyResource]:
    from agent_foundations.security.resources import resolve_validate_patch_resource

    return resolve_validate_patch_resource
