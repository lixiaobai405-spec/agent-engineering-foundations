from __future__ import annotations

import importlib.util
from typing import Any, Literal

import pytest

from agent_foundations.tools.command.run_command import RunCommandTool


def _expand_module() -> Any:
    spec = importlib.util.find_spec("agent_foundations.tools.command.gate_expand")
    assert spec is not None
    return importlib.import_module("agent_foundations.tools.command.gate_expand")


def _manifest() -> Any:
    from agent_foundations.execution.sandbox_manifest import (
        SandboxImageProvenance,
        SandboxManifest,
    )
    from agent_foundations.tools.command.config import default_project_command_manifest

    def provenance(profile: Literal["python", "node"]) -> SandboxImageProvenance:
        return SandboxImageProvenance(
            profile=profile,
            image_tag=f"agent-foundations-sandbox-{profile}:phase2d",
            base_repo_digest=f"{profile}@sha256:{'a' * 64}",
            lockfile_sha256="b" * 64,
            final_image_id=f"sha256:{'c' * 64}",
            final_repo_digest=(
                f"agent-foundations-sandbox-{profile}@sha256:{'d' * 64}"
            ),
        )

    return default_project_command_manifest(
        project_fingerprint="a" * 64,
        sandbox=SandboxManifest(
            python=provenance("python"),
            node=provenance("node"),
        ),
    )


def test_run_command_schema_requires_gate_id_and_forbids_argv() -> None:
    schema = RunCommandTool().input_schema()
    assert schema["required"] == ["gate_id"]
    assert schema["additionalProperties"] is False
    assert "argv" not in schema["properties"]
    assert set(schema["properties"]) == {
        "gate_id",
        "target",
        "flags",
        "cwd",
        "timeout_seconds",
    }


def test_exact_node_gate_expands_to_prefix_only() -> None:
    module = _expand_module()
    argv = module.expand_gate_argv(
        {"gate_id": "manifest.node.test-chat"},
        _manifest(),
    )
    assert argv == ("npm", "run", "test:chat")


def test_exact_gate_rejects_target_or_flags() -> None:
    module = _expand_module()
    with pytest.raises(module.GateExpandError) as rejected:
        module.expand_gate_argv(
            {"gate_id": "manifest.node.test-chat", "flags": ["--watch"]},
            _manifest(),
        )
    assert rejected.value.code == "COMMAND_GATE_ARGUMENTS_REJECTED"
    with pytest.raises(module.GateExpandError) as targeted:
        module.expand_gate_argv(
            {"gate_id": "manifest.node.test-chat", "target": "web/chat"},
            _manifest(),
        )
    assert targeted.value.code == "COMMAND_GATE_ARGUMENTS_REJECTED"


def test_pytest_gate_expands_prefix_flags_then_target() -> None:
    module = _expand_module()
    argv = module.expand_gate_argv(
        {
            "gate_id": "manifest.python.pytest",
            "target": "tests",
            "flags": ["-q"],
        },
        _manifest(),
    )
    assert argv == ("python", "-m", "pytest", "-q", "tests")


def test_unknown_gate_id_is_rejected() -> None:
    module = _expand_module()
    with pytest.raises(module.GateExpandError) as unknown:
        module.expand_gate_argv({"gate_id": "manifest.made-up.gate"}, _manifest())
    assert unknown.value.code == "COMMAND_UNKNOWN_GATE"


def test_argv_is_rejected_without_classifying() -> None:
    module = _expand_module()
    with pytest.raises(module.GateExpandError) as rejected:
        module.expand_gate_argv(
            {"argv": ["npm", "test"], "gate_id": "manifest.node.test-chat"},
            _manifest(),
        )
    assert rejected.value.code == "COMMAND_ARGV_REJECTED"
