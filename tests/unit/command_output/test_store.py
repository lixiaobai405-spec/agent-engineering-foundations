from __future__ import annotations

import importlib.util
import os
import stat
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest


def _store_api() -> Any:
    try:
        spec = importlib.util.find_spec("agent_foundations.command_output.store")
    except ModuleNotFoundError:
        spec = None
    assert spec is not None, "command output store is missing"
    from agent_foundations.command_output.models import compute_artifact_sha256
    from agent_foundations.command_output.permissions import verify_owner_only
    from agent_foundations.command_output.store import (
        ArtifactRootError,
        CommandArtifactStore,
        UnsafeArtifactIdError,
        default_artifact_root,
    )

    return (
        CommandArtifactStore,
        ArtifactRootError,
        UnsafeArtifactIdError,
        default_artifact_root,
        compute_artifact_sha256,
        verify_owner_only,
    )


def test_default_artifact_root_is_localappdata_not_relative() -> None:
    (
        _store,
        _root_error,
        _unsafe,
        default_artifact_root,
        _digest,
        _verify,
    ) = _store_api()
    root = default_artifact_root()
    assert root.is_absolute()
    assert root.name == "command-output"
    assert "AgentFoundations" in root.parts
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA")
        if local:
            assert root.is_relative_to(Path(local))


def test_store_rejects_project_git_relative_and_reparse_roots(
    tmp_path: Path,
) -> None:
    store_cls, root_error, *_rest = _store_api()
    project = tmp_path / "project"
    project.mkdir()
    (project / ".git").mkdir()
    with pytest.raises(root_error):
        store_cls(project / "artifacts")
    with pytest.raises(root_error):
        store_cls(Path("relative-artifacts"))
    with pytest.raises(root_error):
        store_cls(project)


@pytest.mark.parametrize(
    "artifact_id",
    [
        "../coa_escape",
        "..\\coa_escape",
        "/tmp/coa_abs",
        "C:\\Windows\\coa_abs",
        "coa_abc:ads",
        "coa_abc\x00hid",
        "coa_abc\nhid",
        "coa_" + "a" * 21,
        "not-an-id",
        "coa_../../../etc",
    ],
)
def test_store_rejects_path_escape_absolute_ads_and_control_ids(
    tmp_path: Path,
    artifact_id: str,
) -> None:
    store_cls, _root_error, unsafe_error, *_rest = _store_api()
    store = store_cls(tmp_path / "artifacts")
    with pytest.raises(unsafe_error):
        store.directory_for(artifact_id)


def test_store_maps_opaque_id_to_exact_child_directory(tmp_path: Path) -> None:
    (
        store_cls,
        _root_error,
        _unsafe,
        _default,
        _digest,
        _verify,
    ) = _store_api()
    from agent_foundations.command_output.models import generate_artifact_id

    store = store_cls(tmp_path / "artifacts")
    artifact_id = generate_artifact_id()
    directory = store.directory_for(artifact_id)
    assert directory.parent == store.root
    assert directory.name == artifact_id
    assert directory == store.root / artifact_id


def test_atomic_write_persists_two_streams_hash_and_owner_permissions(
    tmp_path: Path,
) -> None:
    (
        store_cls,
        _root_error,
        _unsafe,
        _default,
        compute_artifact_sha256,
        verify_owner_only,
    ) = _store_api()
    store = store_cls(tmp_path / "artifacts")
    stdout = b"fixture-secret"
    stderr = b"failure"
    metadata = store.write(
        stdout=stdout,
        stderr=stderr,
        run_id=uuid4(),
        effect_id=uuid4(),
        execution_id=uuid4(),
    )
    directory = store.directory_for(metadata.artifact_id)
    stdout_path = directory / "stdout"
    stderr_path = directory / "stderr"
    assert stdout_path.read_bytes() == stdout
    assert stderr_path.read_bytes() == stderr
    assert not (directory / "stdout.tmp").exists()
    assert not (directory / "stderr.tmp").exists()
    assert metadata.stdout_bytes == len(stdout)
    assert metadata.stderr_bytes == len(stderr)
    assert metadata.sha256 == compute_artifact_sha256(stdout, stderr)
    verify_owner_only(directory)
    verify_owner_only(stdout_path)
    verify_owner_only(stderr_path)
    if os.name != "nt":
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700
        assert stat.S_IMODE(stdout_path.stat().st_mode) == 0o600
        assert stat.S_IMODE(stderr_path.stat().st_mode) == 0o600
