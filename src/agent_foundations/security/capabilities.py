from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from pydantic import ConfigDict, Field, field_validator, model_validator

from agent_foundations.domain._model import ValidatedCopyModel
from agent_foundations.security.approvals import (
    AuthorizationDecision,
    AuthorizationStatus,
)
from agent_foundations.security.models import (
    PermissionProfileName,
    PolicyDecision,
    PolicyOutcome,
    PolicyRequest,
    PolicyResource,
)
from agent_foundations.security.repository import AuthorizationRepository

Clock = Callable[[], datetime]
MAX_RESOURCE_JSON_BYTES = 2048
MAX_CAPABILITY_TTL = timedelta(hours=24)


def utc_now() -> datetime:
    return datetime.now(UTC)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


class CapabilityError(RuntimeError):
    """Base capability rejection."""


class CapabilityDeniedError(CapabilityError):
    """Policy or human decision does not authorize issuance."""


class CapabilityMismatchError(CapabilityError):
    """Capability or approval is not bound to the exact request."""


class CapabilityExpiredError(CapabilityError):
    """Capability has reached its exclusive expiry boundary."""


class CapabilityNotYetValidError(CapabilityError):
    """Capability clock is earlier than its inclusive issue boundary."""


class CapabilityConsumedError(CapabilityError):
    """Capability was already consumed and cannot be reissued."""


class Capability(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    capability_id: str
    authorization_id: str
    run_id: str
    tool_call_id: str
    tool_name: str
    resource: PolicyResource
    operation: str
    profile_version: int = Field(ge=1)
    issued_at: datetime
    expires_at: datetime
    consumed_at: datetime | None = None

    _issued_utc = field_validator("issued_at")(_utc)
    _expires_utc = field_validator("expires_at")(_utc)
    _consumed_utc = field_validator("consumed_at")(
        lambda value: None if value is None else _utc(value)
    )

    @model_validator(mode="after")
    def _expiry_after_issue(self) -> Capability:
        if self.expires_at <= self.issued_at:
            raise ValueError("expires_at must be after issued_at")
        return self


def canonical_resource_json(resource: PolicyResource) -> str:
    payload: dict[str, str] = {
        "kind": resource.kind,
        "scope": resource.scope.value,
        "identifier": resource.identifier,
    }
    if resource.category is not None:
        payload["category"] = resource.category
    serialized = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    if len(serialized.encode("utf-8")) > MAX_RESOURCE_JSON_BYTES:
        raise ValueError("canonical resource exceeds storage limit")
    return serialized


class CapabilityIssuer:
    def __init__(
        self,
        repository: AuthorizationRepository,
        profile_name: PermissionProfileName,
        *,
        ttl: timedelta,
        clock: Clock = utc_now,
    ) -> None:
        if ttl <= timedelta(0) or ttl > MAX_CAPABILITY_TTL:
            raise ValueError("ttl must be positive and at most 24 hours")
        self._repository = repository
        self._profile_name = profile_name
        self._ttl = ttl
        self._clock = clock

    async def issue(
        self,
        request: PolicyRequest,
        outcome: PolicyOutcome,
        approval: AuthorizationDecision | None,
    ) -> Capability:
        now = _utc(self._clock())
        if outcome.decision is PolicyDecision.DENY:
            await self._repository.record_denied(
                request,
                self._profile_name,
                authorization_id=None,
                decided_at=now,
            )
            raise CapabilityDeniedError("policy denied capability issuance")

        if outcome.decision is PolicyDecision.ALLOW:
            if approval is not None:
                raise CapabilityMismatchError(
                    "policy allow must not include a human approval",
                )
            return await self._repository.issue_capability(
                request,
                self._profile_name,
                authorization_id=None,
                target_status=AuthorizationStatus.POLICY_ALLOWED,
                issued_at=now,
                expires_at=now + self._ttl,
            )

        if approval is None or approval.status is AuthorizationStatus.PENDING:
            raise CapabilityDeniedError("approved human decision is required")
        if approval.status is AuthorizationStatus.DENIED:
            await self._repository.record_denied(
                request,
                self._profile_name,
                authorization_id=approval.authorization_id,
                decided_at=approval.decided_at or now,
            )
            raise CapabilityDeniedError("human denied capability issuance")
        if approval.status is not AuthorizationStatus.APPROVED:
            raise CapabilityDeniedError("approved human decision is required")
        if approval.request != request or approval.profile_name is not self._profile_name:
            raise CapabilityMismatchError("approval does not match exact request")
        return await self._repository.issue_capability(
            request,
            self._profile_name,
            authorization_id=approval.authorization_id,
            target_status=AuthorizationStatus.APPROVED,
            issued_at=now,
            expires_at=now + self._ttl,
        )


class CapabilityConsumer:
    def __init__(
        self,
        repository: AuthorizationRepository,
        *,
        clock: Clock = utc_now,
    ) -> None:
        self._repository = repository
        self._clock = clock

    async def consume(
        self,
        capability_id: str,
        execution: PolicyRequest,
    ) -> Capability:
        return await self._repository.consume_capability(
            capability_id,
            execution,
            consumed_at=_utc(self._clock()),
        )
