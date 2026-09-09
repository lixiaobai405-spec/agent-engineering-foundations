from __future__ import annotations

import re
from enum import StrEnum
from typing import Literal

from pydantic import ConfigDict, Field, field_validator, model_validator

from agent_foundations.domain._model import ValidatedCopyModel
from agent_foundations.execution.sandbox_manifest import SandboxManifest
from agent_foundations.tools.patch.models import DigestHex

_CONTROL_LIMIT = 32
_RULE_ID_RE = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")


def _has_control(value: str) -> bool:
    return any(ord(character) < _CONTROL_LIMIT or ord(character) == 127 for character in value)


def _validated_token(value: str, *, label: str) -> str:
    if not value or value != value.strip():
        raise ValueError(f"{label} must not be empty or padded")
    if _has_control(value):
        raise ValueError(f"{label} must not contain control characters")
    return value


def _validated_rule_id(value: str) -> str:
    _validated_token(value, label="rule_id")
    if _RULE_ID_RE.fullmatch(value) is None:
        raise ValueError("rule_id must use stable lowercase identifier syntax")
    return value


class CommandCategory(StrEnum):
    TEST = "test"
    LINT = "lint"
    TYPECHECK = "typecheck"
    BUILD = "build"
    PACKAGE_CHECK = "package_check"
    DENIED = "denied"
    UNKNOWN = "unknown"


class CommandSpec(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    argv: tuple[str, ...] = Field(min_length=1)
    cwd: str = "."
    timeout_seconds: int = Field(default=120, ge=1, le=300)

    @field_validator("argv")
    @classmethod
    def _valid_argv(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(_validated_token(token, label="argv entry") for token in value)

    @field_validator("cwd")
    @classmethod
    def _valid_cwd(cls, value: str) -> str:
        _validated_token(value, label="cwd")
        normalized = value.replace("/", "\\")
        if normalized.startswith(("\\\\", "\\?\\", "\\.\\")):
            raise ValueError("cwd must not use UNC or device syntax")
        if value.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", value):
            raise ValueError("cwd must not be absolute, drive-qualified, or drive-relative")
        if ":" in value:
            raise ValueError("cwd must not use alternate data stream syntax")
        parts = tuple(part for part in re.split(r"[\\/]", value) if part)
        if not parts or any(part == ".." for part in parts):
            raise ValueError("cwd must remain within the project")
        return value


class CommandGate(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    rule_id: str
    category: CommandCategory
    argv_prefix: tuple[str, ...] = Field(min_length=1)
    sandbox_profile: Literal["python", "node"]
    allowed_targets: tuple[str, ...] = ()
    allowed_flags: tuple[str, ...] = ()
    exact: bool = False

    _rule_id = field_validator("rule_id")(_validated_rule_id)

    @field_validator("argv_prefix", "allowed_targets", "allowed_flags")
    @classmethod
    def _valid_tokens(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(_validated_token(token, label="gate token") for token in value)

    @model_validator(mode="after")
    def _valid_gate(self) -> CommandGate:
        if self.category in {CommandCategory.DENIED, CommandCategory.UNKNOWN}:
            raise ValueError("manifest gates may only grant positive command categories")
        if len(set(self.allowed_targets)) != len(self.allowed_targets):
            raise ValueError("allowed_targets must be unique")
        if len(set(self.allowed_flags)) != len(self.allowed_flags):
            raise ValueError("allowed_flags must be unique")
        if self.exact and (self.allowed_targets or self.allowed_flags):
            raise ValueError("exact command gates cannot accept suffix grammar")
        if not self.exact and not self.allowed_targets:
            raise ValueError("parameterized command gates require allowed_targets")
        return self


class ProjectCommandManifest(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    schema_version: Literal[1] = 1
    project_fingerprint: DigestHex
    gates: tuple[CommandGate, ...] = Field(min_length=1)
    sandbox: SandboxManifest

    @model_validator(mode="after")
    def _unique_non_conflicting_gates(self) -> ProjectCommandManifest:
        rule_ids: set[str] = set()
        prefixes: set[tuple[str, ...]] = set()
        for gate in self.gates:
            if gate.rule_id in rule_ids:
                raise ValueError(f"duplicate rule_id: {gate.rule_id}")
            if gate.argv_prefix in prefixes:
                raise ValueError(f"conflicting command gate: {gate.argv_prefix!r}")
            rule_ids.add(gate.rule_id)
            prefixes.add(gate.argv_prefix)
        return self


class CommandClassification(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    category: CommandCategory
    rule_id: str
    normalized_argv: tuple[str, ...] = Field(min_length=1)
    sandbox_profile: Literal["python", "node"]
    hard_denied: bool

    _rule_id = field_validator("rule_id")(_validated_rule_id)

    @field_validator("normalized_argv")
    @classmethod
    def _valid_normalized_argv(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(_validated_token(token, label="normalized argv entry") for token in value)

    @model_validator(mode="after")
    def _consistent_denial(self) -> CommandClassification:
        denied = self.category in {CommandCategory.DENIED, CommandCategory.UNKNOWN}
        if denied != self.hard_denied:
            raise ValueError("hard_denied must match denied or unknown category")
        return self
