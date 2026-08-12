from __future__ import annotations

from agent_foundations.security.models import (
    CustomPolicyRule,
    PermissionProfile,
    PermissionProfileName,
    PolicyDecision,
    PolicyOutcome,
    PolicyRequest,
    ResourceScope,
    SideEffectKind,
)

_BUILTIN_READ_RESOURCE_KINDS = frozenset({"project_path", "plan", "patch_proposal"})
_KNOWN_RESOURCE_KINDS = _BUILTIN_READ_RESOURCE_KINDS | frozenset(
    {"sandbox_command", "network", "system"},
)
_HARD_DENY_RESOURCE_KINDS = frozenset({"network", "system", "unknown"})


class PolicyEngine:
    """Pure allow / ask / deny decisions without execution or authorization."""

    def decide(
        self,
        profile: PermissionProfile,
        request: PolicyRequest,
    ) -> PolicyOutcome:
        if request.manifest.name != request.tool_name:
            return _outcome(
                PolicyDecision.DENY,
                "hard_deny.unknown_tool",
                "tool_manifest_name_mismatch",
            )
        if request.operation not in request.manifest.operations:
            return _outcome(
                PolicyDecision.DENY,
                "hard_deny.unknown_operation",
                "operation_not_in_manifest",
            )
        if request.profile_version != profile.version:
            return _outcome(
                PolicyDecision.DENY,
                "hard_deny.profile_version_mismatch",
                "profile_version_mismatch",
            )
        if request.manifest.resource_kind != request.resource.kind:
            return _outcome(
                PolicyDecision.DENY,
                "hard_deny.resource_kind_mismatch",
                "manifest_resource_kind_mismatch",
            )
        if request.tool_name not in profile.allowed_tools:
            return _outcome(
                PolicyDecision.DENY,
                "hard_deny.tool_not_in_profile",
                "tool_not_in_profile_allowlist",
            )

        hard_deny = _hard_deny_outcome(request)
        if hard_deny is not None:
            return hard_deny

        if request.manifest.side_effect is SideEffectKind.PROCESS:
            if not request.manifest.sandbox_required:
                return _outcome(
                    PolicyDecision.DENY,
                    "hard_deny.sandbox_required",
                    "process_tool_requires_sandbox",
                )
            if request.resource.kind != "sandbox_command":
                return _outcome(
                    PolicyDecision.DENY,
                    "hard_deny.sandbox_resource",
                    "process_tool_requires_sandbox_command_resource",
                )

        if _is_unconditional_allow(request):
            return _outcome(
                PolicyDecision.ALLOW,
                "builtin.read_plan_validate.allow",
                "read_plan_or_validate_allowed",
            )

        if profile.name is PermissionProfileName.CUSTOM:
            custom = _custom_outcome(profile.custom_rules, request)
            if custom is not None:
                return custom
            return _outcome(
                PolicyDecision.DENY,
                "builtin.default_deny",
                "no_matching_rule",
            )

        builtin = _builtin_matrix_outcome(profile.name, request)
        if builtin is not None:
            return builtin

        return _outcome(
            PolicyDecision.DENY,
            "builtin.default_deny",
            "no_matching_rule",
        )


def _outcome(decision: PolicyDecision, rule_id: str, reason_code: str) -> PolicyOutcome:
    return PolicyOutcome(decision=decision, rule_id=rule_id, reason_code=reason_code)


def _hard_deny_outcome(request: PolicyRequest) -> PolicyOutcome | None:
    manifest = request.manifest
    resource = request.resource

    if manifest.side_effect is SideEffectKind.NETWORK:
        return _outcome(
            PolicyDecision.DENY,
            "hard_deny.network",
            "network_side_effect",
        )
    if resource.kind in _HARD_DENY_RESOURCE_KINDS:
        return _outcome(
            PolicyDecision.DENY,
            "hard_deny.unknown_resource",
            "unknown_or_forbidden_resource_kind",
        )
    if resource.kind not in _KNOWN_RESOURCE_KINDS:
        return _outcome(
            PolicyDecision.DENY,
            "hard_deny.unknown_resource",
            "unknown_resource_kind",
        )
    if (
        manifest.side_effect is SideEffectKind.PROJECT_WRITE
        and resource.scope is not ResourceScope.PROJECT_INTERNAL
    ):
        return _outcome(
            PolicyDecision.DENY,
            "hard_deny.out_of_project_write",
            "non_project_internal_write_forbidden",
        )
    if resource.kind == "system":
        return _outcome(
            PolicyDecision.DENY,
            "hard_deny.system_modification",
            "system_modification_forbidden",
        )
    return None


def _is_unconditional_allow(request: PolicyRequest) -> bool:
    manifest = request.manifest
    if manifest.side_effect is not SideEffectKind.NONE:
        return False
    return _is_read_like_request(request)


def _builtin_matrix_outcome(
    profile_name: PermissionProfileName,
    request: PolicyRequest,
) -> PolicyOutcome | None:
    manifest = request.manifest
    resource = request.resource

    if manifest.side_effect is SideEffectKind.PROJECT_WRITE:
        return _project_write_outcome(profile_name)

    if (
        manifest.side_effect is SideEffectKind.PROCESS
        and resource.kind == "sandbox_command"
        and manifest.sandbox_required
    ):
        return _sandbox_command_outcome(profile_name)

    if (
        resource.kind == "project_path"
        and resource.scope is ResourceScope.EXTERNAL_EXACT_PATH
        and request.operation in {"read", "list", "search"}
    ):
        if profile_name is PermissionProfileName.ASK_ALWAYS:
            return _outcome(
                PolicyDecision.ASK,
                "builtin.external_read.ask",
                "external_exact_read_requires_approval",
            )
        return _outcome(
            PolicyDecision.DENY,
            "builtin.external_read.deny",
            "external_exact_read_not_allowed",
        )

    return None


def _is_read_like_request(request: PolicyRequest) -> bool:
    resource = request.resource
    if resource.kind == "project_path":
        return (
            resource.scope is ResourceScope.PROJECT_INTERNAL
            and request.operation in {"read", "list", "search"}
        )
    if resource.kind == "plan":
        return request.operation in {"create", "update", "replan"}
    if resource.kind == "patch_proposal":
        return request.operation == "validate"
    return False


def _project_write_outcome(profile_name: PermissionProfileName) -> PolicyOutcome:
    matrix = {
        PermissionProfileName.PROJECT_READ_ONLY: PolicyDecision.DENY,
        PermissionProfileName.ASK_ALWAYS: PolicyDecision.ASK,
        PermissionProfileName.RISK_BASED: PolicyDecision.ASK,
        PermissionProfileName.PROJECT_FULL_ACCESS: PolicyDecision.ALLOW,
    }
    if profile_name in matrix:
        decision = matrix[profile_name]
        return _outcome(
            decision,
            f"builtin.project_write.{decision.value}",
            f"project_write_{decision.value}",
        )
    return _outcome(
        PolicyDecision.DENY,
        "builtin.project_write.deny",
        "project_write_custom_default_deny",
    )


def _sandbox_command_outcome(profile_name: PermissionProfileName) -> PolicyOutcome:
    matrix = {
        PermissionProfileName.PROJECT_READ_ONLY: PolicyDecision.DENY,
        PermissionProfileName.ASK_ALWAYS: PolicyDecision.ASK,
        PermissionProfileName.RISK_BASED: PolicyDecision.ALLOW,
        PermissionProfileName.PROJECT_FULL_ACCESS: PolicyDecision.ALLOW,
    }
    if profile_name in matrix:
        decision = matrix[profile_name]
        return _outcome(
            decision,
            f"builtin.sandbox_command.{decision.value}",
            f"sandbox_command_{decision.value}",
        )
    return _outcome(
        PolicyDecision.DENY,
        "builtin.sandbox_command.deny",
        "sandbox_command_custom_default_deny",
    )


def _custom_outcome(
    rules: tuple[CustomPolicyRule, ...],
    request: PolicyRequest,
) -> PolicyOutcome | None:
    manifest = request.manifest
    resource = request.resource
    for rule in rules:
        if rule.tool_name != request.tool_name:
            continue
        if rule.resource_kind != resource.kind:
            continue
        if rule.operation != request.operation:
            continue
        if rule.side_effect is not None and rule.side_effect is not manifest.side_effect:
            continue
        if rule.path_prefix is not None:
            if resource.kind != "project_path":
                continue
            if not _matches_path_prefix(resource.identifier, rule.path_prefix):
                continue
        if rule.command_category is not None:
            if resource.kind != "sandbox_command":
                continue
            if resource.category != rule.command_category:
                continue
        if rule.decision is PolicyDecision.ALLOW:
            hard_deny = _hard_deny_outcome(request)
            if hard_deny is not None:
                return hard_deny
        return _outcome(
            rule.decision,
            "custom.explicit_rule",
            f"custom_{rule.decision.value}",
        )
    return None


def _matches_path_prefix(identifier: str, path_prefix: str) -> bool:
    normalized_identifier = identifier.replace("\\", "/").rstrip("/")
    normalized_prefix = path_prefix.replace("\\", "/").rstrip("/")
    if not normalized_prefix:
        return False
    return normalized_identifier == normalized_prefix or normalized_identifier.startswith(
        f"{normalized_prefix}/",
    )
