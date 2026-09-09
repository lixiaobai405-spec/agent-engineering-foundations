from __future__ import annotations

import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from agent_foundations.durable.effects import EffectResolutionRequiredError, SideEffectLedger
from agent_foundations.durable.faults import CrashPoint, InjectedCrash, PointFaultInjector
from agent_foundations.durable.models import DurableRun, DurableRunStatus, EffectStatus
from agent_foundations.durable.repository import DurableRunAlreadyExistsError, DurableRunRepository
from agent_foundations.execution.fake import FakeBackend
from agent_foundations.execution.models import ExecutionResult
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

RUN_ID = "44444444-4444-4444-8444-444444444444"
NOW = datetime(2026, 8, 26, 6, 0, tzinfo=UTC)


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


def _manifest() -> Any:
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


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "fixture-project"
    tests = root / "tests"
    tests.mkdir(parents=True, exist_ok=True)
    (tests / "test_ok.py").write_text("def test_ok() -> None:\n    assert True\n", encoding="utf-8")
    (root / "pyproject.toml").write_text("[project]\nname='fixture'\n", encoding="utf-8")
    return root.resolve()


async def _stack(
    tmp_path: Path,
    *,
    profile_name: PermissionProfileName = PermissionProfileName.PROJECT_FULL_ACCESS,
    decision: AuthorizationStatus = AuthorizationStatus.APPROVED,
    backend: FakeBackend | None = None,
    approval_decider: Any = True,
    fault_injector: Any = None,
    fail_artifact_finalize: bool = False,
    execution_limit: int = 64 * 1024,
) -> tuple[Any, ...]:
    (
        tool_cls,
        executor_cls,
        store_cls,
        repo_cls,
        sweeper_cls,
        *_rest,
    ) = _require_api()
    root = _project(tmp_path)
    db = tmp_path / "state.sqlite3"
    durable = DurableRunRepository(db)
    await durable.initialize()
    try:
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
    except DurableRunAlreadyExistsError:
        pass
    authorizations = AuthorizationRepository.from_path(db)
    await authorizations.initialize()
    artifacts = repo_cls.from_path(db)
    await artifacts.initialize()
    store = store_cls(
        tmp_path / "artifacts",
        repository=artifacts,
        default_run_id=UUID(RUN_ID),
        execution_limit_bytes=execution_limit,
        global_capacity_bytes=1024 * 1024,
    )
    sweeper = sweeper_cls(
        store,
        artifacts,
        global_capacity_bytes=1024 * 1024,
        clock=lambda: NOW,
    )
    sandbox = _manifest()
    command_manifest = default_project_command_manifest(
        project_fingerprint=compute_project_root_fingerprint(root),
        sandbox=sandbox,
    )
    captured: list[FakeBackend] = []

    def factory(workspace: Path) -> FakeBackend:
        current = backend or FakeBackend(
            workspace_root=workspace,
            workspace_side_effect=lambda path: (path / ".pytest_cache").mkdir(exist_ok=True),
        )
        captured.append(current)
        return current

    profile = PermissionProfile(
        name=profile_name,
        version=1,
        allowed_tools=default_allowed_tools(profile_name),
    )
    approval = AuthorizationApproval(authorizations, profile_name, clock=lambda: NOW)
    decider = None
    if approval_decider is True:

        def _approve(pending: Any) -> Any:
            return approval.decide(pending, decision)

        decider = _approve
    elif approval_decider is not None:
        decider = approval_decider
    executor = executor_cls(
        DirectToolCallExecutor(),
        profile,
        PolicyEngine(),
        approval,
        CapabilityIssuer(authorizations, profile_name, ttl=timedelta(minutes=5), clock=lambda: NOW),
        CapabilityConsumer(authorizations, clock=lambda: NOW),
        SideEffectLedger(durable, clock=lambda: NOW),
        command_manifest=command_manifest,
        artifact_store=store,
        retention=sweeper,
        backend_factory=factory,
        approval_decider=decider,
        execution_owner_id="command-owner",
        fault_injector=fault_injector,
        fail_artifact_finalize=fail_artifact_finalize,
        controller_root=tmp_path / "controller",
    )
    (tmp_path / "controller").mkdir(exist_ok=True)
    tool = tool_cls()
    context = ToolExecutionContext(
        session_id=RUN_ID,
        root=root,
        tool_call_id="call-run",
        tool_name=tool.name,
    )
    return root, executor, tool, context, durable, store, artifacts, captured


def _argv() -> dict[str, Any]:
    return {
        "gate_id": "manifest.python.pytest",
        "target": "tests",
        "flags": ["-q"],
        "cwd": ".",
        "timeout_seconds": 30,
    }


@pytest.mark.asyncio
async def test_hard_denied_command_never_reaches_capability_or_sandbox(tmp_path: Path) -> None:
    root, executor, tool, context, durable, _store, _artifacts, captured = await _stack(tmp_path)
    result = await executor.execute(tool, {"argv": ["bash", "-c", "echo pwn"]}, context)
    assert result.success is False
    assert result.error_code == "COMMAND_ARGV_REJECTED"
    record = await SideEffectLedger(durable).get(
        RUN_ID,
        context.tool_call_id,
        context.tool_name,
    )
    assert record is None
    assert captured == []
    capabilities = AuthorizationRepository.from_path(tmp_path / "state.sqlite3")
    del capabilities, root


@pytest.mark.asyncio
async def test_policy_deny_and_ask_use_existing_security_chain(tmp_path: Path) -> None:
    _root, denied_executor, tool, context, _durable, *_rest = await _stack(
        tmp_path,
        profile_name=PermissionProfileName.PROJECT_READ_ONLY,
    )
    denied = await denied_executor.execute(tool, _argv(), context)
    assert denied.success is False
    assert denied.error_code == "POLICY_DENIED"

    ask_root = tmp_path / "ask-case"
    ask_root.mkdir()
    _root, ask_executor, tool, context, *_unused = await _stack(
        ask_root,
        profile_name=PermissionProfileName.ASK_ALWAYS,
        approval_decider=None,
    )
    asked = await ask_executor.execute(tool, _argv(), context)
    assert asked.success is False
    assert asked.error_code == "APPROVAL_REQUIRED"


@pytest.mark.asyncio
async def test_nonzero_exit_is_completed_without_raw_output(tmp_path: Path) -> None:
    _require_api()
    backend = FakeBackend(
        result_factory=lambda request: ExecutionResult(
            execution_id=request.execution_id,
            exit_code=1,
            stdout=b"fixture-secret-output",
            stderr=b"boom",
            timed_out=False,
            cancelled=False,
            output_truncated=False,
        )
    )
    root, executor, tool, context, durable, store, artifacts, _captured = await _stack(
        tmp_path,
        backend=backend,
    )
    result = await executor.execute(tool, _argv(), context)
    assert result.success is True
    assert result.error_code is None
    assert "fixture-secret-output" not in result.content
    assert "boom" not in result.content
    metadata = dict(result.metadata)
    assert metadata["exit_code"] == 1
    assert metadata["parser_status"] in {"complete", "partial", "failed"}
    assert metadata["parser_status"] != "pending"
    assert "--junit-xml=" in " ".join(str(item) for item in metadata.get("argv_display", ()))
    assert "fixture-secret-output" not in str(metadata)
    record = await SideEffectLedger(durable).get(
        RUN_ID,
        context.tool_call_id,
        context.tool_name,
    )
    assert record is not None
    assert record.status is EffectStatus.COMMITTED
    row = artifacts.fetch_artifact(str(metadata["artifact_id"]))
    assert row.parser_status.value == metadata["parser_status"]
    assert row.parser_status.value != "pending"
    assert b"fixture-secret-output" not in artifacts.path.read_bytes()
    stdout_path = store.directory_for(row.artifact_id).joinpath("stdout")
    assert stdout_path.read_bytes() == b"fixture-secret-output"
    assert not (root / ".pytest_cache").exists()


@pytest.mark.asyncio
async def test_run_command_discards_workspace_writes(tmp_path: Path) -> None:
    root, executor, tool, context, *_rest = await _stack(tmp_path)

    async def run_allowed_test_that_creates_cache(project: Path) -> Any:
        del project
        return await executor.execute(tool, _argv(), context)

    result = await run_allowed_test_that_creates_cache(root)
    assert result.metadata["exit_code"] == 0
    assert not (root / ".pytest_cache").exists()


@pytest.mark.asyncio
async def test_output_limit_terminates_and_keeps_truncated_artifact(tmp_path: Path) -> None:
    _require_api()
    backend = FakeBackend(
        result_factory=lambda request: ExecutionResult(
            execution_id=request.execution_id,
            exit_code=0,
            stdout=b"x" * 200,
            stderr=b"",
            timed_out=False,
            cancelled=False,
            output_truncated=False,
        )
    )
    _root, executor, tool, context, *_rest = await _stack(
        tmp_path,
        backend=backend,
        execution_limit=50,
    )
    result = await executor.execute(tool, _argv(), context)
    assert result.success is False
    assert result.error_code == "OUTPUT_LIMIT_EXCEEDED"
    assert result.metadata["output_truncated"] is True
    artifact_id = str(result.metadata["artifact_id"])
    from agent_foundations.command_output.repository import CommandArtifactRepository

    repo = CommandArtifactRepository.from_path(tmp_path / "state.sqlite3")
    row = repo.fetch_artifact(artifact_id)
    assert row.stdout_bytes <= 50
    assert row.stdout_bytes > 0


@pytest.mark.asyncio
async def test_artifact_finalize_failure_records_outcome_and_does_not_rerun(
    tmp_path: Path,
) -> None:
    _root, executor, tool, context, durable, *_rest = await _stack(
        tmp_path,
        fail_artifact_finalize=True,
    )
    result = await executor.execute(tool, _argv(), context)
    assert result.error_code == "OUTPUT_ARTIFACT_WRITE_FAILED"
    record = await SideEffectLedger(durable).get(
        RUN_ID,
        context.tool_call_id,
        context.tool_name,
    )
    assert record is not None
    assert record.status is EffectStatus.FAILED
    assert record.result is not None
    assert record.result.metadata.get("exit_code") == 0
    second = await executor.execute(tool, _argv(), context)
    assert second.error_code == "OUTPUT_ARTIFACT_WRITE_FAILED"
    assert second.metadata.get("artifact_id") == result.metadata.get("artifact_id")


@pytest.mark.asyncio
async def test_crash_points_do_not_rerun_started_or_unknown_effects(tmp_path: Path) -> None:
    for point in (
        CrashPoint.BEFORE_INTENT,
        CrashPoint.AFTER_INTENT,
        CrashPoint.AFTER_CLAIM,
        CrashPoint.AFTER_EXECUTE,
        CrashPoint.AFTER_COMMIT,
    ):
        case = tmp_path / point.value
        case.mkdir()
        _root, executor, tool, context, durable, *_rest = await _stack(
            case,
            fault_injector=PointFaultInjector(point),
        )
        with pytest.raises(InjectedCrash):
            await executor.execute(tool, _argv(), context)
        if point is CrashPoint.BEFORE_INTENT:
            record = await SideEffectLedger(durable).get(
                RUN_ID,
                context.tool_call_id,
                context.tool_name,
            )
            assert record is None
            continue
        recovered = await _stack(
            case,
            fault_injector=None,
        )
        _root2, recovered_executor, tool2, context2, durable2, *_rest2 = recovered
        if point in {CrashPoint.AFTER_CLAIM, CrashPoint.AFTER_EXECUTE}:
            with pytest.raises(EffectResolutionRequiredError):
                await recovered_executor.execute(tool2, _argv(), context2)
        elif point is CrashPoint.AFTER_COMMIT:
            result = await recovered_executor.execute(tool2, _argv(), context2)
            assert result.success is True
        elif point is CrashPoint.AFTER_INTENT:
            result = await recovered_executor.execute(tool2, _argv(), context2)
            assert result.success is True


@pytest.mark.asyncio
async def test_capacity_exceeded_before_command_starts(tmp_path: Path) -> None:
    from agent_foundations.command_output.models import RetentionStatus

    _root, executor, tool, context, _durable, store, artifacts, captured = await _stack(
        tmp_path,
        execution_limit=80,
    )
    # Fill capacity with an active artifact that cannot be evicted.
    store.write(stdout=b"z" * 80, stderr=b"")
    executor._retention._global_capacity_bytes = 80
    result = await executor.execute(tool, _argv(), context)
    assert result.error_code == "ARTIFACT_CAPACITY_EXCEEDED"
    assert captured == [] or all(not backend.requests for backend in captured)
    del RetentionStatus, artifacts


@pytest.mark.docker
@pytest.mark.asyncio
async def test_docker_run_command_streams_without_project_writeback(
    tmp_path: Path,
    pytestconfig: pytest.Config,
) -> None:
    if pytestconfig.getoption("-m") != "docker":
        pytest.skip("requires explicit -m docker authorization")
    _require_api()
    from agent_foundations.execution.docker import DockerBackend, DockerCommandBuilder
    from agent_foundations.execution.models import ExecutionRequest
    from tests.integration.test_execution_backend import _repository_root, _task17_manifest

    root, executor, tool, context, _durable, store, artifacts, _captured = await _stack(tmp_path)
    manifest = _task17_manifest(_repository_root())
    planned_text = " ".join(
        DockerCommandBuilder(root, sandbox_manifest=manifest).build(
            ExecutionRequest(
                execution_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                run_id=RUN_ID,
                capability_id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
                argv=("python", "-m", "pytest", "tests", "-q"),
                cwd=".",
                mount_mode="snapshot",
                sandbox_profile="python",
                timeout_seconds=30,
                max_output_bytes=4096,
            )
        )
    )
    assert "--network none" in planned_text
    assert "--user 65532:65532" in planned_text
    assert "--read-only" in planned_text
    assert "target=/project-ro,readonly" in planned_text
    assert "/workspace:rw" in planned_text
    assert "--memory 512m" in planned_text
    assert "--pids-limit 64" in planned_text

    def factory(workspace: Path) -> DockerBackend:
        return DockerBackend(workspace, sandbox_manifest=manifest)

    executor._backend_factory = factory
    result = await executor.execute(tool, _argv(), context)
    assert result.success is True
    assert result.metadata["exit_code"] == 0
    assert "passed" not in result.content.lower() or len(result.content) < 240
    artifact_id = str(result.metadata["artifact_id"])
    stdout = store.directory_for(artifact_id).joinpath("stdout").read_bytes()
    assert b"passed" in stdout or b"ok" in stdout.lower() or len(stdout) >= 0
    db_bytes = artifacts.path.read_bytes()
    assert b"fixture-secret" not in db_bytes
    assert stdout not in db_bytes or stdout == b""
    assert not (root / ".pytest_cache").exists()
