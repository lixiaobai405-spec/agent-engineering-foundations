from __future__ import annotations

import importlib.util
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from agent_foundations.durable.effects import SideEffectLedger
from agent_foundations.durable.models import DurableRun, DurableRunStatus, EffectStatus
from agent_foundations.durable.repository import DurableRunRepository
from agent_foundations.execution.docker import DockerBackend
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
from agent_foundations.tools.patch.applier import (
    PatchApplyError,
    apply_prepared_patch_atomically,
    prepare_patch,
)
from agent_foundations.tools.patch.repository import PatchProposalRepository
from agent_foundations.tools.patch.validator import parse_and_validate_patch
from tests.unit.tools.patch_test_helpers import sha256_bytes

RUN_ID = "33333333-3333-4333-8333-333333333333"
NOW = datetime(2026, 8, 12, 5, 45, tzinfo=UTC)


def _api() -> tuple[Any, ...]:
    assert importlib.util.find_spec("agent_foundations.tools.patch.apply_patch") is not None, (
        "Task 15 controlled apply_patch flow is missing"
    )
    from agent_foundations.tools.patch.apply_patch import ApplyPatchTool, ControlledPatchExecutor

    return ApplyPatchTool, ControlledPatchExecutor


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "fixture-project"
    (root / "src").mkdir(parents=True)
    (root / "README.md").write_text("before\n", encoding="utf-8", newline="\n")
    (root / "src" / "app.py").write_text("value = 1\n", encoding="utf-8", newline="\n")
    return root.resolve(strict=True)


def _diff() -> str:
    return """diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -1 +1 @@
-before
+after
diff --git a/src/new.py b/src/new.py
new file mode 100644
--- /dev/null
+++ b/src/new.py
@@ -0,0 +1 @@
+created = True
"""


async def _stack(
    tmp_path: Path,
    *,
    profile_name: PermissionProfileName = PermissionProfileName.PROJECT_FULL_ACCESS,
    decision: AuthorizationStatus = AuthorizationStatus.APPROVED,
    backend_factory: Any = None,
) -> tuple[Any, ...]:
    ApplyPatchTool, ControlledPatchExecutor = _api()
    root = _project(tmp_path)
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
    proposals = PatchProposalRepository.from_path(db)
    await proposals.initialize()
    patch = parse_and_validate_patch(
        _diff(),
        (
            {"path": "README.md", "sha256": sha256_bytes((root / "README.md").read_bytes())},
            {"path": "src/new.py", "sha256": None},
        ),
        root,
    )
    await proposals.save(RUN_ID, patch)
    authorizations = AuthorizationRepository.from_path(db)
    await authorizations.initialize()
    approval = AuthorizationApproval(authorizations, profile_name, clock=lambda: NOW)
    issuer = CapabilityIssuer(
        authorizations,
        profile_name,
        ttl=timedelta(minutes=5),
        clock=lambda: NOW,
    )
    consumer = CapabilityConsumer(authorizations, clock=lambda: NOW)
    ledger = SideEffectLedger(durable, clock=lambda: NOW)
    profile = PermissionProfile(
        name=profile_name,
        version=1,
        allowed_tools=default_allowed_tools(profile_name),
    )
    factory = backend_factory or (lambda project_root: DockerBackend(project_root))
    executor = ControlledPatchExecutor(
        DirectToolCallExecutor(),
        proposals,
        profile,
        PolicyEngine(),
        approval,
        issuer,
        consumer,
        ledger,
        backend_factory=factory,
        approval_decider=lambda pending: approval.decide(pending, decision),
        execution_owner_id="patch-owner",
    )
    tool = ApplyPatchTool()
    context = ToolExecutionContext(
        session_id=RUN_ID,
        root=root,
        tool_call_id="call-apply",
        tool_name=tool.name,
    )
    return root, patch, executor, tool, context, ledger, authorizations


@pytest.mark.docker
@pytest.mark.asyncio
async def test_controlled_patch_applies_modify_create_and_multifile_in_docker(
    tmp_path: Path,
) -> None:
    root, patch, executor, tool, context, ledger, authorizations = await _stack(tmp_path)

    result = await executor.execute(tool, {"patch_id": patch.patch_id}, context)

    assert result.success is True
    assert (root / "README.md").read_bytes() == b"after\n"
    assert (root / "src" / "new.py").read_bytes() == b"created = True\n"
    effect = await ledger.get(RUN_ID, context.tool_call_id, tool.name)
    assert effect is not None and effect.status is EffectStatus.COMMITTED
    capability = await authorizations.find_capability_for_execution(RUN_ID, context.tool_call_id)
    assert capability is not None and capability.consumed_at == NOW
    assert result.metadata["backend"] == "docker"
    assert result.metadata["mount_mode"] == "project_write"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "profile_name,decision",
    [
        (PermissionProfileName.PROJECT_READ_ONLY, AuthorizationStatus.APPROVED),
        (PermissionProfileName.ASK_ALWAYS, AuthorizationStatus.DENIED),
    ],
)
async def test_policy_or_human_deny_never_reaches_backend_or_ledger(
    tmp_path: Path,
    profile_name: PermissionProfileName,
    decision: AuthorizationStatus,
) -> None:
    class NeverBackend:
        calls = 0

        async def execute(self, request: Any) -> Any:
            self.calls += 1
            raise AssertionError("denied write reached backend")

        async def cancel(self, execution_id: str) -> None:
            raise AssertionError("denied write reached backend")

    backend = NeverBackend()
    root, patch, executor, tool, context, ledger, _ = await _stack(
        tmp_path,
        profile_name=profile_name,
        decision=decision,
        backend_factory=lambda _root: backend,
    )
    before = (root / "README.md").read_bytes()

    result = await executor.execute(tool, {"patch_id": patch.patch_id}, context)

    assert result.success is False
    assert result.error_code in {"POLICY_DENIED", "APPROVAL_DENIED"}
    assert backend.calls == 0
    assert await ledger.get(RUN_ID, context.tool_call_id, tool.name) is None
    assert (root / "README.md").read_bytes() == before


@pytest.mark.asyncio
async def test_cross_run_drift_and_capability_replay_are_rejected(tmp_path: Path) -> None:
    from agent_foundations.security.capabilities import CapabilityConsumedError

    root, patch, executor, tool, context, ledger, authorizations = await _stack(tmp_path)
    other_run = context.__class__(
        session_id="44444444-4444-4444-8444-444444444444",
        root=root,
        tool_call_id="call-cross-run",
        tool_name=tool.name,
    )
    cross = await executor.execute(tool, {"patch_id": patch.patch_id}, other_run)
    assert cross.success is False
    assert cross.error_code == "PATCH_NOT_FOUND"
    assert await ledger.get(other_run.session_id, other_run.tool_call_id, tool.name) is None

    (root / "README.md").write_text("drift\n", encoding="utf-8")
    drift = await executor.execute(tool, {"patch_id": patch.patch_id}, context)
    assert drift.success is False
    assert drift.error_code == "PATCH_BASELINE_MISMATCH"
    assert await ledger.get(RUN_ID, context.tool_call_id, tool.name) is None

    root, patch, executor, tool, context, _ledger, authorizations = await _stack(
        tmp_path / "replay"
    )
    result = await executor.execute(tool, {"patch_id": patch.patch_id}, context)
    assert result.success
    capability = await authorizations.find_capability_for_execution(RUN_ID, context.tool_call_id)
    assert capability is not None
    with pytest.raises(CapabilityConsumedError):
        await authorizations.consume_capability(
            capability.capability_id,
            executor.policy_request_for(patch, context),
            consumed_at=NOW,
        )


@pytest.mark.asyncio
async def test_backend_rollback_result_sets_ledger_rolled_back_and_keeps_fixture(
    tmp_path: Path,
) -> None:
    class RolledBackBackend:
        requests: list[Any] = []

        async def execute(self, request: Any) -> ExecutionResult:
            self.requests.append(request)
            return ExecutionResult(
                execution_id=request.execution_id,
                exit_code=20,
                stdout=b'{"status":"rolled_back","error":"OSError"}\n',
                stderr=b"",
                timed_out=False,
                cancelled=False,
                output_truncated=False,
            )

        async def cancel(self, execution_id: str) -> None:
            return None

    backend = RolledBackBackend()
    root, patch, executor, tool, context, ledger, _ = await _stack(
        tmp_path,
        backend_factory=lambda _root: backend,
    )
    before = {path: (root / path).read_bytes() for path in ("README.md", "src/app.py")}

    result = await executor.execute(tool, {"patch_id": patch.patch_id}, context)

    assert result.success is False
    assert result.error_code == "PATCH_ROLLED_BACK"
    assert len(backend.requests) == 1
    assert backend.requests[0].mount_mode == "project_write"
    assert {path: (root / path).read_bytes() for path in before} == before
    effect = await ledger.get(RUN_ID, context.tool_call_id, tool.name)
    assert effect is not None and effect.status is EffectStatus.ROLLED_BACK


@pytest.mark.docker
@pytest.mark.asyncio
async def test_second_file_conflict_rolls_back_first_file_and_ledger(
    tmp_path: Path,
) -> None:
    root_holder: list[Path] = []

    class SecondFileConflictBackend:
        def __init__(self, root: Path) -> None:
            root_holder.append(root)
            self._docker = DockerBackend(root)

        async def execute(self, request: Any) -> ExecutionResult:
            (root_holder[0] / "src" / "new.py").mkdir()
            return await self._docker.execute(request)

        async def cancel(self, execution_id: str) -> None:
            await self._docker.cancel(execution_id)

    root, patch, executor, tool, context, ledger, _ = await _stack(
        tmp_path,
        backend_factory=SecondFileConflictBackend,
    )
    before = (root / "README.md").read_bytes()

    result = await executor.execute(tool, {"patch_id": patch.patch_id}, context)

    assert result.error_code == "PATCH_ROLLED_BACK"
    assert (root / "README.md").read_bytes() == before
    assert (root / "src" / "new.py").is_dir()
    assert tuple(root.glob(".agent-patch-*")) == ()
    effect = await ledger.get(RUN_ID, context.tool_call_id, tool.name)
    assert effect is not None and effect.status is EffectStatus.ROLLED_BACK


@pytest.mark.asyncio
async def test_second_replace_failure_reverses_first_and_sets_ledger_rolled_back(
    tmp_path: Path,
) -> None:
    patch_holder: list[Any] = []

    class InjectedSecondReplaceBackend:
        def __init__(self, root: Path) -> None:
            self._root = root

        async def execute(self, request: Any) -> ExecutionResult:
            replace_count = 0

            def fail_second(source: Path, target: Path) -> None:
                nonlocal replace_count
                replace_count += 1
                if replace_count == 2:
                    raise OSError("injected second replace failure")
                os.replace(source, target)

            prepared = prepare_patch(patch_holder[0], self._root)
            try:
                apply_prepared_patch_atomically(
                    prepared,
                    self._root,
                    replace_file=fail_second,
                )
            except PatchApplyError as exc:
                assert exc.code == "PATCH_ROLLED_BACK"
                return ExecutionResult(
                    execution_id=request.execution_id,
                    exit_code=20,
                    stdout=b'{"status":"rolled_back","error":"OSError"}\n',
                    stderr=b"",
                    timed_out=False,
                    cancelled=False,
                    output_truncated=False,
                )
            raise AssertionError("injected second replace unexpectedly succeeded")

        async def cancel(self, execution_id: str) -> None:
            return None

    root, patch, executor, tool, context, ledger, _ = await _stack(
        tmp_path,
        backend_factory=InjectedSecondReplaceBackend,
    )
    patch_holder.append(patch)
    before = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }

    result = await executor.execute(tool, {"patch_id": patch.patch_id}, context)

    after = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }
    assert result.error_code == "PATCH_ROLLED_BACK"
    assert after == before
    assert tuple(root.glob(".agent-patch-*")) == ()
    effect = await ledger.get(RUN_ID, context.tool_call_id, tool.name)
    assert effect is not None and effect.status is EffectStatus.ROLLED_BACK


@pytest.mark.docker
@pytest.mark.asyncio
async def test_symlink_swap_is_rejected_inside_sandbox_without_touching_outside(
    tmp_path: Path,
) -> None:
    root_holder: list[Path] = []
    outside = tmp_path / "outside.txt"
    outside.write_text("outside\n", encoding="utf-8", newline="\n")

    class SymlinkSwapBackend:
        def __init__(self, root: Path) -> None:
            root_holder.append(root)
            self._docker = DockerBackend(root)

        async def execute(self, request: Any) -> ExecutionResult:
            target = root_holder[0] / "README.md"
            target.unlink()
            try:
                target.symlink_to(outside)
            except OSError:
                pytest.skip("symlink creation is unavailable on this Windows host")
            return await self._docker.execute(request)

        async def cancel(self, execution_id: str) -> None:
            await self._docker.cancel(execution_id)

    _root, patch, executor, tool, context, ledger, _ = await _stack(
        tmp_path,
        backend_factory=SymlinkSwapBackend,
    )

    result = await executor.execute(tool, {"patch_id": patch.patch_id}, context)

    assert result.error_code == "PATCH_ROLLED_BACK"
    assert outside.read_bytes() == b"outside\n"
    effect = await ledger.get(RUN_ID, context.tool_call_id, tool.name)
    assert effect is not None and effect.status is EffectStatus.ROLLED_BACK
