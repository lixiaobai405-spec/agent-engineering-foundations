from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from agent_foundations.security.models import (
    PermissionProfileName,
    PolicyRequest,
    PolicyResource,
    ResourceScope,
    SideEffectKind,
    ToolManifest,
)

NOW = datetime(2026, 8, 12, 10, 0, tzinfo=UTC)


def _components() -> tuple[Any, ...]:
    assert importlib.util.find_spec("agent_foundations.security.approvals") is not None, (
        "Task 13 generic approval module is missing"
    )
    assert importlib.util.find_spec("agent_foundations.security.repository") is not None, (
        "Task 13 authorization repository is missing"
    )
    from agent_foundations.security.approvals import (
        AuthorizationApproval,
        AuthorizationStatus,
    )
    from agent_foundations.security.repository import AuthorizationRepository

    return AuthorizationApproval, AuthorizationStatus, AuthorizationRepository


def _request(*, identifier: str = "outside/readme.txt") -> PolicyRequest:
    return PolicyRequest(
        profile_version=1,
        run_id="11111111-1111-4111-8111-111111111111",
        tool_call_id="call-1",
        tool_name="read_file",
        manifest=ToolManifest(
            name="read_file",
            resource_kind="project_path",
            operations=("read",),
            side_effect=SideEffectKind.NONE,
            sandbox_required=False,
        ),
        resource=PolicyResource(
            kind="project_path",
            scope=ResourceScope.EXTERNAL_EXACT_PATH,
            identifier=identifier,
        ),
        operation="read",
    )


@pytest.mark.asyncio
async def test_human_approval_records_pending_then_builds_exact_decision(
    tmp_path: Path,
) -> None:
    AuthorizationApproval, AuthorizationStatus, AuthorizationRepository = _components()
    repository = AuthorizationRepository.from_path(tmp_path / "state.sqlite3")
    await repository.initialize()
    approval = AuthorizationApproval(
        repository,
        PermissionProfileName.ASK_ALWAYS,
        clock=lambda: NOW,
    )

    pending = await approval.request(
        _request(),
        authorization_id="22222222-2222-4222-8222-222222222222",
    )
    assert pending.status is AuthorizationStatus.PENDING
    assert pending.decided_at is None

    approved = approval.decide(pending, AuthorizationStatus.APPROVED)
    denied = approval.decide(pending, AuthorizationStatus.DENIED)
    assert approved.status is AuthorizationStatus.APPROVED
    assert approved.decided_at == NOW
    assert denied.status is AuthorizationStatus.DENIED
    assert denied.authorization_id == pending.authorization_id
    assert denied.request == pending.request


@pytest.mark.asyncio
async def test_exact_retry_reuses_pending_authorization_and_changed_request_conflicts(
    tmp_path: Path,
) -> None:
    AuthorizationApproval, _AuthorizationStatus, AuthorizationRepository = _components()
    from agent_foundations.security.repository import AuthorizationConflictError

    repository = AuthorizationRepository.from_path(tmp_path / "state.sqlite3")
    await repository.initialize()
    approval = AuthorizationApproval(
        repository,
        PermissionProfileName.ASK_ALWAYS,
        clock=lambda: NOW,
    )
    first = await approval.request(_request())
    retry = await approval.request(_request())
    assert retry.authorization_id == first.authorization_id

    with pytest.raises(AuthorizationConflictError):
        await approval.request(_request(identifier="outside/changed.txt"))


def test_approval_only_represents_a_decision_and_never_executes_a_tool() -> None:
    AuthorizationApproval, AuthorizationStatus, _AuthorizationRepository = _components()

    assert not hasattr(AuthorizationApproval, "execute")
    assert {AuthorizationStatus.APPROVED.value, AuthorizationStatus.DENIED.value} == {
        "approved",
        "denied",
    }
