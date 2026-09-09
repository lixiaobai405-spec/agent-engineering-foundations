from __future__ import annotations

import hashlib
import re
import secrets
from base64 import urlsafe_b64encode
from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import ConfigDict, Field, field_validator, model_validator

from agent_foundations.domain._model import ValidatedCopyModel
from agent_foundations.tools.command.models import CommandCategory

ARTIFACT_ID_PATTERN = re.compile(r"^coa_[A-Za-z0-9_-]{22}$")


class RetentionStatus(StrEnum):
    ACTIVE = "active"
    RETAINED = "retained"
    PENDING_DELETE = "pending_delete"
    DELETED = "deleted"
    DELETE_FAILED = "delete_failed"
    EVICTED = "evicted"


class ParserStatus(StrEnum):
    PENDING = "pending"
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"


class CommandArtifactMetadata(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    artifact_id: str
    run_id: UUID
    effect_id: UUID
    execution_id: UUID
    stdout_bytes: int = Field(ge=0)
    stderr_bytes: int = Field(ge=0)
    sha256: str
    created_at: datetime
    retention_status: RetentionStatus
    parser_status: ParserStatus

    @field_validator("artifact_id")
    @classmethod
    def _valid_artifact_id(cls, value: str) -> str:
        if ARTIFACT_ID_PATTERN.fullmatch(value) is None:
            raise ValueError("artifact_id must be coa_ plus 22 base64url characters")
        return value

    @field_validator("sha256")
    @classmethod
    def _valid_sha256(cls, value: str) -> str:
        if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise ValueError("sha256 must be lowercase hex")
        return value


class RunCommandRequest(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    argv: tuple[str, ...]
    cwd: str = "."
    timeout_seconds: int = Field(default=120, ge=1, le=300)


def generate_artifact_id() -> str:
    encoded = urlsafe_b64encode(secrets.token_bytes(16)).decode("ascii").rstrip("=")
    artifact_id = f"coa_{encoded}"
    if ARTIFACT_ID_PATTERN.fullmatch(artifact_id) is None:
        raise RuntimeError("generated artifact_id failed contract validation")
    return artifact_id


def compute_artifact_sha256(stdout: bytes, stderr: bytes) -> str:
    digest = hashlib.sha256()
    for name, payload in (("stdout", stdout), ("stderr", stderr)):
        digest.update(name.encode("utf-8"))
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


class DiagnosticSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class OutputRange(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    stream: Literal["stdout", "stderr"]
    start_line: int = Field(ge=1)
    line_count: int = Field(ge=1, le=200)
    reason: str


class Diagnostic(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    diagnostic_id: str
    severity: DiagnosticSeverity
    tool: str
    file: str | None = None
    line: int | None = None
    column: int | None = None
    test_id: str | None = None
    error_type: str | None = None
    error_code: str | None = None
    message: str
    expected: str | None = None
    actual: str | None = None
    context: tuple[str, ...] = ()

    @field_validator("context")
    @classmethod
    def _bound_context(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        bounded: list[str] = []
        for line in value[:8]:
            bounded.append(line[:240])
        return tuple(bounded)


class CommandFeedback(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    command_category: CommandCategory
    argv_display: tuple[str, ...]
    cwd: str
    exit_code: int | None
    timed_out: bool
    cancelled: bool
    output_truncated: bool
    passed: int | None
    failed: int | None
    skipped: int | None
    diagnostics: tuple[Diagnostic, ...]
    repeated_diagnostics: int
    parser_status: Literal["complete", "partial", "failed"]
    unparsed_bytes: int = Field(ge=0)
    unparsed_reason: str | None
    recommended_ranges: tuple[OutputRange, ...]
    artifact_id: str
    stdout_bytes: int = Field(ge=0)
    stderr_bytes: int = Field(ge=0)
    raw_sha256: str

    @field_validator("artifact_id")
    @classmethod
    def _valid_artifact_id(cls, value: str) -> str:
        if ARTIFACT_ID_PATTERN.fullmatch(value) is None:
            raise ValueError("artifact_id must be coa_ plus 22 base64url characters")
        return value

    @field_validator("raw_sha256")
    @classmethod
    def _valid_sha256(cls, value: str) -> str:
        if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise ValueError("raw_sha256 must be lowercase hex")
        return value

    @field_validator("cwd")
    @classmethod
    def _relative_cwd(cls, value: str) -> str:
        if value.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", value):
            raise ValueError("cwd must be a relative project path")
        return value

    @model_validator(mode="after")
    def _status_integrity(self) -> CommandFeedback:
        interrupted = self.timed_out or self.cancelled or self.output_truncated
        if self.parser_status == "complete":
            if interrupted:
                raise ValueError("interrupted command cannot have complete parser_status")
            if self.unparsed_bytes != 0 or self.unparsed_reason is not None:
                raise ValueError("complete feedback must have zero unparsed bytes")
        return self
