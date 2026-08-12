from __future__ import annotations

import importlib.util

import pytest
from pydantic import ValidationError


def _require_security_models() -> None:
    try:
        spec = importlib.util.find_spec("agent_foundations.security.models")
    except ModuleNotFoundError:
        spec = None
    assert spec is not None, "agent_foundations.security.models is not implemented"


def test_permission_profile_name_has_exactly_five_values() -> None:
    _require_security_models()
    from agent_foundations.security.models import PermissionProfileName

    values = {member.value for member in PermissionProfileName}
    assert values == {
        "PROJECT_READ_ONLY",
        "ASK_ALWAYS",
        "RISK_BASED",
        "PROJECT_FULL_ACCESS",
        "CUSTOM",
    }


def test_ask_for_access_is_read_only_migration_alias() -> None:
    _require_security_models()
    from agent_foundations.security.models import (
        PermissionProfileName,
        normalize_permission_profile_name,
    )

    assert normalize_permission_profile_name("ASK_FOR_ACCESS") is (
        PermissionProfileName.ASK_ALWAYS
    )


def test_new_profile_serialization_never_emits_ask_for_access() -> None:
    _require_security_models()
    from agent_foundations.security.models import (
        PermissionProfile,
        PermissionProfileName,
        default_allowed_tools,
    )

    profile = PermissionProfile(
        name=PermissionProfileName.ASK_ALWAYS,
        version=1,
        allowed_tools=default_allowed_tools(PermissionProfileName.ASK_ALWAYS),
    )
    payload = profile.model_dump(mode="json")
    assert "ASK_FOR_ACCESS" not in str(payload)


@pytest.mark.parametrize("version", [0, -1])
def test_permission_profile_version_must_be_positive(version: int) -> None:
    _require_security_models()
    from agent_foundations.security.models import PermissionProfile, PermissionProfileName

    with pytest.raises(ValidationError):
        PermissionProfile(
            name=PermissionProfileName.PROJECT_READ_ONLY,
            version=version,
            allowed_tools=("read_file",),
        )


def test_tool_manifest_rejects_empty_operations() -> None:
    _require_security_models()
    from agent_foundations.security.models import SideEffectKind, ToolManifest

    with pytest.raises(ValidationError):
        ToolManifest(
            name="read_file",
            resource_kind="project_path",
            operations=(),
            side_effect=SideEffectKind.NONE,
            sandbox_required=False,
        )


def test_tool_manifest_rejects_duplicate_operations() -> None:
    _require_security_models()
    from agent_foundations.security.models import SideEffectKind, ToolManifest

    with pytest.raises(ValidationError):
        ToolManifest(
            name="read_file",
            resource_kind="project_path",
            operations=("read", "read"),
            side_effect=SideEffectKind.NONE,
            sandbox_required=False,
        )


def test_tool_manifest_is_frozen_and_model_copy_revalidates() -> None:
    _require_security_models()
    from agent_foundations.security.models import SideEffectKind, ToolManifest

    manifest = ToolManifest(
        name="read_file",
        resource_kind="project_path",
        operations=("read",),
        side_effect=SideEffectKind.NONE,
        sandbox_required=False,
    )
    with pytest.raises(ValidationError):
        manifest.model_copy(update={"operations": ()})


def test_policy_outcome_fields_are_decision_rule_id_reason_code_only() -> None:
    _require_security_models()
    from agent_foundations.security.models import PolicyDecision, PolicyOutcome

    outcome = PolicyOutcome(
        decision=PolicyDecision.ALLOW,
        rule_id="builtin.project_read.allow",
        reason_code="project_read_allowed",
    )
    assert set(PolicyOutcome.model_fields) == {"decision", "rule_id", "reason_code"}
    assert outcome.model_dump() == {
        "decision": "allow",
        "rule_id": "builtin.project_read.allow",
        "reason_code": "project_read_allowed",
    }


def test_policy_request_binds_required_fields() -> None:
    _require_security_models()
    from agent_foundations.security.models import (
        PolicyRequest,
        PolicyResource,
        ResourceScope,
        SideEffectKind,
        ToolManifest,
    )

    manifest = ToolManifest(
        name="read_file",
        resource_kind="project_path",
        operations=("read",),
        side_effect=SideEffectKind.NONE,
        sandbox_required=False,
    )
    resource = PolicyResource(
        kind="project_path",
        scope=ResourceScope.PROJECT_INTERNAL,
        identifier="src/main.py",
    )
    request = PolicyRequest(
        profile_version=1,
        run_id="run-1",
        tool_call_id="call-1",
        tool_name="read_file",
        manifest=manifest,
        resource=resource,
        operation="read",
    )
    assert request.profile_version == 1
    assert request.run_id == "run-1"
    assert request.tool_call_id == "call-1"
