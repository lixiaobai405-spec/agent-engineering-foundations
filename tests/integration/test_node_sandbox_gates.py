from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FIXTURE = _REPO_ROOT / "tests" / "fixtures" / "phase2_node_sandbox_project"
_PROBE = (
    "const fs=require('fs');const path=require('path');"
    "const nm='/workspace/node_modules';"
    "const st=fs.lstatSync(nm);"
    "const bin=fs.lstatSync(path.join(nm,'.bin'));"
    "let storeWriteFailed=false;"
    "try{fs.writeFileSync('/opt/sandbox/node_modules/.vite-temp-probe','x')}"
    "catch{storeWriteFailed=true}"
    "let parentWriteOk=false;"
    "try{fs.mkdirSync(path.join(nm,'.vite-overlay-probe'));parentWriteOk=true}"
    "catch{parentWriteOk=false}"
    "console.log(JSON.stringify({"
    "node_modules_is_dir:st.isDirectory(),"
    "node_modules_is_symlink:st.isSymbolicLink(),"
    "bin_is_symlink:bin.isSymbolicLink(),"
    "store_write_failed:storeWriteFailed,"
    "parent_write_ok:parentWriteOk"
    "}));"
)


def _require_docker_marker(pytestconfig: pytest.Config) -> None:
    if pytestconfig.getoption("-m") != "docker":
        pytest.skip("requires explicit -m docker authorization")


def _copy_fixture(tmp_path: Path) -> Path:
    assert not (_FIXTURE / "node_modules").exists()
    project = tmp_path / "project"
    shutil.copytree(_FIXTURE, project)
    assert not (project / "node_modules").exists()
    package = json.loads((project / "package.json").read_text(encoding="utf-8"))
    assert package["scripts"] == {
        "test:chat": "vitest run",
        "typecheck:chat": "tsc --noEmit",
        "build:chat": "vite build",
    }
    return project


async def _run_node(
    project: Path,
    controller: Path,
    argv: tuple[str, ...],
) -> Any:
    from agent_foundations.execution.docker import DockerBackend, DockerCommandBuilder
    from agent_foundations.execution.models import ExecutionRequest
    from agent_foundations.execution.sandbox_manifest import SandboxManifest
    from agent_foundations.execution.workspace import (
        cleanup_workspace_snapshot,
        create_workspace_snapshot,
    )

    manifest = SandboxManifest.load_pinned(_REPO_ROOT)
    snapshot = create_workspace_snapshot(project, controller_root=controller)
    request = ExecutionRequest(
        execution_id=str(uuid4()),
        run_id=str(uuid4()),
        capability_id=str(uuid4()),
        argv=argv,
        cwd=".",
        mount_mode="snapshot",
        sandbox_profile="node",
        timeout_seconds=120,
        max_output_bytes=1_048_576,
    )
    built = DockerCommandBuilder(snapshot.root, sandbox_manifest=manifest).build(request)
    assert built[built.index("--network") + 1] == "none"
    assert "--read-only" in built
    assert built[built.index("--pull") + 1] == "never"
    try:
        return await DockerBackend(snapshot.root, sandbox_manifest=manifest).execute(
            request
        )
    finally:
        cleanup_workspace_snapshot(snapshot)


@pytest.mark.docker
@pytest.mark.asyncio
@pytest.mark.parametrize("script", ["test:chat", "typecheck:chat", "build:chat"])
async def test_repaired_node_fixture_exact_gates_exit_zero(
    tmp_path: Path,
    pytestconfig: pytest.Config,
    script: str,
) -> None:
    _require_docker_marker(pytestconfig)
    project = _copy_fixture(tmp_path)
    controller = tmp_path / "controller"
    controller.mkdir()
    result = await _run_node(project, controller, ("npm", "run", script))
    assert result.exit_code == 0
    assert result.timed_out is False
    assert result.cancelled is False


@pytest.mark.docker
@pytest.mark.asyncio
async def test_node_modules_is_writable_dir_with_store_entry_symlinks(
    tmp_path: Path,
    pytestconfig: pytest.Config,
) -> None:
    _require_docker_marker(pytestconfig)
    project = _copy_fixture(tmp_path)
    controller = tmp_path / "controller"
    controller.mkdir()
    result = await _run_node(project, controller, ("node", "-e", _PROBE))
    assert result.exit_code == 0
    payload = json.loads(result.stdout.decode("utf-8"))
    assert payload["node_modules_is_dir"] is True
    assert payload["node_modules_is_symlink"] is False
    assert payload["bin_is_symlink"] is True
    assert payload["store_write_failed"] is True
    assert payload["parent_write_ok"] is True
