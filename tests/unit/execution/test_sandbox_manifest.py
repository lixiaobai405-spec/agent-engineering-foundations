from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError


def _sandbox() -> tuple[Any, ...]:
    try:
        feature = importlib.util.find_spec("agent_foundations.execution.sandbox_manifest")
    except ModuleNotFoundError:
        feature = None
    assert feature is not None, "Task 17 SandboxManifest is missing"
    from agent_foundations.execution.docker import DockerCommandBuilder
    from agent_foundations.execution.models import ExecutionRequest
    from agent_foundations.execution.sandbox_manifest import (
        SandboxImageProvenance,
        SandboxManifest,
        SandboxManifestMismatchError,
        verify_lockfile_fingerprint,
    )

    return (
        SandboxImageProvenance,
        SandboxManifest,
        SandboxManifestMismatchError,
        verify_lockfile_fingerprint,
        ExecutionRequest,
        DockerCommandBuilder,
    )


def _provenance(profile: str) -> Any:
    Provenance, *_ = _sandbox()
    name = "python" if profile == "python" else "node"
    return Provenance(
        profile=profile,
        image_tag=f"agent-foundations-sandbox-{name}:phase2d",
        base_repo_digest=f"{name}@sha256:{'a' * 64}",
        lockfile_sha256="b" * 64,
        final_image_id=f"sha256:{'c' * 64}",
        final_repo_digest=(
            f"agent-foundations-sandbox-{name}@sha256:{'d' * 64}"
        ),
    )


def _manifest() -> Any:
    _Provenance, Manifest, *_ = _sandbox()
    return Manifest(python=_provenance("python"), node=_provenance("node"))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("base_repo_digest", "python:3.12-slim-bookworm"),
        ("base_repo_digest", "sha256:" + "a" * 64),
        ("lockfile_sha256", "A" * 64),
        ("final_image_id", "c" * 64),
        ("final_repo_digest", "agent-foundations-sandbox-python:phase2d"),
    ],
)
def test_provenance_requires_strict_digests(field: str, value: str) -> None:
    Provenance, *_ = _sandbox()
    payload = _provenance("python").model_dump()
    payload[field] = value

    with pytest.raises(ValidationError):
        Provenance.model_validate(payload)


def test_manifest_has_fixed_profiles_and_rejects_arbitrary_image_selection() -> None:
    _Provenance, Manifest, Error, *_ = _sandbox()
    manifest = _manifest()

    assert manifest.profile("python").image_tag.endswith("-python:phase2d")
    assert manifest.profile("node").image_tag.endswith("-node:phase2d")
    with pytest.raises(Error, match="unknown sandbox profile"):
        manifest.profile("attacker/image:latest")
    with pytest.raises(ValidationError):
        Manifest(python=_provenance("node"), node=_provenance("python"))


def test_manifest_verification_fails_closed_on_image_or_digest_mismatch() -> None:
    _Provenance, _Manifest, Error, *_ = _sandbox()
    manifest = _manifest()

    manifest.verify_runtime(
        "python",
        image_id="sha256:" + "c" * 64,
        repo_digest="agent-foundations-sandbox-python@sha256:" + "d" * 64,
    )
    with pytest.raises(Error, match="image ID mismatch"):
        manifest.verify_runtime(
            "python",
            image_id="sha256:" + "e" * 64,
            repo_digest="agent-foundations-sandbox-python@sha256:" + "d" * 64,
        )
    with pytest.raises(Error, match="RepoDigest mismatch"):
        manifest.verify_runtime(
            "python",
            image_id="sha256:" + "c" * 64,
            repo_digest="agent-foundations-sandbox-python@sha256:" + "e" * 64,
        )


def test_lockfile_fingerprint_mismatch_is_rejected(tmp_path: Path) -> None:
    _Provenance, _Manifest, Error, verify_lock, *_ = _sandbox()
    lock = tmp_path / "requirements.lock"
    lock.write_text("pytest==8.4.2\n", encoding="utf-8")

    with pytest.raises(Error, match="lockfile fingerprint mismatch"):
        verify_lock(_provenance("python"), lock)


def test_snapshot_request_uses_trusted_profile_and_ephemeral_workspace(
    tmp_path: Path,
) -> None:
    *_prefix, ExecutionRequest, DockerCommandBuilder = _sandbox()
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    (snapshot / "src").mkdir()
    request = ExecutionRequest(
        execution_id=str(uuid4()),
        run_id=str(uuid4()),
        capability_id=str(uuid4()),
        argv=("python", "-m", "pytest", "tests", "-q"),
        cwd="src",
        mount_mode="snapshot",
        sandbox_profile="python",
        timeout_seconds=30,
        max_output_bytes=4096,
    )

    argv = DockerCommandBuilder(snapshot, sandbox_manifest=_manifest()).build(request)
    joined = " ".join(argv)

    assert "sha256:" + "c" * 64 in argv
    assert "agent-foundations-sandbox-python:phase2d" not in argv
    assert "target=/project-ro,readonly" in joined
    assert "/workspace" in joined
    assert "--tmpfs" in argv
    assert argv[argv.index("--tmpfs") + 1] == (
        "/workspace:rw,nosuid,nodev,size=536870912,mode=0755,uid=65532,gid=65532"
    )
    assert "--network none" in joined
    assert "--read-only" in argv
    assert "--cap-drop ALL" in joined
    assert "no-new-privileges" in joined
    assert "--pids-limit 64" in joined
    assert "--cpus 1.0" in joined
    assert "--memory 512m" in joined
    assert "/var/run/docker.sock" not in joined
    mount = argv[argv.index("--mount") + 1]
    assert f"source={Path.home()}," not in mount
    assert f"source={snapshot.resolve(strict=True)}," in mount
    assert "node_modules" not in joined


def test_legacy_project_write_builder_behavior_is_preserved(tmp_path: Path) -> None:
    *_prefix, ExecutionRequest, DockerCommandBuilder = _sandbox()
    project = tmp_path / "project"
    project.mkdir()
    request = ExecutionRequest(
        execution_id=str(uuid4()),
        run_id=str(uuid4()),
        capability_id=str(uuid4()),
        argv=("python", "-m", "agent_foundations.tools.patch.applier"),
        cwd=".",
        mount_mode="project_write",
        timeout_seconds=30,
        max_output_bytes=4096,
    )

    argv = DockerCommandBuilder(project).build(request)

    assert "agent-foundations-sandbox:phase2" in argv
    assert any("target=/workspace" in token and "readonly" not in token for token in argv)


def test_entrypoint_and_build_context_are_fixed_and_non_interpreting() -> None:
    root = Path(__file__).resolve().parents[3]
    entrypoint_path = root / "docker/sandbox-entrypoint.sh"
    patch_dockerfile_path = root / "docker/agent-sandbox.Dockerfile"
    assert entrypoint_path.is_file(), "Task 17 fixed sandbox entrypoint is missing"
    assert patch_dockerfile_path.is_file(), (
        "Phase 2C patch sandbox must retain a repository build entrypoint"
    )
    entrypoint = entrypoint_path.read_text(encoding="utf-8")
    patch_dockerfile = patch_dockerfile_path.read_text(encoding="utf-8")
    dockerignore = (root / ".dockerignore").read_text(encoding="utf-8").splitlines()

    assert 'exec "$@"' in entrypoint
    assert "eval" not in entrypoint
    assert "sh -c" not in entrypoint
    assert "/project-ro" in entrypoint
    assert "/workspace" in entrypoint
    assert "FROM python:3.12-slim-bookworm" in patch_dockerfile
    assert "USER 65532:65532" in patch_dockerfile
    assert "WORKDIR /workspace" in patch_dockerfile
    assert dockerignore == [
        "**",
        "!docker/agent-sandbox.Dockerfile",
        "!docker/agent-sandbox-python.Dockerfile",
        "!docker/agent-sandbox-node.Dockerfile",
        "!docker/agent-sandbox-python.requirements.lock",
        "!docker/sandbox-entrypoint.sh",
        "!package.json",
        "!package-lock.json",
    ]


def test_dockerfiles_bind_immutable_base_and_lock_fingerprints() -> None:
    root = Path(__file__).resolve().parents[3]
    python_lock = root / "docker/agent-sandbox-python.requirements.lock"
    package_lock = root / "package-lock.json"
    python_dockerfile = (root / "docker/agent-sandbox-python.Dockerfile").read_text(
        encoding="utf-8"
    )
    node_dockerfile = (root / "docker/agent-sandbox-node.Dockerfile").read_text(
        encoding="utf-8"
    )

    python_hash = hashlib.sha256(python_lock.read_bytes()).hexdigest()
    node_hash = hashlib.sha256(package_lock.read_bytes()).hexdigest()
    assert "FROM python@sha256:" in python_dockerfile
    assert "FROM python:" not in python_dockerfile
    assert f'lockfile-sha256="{python_hash}"' in python_dockerfile
    node_base = (
        "node@sha256:83f487e0a63425e5b4d146fb5e5be574"
        "bcbe1b7b843d3ebafdd95eaf7767a7e5"
    )
    assert f"ARG NODE_BASE_IMAGE={node_base}" in node_dockerfile
    assert f"ARG NODE_BASE_REPO_DIGEST={node_base}" in node_dockerfile
    assert "FROM ${NODE_BASE_IMAGE}" in node_dockerfile
    assert "FROM node:" not in node_dockerfile
    assert f'lockfile-sha256="{node_hash}"' in node_dockerfile


_PINNED_PYTHON_IMAGE_ID = (
    "sha256:730aea0a2ba8ef2998bb0cc43b1f94641a9099f8a0d55b22a0605f384ad26e41"
)
_PINNED_NODE_IMAGE_ID = (
    "sha256:12f2470f314aae00f8757a313d78da471472984f7d039bdfdf1c57a553cfc0e7"
)
_PLACEHOLDER_IMAGE_ID = f"sha256:{'c' * 64}"


def test_phase2d_chat_loader_uses_pinned_final_image_ids() -> None:
    from agent_foundations.cli.main import _phase2d_sandbox_manifest

    manifest = _phase2d_sandbox_manifest()
    assert manifest.schema_version == 1
    assert manifest.python.final_image_id != _PLACEHOLDER_IMAGE_ID
    assert manifest.node.final_image_id != _PLACEHOLDER_IMAGE_ID
    assert manifest.python.final_image_id == _PINNED_PYTHON_IMAGE_ID
    assert manifest.node.final_image_id == _PINNED_NODE_IMAGE_ID


def test_chat_services_pass_sandbox_manifest_into_docker_backends() -> None:
    import inspect

    from agent_foundations.cli import main as cli_main

    source = inspect.getsource(cli_main.build_chat_services)
    loader = inspect.getsource(cli_main._phase2d_sandbox_manifest)
    assert "load_pinned" in loader
    assert "'c' * 64" not in loader
    assert '"c" * 64' not in loader
    assert source.count(
        "backend_factory=lambda workspace: docker_backend_factory(workspace)"
    ) == 2
    assert "sandbox_manifest=sandbox_manifest" in source


def test_from_path_loads_versioned_pin_without_placeholder_ids() -> None:
    _Provenance, Manifest, *_ = _sandbox()
    root = Path(__file__).resolve().parents[3]
    loaded = Manifest.from_path(root / "docker" / "sandbox-manifest.phase2d.json")
    assert loaded.schema_version == 1
    assert loaded.python.final_image_id == _PINNED_PYTHON_IMAGE_ID
    assert loaded.node.final_image_id == _PINNED_NODE_IMAGE_ID
    assert loaded.python.final_image_id != _PLACEHOLDER_IMAGE_ID


def test_load_pinned_fails_closed_when_lockfile_fingerprint_drifts(
    tmp_path: Path,
) -> None:
    _Provenance, Manifest, Error, *_ = _sandbox()
    root = Path(__file__).resolve().parents[3]
    pin = (root / "docker" / "sandbox-manifest.phase2d.json").read_text(encoding="utf-8")
    docker_dir = tmp_path / "docker"
    docker_dir.mkdir()
    (docker_dir / "sandbox-manifest.phase2d.json").write_text(pin, encoding="utf-8")
    (docker_dir / "agent-sandbox-python.requirements.lock").write_text(
        "drifted-lock\n",
        encoding="utf-8",
    )
    (tmp_path / "package-lock.json").write_text("{}\n", encoding="utf-8")

    with pytest.raises(Error, match="lockfile fingerprint mismatch"):
        Manifest.load_pinned(tmp_path)
