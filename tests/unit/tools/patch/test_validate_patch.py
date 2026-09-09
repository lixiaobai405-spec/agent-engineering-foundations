from __future__ import annotations

import importlib.util

import pytest

from agent_foundations.runtime.tool_execution import DirectToolCallExecutor


def _require_tool() -> None:
    assert importlib.util.find_spec("agent_foundations.tools.patch.validate_patch") is not None


@pytest.mark.asyncio
async def test_validate_patch_tool_name() -> None:
    _require_tool()
    from agent_foundations.tools.patch.validate_patch import ValidatePatchTool

    tool = ValidatePatchTool()
    assert tool.name == "validate_patch"


@pytest.mark.asyncio
async def test_direct_call_is_fail_closed() -> None:
    _require_tool()
    from agent_foundations.tools.patch.validate_patch import ValidatePatchTool

    tool = ValidatePatchTool()
    result = await DirectToolCallExecutor().execute(
        tool,
        {"diff": "diff", "baselines": []},
        __import__(
            "agent_foundations.runtime.tool_execution",
            fromlist=["ToolExecutionContext"],
        ).ToolExecutionContext(
            session_id="22222222-2222-4222-8222-222222222222",
            root=__import__("pathlib").Path("."),
            tool_call_id="c1",
            tool_name="validate_patch",
        ),
    )
    assert not result.success
    assert result.error_code == "PATCH_CONTEXT_REQUIRED"


def test_validate_patch_description_prefers_changes_from_read_file() -> None:
    _require_tool()
    from agent_foundations.tools.patch.validate_patch import ValidatePatchTool

    description = ValidatePatchTool().description
    assert "Prefer changes with expected_sha256 from read_file" in description
    assert "Runtime compiles unified diff" in description
    assert "The diff+baselines path remains valid" in description
    assert "Do not guess hashes" in description


def test_validate_patch_schema_oneof_and_expected_sha256_unchanged() -> None:
    _require_tool()
    from agent_foundations.tools.patch.validate_patch import ValidatePatchTool

    schema = ValidatePatchTool().input_schema()
    assert schema["oneOf"] == [
        {
            "required": ["diff", "baselines"],
            "not": {"required": ["changes"]},
        },
        {
            "required": ["changes"],
            "not": {"anyOf": [{"required": ["diff"]}, {"required": ["baselines"]}]},
        },
    ]
    change_items = schema["properties"]["changes"]["items"]
    assert change_items["required"] == [
        "path",
        "expected_sha256",
        "start_line",
        "old_lines",
        "new_lines",
    ]
    assert change_items["properties"]["expected_sha256"]["pattern"] == r"^[a-f0-9]{64}$"
    assert "diff" in schema["properties"]
    assert "baselines" in schema["properties"]
    assert "changes" in schema["properties"]
