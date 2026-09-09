from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

from agent_foundations.domain.tool import ToolResult
from agent_foundations.runtime.tool_execution import DirectToolCallExecutor, ToolExecutionContext
from agent_foundations.security.models import SideEffectKind


def _require_read() -> Any:
    try:
        spec = importlib.util.find_spec("agent_foundations.tools.command.read_output")
    except ModuleNotFoundError:
        spec = None
    assert spec is not None, "read_command_output tool is missing"
    from agent_foundations.tools.command.read_output import (
        READ_COMMAND_OUTPUT_MANIFEST,
        ReadCommandOutputTool,
        build_read_command_output_registered_tool,
    )

    return (
        READ_COMMAND_OUTPUT_MANIFEST,
        ReadCommandOutputTool,
        build_read_command_output_registered_tool,
    )


def _require_search() -> Any:
    try:
        spec = importlib.util.find_spec("agent_foundations.tools.command.search_output")
    except ModuleNotFoundError:
        spec = None
    assert spec is not None, "search_command_output tool is missing"
    from agent_foundations.tools.command.search_output import (
        SEARCH_COMMAND_OUTPUT_MANIFEST,
        SearchCommandOutputTool,
        build_search_command_output_registered_tool,
    )

    return (
        SEARCH_COMMAND_OUTPUT_MANIFEST,
        SearchCommandOutputTool,
        build_search_command_output_registered_tool,
    )


def test_read_and_search_manifest_contracts() -> None:
    read_manifest, read_cls, read_builder = _require_read()
    search_manifest, search_cls, search_builder = _require_search()
    assert read_manifest.name == "read_command_output"
    assert search_manifest.name == "search_command_output"
    assert read_manifest.resource_kind == "command_artifact"
    assert search_manifest.resource_kind == "command_artifact"
    assert read_manifest.sandbox_required is False
    assert search_manifest.sandbox_required is False
    assert read_manifest.side_effect is SideEffectKind.NONE
    assert search_manifest.side_effect is SideEffectKind.NONE
    assert read_manifest.operations == ("read",)
    assert search_manifest.operations == ("search",)
    assert read_builder().tool.name == "read_command_output"
    assert search_builder().tool.name == "search_command_output"
    assert read_cls().name == "read_command_output"


def test_read_command_output_selector_schema_describes_three_shapes() -> None:
    _manifest, read_cls, _builder = _require_read()
    schema = read_cls().input_schema()
    assert schema["type"] == "object"
    assert schema["required"] == ["artifact_id", "selector", "reason"]
    assert schema["additionalProperties"] is False
    selector = schema["properties"]["selector"]
    assert selector != {"type": "object"}
    variants = selector.get("oneOf")
    assert isinstance(variants, list)
    assert len(variants) == 3
    dumped = str(variants)
    assert "diagnostic_id" in dumped
    assert "tail_lines" in dumped
    assert "start_line" in dumped
    assert "line_count" in dumped
    description = read_cls().description
    assert "failing run_command" in description
    assert "CommandFeedback.artifact_id" in description
    assert "diagnostic_id" in description
    assert "tail_lines" in description
    assert "start_line" in description
    assert "line_count" in description


@pytest.mark.asyncio
async def test_direct_executor_still_blocks_patch_and_command(tmp_path: Path) -> None:
    _require_read()
    from agent_foundations.tools.command.run_command import RunCommandTool
    from agent_foundations.tools.patch.apply_patch import ApplyPatchTool

    executor = DirectToolCallExecutor()
    context = ToolExecutionContext(
        session_id="11111111-1111-4111-8111-111111111111",
        root=tmp_path,
        tool_call_id="call-direct",
        tool_name="run_command",
    )
    blocked_run = await executor.execute(
        RunCommandTool(),
        {"argv": ["python", "-m", "pytest"]},
        context,
    )
    blocked_patch = await executor.execute(ApplyPatchTool(), {"patch_id": "x"}, context)
    assert blocked_run.error_code == "CONTROLLED_EXECUTION_REQUIRED"
    assert blocked_patch.error_code == "CONTROLLED_EXECUTION_REQUIRED"
    read_cls = _require_read()[1]
    read_result = await read_cls().execute(
        {
            "artifact_id": "coa_AAAAAAAAAAAAAAAAAAAAAA",
            "selector": {"stream": "stdout", "tail_lines": 2},
            "reason": "inspect parser gap",
        }
    )
    assert isinstance(read_result, ToolResult)
    assert read_result.success is False
    assert read_result.error_code == "CONTROLLED_EXECUTION_REQUIRED"
    content = (read_result.content or "").lower()
    assert "coa_" not in (read_result.content or "") or "artifacts" not in content


def test_policy_allowlist_includes_output_tools_for_command_profiles() -> None:
    _require_read()
    from agent_foundations.security.models import (
        PermissionProfileName,
        default_allowed_tools,
    )

    readonly = default_allowed_tools(PermissionProfileName.PROJECT_READ_ONLY)
    assert "run_command" not in readonly
    assert "read_command_output" not in readonly
    assert "search_command_output" not in readonly
    for profile in (
        PermissionProfileName.ASK_ALWAYS,
        PermissionProfileName.RISK_BASED,
        PermissionProfileName.PROJECT_FULL_ACCESS,
    ):
        allowed = default_allowed_tools(profile)
        assert "run_command" in allowed
        assert "read_command_output" in allowed
        assert "search_command_output" in allowed
