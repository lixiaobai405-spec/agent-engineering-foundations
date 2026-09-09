from __future__ import annotations

import importlib.util
from typing import Any, Literal

import pytest
from pydantic import ValidationError


def _models() -> tuple[Any, ...]:
    try:
        feature = importlib.util.find_spec("agent_foundations.tools.command.models")
    except ModuleNotFoundError:
        feature = None
    assert feature is not None, "Task 17 command models are missing"
    from agent_foundations.tools.command.models import (
        CommandCategory,
        CommandClassification,
        CommandGate,
        CommandSpec,
        ProjectCommandManifest,
    )

    return (
        CommandCategory,
        CommandClassification,
        CommandGate,
        CommandSpec,
        ProjectCommandManifest,
    )


def _sandbox_manifest() -> Any:
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

    return SandboxManifest(python=provenance("python"), node=provenance("node"))


def test_command_category_is_exact_and_complete() -> None:
    CommandCategory, *_ = _models()

    assert {category.value for category in CommandCategory} == {
        "test",
        "lint",
        "typecheck",
        "build",
        "package_check",
        "denied",
        "unknown",
    }


@pytest.mark.parametrize(
    "argv",
    [(), ("",), (" ",), (" python",), ("python ",), ("py\x00thon",), ("py\nthon",)],
)
def test_command_spec_rejects_empty_padded_or_control_argv(
    argv: tuple[str, ...],
) -> None:
    *_prefix, CommandSpec, _Manifest = _models()

    with pytest.raises(ValidationError):
        CommandSpec(argv=argv)


@pytest.mark.parametrize(
    "cwd",
    [
        "",
        " project",
        "project ",
        "/tmp",
        "C:/project",
        "C:project",
        "\\\\server\\share",
        "\\\\?\\C:\\project",
        "\\\\.\\pipe\\docker",
        "src:stream",
        "..",
        "src/../tests",
        "src\x00/tests",
    ],
)
def test_command_spec_rejects_unsafe_cwd(cwd: str) -> None:
    *_prefix, CommandSpec, _Manifest = _models()

    with pytest.raises(ValidationError):
        CommandSpec(argv=("python", "-m", "pip", "check"), cwd=cwd)


@pytest.mark.parametrize("cwd", [".", "src", "tests/unit", "tests\\unit"])
def test_command_spec_accepts_safe_project_relative_cwd(cwd: str) -> None:
    *_prefix, CommandSpec, _Manifest = _models()

    assert CommandSpec(argv=("python", "-m", "pip", "check"), cwd=cwd).cwd == cwd


@pytest.mark.parametrize("timeout", [0, 301])
def test_command_spec_enforces_timeout_bounds(timeout: int) -> None:
    *_prefix, CommandSpec, _Manifest = _models()

    with pytest.raises(ValidationError):
        CommandSpec(argv=("python", "-m", "pip", "check"), timeout_seconds=timeout)


def test_command_spec_defaults_and_validated_copy_are_safe() -> None:
    *_prefix, CommandSpec, _Manifest = _models()
    spec = CommandSpec(argv=("python", "-m", "pip", "check"))

    assert spec.cwd == "."
    assert 1 <= spec.timeout_seconds <= 300
    with pytest.raises(ValidationError):
        spec.model_copy(update={"cwd": "../outside"})


def test_manifest_rejects_unknown_schema_duplicate_and_conflicting_rules() -> None:
    CommandCategory, _Classification, CommandGate, _Spec, Manifest = _models()
    gate = CommandGate(
        rule_id="python.pytest",
        category=CommandCategory.TEST,
        argv_prefix=("python", "-m", "pytest"),
        sandbox_profile="python",
        allowed_targets=(".", "tests"),
        allowed_flags=("-q",),
    )
    other = gate.model_copy(update={"rule_id": "python.pytest.other"})

    with pytest.raises(ValidationError):
        Manifest(
            schema_version=2,
            project_fingerprint="a" * 64,
            gates=(gate,),
            sandbox=_sandbox_manifest(),
        )
    with pytest.raises(ValidationError, match="duplicate rule_id"):
        Manifest(
            project_fingerprint="a" * 64,
            gates=(gate, gate),
            sandbox=_sandbox_manifest(),
        )
    with pytest.raises(ValidationError, match="conflicting command gate"):
        Manifest(
            project_fingerprint="a" * 64,
            gates=(gate, other),
            sandbox=_sandbox_manifest(),
        )


def test_manifest_and_classification_are_strict_frozen_models() -> None:
    CommandCategory, Classification, CommandGate, _Spec, Manifest = _models()
    gate = CommandGate(
        rule_id="python.pip-check",
        category=CommandCategory.PACKAGE_CHECK,
        argv_prefix=("python", "-m", "pip", "check"),
        sandbox_profile="python",
        exact=True,
    )
    manifest = Manifest(
        project_fingerprint="a" * 64,
        gates=(gate,),
        sandbox=_sandbox_manifest(),
    )
    classification = Classification(
        category=CommandCategory.PACKAGE_CHECK,
        rule_id=gate.rule_id,
        normalized_argv=gate.argv_prefix,
        sandbox_profile="python",
        hard_denied=False,
    )

    with pytest.raises(ValidationError):
        Manifest(
            project_fingerprint="a" * 64,
            gates=(gate,),
            sandbox=_sandbox_manifest(),
            surprise=True,
        )
    with pytest.raises(ValidationError):
        classification.model_copy(update={"rule_id": " "})
    with pytest.raises(ValidationError):
        manifest.project_fingerprint = "b" * 64


def test_command_models_do_not_import_security_or_perform_io(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    *_prefix, CommandSpec, _Manifest = _models()

    def fail_io(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("command models performed I/O")

    monkeypatch.setattr("pathlib.Path.resolve", fail_io)
    spec = CommandSpec(argv=("python", "-m", "pip", "check"))
    assert spec.argv[-1] == "check"
