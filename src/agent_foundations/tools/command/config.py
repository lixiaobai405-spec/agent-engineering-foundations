from __future__ import annotations

from pathlib import Path

from agent_foundations.execution.sandbox_manifest import SandboxManifest
from agent_foundations.tools.command.models import (
    CommandCategory,
    CommandGate,
    ProjectCommandManifest,
)
from agent_foundations.tools.patch.models import compute_project_root_fingerprint


def default_project_command_manifest(
    *,
    project_fingerprint: str,
    sandbox: SandboxManifest,
) -> ProjectCommandManifest:
    shared_python_targets = (".", "src", "tests")
    return ProjectCommandManifest(
        project_fingerprint=project_fingerprint,
        gates=(
            CommandGate(
                rule_id="manifest.python.pytest",
                category=CommandCategory.TEST,
                argv_prefix=("python", "-m", "pytest"),
                sandbox_profile="python",
                allowed_targets=shared_python_targets,
                allowed_flags=("-q", "--tb=short", "--disable-warnings"),
            ),
            CommandGate(
                rule_id="manifest.python.ruff-check",
                category=CommandCategory.LINT,
                argv_prefix=("python", "-m", "ruff", "check"),
                sandbox_profile="python",
                allowed_targets=shared_python_targets,
            ),
            CommandGate(
                rule_id="manifest.python.mypy",
                category=CommandCategory.TYPECHECK,
                argv_prefix=("python", "-m", "mypy"),
                sandbox_profile="python",
                allowed_targets=shared_python_targets,
            ),
            CommandGate(
                rule_id="manifest.python.pip-check",
                category=CommandCategory.PACKAGE_CHECK,
                argv_prefix=("python", "-m", "pip", "check"),
                sandbox_profile="python",
                exact=True,
            ),
            CommandGate(
                rule_id="manifest.node.test-viewer",
                category=CommandCategory.TEST,
                argv_prefix=("npm", "run", "test:viewer"),
                sandbox_profile="node",
                exact=True,
            ),
            CommandGate(
                rule_id="manifest.node.typecheck-viewer",
                category=CommandCategory.TYPECHECK,
                argv_prefix=("npm", "run", "typecheck:viewer"),
                sandbox_profile="node",
                exact=True,
            ),
            CommandGate(
                rule_id="manifest.node.test-chat",
                category=CommandCategory.TEST,
                argv_prefix=("npm", "run", "test:chat"),
                sandbox_profile="node",
                exact=True,
            ),
            CommandGate(
                rule_id="manifest.node.typecheck-chat",
                category=CommandCategory.TYPECHECK,
                argv_prefix=("npm", "run", "typecheck:chat"),
                sandbox_profile="node",
                exact=True,
            ),
            CommandGate(
                rule_id="manifest.node.build-chat",
                category=CommandCategory.BUILD,
                argv_prefix=("npm", "run", "build:chat"),
                sandbox_profile="node",
                exact=True,
            ),
        ),
        sandbox=sandbox,
    )


def manifest_for_project(
    project_root: Path,
    *,
    sandbox: SandboxManifest,
) -> ProjectCommandManifest:
    return default_project_command_manifest(
        project_fingerprint=compute_project_root_fingerprint(project_root),
        sandbox=sandbox,
    )
