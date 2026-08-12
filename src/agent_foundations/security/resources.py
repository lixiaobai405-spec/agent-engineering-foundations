from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from agent_foundations.security.models import PolicyResource, ResourceScope
from agent_foundations.tools.filesystem.path_policy import PathPolicy

_MAX_IDENTIFIER_LEN = 256


def _bounded(value: str) -> str:
    normalized = value.strip().replace("\n", " ").replace("\r", " ")
    if not normalized:
        return "."
    return normalized[:_MAX_IDENTIFIER_LEN]


def _project_path_resource(arguments: Mapping[str, Any], policy: PathPolicy) -> PolicyResource:
    raw_path = str(arguments.get("path", "."))
    if _is_absolute_request(raw_path):
        canonical = PathPolicy.resolve_external_read_target(raw_path)
        scope = (
            ResourceScope.PROJECT_INTERNAL
            if canonical.is_relative_to(policy.root)
            else ResourceScope.EXTERNAL_EXACT_PATH
        )
        identifier = _bounded(str(canonical))
    else:
        authorized = policy.authorize(raw_path)
        scope = ResourceScope.PROJECT_INTERNAL
        identifier = _bounded(policy.display_path(authorized))
    return PolicyResource(kind="project_path", scope=scope, identifier=identifier)


def _is_absolute_request(value: str) -> bool:
    candidate = Path(value)
    return candidate.is_absolute() or candidate.drive != ""


def resolve_list_directory_resource(
    arguments: Mapping[str, Any],
    policy: PathPolicy,
) -> PolicyResource:
    return _project_path_resource(arguments, policy)


def resolve_read_file_resource(
    arguments: Mapping[str, Any],
    policy: PathPolicy,
) -> PolicyResource:
    return _project_path_resource(arguments, policy)


def resolve_search_text_resource(
    arguments: Mapping[str, Any],
    policy: PathPolicy,
) -> PolicyResource:
    return _project_path_resource(arguments, policy)


def resolve_set_plan_resource(arguments: Mapping[str, Any]) -> PolicyResource:
    goal = _bounded(str(arguments.get("goal", "plan")))
    return PolicyResource(kind="plan", scope=ResourceScope.PROJECT_INTERNAL, identifier=goal)


def resolve_update_plan_step_resource(arguments: Mapping[str, Any]) -> PolicyResource:
    step_id = _bounded(str(arguments.get("step_id", "step")))
    return PolicyResource(kind="plan", scope=ResourceScope.PROJECT_INTERNAL, identifier=step_id)


def resolve_replan_resource(arguments: Mapping[str, Any]) -> PolicyResource:
    reason = _bounded(str(arguments.get("reason", "replan")))
    return PolicyResource(kind="plan", scope=ResourceScope.PROJECT_INTERNAL, identifier=reason)


def resolve_validate_patch_resource(arguments: Mapping[str, Any]) -> PolicyResource:
    baselines = arguments.get("baselines", ())
    if isinstance(baselines, list):
        paths = [
            _bounded(str(item.get("path", "")))
            for item in baselines
            if isinstance(item, dict)
        ]
        summary = ",".join(path for path in paths if path) or "patch"
    else:
        summary = "patch"
    return PolicyResource(
        kind="patch_proposal",
        scope=ResourceScope.PROJECT_INTERNAL,
        identifier=summary[:_MAX_IDENTIFIER_LEN],
    )


def resolve_echo_resource(arguments: Mapping[str, Any]) -> PolicyResource:
    text = _bounded(str(arguments.get("text", "echo")))
    return PolicyResource(
        kind="project_path",
        scope=ResourceScope.PROJECT_INTERNAL,
        identifier=text,
    )


def resolve_contract_resource(_arguments: Mapping[str, Any]) -> PolicyResource:
    return PolicyResource(
        kind="project_path",
        scope=ResourceScope.PROJECT_INTERNAL,
        identifier="contract",
    )
