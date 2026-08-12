from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

from agent_foundations.domain.errors import InvalidToolArgumentsError
from agent_foundations.domain.tool import ToolResult
from agent_foundations.runtime.tool_execution import (
    ToolExecutionContext,
)
from agent_foundations.tools.registry import ToolRegistry

SESSION_ID = "22222222-2222-4222-8222-222222222222"
FIXTURE_ROOT = Path("tests/fixtures/sample_project").resolve()


def _require_planning_module(module_name: str) -> None:
    package_spec = importlib.util.find_spec("agent_foundations.planning")
    assert package_spec is not None, "agent_foundations.planning package must exist"
    module_spec = importlib.util.find_spec(f"agent_foundations.planning.{module_name}")
    assert module_spec is not None, f"agent_foundations.planning.{module_name} must exist"


def _planning_stack() -> tuple[Any, Any, tuple[Any, ...], dict[str, Any], tuple[Any, ...]]:
    _require_planning_module("tools")
    from agent_foundations.planning.controller import PlanController
    from agent_foundations.planning.execution import ExecutionFactJournal
    from agent_foundations.planning.tools import (
        build_planning_registered_tools,
        build_planning_tools,
    )

    controller = PlanController(plan_id_factory=lambda: "plan-1")
    journal = ExecutionFactJournal()
    tools = build_planning_tools(controller, journal)
    registered = build_planning_registered_tools(controller, journal)
    return controller, journal, tools, {tool.name: tool for tool in tools}, registered


def _assert_schema_contract(schema: dict[str, Any], *, required: list[str]) -> None:
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert schema["required"] == required


def test_set_plan_schema_contract() -> None:
    _require_planning_module("tools")
    from agent_foundations.planning.tools import SetPlanTool

    _, _, tools, _, _ = _planning_stack()
    set_plan = next(tool for tool in tools if tool.name == "set_plan")
    assert isinstance(set_plan, SetPlanTool)

    schema = set_plan.input_schema()
    _assert_schema_contract(schema, required=["goal", "steps"])
    step_schema = schema["properties"]["steps"]["items"]
    assert step_schema["additionalProperties"] is False
    assert step_schema["required"] == ["step_id", "description"]


def test_update_plan_step_schema_contract() -> None:
    _require_planning_module("tools")
    from agent_foundations.planning.tools import UpdatePlanStepTool

    _, _, tools, _, _ = _planning_stack()
    update_step = next(tool for tool in tools if tool.name == "update_plan_step")
    assert isinstance(update_step, UpdatePlanStepTool)

    schema = update_step.input_schema()
    _assert_schema_contract(
        schema,
        required=["plan_version", "step_id", "status"],
    )


def test_replan_schema_contract() -> None:
    _require_planning_module("tools")
    from agent_foundations.planning.tools import ReplanTool

    _, _, tools, _, _ = _planning_stack()
    replan = next(tool for tool in tools if tool.name == "replan")
    assert isinstance(replan, ReplanTool)

    schema = replan.input_schema()
    _assert_schema_contract(
        schema,
        required=["plan_version", "reason", "replacement_pending_steps"],
    )
    replacement_schema = schema["properties"]["replacement_pending_steps"]["items"]
    assert replacement_schema["additionalProperties"] is False
    assert replacement_schema["required"] == ["step_id", "description"]


@pytest.mark.parametrize(
    ("tool_name", "arguments", "expected_match"),
    [
        ("set_plan", {}, "required property"),
        ("set_plan", {"goal": "g", "steps": [], "extra": True}, "Additional properties"),
        (
            "update_plan_step",
            {"plan_version": 1, "step_id": "a", "status": "pending", "extra": True},
            "Additional properties",
        ),
        (
            "replan",
            {
                "plan_version": 1,
                "reason": "why",
                "replacement_pending_steps": [{"step_id": "b", "description": "d"}],
                "extra": True,
            },
            "Additional properties",
        ),
    ],
)
def test_planning_tool_schemas_reject_invalid_arguments(
    tool_name: str,
    arguments: dict[str, Any],
    expected_match: str,
) -> None:
    _require_planning_module("tools")
    _, _, _, _, registered = _planning_stack()
    registry = ToolRegistry(registered)

    with pytest.raises(InvalidToolArgumentsError, match=expected_match):
        registry.validate_call(tool_name, arguments)


@pytest.mark.asyncio
async def test_set_plan_success_emits_plan_created_metadata() -> None:
    _require_planning_module("tools")
    _, _, tools, _, _ = _planning_stack()
    set_plan = next(tool for tool in tools if tool.name == "set_plan")

    result = await set_plan.execute(
        {
            "goal": "inspect project",
            "steps": [{"step_id": "read", "description": "list files"}],
        },
    )

    assert result.success is True
    assert result.metadata["plan_event"] == "plan.created"
    assert result.metadata["plan_id"] == "plan-1"
    assert result.metadata["version"] == 1


@pytest.mark.asyncio
async def test_set_plan_blank_goal_returns_failed_tool_result() -> None:
    _require_planning_module("tools")
    _, _, tools, _, registered = _planning_stack()
    set_plan = next(tool for tool in tools if tool.name == "set_plan")
    registry = ToolRegistry(registered)

    _, normalized = registry.validate_call(
        "set_plan",
        {
            "goal": "   ",
            "steps": [{"step_id": "read", "description": "list files"}],
        },
    )

    result = await set_plan.execute(normalized)

    assert result.success is False
    assert result.error_code == "ValidationError"
    assert "blank" in result.content.lower()


@pytest.mark.asyncio
async def test_set_plan_blank_step_description_returns_failed_tool_result() -> None:
    _require_planning_module("tools")
    _, _, tools, _, registered = _planning_stack()
    set_plan = next(tool for tool in tools if tool.name == "set_plan")
    registry = ToolRegistry(registered)

    _, normalized = registry.validate_call(
        "set_plan",
        {
            "goal": "valid goal",
            "steps": [{"step_id": "read", "description": "   "}],
        },
    )

    result = await set_plan.execute(normalized)

    assert result.success is False
    assert result.error_code == "ValidationError"


@pytest.mark.asyncio
async def test_replan_blank_replacement_step_returns_failed_tool_result() -> None:
    _require_planning_module("tools")
    _, _, tools, _, registered = _planning_stack()
    set_plan = next(tool for tool in tools if tool.name == "set_plan")
    replan = next(tool for tool in tools if tool.name == "replan")
    registry = ToolRegistry(registered)

    created = await set_plan.execute(
        {
            "goal": "goal",
            "steps": [{"step_id": "a", "description": "first"}],
        },
    )
    assert created.success is True

    _, normalized = registry.validate_call(
        "replan",
        {
            "plan_version": int(created.metadata["version"]),
            "reason": "adjust",
            "replacement_pending_steps": [
                {"step_id": "b", "description": "   "},
            ],
        },
    )

    result = await replan.execute(normalized)

    assert result.success is False
    assert result.error_code == "ValidationError"


@pytest.mark.asyncio
async def test_replan_limit_returns_failed_tool_result() -> None:
    _require_planning_module("tools")
    from agent_foundations.planning.controller import PlanReplanLimitError

    controller, _, tools, _, _ = _planning_stack()
    replan = next(tool for tool in tools if tool.name == "replan")
    plan = await next(tool for tool in tools if tool.name == "set_plan").execute(
        {
            "goal": "goal",
            "steps": [{"step_id": "a", "description": "first"}],
        },
    )
    assert plan.success is True
    version = int(plan.metadata["version"])

    for reason, replacement_id in (
        ("first", "b"),
        ("second", "c"),
    ):
        result = await replan.execute(
            {
                "plan_version": version,
                "reason": reason,
                "replacement_pending_steps": [
                    {"step_id": replacement_id, "description": replacement_id},
                ],
            },
        )
        assert result.success is True
        version = int(result.metadata["version"])

    failed = await replan.execute(
        {
            "plan_version": version,
            "reason": "third",
            "replacement_pending_steps": [
                {"step_id": "d", "description": "blocked"},
            ],
        },
    )

    assert failed.success is False
    assert failed.error_code == PlanReplanLimitError.__name__
    assert controller.current_plan.replan_count == 2


class SpyDownstreamExecutor:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, dict[str, Any], ToolExecutionContext]] = []

    async def execute(
        self,
        tool: Any,
        arguments: dict[str, Any],
        context: ToolExecutionContext,
    ) -> ToolResult:
        self.calls.append((tool, arguments, context))
        return ToolResult(success=True, content="downstream ok")


class RecordingTool:
    name = "record"
    description = "Record downstream delegation."

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, content="recorded")


@pytest.mark.asyncio
async def test_planning_tool_executor_delegates_to_downstream_and_records_fact() -> None:
    _require_planning_module("tools")
    from agent_foundations.planning.tools import PlanningToolExecutor

    controller, journal, tools, planning_tools, _ = _planning_stack()
    downstream = SpyDownstreamExecutor()
    executor = PlanningToolExecutor(
        downstream,
        controller,
        journal,
        planning_tools,
    )
    tool = RecordingTool()
    context = ToolExecutionContext(
        session_id=SESSION_ID,
        root=FIXTURE_ROOT,
        tool_call_id="call-downstream",
        tool_name=tool.name,
    )

    result = await executor.execute(tool, {}, context)

    assert result.success is True
    assert len(downstream.calls) == 1
    journal.validate_evidence_refs(SESSION_ID, ("call-downstream",))


@pytest.mark.asyncio
async def test_planning_tool_executor_records_failed_downstream_fact() -> None:
    _require_planning_module("tools")
    from agent_foundations.planning.execution import (
        InvalidEvidenceReferenceError,
    )
    from agent_foundations.planning.tools import PlanningToolExecutor

    controller, journal, _, planning_tools, _ = _planning_stack()

    class FailingDownstream:
        async def execute(
            self,
            tool: Any,
            arguments: dict[str, Any],
            context: ToolExecutionContext,
        ) -> ToolResult:
            raise RuntimeError("downstream exploded")

    executor = PlanningToolExecutor(
        FailingDownstream(),
        controller,
        journal,
        planning_tools,
    )
    context = ToolExecutionContext(
        session_id=SESSION_ID,
        root=FIXTURE_ROOT,
        tool_call_id="call-fail",
        tool_name="record",
    )

    with pytest.raises(RuntimeError, match="downstream exploded"):
        await executor.execute(RecordingTool(), {}, context)

    with pytest.raises(InvalidEvidenceReferenceError, match="failed"):
        journal.validate_evidence_refs(SESSION_ID, ("call-fail",))
