from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AfterValidator,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

from agent_foundations.domain._model import ValidatedCopyModel
from agent_foundations.domain.tool import ToolResult
from agent_foundations.runtime.state_machine import AgentRunState

RunState = AgentRunState


class DurableRunStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


def _valid_uuid(value: str) -> str:
    UUID(value)
    return value


def _utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


def _non_blank(value: str, field_name: str) -> str:
    if not value or not value.strip():
        raise ValueError(f"{field_name} must not be blank")
    return value


UUIDString = Annotated[str, AfterValidator(_valid_uuid)]
UTCDateTime = Annotated[datetime, AfterValidator(_utc_datetime)]


class DurableRun(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: UUIDString
    project_root: str
    status: DurableRunStatus
    schema_version: Literal[1]
    state_version: int = Field(ge=0)
    attempt: int = Field(ge=1)
    created_at: UTCDateTime
    updated_at: UTCDateTime

    @field_validator("project_root")
    @classmethod
    def validate_project_root(cls, value: str) -> str:
        return _non_blank(value, "project_root")


class RunCheckpoint(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    checkpoint_id: UUIDString
    run_id: UUIDString
    sequence: int = Field(ge=1)
    schema_version: Literal[1]
    state: RunState
    created_at: UTCDateTime


class RunLease(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: UUIDString
    owner_id: str
    lease_token: UUIDString
    acquired_at: UTCDateTime
    expires_at: UTCDateTime

    @field_validator("owner_id")
    @classmethod
    def validate_owner_id(cls, value: str) -> str:
        return _non_blank(value, "owner_id")

    @model_validator(mode="after")
    def validate_expiry(self) -> RunLease:
        if self.expires_at <= self.acquired_at:
            raise ValueError("expires_at must be after acquired_at")
        return self


class EffectStatus(StrEnum):
    INTENT_RECORDED = "intent_recorded"
    EXECUTING = "executing"
    COMMITTED = "committed"
    FAILED = "failed"
    UNKNOWN = "unknown"
    ROLLED_BACK = "rolled_back"


DigestHex = Annotated[str, Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")]


class SideEffectIntent(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    operation: str
    resource_key: str
    summary: str = Field(max_length=240)

    @field_validator("operation", "resource_key", "summary")
    @classmethod
    def validate_non_blank_fields(cls, value: str, info: ValidationInfo) -> str:
        return _non_blank(value, info.field_name or "field")


class SideEffectRecord(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    effect_id: UUIDString
    run_id: UUIDString
    tool_call_id: str
    tool_name: str
    idempotency_key: DigestHex
    intent_digest: DigestHex
    intent_summary: str = Field(max_length=240)
    status: EffectStatus
    result: ToolResult | None = None
    error_code: str | None = None
    execution_owner_id: str | None = None
    created_at: UTCDateTime
    updated_at: UTCDateTime
    executing_at: UTCDateTime | None = None
    resolved_at: UTCDateTime | None = None

    @field_validator("tool_call_id", "tool_name")
    @classmethod
    def validate_identity_fields(cls, value: str, info: ValidationInfo) -> str:
        return _non_blank(value, info.field_name or "field")

    @field_validator("intent_summary")
    @classmethod
    def validate_intent_summary(cls, value: str) -> str:
        return _non_blank(value, "intent_summary")

    @model_validator(mode="after")
    def validate_status_constraints(self) -> SideEffectRecord:
        if self.status == EffectStatus.INTENT_RECORDED:
            if (
                self.execution_owner_id is not None
                or self.result is not None
                or self.resolved_at is not None
            ):
                raise ValueError("INTENT_RECORDED must not include owner, result, or resolved_at")
        if self.status == EffectStatus.EXECUTING:
            if self.execution_owner_id is None or self.executing_at is None:
                raise ValueError("EXECUTING requires execution_owner_id and executing_at")
        if self.status == EffectStatus.COMMITTED:
            if self.result is None or not self.result.success:
                raise ValueError("COMMITTED requires a successful result")
        if self.status == EffectStatus.FAILED:
            if self.result is None and self.error_code is None:
                raise ValueError("FAILED requires result or error_code")
            if self.result is not None and self.result.success:
                raise ValueError("FAILED result must not be successful")
        if self.status in {EffectStatus.UNKNOWN, EffectStatus.ROLLED_BACK}:
            if self.resolved_at is None:
                raise ValueError(f"{self.status.value} requires resolved_at")
        return self
