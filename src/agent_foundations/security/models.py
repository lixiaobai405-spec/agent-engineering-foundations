from __future__ import annotations

from enum import StrEnum

from pydantic import ConfigDict, Field, field_validator, model_validator

from agent_foundations.domain._model import ValidatedCopyModel

_MAX_IDENTIFIER_LEN = 256
_LEGACY_ASK_FOR_ACCESS = "ASK_FOR_ACCESS"


class PermissionProfileName(StrEnum):
    PROJECT_READ_ONLY = "PROJECT_READ_ONLY"
    ASK_ALWAYS = "ASK_ALWAYS"
    RISK_BASED = "RISK_BASED"
    PROJECT_FULL_ACCESS = "PROJECT_FULL_ACCESS"
    CUSTOM = "CUSTOM"


PHASE2C_READONLY_TOOLS: tuple[str, ...] = (
    "list_directory",
    "read_file",
    "search_text",
    "set_plan",
    "update_plan_step",
    "replan",
    "validate_patch",
)

PHASE2C_KNOWN_WRITE_TOOLS: tuple[str, ...] = ("apply_patch",)

PHASE2C_KNOWN_PROCESS_TOOLS: tuple[str, ...] = ("run_command",)


def default_allowed_tools(profile_name: PermissionProfileName) -> tuple[str, ...]:
    if profile_name is PermissionProfileName.PROJECT_READ_ONLY:
        return PHASE2C_READONLY_TOOLS
    if profile_name in {
        PermissionProfileName.ASK_ALWAYS,
        PermissionProfileName.RISK_BASED,
        PermissionProfileName.PROJECT_FULL_ACCESS,
    }:
        return (
            PHASE2C_READONLY_TOOLS
            + PHASE2C_KNOWN_WRITE_TOOLS
            + PHASE2C_KNOWN_PROCESS_TOOLS
        )
    return PHASE2C_READONLY_TOOLS


class SideEffectKind(StrEnum):
    NONE = "none"
    PROJECT_WRITE = "project_write"
    PROCESS = "process"
    NETWORK = "network"


class PolicyDecision(StrEnum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


class ResourceScope(StrEnum):
    PROJECT_INTERNAL = "project_internal"
    EXTERNAL_EXACT_PATH = "external_exact_path"
    UNKNOWN = "unknown"


def normalize_permission_profile_name(value: str) -> PermissionProfileName:
    if value == _LEGACY_ASK_FOR_ACCESS:
        return PermissionProfileName.ASK_ALWAYS
    return PermissionProfileName(value)


class ToolManifest(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True)

    name: str
    resource_kind: str
    operations: tuple[str, ...]
    side_effect: SideEffectKind
    sandbox_required: bool

    @field_validator("name", "resource_kind")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value

    @field_validator("operations")
    @classmethod
    def _validate_operations(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("operations must not be empty")
        if len(set(value)) != len(value):
            raise ValueError("operations must not contain duplicates")
        for operation in value:
            if not operation.strip():
                raise ValueError("operation must not be empty")
        return value


class PolicyResource(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True)

    kind: str
    scope: ResourceScope
    identifier: str = Field(max_length=_MAX_IDENTIFIER_LEN)
    category: str | None = None

    @field_validator("kind")
    @classmethod
    def _non_empty_kind(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("kind must not be empty")
        return value

    @field_validator("identifier")
    @classmethod
    def _bounded_identifier(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("identifier must not be empty")
        return value[:_MAX_IDENTIFIER_LEN]


class CustomPolicyRule(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True)

    tool_name: str
    resource_kind: str
    operation: str
    side_effect: SideEffectKind | None = None
    path_prefix: str | None = None
    command_category: str | None = None
    decision: PolicyDecision

    @field_validator("tool_name", "resource_kind", "operation")
    @classmethod
    def _non_empty_rule_field(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value


class PermissionProfile(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True)

    name: PermissionProfileName
    version: int = Field(ge=1)
    allowed_tools: tuple[str, ...]
    custom_rules: tuple[CustomPolicyRule, ...] = ()

    @field_validator("allowed_tools")
    @classmethod
    def _validate_allowed_tools(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("allowed_tools must not be empty")
        if len(set(value)) != len(value):
            raise ValueError("allowed_tools must not contain duplicates")
        for tool_name in value:
            if not tool_name.strip():
                raise ValueError("allowed_tools entries must not be empty")
        return value

    @model_validator(mode="after")
    def _custom_profile_requires_rules(self) -> PermissionProfile:
        if self.name is PermissionProfileName.CUSTOM and not self.custom_rules:
            # Empty CUSTOM is valid but always default-denies unmatched requests.
            return self
        return self


class PolicyRequest(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True)

    profile_version: int = Field(ge=1)
    run_id: str
    tool_call_id: str
    tool_name: str
    manifest: ToolManifest
    resource: PolicyResource
    operation: str


class PolicyOutcome(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True)

    decision: PolicyDecision
    rule_id: str
    reason_code: str
