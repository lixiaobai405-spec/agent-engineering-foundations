from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import IO, Any

import pytest


def _workspace() -> tuple[Any, ...]:
    try:
        feature = importlib.util.find_spec("agent_foundations.execution.workspace")
    except ModuleNotFoundError:
        feature = None
    assert feature is not None, "Task 17 filtered workspace snapshot is missing"
    from agent_foundations.execution.workspace import (
        WorkspaceLimits,
        WorkspaceSnapshotError,
        cleanup_workspace_snapshot,
        create_workspace_snapshot,
    )

    return (
        WorkspaceLimits,
        WorkspaceSnapshotError,
        cleanup_workspace_snapshot,
        create_workspace_snapshot,
    )


def _write(root: Path, relative: str, content: str = "safe\n") -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_snapshot_copies_only_regular_non_sensitive_project_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _Limits, _Error, cleanup, create = _workspace()
    project = tmp_path / "project"
    controller = tmp_path / "controller"
    project.mkdir()
    controller.mkdir()
    safe = _write(project, "src/app.py")
    sensitive_paths = {
        _write(project, ".env", "SECRET_SENTINEL\n"),
        _write(project, ".docker/config.json", "REGISTRY_TOKEN_SENTINEL\n"),
        _write(project, "pip.conf", "PRIVATE_INDEX_SENTINEL\n"),
        _write(project, ".config/pip/pip.conf", "PIP_PASSWORD_SENTINEL\n"),
        _write(project, "auth.json", "AUTH_TOKEN_SENTINEL\n"),
        _write(project, "token.txt", "TOKEN_SENTINEL\n"),
    }
    excluded = (
        ".env.local",
        ".git/config",
        ".agents/private.txt",
        ".gate-backup/state.json",
        ".ssh/id_rsa",
        ".npmrc",
        "credentials.json",
        "private.pem",
        "node_modules/pkg/index.js",
        ".venv/pyvenv.cfg",
        "venv/pyvenv.cfg",
        "__pycache__/x.pyc",
        ".pytest_cache/v/cache/nodeids",
        ".mypy_cache/x.json",
        ".ruff_cache/x",
        "dist/bundle.js",
        "build/output.bin",
        "coverage/report.txt",
        "app.log",
        "state.sqlite3",
        ".agent-foundations/artifacts/raw.bin",
    )
    for relative in excluded:
        _write(project, relative, "EXCLUDED_SENTINEL\n")

    real_open = Path.open

    def guarded_open(
        path: Path,
        mode: str = "r",
        buffering: int = -1,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> IO[Any]:
        if path in sensitive_paths:
            raise AssertionError("excluded sensitive file was opened")
        return real_open(path, mode, buffering, encoding, errors, newline)

    monkeypatch.setattr(Path, "open", guarded_open)
    snapshot = create(project, controller_root=controller)
    try:
        assert snapshot.root.parent == controller.resolve()
        assert not snapshot.root.is_relative_to(project.resolve())
        assert [entry.path for entry in snapshot.files] == ["src/app.py"]
        assert (snapshot.root / "src/app.py").read_bytes() == safe.read_bytes()
        assert "SECRET_SENTINEL" not in "".join(
            path.read_text(encoding="utf-8", errors="ignore")
            for path in snapshot.root.rglob("*")
            if path.is_file()
        )
    finally:
        cleanup(snapshot)
    assert not snapshot.root.exists()


def test_snapshot_skips_symlink_and_reparse_entries(tmp_path: Path) -> None:
    _Limits, _Error, cleanup, create = _workspace()
    project = tmp_path / "project"
    controller = tmp_path / "controller"
    outside = tmp_path / "outside.txt"
    project.mkdir()
    controller.mkdir()
    outside.write_text("outside", encoding="utf-8")
    _write(project, "safe.txt")
    link = project / "linked.txt"
    try:
        os.symlink(outside, link)
    except OSError:
        pytest.skip("symlink creation is unavailable on this host")

    snapshot = create(project, controller_root=controller)
    try:
        assert [entry.path for entry in snapshot.files] == ["safe.txt"]
        assert not (snapshot.root / "linked.txt").exists()
    finally:
        cleanup(snapshot)


def test_snapshot_manifest_and_fingerprint_are_deterministic(tmp_path: Path) -> None:
    _Limits, _Error, cleanup, create = _workspace()
    project = tmp_path / "project"
    controller = tmp_path / "controller"
    project.mkdir()
    controller.mkdir()
    _write(project, "z.txt", "z")
    _write(project, "a.txt", "a")

    first = create(project, controller_root=controller)
    second = create(project, controller_root=controller)
    try:
        assert [entry.path for entry in first.files] == ["a.txt", "z.txt"]
        assert first.files == second.files
        assert first.fingerprint == second.fingerprint
        assert first.total_bytes == 2
    finally:
        cleanup(first)
        cleanup(second)


@pytest.mark.parametrize(
    ("limits", "files"),
    [
        ({"max_files": 1}, (("one.txt", "1"), ("two.txt", "2"))),
        ({"max_file_bytes": 1}, (("large.txt", "12"),)),
        ({"max_total_bytes": 1}, (("one.txt", "1"), ("two.txt", "2"))),
    ],
)
def test_snapshot_limits_fail_without_silent_omission(
    tmp_path: Path,
    limits: dict[str, int],
    files: tuple[tuple[str, str], ...],
) -> None:
    Limits, Error, _cleanup, create = _workspace()
    project = tmp_path / "project"
    controller = tmp_path / "controller"
    project.mkdir()
    controller.mkdir()
    for relative, content in files:
        _write(project, relative, content)

    with pytest.raises(Error, match="limit"):
        create(project, controller_root=controller, limits=Limits(**limits))

    assert list(controller.iterdir()) == []


def test_snapshot_detects_source_replacement_race_and_discards_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _Limits, Error, _cleanup, create = _workspace()
    import agent_foundations.execution.workspace as workspace

    project = tmp_path / "project"
    controller = tmp_path / "controller"
    project.mkdir()
    controller.mkdir()
    source = _write(project, "src/app.py", "before")
    real_copy = workspace._copy_file_contents

    def replace_after_copy(source_path: Path, destination: Path) -> str:
        digest = real_copy(source_path, destination)
        source.write_text("after-with-different-size", encoding="utf-8")
        return digest

    monkeypatch.setattr(workspace, "_copy_file_contents", replace_after_copy)

    with pytest.raises(Error, match="changed during snapshot"):
        create(project, controller_root=controller)
    assert list(controller.iterdir()) == []


def test_snapshot_rejects_controller_inside_project(tmp_path: Path) -> None:
    _Limits, Error, _cleanup, create = _workspace()
    project = tmp_path / "project"
    project.mkdir()
    controller = project / ".controller"
    controller.mkdir()

    with pytest.raises(Error, match="outside project"):
        create(project, controller_root=controller)
