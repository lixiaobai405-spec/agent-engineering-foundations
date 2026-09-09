from __future__ import annotations

import importlib.util
from typing import Any, Literal

import pytest


def _command() -> tuple[Any, ...]:
    try:
        feature = importlib.util.find_spec("agent_foundations.tools.command.classifier")
    except ModuleNotFoundError:
        feature = None
    assert feature is not None, "Task 17 command classifier is missing"
    from agent_foundations.tools.command.classifier import CommandClassifier
    from agent_foundations.tools.command.config import default_project_command_manifest
    from agent_foundations.tools.command.models import CommandCategory, CommandSpec

    return CommandClassifier, default_project_command_manifest, CommandCategory, CommandSpec


def _classifier_and_manifest() -> tuple[Any, Any, Any, Any]:
    CommandClassifier, build_manifest, CommandCategory, CommandSpec = _command()
    from agent_foundations.execution.sandbox_manifest import (
        SandboxImageProvenance,
        SandboxManifest,
    )

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

    fingerprint = "a" * 64
    return (
        CommandClassifier(project_fingerprint=fingerprint),
        build_manifest(
            project_fingerprint=fingerprint,
            sandbox=SandboxManifest(
                python=provenance("python"),
                node=provenance("node"),
            ),
        ),
        CommandCategory,
        CommandSpec,
    )


@pytest.mark.parametrize(
    ("argv", "category", "profile"),
    [
        (("python", "-m", "pytest", "tests/unit", "-q"), "test", "python"),
        (("python", "-m", "pytest", "tests/unit/test_x.py::test_y"), "test", "python"),
        (("python", "-m", "ruff", "check", "src", "tests"), "lint", "python"),
        (("python", "-m", "mypy", "src", "tests"), "typecheck", "python"),
        (("python", "-m", "pip", "check"), "package_check", "python"),
        (("npm", "run", "test:viewer"), "test", "node"),
        (("npm", "run", "typecheck:viewer"), "typecheck", "node"),
        (("npm", "run", "test:chat"), "test", "node"),
        (("npm", "run", "typecheck:chat"), "typecheck", "node"),
        (("npm", "run", "build:chat"), "build", "node"),
    ],
)
def test_classifier_allows_only_manifest_gates(
    argv: tuple[str, ...],
    category: str,
    profile: str,
) -> None:
    classifier, manifest, CommandCategory, CommandSpec = _classifier_and_manifest()

    result = classifier.classify(CommandSpec(argv=argv), manifest)

    assert result.category is CommandCategory(category)
    assert result.normalized_argv == argv
    assert result.sandbox_profile == profile
    assert result.hard_denied is False
    assert result.rule_id.startswith("manifest.")


@pytest.mark.parametrize(
    "argv",
    [
        ("pwsh", "-Command", "Get-ChildItem"),
        ("powershell", "-File", "script.ps1"),
        ("bash", "-c", "pytest"),
        ("cmd", "/c", "pytest"),
        ("sh", "-c", "pytest"),
        ("python", "-c", "print('x')"),
        ("python", "script.py"),
        ("python", "-m", "pip", "install", "x"),
        ("npm", "install"),
        ("curl", "https://example.invalid"),
        ("wget", "https://example.invalid"),
        ("git", "status"),
        ("python", "-m", "pytest", "tests", "|", "tee", "out"),
        ("python", "-m", "pytest", "tests", ">", "out"),
        ("python", "-m", "pytest", "tests;whoami"),
    ],
)
def test_classifier_hard_denies_known_dangerous_commands(argv: tuple[str, ...]) -> None:
    classifier, manifest, CommandCategory, CommandSpec = _classifier_and_manifest()

    result = classifier.classify(CommandSpec(argv=argv), manifest)

    assert result.category is CommandCategory.DENIED
    assert result.hard_denied is True
    assert result.rule_id.startswith("builtin.command.")


@pytest.mark.parametrize(
    "argv",
    [
        ("python", "-m", "pytest", "src_evil"),
        ("python", "-m", "pytest", "../tests"),
        ("python", "-m", "pytest", "/tmp/test_x.py"),
        ("python", "-m", "pytest", "C:/tests"),
        ("python", "-m", "pytest", "tests:stream"),
        ("python", "-m", "pytest", "tests", "--unknown"),
        ("python", "-m", "pytest"),
        ("python", "-m", "ruff", "check", "src_evil"),
        ("python", "-m", "mypy", "src", "extra"),
        ("python", "-m", "pip", "check", "extra"),
        ("npm", "run", "test:chat", "--", "--watch"),
        ("npm", "run", "unknown"),
    ],
)
def test_classifier_fully_consumes_suffix_grammar_and_target_segments(
    argv: tuple[str, ...],
) -> None:
    classifier, manifest, _CommandCategory, CommandSpec = _classifier_and_manifest()

    result = classifier.classify(CommandSpec(argv=argv), manifest)

    assert result.hard_denied is True


def test_classifier_hard_denies_unknown_with_stable_rule() -> None:
    classifier, manifest, CommandCategory, CommandSpec = _classifier_and_manifest()
    spec = CommandSpec(argv=("unknown-command", "arg"))

    first = classifier.classify(spec, manifest)
    second = classifier.classify(spec, manifest)

    assert first == second
    assert first.category is CommandCategory.UNKNOWN
    assert first.rule_id == "builtin.command.unknown"
    assert first.hard_denied is True


def test_classifier_rejects_project_fingerprint_drift() -> None:
    classifier, manifest, _CommandCategory, CommandSpec = _classifier_and_manifest()
    drifted = manifest.model_copy(update={"project_fingerprint": "b" * 64})

    result = classifier.classify(
        CommandSpec(argv=("python", "-m", "pip", "check")),
        drifted,
    )

    assert result.hard_denied is True
    assert result.rule_id == "builtin.command.project-fingerprint-mismatch"


def test_classifier_is_pure_and_does_not_call_security_or_io(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    classifier, manifest, _CommandCategory, CommandSpec = _classifier_and_manifest()

    def fail_boundary(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("classifier crossed a forbidden boundary")

    monkeypatch.setattr("pathlib.Path.resolve", fail_boundary)
    result = classifier.classify(
        CommandSpec(argv=("python", "-m", "pip", "check")),
        manifest,
    )
    assert result.hard_denied is False
