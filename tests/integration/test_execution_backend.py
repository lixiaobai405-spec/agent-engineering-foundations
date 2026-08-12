from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
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
