from __future__ import annotations

import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from agent_foundations.security.models import (
    PermissionProfileName,
    PolicyDecision,
    PolicyOutcome,
    PolicyRequest,
    PolicyResource,
    ResourceScope,
    SideEffectKind,
    ToolManifest,
)

NOW = datetime(2026, 8, 12, 13, 0, tzinfo=UTC)


def _components() -> tuple[Any, ...]:
    assert importlib.util.find_spec("agent_foundations.security.capabilities") is not None, (
        "Task 13 authorization flow is missing"
    )
    from agent_foundations.security.approvals import (
        AuthorizationApproval,
        AuthorizationStatus,
    )
    from agent_foundations.security.capabilities import (
        CapabilityConsumer,
        CapabilityDeniedError,
        CapabilityIssuer,
    )
    from agent_foundations.security.repository import AuthorizationRepository

    return (
        AuthorizationApproval,
        AuthorizationStatus,
        CapabilityIssuer,
        CapabilityConsumer,
        CapabilityDeniedError,
        AuthorizationRepository,
    )


def _request(call_id: str) -> PolicyRequest:
    return PolicyRequest(
        profile_version=1,
        run_id="11111111-1111-4111-8111-111111111111",
        tool_call_id=call_id,
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
            identifier="C:/fixtures/external.txt",
        ),
        operation="read",
    )


def _outcome(decision: PolicyDecision) -> PolicyOutcome:
    return PolicyOutcome(decision=decision, rule_id="integration", reason_code="integration")


@pytest.mark.asyncio
async def test_allow_ask_and_deny_have_distinct_authorization_sequences(
    tmp_path: Path,
) -> None:
    (
        AuthorizationApproval,
        AuthorizationStatus,
        CapabilityIssuer,
        CapabilityConsumer,
        CapabilityDeniedError,
        AuthorizationRepository,
    ) = _components()
    repository = AuthorizationRepository.from_path(tmp_path / "state.sqlite3")
    await repository.initialize()
    approval = AuthorizationApproval(
        repository,
        PermissionProfileName.ASK_ALWAYS,
        clock=lambda: NOW,
    )
    issuer = CapabilityIssuer(
        repository,
        PermissionProfileName.ASK_ALWAYS,
        ttl=timedelta(minutes=5),
        clock=lambda: NOW,
    )
    consumer = CapabilityConsumer(repository, clock=lambda: NOW)

    allowed_request = _request("allow-call")
    allowed = await issuer.issue(allowed_request, _outcome(PolicyDecision.ALLOW), None)
    assert (await consumer.consume(allowed.capability_id, allowed_request)).consumed_at == NOW

    asked_request = _request("ask-call")
    pending = await approval.request(asked_request)
    approved = approval.decide(pending, AuthorizationStatus.APPROVED)
    asked = await issuer.issue(asked_request, _outcome(PolicyDecision.ASK), approved)
    assert (await consumer.consume(asked.capability_id, asked_request)).consumed_at == NOW

    denied_request = _request("deny-call")
    with pytest.raises(CapabilityDeniedError):
        await issuer.issue(denied_request, _outcome(PolicyDecision.DENY), approved)
    assert await repository.find_capability_for_execution(
        denied_request.run_id,
        denied_request.tool_call_id,
    ) is None
