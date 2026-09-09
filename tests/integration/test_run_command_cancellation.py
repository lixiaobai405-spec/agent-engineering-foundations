from __future__ import annotations

import asyncio
import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from agent_foundations.durable.effects import SideEffectLedger
from agent_foundations.durable.models import DurableRun, DurableRunStatus
from agent_foundations.durable.repository import DurableRunRepository
from agent_foundations.execution.fake import FakeBackend
from agent_foundations.runtime.tool_execution import DirectToolCallExecutor, ToolExecutionContext
from agent_foundations.security.approvals import AuthorizationApproval, AuthorizationStatus
from agent_foundations.security.capabilities import CapabilityConsumer, CapabilityIssuer
from agent_foundations.security.models import (
    PermissionProfile,
    PermissionProfileName,
    default_allowed_tools,
)
from agent_foundations.security.policy import PolicyEngine
from agent_foundations.security.repository import AuthorizationRepository
from agent_foundations.tools.command.config import default_project_command_manifest
from agent_foundations.tools.patch.models import compute_project_root_fingerprint

RUN_ID = "55555555-5555-4555-8555-555555555555"
NOW = datetime(2026, 8, 26, 6, 30, tzinfo=UTC)


def _require_api() -> Any:
    try:
        spec = importlib.util.find_spec("agent_foundations.tools.command.run_command")
    except ModuleNotFoundError:
        spec = None
    assert spec is not None, "run_command tool is missing"
    from agent_foundations.command_output.repository import CommandArtifactRepository
    from agent_foundations.command_output.retention import ArtifactRetentionSweeper
    from agent_foundations.command_output.store import CommandArtifactStore
    from agent_foundations.execution.sandbox_manifest import (
        SandboxImageProvenance,
        SandboxManifest,
    )
    from agent_foundations.tools.command.run_command import (
        ControlledCommandExecutor,
        RunCommandTool,
    )

    return (
        RunCommandTool,
        ControlledCommandExecutor,
        CommandArtifactStore,
        CommandArtifactRepository,
        ArtifactRetentionSweeper,
        SandboxManifest,
        SandboxImageProvenance,
    )


def _sandbox() -> Any:
    *_rest, sandbox_cls, provenance_cls = _require_api()

    def provenance(profile: str) -> Any:
        name = "python" if profile == "python" else "node"
        return provenance_cls(
            profile=profile,
            image_tag=f"agent-foundations-sandbox-{name}:phase2d",
            base_repo_digest=f"{name}@sha256:{'a' * 64}",
            lockfile_sha256="b" * 64,
            final_image_id=f"sha256:{'c' * 64}",
        )

    return sandbox_cls(python=provenance("python"), node=provenance("node"))


async def _executor(
    tmp_path: Path,
    backend: FakeBackend,
) -> tuple[Any, ...]:
    (
        tool_cls,
        executor_cls,
        store_cls,
        repo_cls,
        sweeper_cls,
        *_rest,
    ) = _require_api()
    root = tmp_path / "project"
    (root / "tests").mkdir(parents=True)
    (root / "tests" / "test_ok.py").write_text(
        "def test_ok() -> None:\n    assert True\n",
        encoding="utf-8",
    )
    db = tmp_path / "state.sqlite3"
    durable = DurableRunRepository(db)
    await durable.initialize()
    await durable.create_run(
        DurableRun(
            run_id=RUN_ID,
            project_root=str(root),
            status=DurableRunStatus.CREATED,
            schema_version=1,
            state_version=0,
            attempt=1,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    authorizations = AuthorizationRepository.from_path(db)
    await authorizations.initialize()
    artifacts = repo_cls.from_path(db)
    await artifacts.initialize()
    store = store_cls(tmp_path / "artifacts", repository=artifacts)
    sweeper = sweeper_cls(store, artifacts, clock=lambda: NOW)
    (tmp_path / "controller").mkdir()
    profile = PermissionProfile(
        name=PermissionProfileName.PROJECT_FULL_ACCESS,
        version=1,
        allowed_tools=default_allowed_tools(PermissionProfileName.PROJECT_FULL_ACCESS),
    )
    approval = AuthorizationApproval(
        authorizations,
        PermissionProfileName.PROJECT_FULL_ACCESS,
        clock=lambda: NOW,
    )
    command_manifest = default_project_command_manifest(
        project_fingerprint=compute_project_root_fingerprint(root),
        sandbox=_sandbox(),
    )
    executor = executor_cls(
        DirectToolCallExecutor(),
        profile,
        PolicyEngine(),
        approval,
        CapabilityIssuer(
            authorizations,
            PermissionProfileName.PROJECT_FULL_ACCESS,
            ttl=timedelta(minutes=5),
            clock=lambda: NOW,
        ),
        CapabilityConsumer(authorizations, clock=lambda: NOW),
        SideEffectLedger(durable, clock=lambda: NOW),
        command_manifest=command_manifest,
        artifact_store=store,
        retention=sweeper,
        backend_factory=lambda _workspace: backend,
        approval_decider=lambda pending: approval.decide(pending, AuthorizationStatus.APPROVED),
        execution_owner_id="command-owner",
        controller_root=tmp_path / "controller",
    )
    tool = tool_cls()
    context = ToolExecutionContext(
        session_id=RUN_ID,
        root=root,
        tool_call_id=f"call-{uuid4()}",
        tool_name=tool.name,
    )
    return executor, tool, context, backend


@pytest.mark.asyncio
async def test_run_command_cancel_stops_active_execution(tmp_path: Path) -> None:
    backend = FakeBackend(block=True)
    executor, tool, context, backend = await _executor(tmp_path, backend)
    running = asyncio.create_task(
        executor.execute(
            tool,
            {
                "gate_id": "manifest.python.pytest",
                "target": "tests",
                "flags": ["-q"],
                "timeout_seconds": 30,
            },
            context,
        )
    )
    for _attempt in range(50):
        if backend.active_execution_ids:
            break
        await asyncio.sleep(0.01)
    assert backend.active_execution_ids
    execution_id = backend.active_execution_ids[0]
    await executor.cancel(execution_id)
    result = await running
    assert result.metadata["cancelled"] is True
    assert result.metadata["timed_out"] is False
    assert backend.active_execution_ids == ()


@pytest.mark.asyncio
async def test_run_command_timeout_is_exact_and_does_not_leave_active_backend(
    tmp_path: Path,
) -> None:
    _require_api()
    backend = FakeBackend(block=True, honor_timeout=True)
    executor, tool, context, backend = await _executor(tmp_path, backend)
    result = await executor.execute(
        tool,
        {
            "gate_id": "manifest.python.pytest",
            "target": "tests",
            "flags": ["-q"],
            "timeout_seconds": 1,
        },
        context,
    )
    assert result.metadata["timed_out"] is True
    assert result.metadata["cancelled"] is False
    assert backend.active_execution_ids == ()


@pytest.mark.docker
@pytest.mark.asyncio
async def test_docker_cancel_and_timeout_cleanup_af_containers(
    tmp_path: Path,
    pytestconfig: pytest.Config,
) -> None:
    if pytestconfig.getoption("-m") != "docker":
        pytest.skip("requires explicit -m docker authorization")
    _require_api()
    from agent_foundations.execution.docker import DockerBackend, container_name
    from tests.integration.test_execution_backend import (
        _container_exists,
        _repository_root,
        _task17_manifest,
    )
    from tests.integration.test_run_command_flow import _stack

    root, executor, tool, context, _durable, _store, _artifacts, _captured = await _stack(
        tmp_path
    )
    (root / "tests" / "test_ok.py").write_text(
        "import time\n\n\ndef test_hang() -> None:\n    time.sleep(30)\n",
        encoding="utf-8",
    )
    manifest = _task17_manifest(_repository_root())

    def factory(workspace: Path) -> DockerBackend:
        return DockerBackend(workspace, sandbox_manifest=manifest)

    executor._backend_factory = factory
    timeout_result = await executor.execute(
        tool,
        {
            "gate_id": "manifest.python.pytest",
            "target": "tests",
            "flags": ["-q"],
            "cwd": ".",
            "timeout_seconds": 3,
        },
        context,
    )
    assert timeout_result.metadata["timed_out"] is True
    leftover = await _container_exists(container_name(str(uuid4())))
    assert leftover is False
    assert executor._active_execution_id is None
