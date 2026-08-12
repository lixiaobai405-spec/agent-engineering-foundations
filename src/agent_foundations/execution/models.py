from __future__ import annotations

import re
from typing import Literal
from uuid import UUID

from pydantic import ConfigDict, Field, field_validator, model_validator

from agent_foundations.domain._model import ValidatedCopyModel

MAX_STDIN_BYTES = 1024 * 1024
MAX_TIMEOUT_SECONDS = 600
MAX_OUTPUT_BYTES = 16 * 1024 * 1024
_CONTROL_LIMIT = 32


def _uuid_string(value: str) -> str:
    if not value.strip() or value != value.strip():
        raise ValueError("identifier must be a non-empty UUID")
    UUID(value)
    return value


def _has_control(value: str) -> bool:
    return any(ord(character) < _CONTROL_LIMIT or ord(character) == 127 for character in value)


class ExecutionRequest(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    execution_id: str
    run_id: str
    capability_id: str
    argv: tuple[str, ...]
    cwd: str
    mount_mode: Literal["read_only", "project_write"]
    stdin: bytes = Field(default=b"", max_length=MAX_STDIN_BYTES)
    timeout_seconds: int = Field(gt=0, le=MAX_TIMEOUT_SECONDS)
    max_output_bytes: int = Field(gt=0, le=MAX_OUTPUT_BYTES)

    _execution_uuid = field_validator("execution_id")(_uuid_string)
    _run_uuid = field_validator("run_id")(_uuid_string)
    _capability_uuid = field_validator("capability_id")(_uuid_string)

    @field_validator("argv")
    @classmethod
    def _valid_argv(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("argv must not be empty")
        for argument in value:
            if not argument or not argument.strip():
                raise ValueError("argv entries must not be empty")
            if _has_control(argument):
                raise ValueError("argv entries must not contain control characters")
        return value

    @field_validator("cwd")
    @classmethod
    def _safe_relative_cwd(cls, value: str) -> str:
        if not value or not value.strip() or value != value.strip():
            raise ValueError("cwd must be a non-empty relative path")
        normalized = value.replace("/", "\\")
        if normalized.startswith(("\\\\", "\\?\\", "\\.\\")):
            raise ValueError("cwd must not use UNC or device syntax")
        if value.startswith("/") or re.match(r"^[A-Za-z]:", value):
            raise ValueError("cwd must not be absolute or drive-qualified")
        if ":" in value or _has_control(value):
            raise ValueError("cwd contains unsafe path syntax")
        parts = tuple(part for part in re.split(r"[\\/]", value) if part)
        if not parts or any(part == ".." for part in parts):
            raise ValueError("cwd must remain within the workspace")
        return value


class ExecutionResult(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    execution_id: str
    exit_code: int | None
    stdout: bytes
    stderr: bytes
    timed_out: bool
    cancelled: bool
    output_truncated: bool

    _execution_uuid = field_validator("execution_id")(_uuid_string)

    @model_validator(mode="after")
    def _valid_terminal_state(self) -> ExecutionResult:
        if self.timed_out and self.cancelled:
            raise ValueError("execution cannot be both timed out and cancelled")
        interrupted = self.timed_out or self.cancelled
        if interrupted and self.exit_code is not None:
            raise ValueError("interrupted execution must not expose an exit code")
        if not interrupted and self.exit_code is None:
            raise ValueError("completed execution requires an exit code")
        return self
