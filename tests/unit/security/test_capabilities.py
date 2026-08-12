from __future__ import annotations

import asyncio
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

NOW = datetime(2026, 8, 12, 11, 0, tzinfo=UTC)
AUTHORIZATION_ID = "22222222-2222-4222-8222-222222222222"


def _components() -> tuple[Any, ...]:
    assert importlib.util.find_spec("agent_foundations.security.capabilities") is not None, (
        "Task 13 capability module is missing"
    )
    from agent_foundations.security.approvals import (
        AuthorizationApproval,
        AuthorizationStatus,
    )
    from agent_foundations.security.capabilities import (
        CapabilityConsumedError,
        CapabilityConsumer,
        CapabilityDeniedError,
        CapabilityExpiredError,
        CapabilityIssuer,
        CapabilityMismatchError,
    )
    from agent_foundations.security.repository import AuthorizationRepository

    return (
        AuthorizationApproval,
        AuthorizationStatus,
        CapabilityIssuer,
        CapabilityConsumer,
        CapabilityDeniedError,
        CapabilityMismatchError,
        CapabilityExpiredError,
        CapabilityConsumedError,
        AuthorizationRepository,
    )


def _request(**changes: object) -> PolicyRequest:
    values: dict[str, object] = {
        "profile_version": 3,
        "run_id": "11111111-1111-4111-8111-111111111111",
        "tool_call_id": "call-1",
        "tool_name": "read_file",
        "manifest": ToolManifest(
            name="read_file",
            resource_kind="project_path",
            operations=("read",),
            side_effect=SideEffectKind.NONE,
            sandbox_required=False,
        ),
        "resource": PolicyResource(
            kind="project_path",
            scope=ResourceScope.EXTERNAL_EXACT_PATH,
            identifier="outside/readme.txt",
            category="docs",
        ),
        "operation": "read",
    }
    values.update(changes)
    return PolicyRequest.model_validate(values)


def _outcome(decision: PolicyDecision) -> PolicyOutcome:
    return PolicyOutcome(decision=decision, rule_id="test.rule", reason_code="test")


async def _stack(tmp_path: Path, *, clock: Any = lambda: NOW) -> tuple[Any, ...]:
    components = _components()
    repository_type = components[-1]
    repository = repository_type.from_path(tmp_path / "state.sqlite3")
    await repository.initialize()
    issuer = components[2](
        repository,
        PermissionProfileName.ASK_ALWAYS,
        ttl=timedelta(minutes=5),
        clock=clock,
    )
    consumer = components[3](repository, clock=clock)
    approval = components[0](
        repository,
        PermissionProfileName.ASK_ALWAYS,
        clock=clock,
    )
    return (*components, repository, issuer, consumer, approval)


@pytest.mark.asyncio
async def test_allow_issues_without_fake_human_approval_and_exact_retry_is_idempotent(
    tmp_path: Path,
) -> None:
    *_, repository, issuer, _consumer, _approval = await _stack(tmp_path)
    request = _request()
    capability = await issuer.issue(request, _outcome(PolicyDecision.ALLOW), None)
    retry = await issuer.issue(request, _outcome(PolicyDecision.ALLOW), None)

    assert retry.capability_id == capability.capability_id
    authorization = await repository.get_authorization(capability.authorization_id)
    assert authorization.status.value == "policy_allowed"
    assert authorization.decided_at is None
    assert await repository.count_capabilities(capability.authorization_id) == 1


@pytest.mark.asyncio
async def test_ask_requires_exact_approved_decision_and_deny_never_issues(
    tmp_path: Path,
) -> None:
    (
        _AuthorizationApproval,
        AuthorizationStatus,
        _CapabilityIssuer,
        _CapabilityConsumer,
        CapabilityDeniedError,
        CapabilityMismatchError,
        *_rest,
        repository,
        issuer,
        _consumer,
        approval,
    ) = await _stack(tmp_path)
    request = _request()
    pending = await approval.request(request, authorization_id=AUTHORIZATION_ID)

    with pytest.raises(CapabilityDeniedError):
        await issuer.issue(request, _outcome(PolicyDecision.ASK), None)
    with pytest.raises(CapabilityDeniedError):
        await issuer.issue(request, _outcome(PolicyDecision.ASK), pending)
    with pytest.raises(CapabilityDeniedError):
        await issuer.issue(
            request,
            _outcome(PolicyDecision.ASK),
            approval.decide(pending, AuthorizationStatus.DENIED),
        )
    assert await repository.count_capabilities(AUTHORIZATION_ID) == 0

    pending = await approval.request(_request(tool_call_id="call-2"))
    wrong = approval.decide(pending, AuthorizationStatus.APPROVED).model_copy(
        update={"request": _request(tool_call_id="call-3")},
    )
    with pytest.raises(CapabilityMismatchError):
        await issuer.issue(
            _request(tool_call_id="call-2"),
            _outcome(PolicyDecision.ASK),
            wrong,
        )

    forged = approval.decide(pending, AuthorizationStatus.APPROVED)
    with pytest.raises(CapabilityDeniedError):
        await issuer.issue(
            _request(tool_call_id="call-2"),
            _outcome(PolicyDecision.DENY),
            forged,
        )
    assert await repository.count_capabilities(forged.authorization_id) == 0


@pytest.mark.asyncio
async def test_approved_ask_issues_and_consumer_requires_every_exact_binding(
    tmp_path: Path,
) -> None:
    (
        _AuthorizationApproval,
        AuthorizationStatus,
        _CapabilityIssuer,
        _CapabilityConsumer,
        _CapabilityDeniedError,
        CapabilityMismatchError,
        *_rest,
        repository,
        issuer,
        consumer,
        approval,
    ) = await _stack(tmp_path)
    request = _request()
    pending = await approval.request(request, authorization_id=AUTHORIZATION_ID)
    capability = await issuer.issue(
        request,
        _outcome(PolicyDecision.ASK),
        approval.decide(pending, AuthorizationStatus.APPROVED),
    )

    variants = (
        _request(run_id="33333333-3333-4333-8333-333333333333"),
        _request(tool_call_id="other-call"),
        _request(tool_name="search_text"),
        _request(operation="list"),
        _request(profile_version=4),
        _request(
            resource=PolicyResource(
                kind="project_path",
                scope=ResourceScope.EXTERNAL_EXACT_PATH,
                identifier="outside/other.txt",
                category="docs",
            ),
        ),
    )
    for variant in variants:
        with pytest.raises(CapabilityMismatchError):
            await consumer.consume(capability.capability_id, variant)
        assert (await repository.get_capability(capability.capability_id)).consumed_at is None

    consumed = await consumer.consume(capability.capability_id, request)
    assert consumed.consumed_at == NOW


@pytest.mark.asyncio
async def test_expiry_boundary_repeat_and_concurrent_consume_fail_closed(
    tmp_path: Path,
) -> None:
    (
        _AuthorizationApproval,
        _AuthorizationStatus,
        _CapabilityIssuer,
        _CapabilityConsumer,
        _CapabilityDeniedError,
        _CapabilityMismatchError,
        CapabilityExpiredError,
        CapabilityConsumedError,
        *_rest,
        repository,
        issuer,
        consumer,
        _approval,
    ) = await _stack(tmp_path)
    request = _request()
    expired = await issuer.issue(request, _outcome(PolicyDecision.ALLOW), None)
    consumer._clock = lambda: expired.expires_at
    with pytest.raises(CapabilityExpiredError):
        await consumer.consume(expired.capability_id, request)
    assert (await repository.get_capability(expired.capability_id)).consumed_at is None

    concurrent_request = _request(tool_call_id="call-concurrent")
    concurrent = await issuer.issue(
        concurrent_request,
        _outcome(PolicyDecision.ALLOW),
        None,
    )
    consumer._clock = lambda: NOW
    results = await asyncio.gather(
        consumer.consume(concurrent.capability_id, concurrent_request),
        consumer.consume(concurrent.capability_id, concurrent_request),
        return_exceptions=True,
    )
    assert sum(not isinstance(result, BaseException) for result in results) == 1
    assert sum(isinstance(result, CapabilityConsumedError) for result in results) == 1

    with pytest.raises(CapabilityConsumedError):
        await issuer.issue(
            concurrent_request,
            _outcome(PolicyDecision.ALLOW),
            None,
        )


@pytest.mark.asyncio
async def test_capability_rejects_consumption_before_issued_at_without_mutation(
    tmp_path: Path,
) -> None:
    (
        _AuthorizationApproval,
        _AuthorizationStatus,
        _CapabilityIssuer,
        _CapabilityConsumer,
        _CapabilityDeniedError,
        _CapabilityMismatchError,
        _CapabilityExpiredError,
        _CapabilityConsumedError,
        *_rest,
        repository,
        issuer,
        consumer,
        _approval,
    ) = await _stack(tmp_path)
    from agent_foundations.security.capabilities import CapabilityError

    request = _request(tool_call_id="clock-rollback")
    capability = await issuer.issue(request, _outcome(PolicyDecision.ALLOW), None)
    consumer._clock = lambda: capability.issued_at - timedelta(seconds=1)

    with pytest.raises(CapabilityError):
        await consumer.consume(capability.capability_id, request)

    assert (await repository.get_capability(capability.capability_id)).consumed_at is None


@pytest.mark.asyncio
async def test_approved_decision_profile_name_must_match_issuer_profile(
    tmp_path: Path,
) -> None:
    (
        AuthorizationApproval,
        AuthorizationStatus,
        CapabilityIssuer,
        _CapabilityConsumer,
        _CapabilityDeniedError,
        CapabilityMismatchError,
        *_rest,
        repository,
        _issuer,
        _consumer,
        _approval,
    ) = await _stack(tmp_path)
    request = _request(tool_call_id="profile-name-mismatch")
    ask_always_approval = AuthorizationApproval(
        repository,
        PermissionProfileName.ASK_ALWAYS,
        clock=lambda: NOW,
    )
    pending = await ask_always_approval.request(request)
    approved = ask_always_approval.decide(pending, AuthorizationStatus.APPROVED)
    risk_based_issuer = CapabilityIssuer(
        repository,
        PermissionProfileName.RISK_BASED,
        ttl=timedelta(minutes=5),
        clock=lambda: NOW,
    )

    with pytest.raises(CapabilityMismatchError):
        await risk_based_issuer.issue(
            request,
            _outcome(PolicyDecision.ASK),
            approved,
        )

    assert await repository.count_capabilities(approved.authorization_id) == 0


@pytest.mark.asyncio
async def test_concurrent_exact_issue_returns_one_persisted_capability(
    tmp_path: Path,
) -> None:
    *_, repository, issuer, _consumer, _approval = await _stack(tmp_path)
    request = _request(tool_call_id="concurrent-issue")

    first, second = await asyncio.gather(
        issuer.issue(request, _outcome(PolicyDecision.ALLOW), None),
        issuer.issue(request, _outcome(PolicyDecision.ALLOW), None),
    )

    assert first.capability_id == second.capability_id
    assert await repository.count_capabilities(first.authorization_id) == 1


def test_ttl_must_be_positive_and_bounded(tmp_path: Path) -> None:
    *components, AuthorizationRepository = _components()
    CapabilityIssuer = components[2]
    repository = AuthorizationRepository.from_path(tmp_path / "state.sqlite3")
    with pytest.raises(ValueError):
        CapabilityIssuer(
            repository,
            PermissionProfileName.ASK_ALWAYS,
            ttl=timedelta(0),
            clock=lambda: NOW,
        )
    with pytest.raises(ValueError):
        CapabilityIssuer(
            repository,
            PermissionProfileName.ASK_ALWAYS,
            ttl=timedelta(days=2),
            clock=lambda: NOW,
        )


def test_resource_json_is_deterministic_bounded_and_excludes_manifest_payload() -> None:
    _components()
    from agent_foundations.security.capabilities import canonical_resource_json

    resource = _request().resource
    first = canonical_resource_json(resource)
    second = canonical_resource_json(resource.model_copy())
    assert first == second
    assert first == (
        '{"category":"docs","identifier":"outside/readme.txt",'
        '"kind":"project_path","scope":"external_exact_path"}'
    )
    assert "operations" not in first
    assert "sandbox_required" not in first
    assert len(first.encode("utf-8")) <= 2048
