from __future__ import annotations

import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from agent_foundations.durable.effects import SideEffectLedger
from agent_foundations.durable.faults import CrashPoint, InjectedCrash, PointFaultInjector
from agent_foundations.durable.models import DurableRun, DurableRunStatus, EffectStatus
from agent_foundations.durable.repository import DurableRunRepository
from agent_foundations.execution.docker import DockerBackend
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
from agent_foundations.tools.patch.repository import PatchProposalRepository
from agent_foundations.tools.patch.validator import parse_and_validate_patch
from tests.unit.tools.patch_test_helpers import sha256_bytes

RUN_ID = "55555555-5555-4555-8555-555555555555"
NOW = datetime(2026, 8, 12, 6, 0, tzinfo=UTC)


def _api() -> tuple[Any, ...]:
    assert importlib.util.find_spec("agent_foundations.tools.patch.apply_patch") is not None, (
        "Task 15 patch crash recovery is missing"
    )
    from agent_foundations.tools.patch.apply_patch import ApplyPatchTool, ControlledPatchExecutor

    return ApplyPatchTool, ControlledPatchExecutor


async def _stack(tmp_path: Path, crash_at: CrashPoint | None) -> tuple[Any, ...]:
    ApplyPatchTool, ControlledPatchExecutor = _api()
    root = tmp_path / "fixture-project"
    root.mkdir(parents=True)
    target = root / "value.txt"
    target.write_text("before\n", encoding="utf-8", newline="\n")
    db = tmp_path / "state.sqlite3"
    durable = DurableRunRepository(db)
    await durable.initialize()
    await durable.create_run(
        DurableRun(
            run_id=RUN_ID,
            project_root=str(root.resolve()),
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
        """diff --git a/value.txt b/value.txt
--- a/value.txt
+++ b/value.txt
@@ -1 +1 @@
-before
+after
""",
        ({"path": "value.txt", "sha256": sha256_bytes(target.read_bytes())},),
        root,
    )
    await proposals.save(RUN_ID, patch)
    auth_repo = AuthorizationRepository.from_path(db)
    await auth_repo.initialize()
    profile_name = PermissionProfileName.PROJECT_FULL_ACCESS
    approval = AuthorizationApproval(auth_repo, profile_name, clock=lambda: NOW)
    issuer = CapabilityIssuer(auth_repo, profile_name, ttl=timedelta(minutes=5), clock=lambda: NOW)
    consumer = CapabilityConsumer(auth_repo, clock=lambda: NOW)
    ledger = SideEffectLedger(durable, clock=lambda: NOW)
    backend_calls: list[str] = []

    def backend_factory(project_root: Path) -> Any:
        backend = DockerBackend(project_root)

        class CountingBackend:
            async def execute(self, request: Any) -> Any:
                backend_calls.append(request.execution_id)
                return await backend.execute(request)

            async def cancel(self, execution_id: str) -> None:
                await backend.cancel(execution_id)

        return CountingBackend()

    common = dict(
        downstream=DirectToolCallExecutor(),
        proposal_repository=proposals,
        profile=PermissionProfile(
            name=profile_name,
            version=1,
            allowed_tools=default_allowed_tools(profile_name),
        ),
        policy=PolicyEngine(),
        approval=approval,
        issuer=issuer,
        consumer=consumer,
        ledger=ledger,
        backend_factory=backend_factory,
        approval_decider=lambda pending: approval.decide(pending, AuthorizationStatus.APPROVED),
    )
    tool = ApplyPatchTool()
    context = ToolExecutionContext(
        session_id=RUN_ID,
        root=root.resolve(),
        tool_call_id="call-crash",
        tool_name=tool.name,
    )
    executor = ControlledPatchExecutor(
        **common,
        execution_owner_id="owner-1",
        fault_injector=PointFaultInjector(crash_at),
    )
    recovery = ControlledPatchExecutor(
        **common,
        execution_owner_id="owner-2",
    )
    return target, patch, tool, context, executor, recovery, ledger, backend_calls


@pytest.mark.docker
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "crash_at,expected_calls",
    [
        (CrashPoint.BEFORE_INTENT, 1),
        (CrashPoint.AFTER_INTENT, 1),
        (CrashPoint.AFTER_EXECUTE, 1),
        (CrashPoint.AFTER_COMMIT, 1),
    ],
)
async def test_four_crash_points_recover_without_duplicate_write(
    tmp_path: Path,
    crash_at: CrashPoint,
    expected_calls: int,
) -> None:
    target, patch, tool, context, executor, recovery, ledger, calls = await _stack(
        tmp_path,
        crash_at,
    )
    with pytest.raises(InjectedCrash):
        await executor.execute(tool, {"patch_id": patch.patch_id}, context)

    result = await recovery.execute(tool, {"patch_id": patch.patch_id}, context)

    assert result.success is True
    assert target.read_bytes() == b"after\n"
    assert len(calls) == expected_calls
    effect = await ledger.get(RUN_ID, context.tool_call_id, tool.name)
    assert effect is not None and effect.status is EffectStatus.COMMITTED
