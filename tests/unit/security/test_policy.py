from __future__ import annotations

import importlib.util
from typing import Any

import pytest

from agent_foundations.domain.tool import ToolResult


def _require_security() -> None:
    for module in ("agent_foundations.security.policy", "agent_foundations.security.models"):
        try:
            spec = importlib.util.find_spec(module)
        except ModuleNotFoundError:
            spec = None
        assert spec is not None, f"{module} is not implemented"


def _profile(
    name: str,
    *,
    version: int = 1,
    allowed_tools: tuple[str, ...] | None = None,
    custom_rules: tuple[Any, ...] = (),
) -> Any:
    _require_security()
    from agent_foundations.security.models import (
        CustomPolicyRule,
        PermissionProfile,
        PermissionProfileName,
        PolicyDecision,
        default_allowed_tools,
    )

    profile_name = PermissionProfileName(name)
    rules = tuple(
        CustomPolicyRule(
            tool_name=rule["tool_name"],
            resource_kind=rule["resource_kind"],
            operation=rule["operation"],
            side_effect=rule.get("side_effect"),
            path_prefix=rule.get("path_prefix"),
            command_category=rule.get("command_category"),
            decision=PolicyDecision(rule["decision"]),
        )
        for rule in custom_rules
    )
    return PermissionProfile(
        name=profile_name,
        version=version,
        allowed_tools=allowed_tools or default_allowed_tools(profile_name),
        custom_rules=rules,
    )


def _manifest(
    *,
    name: str = "read_file",
    resource_kind: str = "project_path",
    operations: tuple[str, ...] = ("read",),
    side_effect: str = "none",
) -> Any:
    _require_security()
    from agent_foundations.security.models import SideEffectKind, ToolManifest

    return ToolManifest(
        name=name,
        resource_kind=resource_kind,
        operations=operations,
        side_effect=SideEffectKind(side_effect),
        sandbox_required=side_effect == "process",
    )


def _resource(
    *,
    kind: str = "project_path",
    scope: str = "project_internal",
    identifier: str = "src/main.py",
    category: str | None = None,
) -> Any:
    _require_security()
    from agent_foundations.security.models import PolicyResource, ResourceScope

    return PolicyResource(
        kind=kind,
        scope=ResourceScope(scope),
        identifier=identifier,
        category=category,
    )


def _request(
    profile_version: int = 1,
    *,
    tool_name: str = "read_file",
    manifest: Any | None = None,
    resource: Any | None = None,
    operation: str = "read",
) -> Any:
    _require_security()
    from agent_foundations.security.models import PolicyRequest

    resolved_manifest = manifest or _manifest(name=tool_name, operations=(operation,))
    return PolicyRequest(
        profile_version=profile_version,
        run_id="run-1",
        tool_call_id="call-1",
        tool_name=tool_name,
        manifest=resolved_manifest,
        resource=resource or _resource(),
        operation=operation,
    )


def _decide(
    profile_name: str,
    request: Any,
    *,
    custom_rules: tuple[Any, ...] = (),
    allowed_tools: tuple[str, ...] | None = None,
) -> Any:
    _require_security()
    from agent_foundations.security.policy import PolicyEngine

    engine = PolicyEngine()
    profile = _profile(
        profile_name,
        custom_rules=custom_rules,
        allowed_tools=allowed_tools,
    )
    return engine.decide(profile, request)


@pytest.mark.parametrize(
    "profile_name",
    [
        "PROJECT_READ_ONLY",
        "ASK_ALWAYS",
        "RISK_BASED",
        "PROJECT_FULL_ACCESS",
        "CUSTOM",
    ],
)
@pytest.mark.parametrize(
    ("tool_name", "operation", "resource_kind"),
    [
        ("read_file", "read", "project_path"),
        ("list_directory", "list", "project_path"),
        ("search_text", "search", "project_path"),
        ("set_plan", "create", "plan"),
        ("update_plan_step", "update", "plan"),
        ("replan", "replan", "plan"),
        ("validate_patch", "validate", "patch_proposal"),
    ],
)
def test_builtin_read_planning_and_validate_patch_always_allow(
    profile_name: str,
    tool_name: str,
    operation: str,
    resource_kind: str,
) -> None:
    _require_security()
    from agent_foundations.security.models import PolicyDecision, ResourceScope

    scope = (
        ResourceScope.PROJECT_INTERNAL
        if resource_kind == "project_path"
        else ResourceScope.PROJECT_INTERNAL
    )
    identifier = "plan-1" if resource_kind == "plan" else "patch-1"
    if resource_kind == "project_path":
        identifier = "src/main.py"
    request = _request(
        tool_name=tool_name,
        manifest=_manifest(
            name=tool_name,
            resource_kind=resource_kind,
            operations=(operation,),
        ),
        resource=_resource(kind=resource_kind, scope=scope.value, identifier=identifier),
        operation=operation,
    )
    outcome = _decide(profile_name, request)
    assert outcome.decision is PolicyDecision.ALLOW


@pytest.mark.parametrize(
    ("profile", "expected"),
    [
        ("PROJECT_READ_ONLY", "deny"),
        ("ASK_ALWAYS", "ask"),
        ("RISK_BASED", "ask"),
        ("PROJECT_FULL_ACCESS", "allow"),
    ],
)
def test_project_write_policy_matrix(profile: str, expected: str) -> None:
    request = _request(
        tool_name="apply_patch",
        manifest=_manifest(
            name="apply_patch",
            resource_kind="project_path",
            operations=("write",),
            side_effect="project_write",
        ),
        resource=_resource(scope="project_internal"),
        operation="write",
    )
    outcome = _decide(profile, request)
    assert outcome.decision.value == expected


@pytest.mark.parametrize(
    ("profile", "expected"),
    [
        ("PROJECT_READ_ONLY", "deny"),
        ("ASK_ALWAYS", "ask"),
        ("RISK_BASED", "allow"),
        ("PROJECT_FULL_ACCESS", "allow"),
    ],
)
def test_sandbox_allowlist_command_policy_matrix(profile: str, expected: str) -> None:
    request = _request(
        tool_name="run_command",
        manifest=_manifest(
            name="run_command",
            resource_kind="sandbox_command",
            operations=("execute",),
            side_effect="process",
        ),
        resource=_resource(
            kind="sandbox_command",
            scope="project_internal",
            identifier="pytest -q",
        ),
        operation="execute",
    )
    outcome = _decide(profile, request)
    assert outcome.decision.value == expected


def test_external_exact_read_asks_only_for_ask_always() -> None:
    _require_security()
    from agent_foundations.security.models import PolicyDecision

    request = _request(
        operation="read",
        resource=_resource(scope="external_exact_path", identifier="/tmp/outside.txt"),
    )
    assert _decide("ASK_ALWAYS", request).decision is PolicyDecision.ASK
    for profile in ("PROJECT_READ_ONLY", "RISK_BASED", "PROJECT_FULL_ACCESS", "CUSTOM"):
        assert _decide(profile, request).decision is PolicyDecision.DENY


def test_custom_unmatched_defaults_to_deny() -> None:
    _require_security()
    from agent_foundations.security.models import PolicyDecision

    request = _request(
        tool_name="apply_patch",
        manifest=_manifest(
            name="apply_patch",
            resource_kind="project_path",
            operations=("write",),
            side_effect="project_write",
        ),
        operation="write",
    )
    assert _decide("CUSTOM", request).decision is PolicyDecision.DENY


def test_custom_allow_rule_can_allow_project_write() -> None:
    _require_security()
    from agent_foundations.security.models import (
        PermissionProfileName,
        default_allowed_tools,
    )

    request = _request(
        tool_name="apply_patch",
        manifest=_manifest(
            name="apply_patch",
            resource_kind="project_path",
            operations=("write",),
            side_effect="project_write",
        ),
        operation="write",
    )
    outcome = _decide(
        "CUSTOM",
        request,
        allowed_tools=default_allowed_tools(PermissionProfileName.PROJECT_FULL_ACCESS),
        custom_rules=(
            {
                "tool_name": "apply_patch",
                "resource_kind": "project_path",
                "operation": "write",
                "side_effect": "project_write",
                "path_prefix": "src/",
                "decision": "allow",
            },
        ),
    )
    assert outcome.decision.value == "allow"


@pytest.mark.parametrize(
    "side_effect",
    ["network"],
)
def test_hard_deny_cannot_be_overridden_by_custom_allow(side_effect: str) -> None:
    _require_security()
    from agent_foundations.security.models import PolicyDecision

    request = _request(
        tool_name="fetch_url",
        manifest=_manifest(
            name="fetch_url",
            resource_kind="network",
            operations=("fetch",),
            side_effect=side_effect,
        ),
        resource=_resource(kind="network", scope="unknown", identifier="https://example.com"),
        operation="fetch",
    )
    outcome = _decide(
        "CUSTOM",
        request,
        allowed_tools=("fetch_url",),
        custom_rules=(
            {
                "tool_name": "fetch_url",
                "resource_kind": "network",
                "operation": "fetch",
                "decision": "allow",
            },
        ),
    )
    assert outcome.decision is PolicyDecision.DENY


@pytest.mark.parametrize(
    ("tool_name", "manifest_name"),
    [
        ("read_file", "wrong_name"),
    ],
)
def test_manifest_name_mismatch_is_denied(tool_name: str, manifest_name: str) -> None:
    _require_security()
    from agent_foundations.security.models import PolicyDecision

    request = _request(
        tool_name=tool_name,
        manifest=_manifest(name=manifest_name),
    )
    assert _decide("PROJECT_FULL_ACCESS", request).decision is PolicyDecision.DENY


def test_unknown_operation_is_denied() -> None:
    _require_security()
    from agent_foundations.security.models import PolicyDecision

    request = _request(operation="delete")
    assert _decide("PROJECT_FULL_ACCESS", request).decision is PolicyDecision.DENY


def test_unknown_resource_kind_is_hard_denied() -> None:
    _require_security()
    from agent_foundations.security.models import PolicyDecision

    request = _request(resource=_resource(kind="unknown", scope="unknown", identifier="x"))
    assert _decide("PROJECT_FULL_ACCESS", request).decision is PolicyDecision.DENY


def test_out_of_project_write_is_hard_denied() -> None:
    _require_security()
    from agent_foundations.security.models import PolicyDecision

    request = _request(
        tool_name="apply_patch",
        manifest=_manifest(
            name="apply_patch",
            resource_kind="project_path",
            operations=("write",),
            side_effect="project_write",
        ),
        resource=_resource(scope="external_exact_path", identifier="/tmp/x"),
        operation="write",
    )
    assert _decide("PROJECT_FULL_ACCESS", request).decision is PolicyDecision.DENY


def test_unknown_scope_project_write_is_hard_denied() -> None:
    _require_security()
    from agent_foundations.security.models import PolicyDecision

    request = _request(
        tool_name="apply_patch",
        manifest=_manifest(
            name="apply_patch",
            resource_kind="project_path",
            operations=("write",),
            side_effect="project_write",
        ),
        resource=_resource(scope="unknown", identifier="unresolved-target"),
        operation="write",
    )
    outcome = _decide("PROJECT_FULL_ACCESS", request)
    assert outcome.decision is PolicyDecision.DENY
    assert outcome.reason_code == "non_project_internal_write_forbidden"


def test_system_modification_is_hard_denied() -> None:
    _require_security()
    from agent_foundations.security.models import PolicyDecision

    request = _request(
        tool_name="set_env",
        manifest=_manifest(
            name="set_env",
            resource_kind="system",
            operations=("modify",),
            side_effect="none",
        ),
        resource=_resource(kind="system", scope="unknown", identifier="PATH"),
        operation="modify",
    )
    assert _decide("PROJECT_FULL_ACCESS", request).decision is PolicyDecision.DENY


def test_policy_engine_is_deterministic() -> None:
    _require_security()
    from agent_foundations.security.policy import PolicyEngine

    engine = PolicyEngine()
    profile = _profile("ASK_ALWAYS")
    request = _request()
    first = engine.decide(profile, request)
    second = engine.decide(profile, request)
    assert first == second


def test_policy_engine_has_no_io_side_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    _require_security()
    from agent_foundations.security.policy import PolicyEngine

    def fail_execute(*_args: object, **_kwargs: object) -> ToolResult:
        raise AssertionError("PolicyEngine must not execute tools")

    monkeypatch.setattr("builtins.open", fail_execute)
    engine = PolicyEngine()
    outcome = engine.decide(_profile("PROJECT_READ_ONLY"), _request())
    assert outcome.decision.value == "allow"


def test_future_write_denied_when_not_in_profile_allowlist() -> None:
    _require_security()
    from agent_foundations.security.models import (
        PermissionProfileName,
        PolicyDecision,
        default_allowed_tools,
    )
    from agent_foundations.security.policy import PolicyEngine

    request = _request(
        tool_name="future_write",
        manifest=_manifest(
            name="future_write",
            resource_kind="project_path",
            operations=("write",),
            side_effect="project_write",
        ),
        operation="write",
    )
    profile = _profile(
        "PROJECT_FULL_ACCESS",
        allowed_tools=default_allowed_tools(PermissionProfileName.PROJECT_FULL_ACCESS),
    )
    outcome = PolicyEngine().decide(profile, request)
    assert outcome.decision is PolicyDecision.DENY
    assert outcome.reason_code == "tool_not_in_profile_allowlist"


def test_profile_version_mismatch_is_denied() -> None:
    _require_security()
    from agent_foundations.security.models import PolicyDecision
    from agent_foundations.security.policy import PolicyEngine

    profile = _profile("ASK_ALWAYS", version=2)
    request = _request(profile_version=1)
    outcome = PolicyEngine().decide(profile, request)
    assert outcome.decision is PolicyDecision.DENY
    assert outcome.reason_code == "profile_version_mismatch"


def test_manifest_resource_kind_mismatch_is_denied() -> None:
    _require_security()
    from agent_foundations.security.models import PolicyDecision
    from agent_foundations.security.policy import PolicyEngine

    request = _request(
        manifest=_manifest(name="read_file", resource_kind="network", operations=("read",)),
        resource=_resource(kind="project_path"),
    )
    outcome = PolicyEngine().decide(_profile("PROJECT_READ_ONLY"), request)
    assert outcome.decision is PolicyDecision.DENY
    assert outcome.reason_code == "manifest_resource_kind_mismatch"


def test_process_tool_without_sandbox_required_is_denied() -> None:
    _require_security()
    from agent_foundations.security.models import PolicyDecision, SideEffectKind, ToolManifest
    from agent_foundations.security.policy import PolicyEngine

    manifest = ToolManifest(
        name="run_command",
        resource_kind="sandbox_command",
        operations=("execute",),
        side_effect=SideEffectKind.PROCESS,
        sandbox_required=False,
    )
    request = _request(
        tool_name="run_command",
        manifest=manifest,
        resource=_resource(
            kind="sandbox_command",
            identifier="pytest -q",
            category="test",
        ),
        operation="execute",
    )
    outcome = PolicyEngine().decide(_profile("RISK_BASED"), request)
    assert outcome.decision is PolicyDecision.DENY
    assert outcome.reason_code == "process_tool_requires_sandbox"


def test_custom_rule_requires_matching_tool_and_path_prefix() -> None:
    _require_security()
    from agent_foundations.security.models import (
        PermissionProfileName,
        PolicyDecision,
        default_allowed_tools,
    )

    allowed_tools = default_allowed_tools(PermissionProfileName.PROJECT_FULL_ACCESS)
    request = _request(
        tool_name="apply_patch",
        manifest=_manifest(
            name="apply_patch",
            resource_kind="project_path",
            operations=("write",),
            side_effect="project_write",
        ),
        resource=_resource(identifier="lib/other.py"),
        operation="write",
    )
    outcome = _decide(
        "CUSTOM",
        request,
        allowed_tools=allowed_tools,
        custom_rules=(
            {
                "tool_name": "apply_patch",
                "resource_kind": "project_path",
                "operation": "write",
                "side_effect": "project_write",
                "path_prefix": "src/",
                "decision": "allow",
            },
        ),
    )
    assert outcome.decision is PolicyDecision.DENY

    allowed = _decide(
        "CUSTOM",
        _request(
            tool_name="apply_patch",
            manifest=_manifest(
                name="apply_patch",
                resource_kind="project_path",
                operations=("write",),
                side_effect="project_write",
            ),
            resource=_resource(identifier="src/main.py"),
            operation="write",
        ),
        allowed_tools=allowed_tools,
        custom_rules=(
            {
                "tool_name": "apply_patch",
                "resource_kind": "project_path",
                "operation": "write",
                "side_effect": "project_write",
                "path_prefix": "src/",
                "decision": "allow",
            },
        ),
    )
    assert allowed.decision is PolicyDecision.ALLOW


def test_custom_path_prefix_requires_segment_boundary() -> None:
    _require_security()
    from agent_foundations.security.models import (
        PermissionProfileName,
        PolicyDecision,
        default_allowed_tools,
    )

    allowed_tools = default_allowed_tools(PermissionProfileName.PROJECT_FULL_ACCESS)
    custom_rules = (
        {
            "tool_name": "apply_patch",
            "resource_kind": "project_path",
            "operation": "write",
            "side_effect": "project_write",
            "path_prefix": "src",
            "decision": "allow",
        },
    )

    escaped = _decide(
        "CUSTOM",
        _request(
            tool_name="apply_patch",
            manifest=_manifest(
                name="apply_patch",
                resource_kind="project_path",
                operations=("write",),
                side_effect="project_write",
            ),
            resource=_resource(identifier="src_evil/payload.py"),
            operation="write",
        ),
        allowed_tools=allowed_tools,
        custom_rules=custom_rules,
    )
    assert escaped.decision is PolicyDecision.DENY

    descendant = _decide(
        "CUSTOM",
        _request(
            tool_name="apply_patch",
            manifest=_manifest(
                name="apply_patch",
                resource_kind="project_path",
                operations=("write",),
                side_effect="project_write",
            ),
            resource=_resource(identifier="src/main.py"),
            operation="write",
        ),
        allowed_tools=allowed_tools,
        custom_rules=custom_rules,
    )
    assert descendant.decision is PolicyDecision.ALLOW
