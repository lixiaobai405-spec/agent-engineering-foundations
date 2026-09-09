from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

from agent_foundations.domain.tool import RegisteredTool
from agent_foundations.runtime.tool_execution import DirectToolCallExecutor, ToolExecutionContext
from agent_foundations.security.models import ResourceScope, SideEffectKind
from agent_foundations.tools.patch.parser import PatchParseError, parse_unified_diff


def _api() -> tuple[Any, ...]:
    assert importlib.util.find_spec("agent_foundations.tools.patch.apply_patch") is not None, (
        "Task 15 controlled apply_patch Tool is missing"
    )
    from agent_foundations.tools.patch.apply_patch import (
        APPLY_PATCH_MANIFEST,
        APPLY_PATCH_TOOL_NAME,
        ApplyPatchTool,
        build_apply_patch_registered_tool,
        resolve_apply_patch_resource,
    )

    return (
        APPLY_PATCH_TOOL_NAME,
        APPLY_PATCH_MANIFEST,
        ApplyPatchTool,
        build_apply_patch_registered_tool,
        resolve_apply_patch_resource,
    )


def test_apply_patch_contract_and_metadata_are_exact() -> None:
    name, manifest, Tool, registered_builder, resolver = _api()
    tool = Tool()
    patch_id = "a" * 64

    assert name == "apply_patch"
    assert tool.input_schema() == {
        "type": "object",
        "properties": {"patch_id": {"type": "string", "pattern": "^[a-f0-9]{64}$"}},
        "required": ["patch_id"],
        "additionalProperties": False,
    }
    assert manifest.name == name
    assert manifest.resource_kind == "project_path"
    assert manifest.operations == ("apply",)
    assert manifest.side_effect is SideEffectKind.PROJECT_WRITE
    assert manifest.sandbox_required is True
    resource = resolver({"patch_id": patch_id})
    assert resource.scope is ResourceScope.PROJECT_INTERNAL
    assert resource.identifier == f"patch:{patch_id}"
    registered = registered_builder()
    assert isinstance(registered, RegisteredTool)
    assert registered.tool.name == name
    assert registered.manifest == manifest


def test_cli_registry_requires_explicit_apply_patch_opt_in(tmp_path: Path) -> None:
    from agent_foundations.cli.main import build_tool_registry

    default_names = {entry.tool.name for entry in build_tool_registry(tmp_path).registered_tools()}
    controlled_names = {
        entry.tool.name
        for entry in build_tool_registry(
            tmp_path,
            include_apply_patch=True,
        ).registered_tools()
    }

    assert "apply_patch" not in default_names
    assert "apply_patch" in controlled_names


@pytest.mark.asyncio
async def test_direct_executor_cannot_execute_apply_patch(tmp_path: Path) -> None:
    _name, _manifest, Tool, *_ = _api()
    tool = Tool()
    context = ToolExecutionContext(
        session_id="11111111-1111-4111-8111-111111111111",
        root=tmp_path,
        tool_call_id="call-direct",
        tool_name=tool.name,
    )

    result = await DirectToolCallExecutor().execute(tool, {"patch_id": "a" * 64}, context)

    assert result.success is False
    assert result.error_code == "CONTROLLED_EXECUTION_REQUIRED"


@pytest.mark.asyncio
async def test_tool_itself_never_writes_without_controlled_context(tmp_path: Path) -> None:
    _name, _manifest, Tool, *_ = _api()
    target = tmp_path / "sentinel.txt"
    target.write_text("before", encoding="utf-8")

    result = await Tool().execute({"patch_id": "a" * 64})

    assert result.success is False
    assert result.error_code == "CONTROLLED_EXECUTION_REQUIRED"
    assert target.read_text(encoding="utf-8") == "before"


@pytest.mark.parametrize(
    "diff",
    [
        """diff --git a/a.txt b/a.txt
deleted file mode 100644
--- a/a.txt
+++ /dev/null
""",
        """diff --git a/a.txt b/b.txt
similarity index 100%
rename from a.txt
rename to b.txt
--- a/a.txt
+++ b/b.txt
@@ -1 +1 @@
-a
+a
""",
    ],
)
def test_apply_patch_input_rejects_delete_and_rename(diff: str) -> None:
    with pytest.raises(PatchParseError):
        parse_unified_diff(diff)
