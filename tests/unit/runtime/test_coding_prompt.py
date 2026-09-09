from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path
from uuid import uuid4

import pytest

from agent_foundations.chat.models import PermissionMode
from agent_foundations.providers.fake import FakeModelProvider
from agent_foundations.runtime.agent import AgentConfig, PlanningMode
from agent_foundations.runtime.redaction import Redactor
from agent_foundations.runtime.sinks import JsonlEventSink
from agent_foundations.security.models import PermissionProfileName
from agent_foundations.tools.command.read_output import ReadCommandOutputTool
from agent_foundations.tools.command.run_command import RunCommandTool
from agent_foundations.tools.filesystem.read_file import ReadFileTool
from agent_foundations.tools.patch.validate_patch import ValidatePatchTool

LOCKED_CODING_PROMPT_SENTENCES = (
    "Before editing a file, call read_file.",
    "Use the sha256 returned by read_file; do not guess hashes.",
    "Prefer validate_patch with changes; do not hand-write complex unified diffs.",
    "Call run_command with gate_id from the command manifest; do not submit argv.",
    "Do not add extra npm arguments or use npm test.",
    "Do not retry POLICY_DENIED, PATCH_PATH_REJECTED, or the same denied action.",
    (
        "After a failing test, read CommandFeedback and call "
        "read_command_output before rerunning the same gate."
    ),
)

_READ_ONLY_DEFAULT_PROMPT = (
    "You are a read-only coding agent. Use only the supplied tools. "
    "Never claim to modify files, run commands, or access paths outside the project."
)


def test_agent_config_default_system_prompt_remains_read_only() -> None:
    assert AgentConfig().system_prompt == _READ_ONLY_DEFAULT_PROMPT


def test_controlled_coding_agent_prompt_constant_contains_locked_sentences() -> None:
    spec = importlib.util.find_spec("agent_foundations.runtime.coding_prompt")
    assert spec is not None
    from agent_foundations.runtime.coding_prompt import CONTROLLED_CODING_AGENT_PROMPT

    for sentence in LOCKED_CODING_PROMPT_SENTENCES:
        assert sentence in CONTROLLED_CODING_AGENT_PROMPT
    assert "Command argv must match the whitelist exactly" not in CONTROLLED_CODING_AGENT_PROMPT
    assert "before rerunning the same argv" not in CONTROLLED_CODING_AGENT_PROMPT


@pytest.mark.asyncio
async def test_chat_runtime_factory_uses_controlled_coding_prompt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent_foundations.cli import main

    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "README.md").write_text("# fixture\n", encoding="utf-8")
    monkeypatch.setenv("AGENT_API_KEY", "test-placeholder")
    monkeypatch.setenv("AGENT_MODEL", "test-model")
    monkeypatch.setattr(main, "build_provider", lambda: FakeModelProvider([]))

    services = main.build_chat_services(tmp_path)
    await services.repository.initialize()
    conversation = await services.repository.create_conversation(
        title="Coding prompt",
        project_root=project_root,
        permission_profile=PermissionProfileName.ASK_ALWAYS,
        permission_mode=PermissionMode.ASK_FOR_ACCESS,
    )
    executor = services.runner._tool_executor_factory(conversation, str(uuid4()))
    sink = JsonlEventSink(tmp_path / "traces", Redactor(project_root))
    loop = services.runner._runtime_factory(conversation, sink, executor)
    prompt = loop._config.system_prompt

    assert prompt != AgentConfig().system_prompt
    for sentence in LOCKED_CODING_PROMPT_SENTENCES:
        assert sentence in prompt
    assert "Use only the supplied tools." in prompt
    assert "apply_patch" in prompt
    assert "run_command" in prompt
    assert "git_status" in prompt
    assert "git_diff" in prompt
    assert "git_log" in prompt
    assert "set_plan" in prompt
    assert "planning is not required" in prompt
    assert loop._config.planning_mode is PlanningMode.DISABLED

    factory_source = inspect.getsource(services.runner._runtime_factory)
    assert "CONTROLLED_CODING_AGENT_PROMPT" in factory_source
    assert "PlanningMode.REQUIRED" not in factory_source

    spec = importlib.util.find_spec("agent_foundations.runtime.coding_prompt")
    assert spec is not None
    from agent_foundations.runtime.coding_prompt import CONTROLLED_CODING_AGENT_PROMPT

    assert prompt == CONTROLLED_CODING_AGENT_PROMPT


def test_read_file_description_names_full_file_digest_metadata() -> None:
    description = ReadFileTool.description
    for token in ("sha256", "size_bytes", "encoding", "truncated"):
        assert token in description
    assert "full-file digest" in description


def test_validate_patch_description_prefers_changes_and_forbids_guessing() -> None:
    description = ValidatePatchTool.description
    assert "Prefer changes with expected_sha256 from read_file" in description
    assert "Runtime compiles unified diff" in description
    assert "diff+baselines" in description
    assert "Do not guess hashes" in description


def test_run_command_description_requires_gate_id_not_argv() -> None:
    description = RunCommandTool.description
    assert "gate_id" in description
    assert "do not submit argv" in description


def test_read_command_output_description_follows_command_feedback() -> None:
    description = ReadCommandOutputTool.description
    assert "failing run_command" in description
    assert "CommandFeedback.artifact_id" in description
