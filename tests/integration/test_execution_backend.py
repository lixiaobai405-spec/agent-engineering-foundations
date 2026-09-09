from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

import pytest


def _execution() -> tuple[Any, ...]:
    assert importlib.util.find_spec("agent_foundations.execution") is not None, (
        "Task 14 execution package is missing"
    )
    assert importlib.util.find_spec("agent_foundations.execution.container_runner") is not None, (
        "Task 14 authorized container runner is missing"
    )
    from agent_foundations.execution.container_runner import (
        CapabilityBindingError,
        ContainerRunner,
    )
    from agent_foundations.execution.docker import DockerBackend
    from agent_foundations.execution.fake import FakeBackend
    from agent_foundations.execution.models import ExecutionRequest
    from agent_foundations.security.capabilities import Capability
    from agent_foundations.security.models import PolicyResource, ResourceScope

    return (
        ContainerRunner,
        CapabilityBindingError,
        FakeBackend,
        DockerBackend,
        ExecutionRequest,
        Capability,
        PolicyResource,
        ResourceScope,
    )


def _bound_pair(**request_changes: object) -> tuple[Any, Any]:
    (
        _ContainerRunner,
        _CapabilityBindingError,
        _FakeBackend,
        _DockerBackend,
        ExecutionRequest,
        Capability,
        PolicyResource,
        ResourceScope,
    ) = _execution()
    run_id = str(uuid4())
    capability_id = str(uuid4())
    now = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
    values: dict[str, object] = {
        "execution_id": str(uuid4()),
        "run_id": run_id,
        "capability_id": capability_id,
        "argv": ("python", "-c", "print('ok')"),
        "cwd": ".",
        "mount_mode": "read_only",
        "timeout_seconds": 5,
        "max_output_bytes": 4096,
    }
    values.update(request_changes)
    request = ExecutionRequest.model_validate(values)
    capability = Capability(
        capability_id=capability_id,
        authorization_id=str(uuid4()),
        run_id=run_id,
        tool_call_id="call-execute",
        tool_name="run_command",
        resource=PolicyResource(
            kind="process",
            scope=ResourceScope.PROJECT_INTERNAL,
            identifier="sandbox",
            category="test",
        ),
        operation="execute",
        profile_version=1,
        issued_at=now,
        expires_at=now + timedelta(minutes=5),
        consumed_at=now + timedelta(seconds=1),
    )
    return request, capability


def _task17_manifest(root: Path) -> Any:
    from agent_foundations.execution.sandbox_manifest import (
        SandboxImageProvenance,
        SandboxManifest,
    )

    profiles: tuple[
        tuple[Literal["python", "node"], str, str | None, Path], ...
    ] = (
        (
            "python",
            "agent-foundations-sandbox-python:phase2d",
            "python@sha256:4766d8b510c428e595d74b9cc5bbb2fae8e26316fffb4adc89908d79aacd58a2",
            root / "docker/agent-sandbox-python.requirements.lock",
        ),
        (
            "node",
            "agent-foundations-sandbox-node:phase2d",
            None,
            root / "package-lock.json",
        ),
    )
    provenance: dict[Literal["python", "node"], SandboxImageProvenance] = {}
    for profile, tag, expected_base, lockfile in profiles:
        completed = subprocess.run(
            ["docker", "image", "inspect", tag],
            check=True,
            capture_output=True,
            text=True,
        )
        inspected = json.loads(completed.stdout)[0]
        labels = inspected["Config"]["Labels"]
        lock_hash = hashlib.sha256(lockfile.read_bytes()).hexdigest()
        assert labels["io.agent-foundations.sandbox-profile"] == profile
        assert labels["io.agent-foundations.lockfile-sha256"] == lock_hash
        if expected_base is not None:
            assert labels["io.agent-foundations.base-repo-digest"] == expected_base
        base_digest = labels["io.agent-foundations.base-repo-digest"]
        repo_digests = inspected.get("RepoDigests") or []
        final_repo_digest = next(
            (
                digest
                for digest in repo_digests
                if digest.startswith(f"agent-foundations-sandbox-{profile}@")
            ),
            None,
        )
        provenance[profile] = SandboxImageProvenance(
            profile=profile,
            image_tag=tag,
            base_repo_digest=base_digest,
            lockfile_sha256=lock_hash,
            final_image_id=inspected["Id"],
            final_repo_digest=final_repo_digest,
        )
    return SandboxManifest(python=provenance["python"], node=provenance["node"])


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


async def _wait_for_host_config(container: str) -> dict[str, Any]:
    stderr = b""
    for _attempt in range(50):
        process = await asyncio.create_subprocess_exec(
            "docker",
            "inspect",
            "--format",
            "{{json .HostConfig}}",
            container,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode == 0:
            parsed = json.loads(stdout)
            assert isinstance(parsed, dict)
            return parsed
        await asyncio.sleep(0.1)
    raise AssertionError(f"container did not become inspectable: {stderr!r}")


async def _container_exists(container: str) -> bool:
    process = await asyncio.create_subprocess_exec(
        "docker",
        "inspect",
        container,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    return await process.wait() == 0


@pytest.mark.asyncio
async def test_runner_calls_backend_only_for_exact_consumed_capability() -> None:
    ContainerRunner, _BindingError, FakeBackend, *_ = _execution()
    request, capability = _bound_pair()
    backend = FakeBackend()

    result = await ContainerRunner(backend).execute(request, capability)

    assert result.exit_code == 0
    assert backend.requests == [request]


@pytest.mark.asyncio
@pytest.mark.parametrize("mismatch", ["capability_id", "run_id", "unconsumed"])
async def test_runner_rejects_capability_mismatch_before_backend(
    mismatch: str,
) -> None:
    ContainerRunner, CapabilityBindingError, FakeBackend, *_ = _execution()
    request, capability = _bound_pair()
    if mismatch == "capability_id":
        request = request.model_copy(update={"capability_id": str(uuid4())})
    elif mismatch == "run_id":
        request = request.model_copy(update={"run_id": str(uuid4())})
    else:
        capability = capability.model_copy(update={"consumed_at": None})
    backend = FakeBackend()

    with pytest.raises(CapabilityBindingError):
        await ContainerRunner(backend).execute(request, capability)

    assert backend.requests == []


@pytest.mark.asyncio
async def test_runner_rejects_corrupt_consumption_window_before_backend() -> None:
    ContainerRunner, CapabilityBindingError, FakeBackend, *_ = _execution()
    request, capability = _bound_pair()
    capability = capability.model_copy(update={"consumed_at": capability.expires_at})
    backend = FakeBackend()

    with pytest.raises(CapabilityBindingError):
        await ContainerRunner(backend).execute(request, capability)

    assert backend.requests == []


@pytest.mark.docker
@pytest.mark.asyncio
async def test_real_docker_sandbox_readonly_smoke(
    tmp_path: Path,
    pytestconfig: pytest.Config,
) -> None:
    if pytestconfig.getoption("-m") != "docker":
        pytest.skip("requires explicit -m docker authorization")
    ContainerRunner, _BindingError, _FakeBackend, DockerBackend, *_ = _execution()
    project = tmp_path / "project"
    project.mkdir()
    script = (
        "import json,os,socket,pathlib; "
        "state={'root_readonly':False,'workspace_readonly':False}; "
        "exec(\"try:\\n pathlib.Path('/probe').write_text('x')\\n"
        "except OSError:\\n state['root_readonly']=True\"); "
        "exec(\"try:\\n pathlib.Path('/workspace/probe').write_text('x')\\n"
        "except OSError:\\n state['workspace_readonly']=True\"); "
        "print(json.dumps({'uid':os.getuid(),**state,"
        "'interfaces':socket.if_nameindex(),"
        "'docker_socket':pathlib.Path('/var/run/docker.sock').exists()}))"
    )
    request, capability = _bound_pair(argv=("python", "-c", script))
    result = await ContainerRunner(DockerBackend(project)).execute(request, capability)
    payload = json.loads(result.stdout)

    assert result.exit_code == 0
    assert payload["uid"] != 0
    assert payload["root_readonly"] is True
    assert payload["workspace_readonly"] is True
    assert [name for _index, name in payload["interfaces"]] == ["lo"]
    assert payload["docker_socket"] is False


@pytest.mark.docker
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("profile", "command"),
    [
        (
            "python",
            (
                "python",
                "-c",
                "import json,os,pathlib,socket; "
                "state={'root_readonly':False,'input_readonly':False}; "
                "exec(\"try:\\n pathlib.Path('/probe').write_text('x')\\n"
                "except OSError:\\n state['root_readonly']=True\"); "
                "exec(\"try:\\n pathlib.Path('/project-ro/probe').write_text('x')\\n"
                "except OSError:\\n state['input_readonly']=True\"); "
                "pathlib.Path('/workspace/generated.txt').write_text('ephemeral'); "
                "status=dict(line.split(':',1) for line in "
                "pathlib.Path('/proc/self/status').read_text().splitlines() if ':' in line); "
                "print(json.dumps({'runtime':os.sys.version_info[:2],"
                "'uid':os.getuid(),**state,'interfaces':socket.if_nameindex(),"
                "'docker_socket':pathlib.Path('/var/run/docker.sock').exists(),"
                "'conda':pathlib.Path('/opt/conda').exists(),"
                "'secret_visible':pathlib.Path('/project-ro/.env').exists(),"
                "'no_new_privs':status['NoNewPrivs'].strip(),"
                "'cap_eff':status['CapEff'].strip()}))",
            ),
        ),
        (
            "node",
            (
                "node",
                "-e",
                "const fs=require('fs'),os=require('os');"
                "let state={root_readonly:false,input_readonly:false};"
                "try{fs.writeFileSync('/probe','x')}catch{state.root_readonly=true}"
                "try{fs.writeFileSync('/project-ro/probe','x')}"
                "catch{state.input_readonly=true}"
                "fs.writeFileSync('/workspace/generated.txt','ephemeral');"
                "const status=Object.fromEntries(fs.readFileSync('/proc/self/status','utf8')"
                ".split('\\n').filter(x=>x.includes(':')).map(x=>x.split(/:(.*)/s).slice(0,2)));"
                "console.log(JSON.stringify({runtime:process.versions.node,"
                "npm:require('child_process').execFileSync('npm',['--version'],"
                "{encoding:'utf8'}).trim(),"
                "uid:process.getuid(),...state,interfaces:Object.keys(os.networkInterfaces()),"
                "docker_socket:fs.existsSync('/var/run/docker.sock'),"
                "conda:fs.existsSync('/opt/conda'),"
                "secret_visible:fs.existsSync('/project-ro/.env'),"
                "no_new_privs:status.NoNewPrivs.trim(),cap_eff:status.CapEff.trim()}))",
            ),
        ),
    ],
)
async def test_task17_fixed_profile_snapshot_smoke(
    tmp_path: Path,
    pytestconfig: pytest.Config,
    profile: Literal["python", "node"],
    command: tuple[str, ...],
) -> None:
    if pytestconfig.getoption("-m") != "docker":
        pytest.skip("requires explicit -m docker authorization")
    from agent_foundations.execution.docker import DockerBackend
    from agent_foundations.execution.models import ExecutionRequest
    from agent_foundations.execution.workspace import (
        cleanup_workspace_snapshot,
        create_workspace_snapshot,
    )

    root = _repository_root()
    project = tmp_path / "project"
    controller = tmp_path / "controller"
    project.mkdir()
    controller.mkdir()
    source = project / "source.txt"
    source.write_text("unchanged", encoding="utf-8")
    snapshot = create_workspace_snapshot(project, controller_root=controller)
    try:
        request = ExecutionRequest(
            execution_id=str(uuid4()),
            run_id=str(uuid4()),
            capability_id=str(uuid4()),
            argv=command,
            cwd=".",
            mount_mode="snapshot",
            sandbox_profile=profile,
            timeout_seconds=30,
            max_output_bytes=16_384,
        )
        result = await DockerBackend(
            snapshot.root,
            sandbox_manifest=_task17_manifest(root),
        ).execute(request)
    finally:
        cleanup_workspace_snapshot(snapshot)

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["uid"] != 0
    assert payload["root_readonly"] is True
    assert payload["input_readonly"] is True
    assert payload["interfaces"] in (["lo"], [[1, "lo"]])
    assert payload["docker_socket"] is False
    assert payload["conda"] is False
    assert payload["secret_visible"] is False
    assert payload["no_new_privs"] == "1"
    assert payload["cap_eff"] == "0000000000000000"
    if profile == "python":
        assert payload["runtime"] == [3, 12]
    else:
        assert payload["runtime"].startswith("22.")
        assert payload["npm"]
    assert source.read_text(encoding="utf-8") == "unchanged"
    assert not (project / "generated.txt").exists()


@pytest.mark.docker
@pytest.mark.asyncio
async def test_task17_runtime_limits_are_applied_to_live_container(
    tmp_path: Path,
    pytestconfig: pytest.Config,
) -> None:
    if pytestconfig.getoption("-m") != "docker":
        pytest.skip("requires explicit -m docker authorization")
    from agent_foundations.execution.docker import DockerBackend
    from agent_foundations.execution.models import ExecutionRequest
    from agent_foundations.execution.workspace import (
        cleanup_workspace_snapshot,
        create_workspace_snapshot,
    )

    root = _repository_root()
    project = tmp_path / "project"
    controller = tmp_path / "controller"
    project.mkdir()
    controller.mkdir()
    snapshot = create_workspace_snapshot(project, controller_root=controller)
    execution_id = str(uuid4())
    request = ExecutionRequest(
        execution_id=execution_id,
        run_id=str(uuid4()),
        capability_id=str(uuid4()),
        argv=("python", "-c", "import time; time.sleep(30)"),
        cwd=".",
        mount_mode="snapshot",
        sandbox_profile="python",
        timeout_seconds=60,
        max_output_bytes=4096,
    )
    backend = DockerBackend(snapshot.root, sandbox_manifest=_task17_manifest(root))
    running = asyncio.create_task(backend.execute(request))
    try:
        host_config = await _wait_for_host_config(f"af-{execution_id}")
        assert host_config["NetworkMode"] == "none"
        assert host_config["ReadonlyRootfs"] is True
        assert host_config["CapDrop"] == ["ALL"]
        assert "no-new-privileges" in host_config["SecurityOpt"]
        assert host_config["PidsLimit"] == 64
        assert host_config["NanoCpus"] == 1_000_000_000
        assert host_config["Memory"] == 512 * 1024 * 1024
        assert "/workspace" in host_config["Tmpfs"]
    finally:
        await backend.cancel(execution_id)
        result = await running
        cleanup_workspace_snapshot(snapshot)

    assert result.cancelled is True
    assert await _container_exists(f"af-{execution_id}") is False


@pytest.mark.docker
@pytest.mark.asyncio
async def test_task17_real_timeout_cleans_exact_container(
    tmp_path: Path,
    pytestconfig: pytest.Config,
) -> None:
    if pytestconfig.getoption("-m") != "docker":
        pytest.skip("requires explicit -m docker authorization")
    from agent_foundations.execution.docker import DockerBackend
    from agent_foundations.execution.models import ExecutionRequest
    from agent_foundations.execution.workspace import (
        cleanup_workspace_snapshot,
        create_workspace_snapshot,
    )

    root = _repository_root()
    project = tmp_path / "project"
    controller = tmp_path / "controller"
    project.mkdir()
    controller.mkdir()
    snapshot = create_workspace_snapshot(project, controller_root=controller)
    execution_id = str(uuid4())
    request = ExecutionRequest(
        execution_id=execution_id,
        run_id=str(uuid4()),
        capability_id=str(uuid4()),
        argv=("python", "-c", "import time; time.sleep(30)"),
        cwd=".",
        mount_mode="snapshot",
        sandbox_profile="python",
        timeout_seconds=1,
        max_output_bytes=4096,
    )
    try:
        result = await DockerBackend(
            snapshot.root,
            sandbox_manifest=_task17_manifest(root),
        ).execute(request)
    finally:
        cleanup_workspace_snapshot(snapshot)

    assert result.timed_out is True
    assert result.exit_code is None
    assert await _container_exists(f"af-{execution_id}") is False
