from __future__ import annotations

from typing import Any, cast

from pydantic import ValidationError

from agent_foundations.domain.tool import RegisteredTool, Tool, ToolResult
from agent_foundations.planning.controller import (
    PlanController,
    PlanError,
)
from agent_foundations.planning.execution import (
    ExecutionFactJournal,
    InvalidEvidenceReferenceError,
)
from agent_foundations.planning.models import PlanStep, PlanStepStatus
from agent_foundations.runtime.tool_execution import (
    ToolCallExecutor,
    ToolExecutionContext,
)
from agent_foundations.security.models import SideEffectKind, ToolManifest
from agent_foundations.security.resources import (
    resolve_replan_resource,
    resolve_set_plan_resource,
    resolve_update_plan_step_resource,
)

PLANNING_TOOL_NAMES = frozenset({"set_plan", "update_plan_step", "replan"})

SET_PLAN_MANIFEST = ToolManifest(
    name="set_plan",
    resource_kind="plan",
    operations=("create",),
    side_effect=SideEffectKind.NONE,
    sandbox_required=False,
)

UPDATE_PLAN_STEP_MANIFEST = ToolManifest(
    name="update_plan_step",
    resource_kind="plan",
    operations=("update",),
    side_effect=SideEffectKind.NONE,
    sandbox_required=False,
)

REPLAN_MANIFEST = ToolManifest(
    name="replan",
    resource_kind="plan",
    operations=("replan",),
    side_effect=SideEffectKind.NONE,
    sandbox_required=False,
)

_MAX_GOAL_LEN = 500
_MAX_STEPS = 20
_MAX_STEP_ID_LEN = 64
_MAX_DESCRIPTION_LEN = 500
_MAX_DEPENDS_ON = 10
_MAX_EVIDENCE_IDS = 10
_MAX_REASON_LEN = 500


def _bounded(message: str, limit: int = 200) -> str:
    return message[:limit]


def _plan_error_result(exc: PlanError) -> ToolResult:
    return ToolResult(
        success=False,
        content=_bounded(str(exc)),
        error_code=type(exc).__name__,
    )


def _validation_error_result(exc: ValidationError) -> ToolResult:
    first_error = exc.errors()[0]
    message = str(first_error.get("msg", exc))
    return ToolResult(
        success=False,
        content=_bounded(message),
        error_code="ValidationError",
    )


def _pending_steps_from_arguments(
    step_dicts: list[dict[str, Any]],
) -> tuple[PlanStep, ...]:
    return tuple(
        PlanStep(
            step_id=str(step["step_id"]),
            description=str(step["description"]),
            depends_on=tuple(step.get("depends_on", ())),
        )
        for step in step_dicts
    )


class SetPlanTool:
    name = "set_plan"
    description = "Create a bounded execution plan with pending steps only."

    def __init__(self, controller: PlanController) -> None:
        self._controller = controller

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "goal": {"type": "string", "minLength": 1, "maxLength": _MAX_GOAL_LEN},
                "steps": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": _MAX_STEPS,
                    "items": {
                        "type": "object",
                        "properties": {
                            "step_id": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": _MAX_STEP_ID_LEN,
                            },
                            "description": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": _MAX_DESCRIPTION_LEN,
                            },
                            "depends_on": {
                                "type": "array",
                                "items": {"type": "string", "minLength": 1},
                                "maxItems": _MAX_DEPENDS_ON,
                            },
                        },
                        "required": ["step_id", "description"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["goal", "steps"],
            "additionalProperties": False,
        }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            steps = _pending_steps_from_arguments(list(arguments["steps"]))
            plan = self._controller.create(str(arguments["goal"]), steps)
        except PlanError as exc:
            return _plan_error_result(exc)
        except ValidationError as exc:
            return _validation_error_result(exc)
        return ToolResult(
            success=True,
            content=_bounded(f"plan {plan.plan_id} created at version {plan.version}"),
            metadata={
                "plan_event": "plan.created",
                "plan_id": plan.plan_id,
                "version": plan.version,
            },
        )


class UpdatePlanStepTool:
    name = "update_plan_step"
    description = "Transition one plan step using version CAS and optional evidence IDs."

    def __init__(
        self,
        controller: PlanController,
        journal: ExecutionFactJournal,
    ) -> None:
        self._controller = controller
        self._journal = journal

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "plan_version": {"type": "integer", "minimum": 1},
                "step_id": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": _MAX_STEP_ID_LEN,
                },
                "status": {
                    "type": "string",
                    "enum": [status.value for status in PlanStepStatus],
                },
                "evidence_tool_call_ids": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                    "maxItems": _MAX_EVIDENCE_IDS,
                },
            },
            "required": ["plan_version", "step_id", "status"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        arguments: dict[str, Any],
        context: ToolExecutionContext,
    ) -> ToolResult:
        status = PlanStepStatus(str(arguments["status"]))
        evidence_ids = tuple(arguments.get("evidence_tool_call_ids", ()))
        if status == PlanStepStatus.COMPLETED:
            try:
                self._journal.validate_evidence_refs(context.session_id, evidence_ids)
            except InvalidEvidenceReferenceError as exc:
                return ToolResult(
                    success=False,
                    content=_bounded(str(exc)),
                    error_code=type(exc).__name__,
                )
        try:
            plan = self._controller.transition(
                int(arguments["plan_version"]),
                str(arguments["step_id"]),
                status,
                evidence_ids,
            )
        except PlanError as exc:
            return _plan_error_result(exc)
        return ToolResult(
            success=True,
            content=_bounded(
                f"step {arguments['step_id']} -> {status.value} at version {plan.version}",
            ),
            metadata={
                "plan_event": "plan.step.updated",
                "plan_id": plan.plan_id,
                "version": plan.version,
                "step_id": str(arguments["step_id"]),
                "status": status.value,
            },
        )


class ReplanTool:
    name = "replan"
    description = "Replace unfinished plan steps with new pending steps under CAS."

    def __init__(self, controller: PlanController) -> None:
        self._controller = controller

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "plan_version": {"type": "integer", "minimum": 1},
                "reason": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": _MAX_REASON_LEN,
                },
                "replacement_pending_steps": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": _MAX_STEPS,
                    "items": {
                        "type": "object",
                        "properties": {
                            "step_id": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": _MAX_STEP_ID_LEN,
                            },
                            "description": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": _MAX_DESCRIPTION_LEN,
                            },
                            "depends_on": {
                                "type": "array",
                                "items": {"type": "string", "minLength": 1},
                                "maxItems": _MAX_DEPENDS_ON,
                            },
                        },
                        "required": ["step_id", "description"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["plan_version", "reason", "replacement_pending_steps"],
            "additionalProperties": False,
        }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            replacement = _pending_steps_from_arguments(
                list(arguments["replacement_pending_steps"]),
            )
            plan = self._controller.replan(
                int(arguments["plan_version"]),
                str(arguments["reason"]),
                replacement,
            )
        except PlanError as exc:
            return _plan_error_result(exc)
        except ValidationError as exc:
            return _validation_error_result(exc)
        return ToolResult(
            success=True,
            content=_bounded(
                f"replanned to version {plan.version} (replan_count={plan.replan_count})",
            ),
            metadata={
                "plan_event": "plan.replanned",
                "plan_id": plan.plan_id,
                "version": plan.version,
                "replan_count": plan.replan_count,
                "reason": _bounded(str(arguments["reason"]), _MAX_REASON_LEN),
            },
        )


def build_planning_tools(
    controller: PlanController,
    journal: ExecutionFactJournal,
) -> tuple[Tool, ...]:
    return cast(
        tuple[Tool, ...],
        (
            SetPlanTool(controller),
            UpdatePlanStepTool(controller, journal),
            ReplanTool(controller),
        ),
    )


def build_planning_registered_tools(
    controller: PlanController,
    journal: ExecutionFactJournal,
) -> tuple[RegisteredTool, ...]:
    return (
        RegisteredTool(
            cast(Tool, SetPlanTool(controller)),
            SET_PLAN_MANIFEST,
            resolve_set_plan_resource,
        ),
        RegisteredTool(
            cast(Tool, UpdatePlanStepTool(controller, journal)),
            UPDATE_PLAN_STEP_MANIFEST,
            resolve_update_plan_step_resource,
        ),
        RegisteredTool(
            cast(Tool, ReplanTool(controller)),
            REPLAN_MANIFEST,
            resolve_replan_resource,
        ),
    )


class PlanningToolExecutor:
    def __init__(
        self,
        downstream: ToolCallExecutor,
        controller: PlanController,
        journal: ExecutionFactJournal,
        planning_tools: dict[str, Any],
    ) -> None:
        self._downstream = downstream
        self._controller = controller
        self._journal = journal
        self._planning_tools = planning_tools

    async def execute(
        self,
        tool: Any,
        arguments: dict[str, Any],
        context: ToolExecutionContext,
    ) -> ToolResult:
        if tool.name in PLANNING_TOOL_NAMES:
            return await self._execute_planning(tool.name, arguments, context)
        try:
            result = await self._downstream.execute(tool, arguments, context)
        except Exception as exc:
            from agent_foundations.planning.execution import ExecutionFact

            self._journal.record(
                ExecutionFact(
                    session_id=context.session_id,
                    tool_call_id=context.tool_call_id,
                    tool_name=context.tool_name,
                    success=False,
                    error_code=type(exc).__name__,
                ),
            )
            raise
        from agent_foundations.planning.execution import ExecutionFact

        self._journal.record(
            ExecutionFact(
                session_id=context.session_id,
                tool_call_id=context.tool_call_id,
                tool_name=context.tool_name,
                success=result.success,
                error_code=result.error_code if not result.success else None,
            ),
        )
        return result

    async def _execute_planning(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        context: ToolExecutionContext,
    ) -> ToolResult:
        tool = self._planning_tools[tool_name]
        if tool_name == "update_plan_step":
            return cast(ToolResult, await tool.execute(arguments, context))
        return cast(ToolResult, await tool.execute(arguments))
