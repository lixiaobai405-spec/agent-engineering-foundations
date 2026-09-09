from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from agent_foundations.cli.main import build_tool_registry
from agent_foundations.security.models import (
    PermissionProfile,
    PermissionProfileName,
    PolicyRequest,
    PolicyResource,
    ResourceScope,
    default_allowed_tools,
)
from agent_foundations.security.policy import PolicyEngine
from agent_foundations.tools.patch.apply_patch import APPLY_PATCH_MANIFEST

FIXTURE = (
    Path(__file__).parents[1]
    / "fixtures"
    / "evals"
    / "phase-2c-permission-profiles-v1.json"
)


def _dataset() -> dict[str, Any]:
    value = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    assert value["schema_version"] == 1
    assert value["dataset_version"] == "v1"
    return {str(key): item for key, item in value.items()}


@pytest.mark.parametrize("case", _dataset()["cases"], ids=lambda case: case["profile"])
def test_phase2c_profile_eval_is_deterministic_and_project_bounded(
    case: dict[str, Any],
    tmp_path: Path,
) -> None:
    profile_name = PermissionProfileName(case["profile"])
    profile = PermissionProfile(
        name=profile_name,
        version=case["profile_version"],
        allowed_tools=default_allowed_tools(profile_name),
    )
    request = PolicyRequest(
        profile_version=profile.version,
        run_id="11111111-1111-4111-8111-111111111111",
        tool_call_id="profile-eval-call",
        tool_name="apply_patch",
        manifest=APPLY_PATCH_MANIFEST,
        resource=PolicyResource(
            kind="project_path",
            scope=ResourceScope.PROJECT_INTERNAL,
            identifier=f"patch:{'a' * 64}",
        ),
        operation="apply",
    )
    outcome = PolicyEngine().decide(profile, request)
    expose_apply = "apply_patch" in profile.allowed_tools
    registry = build_tool_registry(
        tmp_path,
        include_validate_patch=True,
        include_apply_patch=expose_apply,
    )
    exposed_tools = {entry.tool.name for entry in registry.registered_tools()}

    assert outcome.decision.value == case["expected_write_decision"]
    assert request.profile_version == case["profile_version"]
    assert ("apply_patch" in exposed_tools) is case["apply_patch_exposed"]
    assert "validate_patch" in exposed_tools
    assert exposed_tools.isdisjoint(_dataset()["forbidden_tools"])
