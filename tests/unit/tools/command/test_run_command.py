from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

from agent_foundations.domain.tool import ToolResult
from agent_foundations.runtime.tool_execution import DirectToolCallExecutor, ToolExecutionContext
from agent_foundations.security.models import ResourceScope, SideEffectKind


def _require_run_command() -> Any:
    try:
        spec = importlib.util.find_spec("agent_foundations.tools.command.run_command")
    except ModuleNotFoundError:
        spec = None
    assert spec is not None, "run_command tool is missing"
    from agent_foundations.tools.command.run_command import (
        RUN_COMMAND_MANIFEST,
        RUN_COMMAND_TOOL_NAME,
        RunCommandTool,
        build_run_command_registered_tool,
        resolve_run_command_resource,
    )

    return (
        RUN_COMMAND_TOOL_NAME,
        RUN_COMMAND_MANIFEST,
        RunCommandTool,
        build_run_command_registered_tool,
        resolve_run_command_resource,
    )


def test_run_command_manifest_and_resource_contract() -> None:
    name, manifest, _tool, builder, resolve = _require_run_command()
    assert name == "run_command"
    assert manifest.name == "run_command"
    assert manifest.resource_kind == "sandbox_command"
    assert "run" in manifest.operations
    assert manifest.side_effect is SideEffectKind.PROCESS
    assert manifest.sandbox_required is True
    resource = resolve(
        {"gate_id": "manifest.python.pytest", "target": "tests", "cwd": "."},
    )
    assert resource.kind == "sandbox_command"
    assert resource.scope is ResourceScope.PROJECT_INTERNAL
    assert resource.identifier.startswith("manifest.python.pytest")
    assert "tests" in resource.identifier
    argv_bypass = resolve(
        {
            "argv": ["python", "-c", "pwn"],
            "gate_id": "manifest.python.pytest",
            "target": "tests",
        },
    )
    assert "pwn" not in argv_bypass.identifier
    assert argv_bypass.identifier.startswith("manifest.python.pytest")
    registered = builder()
    assert registered.tool.name == name
    assert registered.manifest == manifest


def test_cli_registry_requires_explicit_run_command_opt_in(tmp_path: Path) -> None:
    _require_run_command()
    from agent_foundations.cli.main import build_tool_registry

    default_names = {entry.tool.name for entry in build_tool_registry(tmp_path).registered_tools()}
    controlled_names = {
        entry.tool.name
        for entry in build_tool_registry(tmp_path, include_run_command=True).registered_tools()
    }
    assert "run_command" not in default_names
    assert "run_command" in controlled_names


@pytest.mark.asyncio
async def test_direct_executor_cannot_execute_run_command(tmp_path: Path) -> None:
    _name, _manifest, tool_cls, *_rest = _require_run_command()
    tool = tool_cls()
    result = await DirectToolCallExecutor().execute(
        tool,
        {"gate_id": "manifest.python.pytest", "target": "tests", "flags": ["-q"]},
        ToolExecutionContext(
            session_id="11111111-1111-4111-8111-111111111111",
            root=tmp_path,
            tool_call_id="call-direct",
            tool_name=tool.name,
        ),
    )
    assert result.success is False
    assert result.error_code == "CONTROLLED_EXECUTION_REQUIRED"
    assert isinstance(result, ToolResult)


def test_chat_services_register_command_tools_in_production_loop() -> None:
    _require_run_command()
    import inspect

    from agent_foundations.cli import main as cli_main

    source = inspect.getsource(cli_main.build_chat_services)
    assert "include_run_command" in source
    assert "include_command_output" in source
    assert "read_command_output" in source or "include_command_output" in source
    assert "Never claim" not in source
    from agent_foundations.runtime.tool_execution import DirectToolCallExecutor

    assert "apply_patch" in inspect.getsource(DirectToolCallExecutor.execute)
    assert "run_command" in inspect.getsource(DirectToolCallExecutor.execute)
