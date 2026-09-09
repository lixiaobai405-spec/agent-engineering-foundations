from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from agent_foundations.tools.command.classifier import CommandClassifier
from agent_foundations.tools.command.config import default_project_command_manifest
from agent_foundations.tools.command.models import CommandSpec
from agent_foundations.tools.patch.models import compute_project_root_fingerprint


def _require_harness() -> Any:
    try:
        spec = importlib.util.find_spec("agent_foundations.command_output.harness")
    except ModuleNotFoundError:
        spec = None
    assert spec is not None, "command output harness is missing"
    from agent_foundations.command_output.harness import inject_trusted_format

    return inject_trusted_format


def _require_registry() -> Any:
    try:
        spec = importlib.util.find_spec("agent_foundations.command_output.parsers.registry")
    except ModuleNotFoundError:
        spec = None
    assert spec is not None, "parser registry is missing"
    from agent_foundations.command_output.parsers.registry import parser_for

    return parser_for


def test_agent_cannot_supply_reporter_or_format_flags() -> None:
    _require_harness()
    root = Path(".").resolve()
    fingerprint = compute_project_root_fingerprint(root)
    manifest = default_project_command_manifest(
        project_fingerprint=fingerprint,
        sandbox=__import__(
            "agent_foundations.execution.sandbox_manifest",
            fromlist=["SandboxManifest"],
        ).SandboxManifest.model_validate(
            {
                "python": {
                    "profile": "python",
                    "image_tag": "agent-foundations-sandbox-python:phase2d",
                    "base_repo_digest": "python@sha256:" + ("a" * 64),
                    "lockfile_sha256": "b" * 64,
                    "final_image_id": "sha256:" + ("c" * 64),
                },
                "node": {
                    "profile": "node",
                    "image_tag": "agent-foundations-sandbox-node:phase2d",
                    "base_repo_digest": "node@sha256:" + ("a" * 64),
                    "lockfile_sha256": "b" * 64,
                    "final_image_id": "sha256:" + ("c" * 64),
                },
            }
        ),
    )
    classifier = CommandClassifier(project_fingerprint=fingerprint)
    denied = classifier.classify(
        CommandSpec(argv=("python", "-m", "ruff", "check", "src", "--output-format=json")),
        manifest,
    )
    assert denied.hard_denied is True


def test_controller_injects_trusted_format_after_classify() -> None:
    inject_trusted_format = _require_harness()
    parser_for = _require_registry()
    ruff_argv = inject_trusted_format(
        ("python", "-m", "ruff", "check", "src"),
        "manifest.python.ruff-check",
    )
    assert ruff_argv[:5] == ("python", "-m", "ruff", "check", "src")
    assert "--output-format=json" in ruff_argv
    pytest_argv = inject_trusted_format(
        ("python", "-m", "pytest", "tests", "-q"),
        "manifest.python.pytest",
    )
    assert any(token.startswith("--junit-xml=") for token in pytest_argv)
    npm_argv = inject_trusted_format(
        ("npm", "run", "test:chat"),
        "manifest.node.test-chat",
    )
    assert npm_argv[:3] == ("npm", "run", "test:chat")
    assert "--" in npm_argv
    assert parser_for("manifest.python.pytest").__class__.__name__ == "PytestOutputParser"
    assert parser_for("manifest.python.ruff-check").__class__.__name__ == "RuffOutputParser"
    assert parser_for("manifest.python.mypy").__class__.__name__ == "MypyOutputParser"
    assert parser_for("manifest.node.test-viewer").__class__.__name__ == "VitestOutputParser"
    assert parser_for("manifest.node.typecheck-chat").__class__.__name__ == "TypeScriptOutputParser"
    assert parser_for("manifest.node.build-chat").__class__.__name__ == "BuildOutputParser"
    assert parser_for("manifest.python.pip-check").__class__.__name__ == "BuildOutputParser"
