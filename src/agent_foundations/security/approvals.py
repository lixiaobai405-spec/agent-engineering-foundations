from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import uuid4

from pydantic import ConfigDict, Field, field_validator, model_validator

from agent_foundations.domain._model import ValidatedCopyModel
from agent_foundations.security.models import (
    PermissionProfileName,
    PolicyRequest,
    PolicyResource,
)

if TYPE_CHECKING:
    from agent_foundations.security.repository import AuthorizationRepository

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(UTC)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


class AuthorizationStatus(StrEnum):
    POLICY_ALLOWED = "policy_allowed"
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    INVALIDATED = "invalidated"
    CONFLICT = "conflict"


class AuthorizationRecord(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    authorization_id: str
    run_id: str
    tool_call_id: str
    tool_name: str
    resource: PolicyResource
    operation: str
    profile_name: PermissionProfileName
    profile_version: int = Field(ge=1)
    status: AuthorizationStatus
    requested_at: datetime
    decided_at: datetime | None = None

    _requested_utc = field_validator("requested_at")(_utc)
    _decided_utc = field_validator("decided_at")(
        lambda value: None if value is None else _utc(value)
    )

    @model_validator(mode="after")
    def _validate_decision_time(self) -> AuthorizationRecord:
        if self.status is AuthorizationStatus.PENDING and self.decided_at is not None:
            raise ValueError("pending authorization must not have decided_at")
        if self.status is AuthorizationStatus.POLICY_ALLOWED and self.decided_at is not None:
            raise ValueError("policy allow must not be represented as a human decision")
        if self.status in {
            AuthorizationStatus.APPROVED,
            AuthorizationStatus.DENIED,
            AuthorizationStatus.INVALIDATED,
            AuthorizationStatus.CONFLICT,
        } and self.decided_at is None:
            raise ValueError("resolved authorization requires decided_at")
        return self


class AuthorizationDecision(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    authorization_id: str
    request: PolicyRequest
    profile_name: PermissionProfileName
    status: AuthorizationStatus
    requested_at: datetime
    decided_at: datetime | None = None

    _requested_utc = field_validator("requested_at")(_utc)
    _decided_utc = field_validator("decided_at")(
        lambda value: None if value is None else _utc(value)
    )

    @model_validator(mode="after")
    def _human_status_only(self) -> AuthorizationDecision:
        if self.status not in {
            AuthorizationStatus.PENDING,
            AuthorizationStatus.APPROVED,
            AuthorizationStatus.DENIED,
        }:
            raise ValueError("human decision status is invalid")
        if self.status is AuthorizationStatus.PENDING and self.decided_at is not None:
            raise ValueError("pending decision must not have decided_at")
        if self.status is not AuthorizationStatus.PENDING and self.decided_at is None:
            raise ValueError("resolved decision requires decided_at")
        return self


class AuthorizationApproval:
    """Persist a pending request and represent, but never execute, a human decision."""

    def __init__(
        self,
        repository: AuthorizationRepository,
        profile_name: PermissionProfileName,
        *,
        clock: Clock = utc_now,
    ) -> None:
        self._repository = repository
        self._profile_name = profile_name
        self._clock = clock

    async def request(
        self,
        request: PolicyRequest,
        *,
        authorization_id: str | None = None,
    ) -> AuthorizationDecision:
        now = _utc(self._clock())
        record = await self._repository.create_pending(
            request,
            self._profile_name,
            authorization_id=authorization_id or str(uuid4()),
            requested_at=now,
        )
        return AuthorizationDecision(
            authorization_id=record.authorization_id,
            request=request,
            profile_name=record.profile_name,
            status=record.status,
            requested_at=record.requested_at,
            decided_at=record.decided_at,
        )

    def decide(
        self,
        pending: AuthorizationDecision,
        status: AuthorizationStatus,
    ) -> AuthorizationDecision:
        if pending.status is not AuthorizationStatus.PENDING:
            raise ValueError("only a pending authorization can be decided")
        if status not in {AuthorizationStatus.APPROVED, AuthorizationStatus.DENIED}:
            raise ValueError("decision must be approved or denied")
        return pending.model_copy(
            update={"status": status, "decided_at": _utc(self._clock())},
        )
