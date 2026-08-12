from __future__ import annotations

import importlib.util
from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError

if TYPE_CHECKING:
    from agent_foundations.planning.models import ExecutionPlan, PlanStep


def _require_planning_module(module_name: str) -> None:
    package_spec = importlib.util.find_spec("agent_foundations.planning")
    assert package_spec is not None, "agent_foundations.planning package must exist"
    module_spec = importlib.util.find_spec(f"agent_foundations.planning.{module_name}")
    assert module_spec is not None, f"agent_foundations.planning.{module_name} must exist"


def _step(
    step_id: str,
    description: str = "work",
    *,
    status: str = "pending",
    depends_on: tuple[str, ...] = (),
    evidence_refs: tuple[str, ...] = (),
) -> PlanStep:
    from agent_foundations.planning.models import PlanStep, PlanStepStatus

    return PlanStep(
        step_id=step_id,
        description=description,
        status=PlanStepStatus(status),
        depends_on=depends_on,
        evidence_refs=evidence_refs,
    )


def _plan(
    goal: str,
    steps: tuple[PlanStep, ...],
    *,
    plan_id: str = "plan-1",
    version: int = 1,
    replan_count: int = 0,
    max_replans: int = 2,
) -> ExecutionPlan:
    from agent_foundations.planning.models import ExecutionPlan

    return ExecutionPlan(
        plan_id=plan_id,
        version=version,
        goal=goal,
        steps=steps,
        replan_count=replan_count,
        max_replans=max_replans,
    )


def test_plan_models_are_frozen() -> None:
    _require_planning_module("models")
    step = _step("a")

    with pytest.raises(ValidationError):
        step.step_id = "changed"


def test_plan_step_model_copy_revalidates_invalid_update() -> None:
    _require_planning_module("models")
    step = _step("a")

    with pytest.raises(ValidationError):
        step.model_copy(update={"description": "   "})


def test_plan_step_rejects_blank_step_id() -> None:
    _require_planning_module("models")
    from agent_foundations.planning.models import PlanStep

    with pytest.raises(ValidationError, match="step_id"):
        PlanStep(step_id="   ", description="read")


def test_plan_step_rejects_blank_description() -> None:
    _require_planning_module("models")
    from agent_foundations.planning.models import PlanStep

    with pytest.raises(ValidationError, match="description"):
        PlanStep(step_id="read", description="  \t  ")


def test_plan_step_rejects_duplicate_dependencies() -> None:
    _require_planning_module("models")
    from agent_foundations.planning.models import PlanStep

    with pytest.raises(ValidationError, match="depends_on"):
        PlanStep(step_id="b", description="b", depends_on=("a", "a"))


def test_plan_step_rejects_self_dependency() -> None:
    _require_planning_module("models")
    from agent_foundations.planning.models import PlanStep

    with pytest.raises(ValidationError, match="depends_on"):
        PlanStep(step_id="a", description="a", depends_on=("a",))


def test_plan_step_completed_requires_evidence_refs() -> None:
    _require_planning_module("models")
    from agent_foundations.planning.models import PlanStep, PlanStepStatus

    with pytest.raises(ValidationError, match="evidence"):
        PlanStep(
            step_id="done",
            description="done",
            status=PlanStepStatus.COMPLETED,
            evidence_refs=(),
        )


def test_plan_step_rejects_blank_evidence_ref_item() -> None:
    _require_planning_module("models")
    from agent_foundations.planning.models import PlanStep, PlanStepStatus

    with pytest.raises(ValidationError, match="blank"):
        PlanStep(
            step_id="done",
            description="done",
            status=PlanStepStatus.COMPLETED,
            evidence_refs=("",),
        )


def test_plan_step_rejects_whitespace_evidence_ref_item() -> None:
    _require_planning_module("models")
    from agent_foundations.planning.models import PlanStep, PlanStepStatus

    with pytest.raises(ValidationError, match="blank"):
        PlanStep(
            step_id="done",
            description="done",
            status=PlanStepStatus.COMPLETED,
            evidence_refs=("  ",),
        )


def test_execution_plan_rejects_completed_with_blank_evidence_ref() -> None:
    _require_planning_module("models")
    from agent_foundations.planning.models import PlanStep, PlanStepStatus

    with pytest.raises(ValidationError, match="blank"):
        _plan(
            "goal",
            (
                PlanStep(
                    step_id="done",
                    description="done",
                    status=PlanStepStatus.COMPLETED,
                    evidence_refs=(" ",),
                ),
            ),
        )


def test_execution_plan_rejects_blank_plan_id() -> None:
    _require_planning_module("models")
    from agent_foundations.planning.models import ExecutionPlan

    with pytest.raises(ValidationError, match="plan_id"):
        ExecutionPlan(
            plan_id="  ",
            version=1,
            goal="goal",
            steps=(_step("a"),),
        )


def test_execution_plan_rejects_blank_goal() -> None:
    _require_planning_module("models")
    from agent_foundations.planning.models import ExecutionPlan

    with pytest.raises(ValidationError, match="goal"):
        ExecutionPlan(
            plan_id="plan-1",
            version=1,
            goal="  ",
            steps=(_step("a"),),
        )


def test_execution_plan_rejects_version_below_one() -> None:
    _require_planning_module("models")
    from agent_foundations.planning.models import ExecutionPlan

    with pytest.raises(ValidationError, match="version"):
        ExecutionPlan(
            plan_id="plan-1",
            version=0,
            goal="goal",
            steps=(_step("a"),),
        )


def test_execution_plan_rejects_empty_steps() -> None:
    _require_planning_module("models")
    from agent_foundations.planning.models import ExecutionPlan

    with pytest.raises(ValidationError, match="steps"):
        ExecutionPlan(plan_id="plan-1", version=1, goal="goal", steps=())


def test_execution_plan_rejects_duplicate_step_ids() -> None:
    _require_planning_module("models")

    with pytest.raises(ValidationError, match="step_id"):
        _plan("goal", (_step("dup"), _step("dup")))


def test_execution_plan_rejects_dangling_dependency() -> None:
    _require_planning_module("models")

    with pytest.raises(ValidationError, match="depends_on"):
        _plan("goal", (_step("b", depends_on=("missing",)),))


def test_execution_plan_rejects_two_node_dependency_cycle() -> None:
    _require_planning_module("models")

    with pytest.raises(ValidationError, match="cycle"):
        _plan(
            "goal",
            (
                _step("a", depends_on=("b",)),
                _step("b", depends_on=("a",)),
            ),
        )


def test_execution_plan_rejects_multi_node_dependency_cycle() -> None:
    _require_planning_module("models")

    with pytest.raises(ValidationError, match="cycle"):
        _plan(
            "goal",
            (
                _step("a", depends_on=("c",)),
                _step("b", depends_on=("a",)),
                _step("c", depends_on=("b",)),
            ),
        )


def test_execution_plan_rejects_multiple_in_progress_steps() -> None:
    _require_planning_module("models")
    from agent_foundations.planning.models import PlanStepStatus

    with pytest.raises(ValidationError, match="in_progress"):
        _plan(
            "goal",
            (
                _step("a", status=PlanStepStatus.IN_PROGRESS.value),
                _step("b", status=PlanStepStatus.IN_PROGRESS.value),
            ),
        )


def test_execution_plan_rejects_completed_step_without_evidence() -> None:
    _require_planning_module("models")
    from agent_foundations.planning.models import PlanStep, PlanStepStatus

    completed = PlanStep(
        step_id="done",
        description="done",
        status=PlanStepStatus.COMPLETED,
        evidence_refs=("fact-1",),
    )
    with pytest.raises(ValidationError, match="evidence"):
        completed.model_copy(update={"evidence_refs": ()})


def test_execution_plan_rejects_in_progress_with_unmet_dependencies() -> None:
    _require_planning_module("models")
    from agent_foundations.planning.models import PlanStepStatus

    with pytest.raises(ValidationError, match="dependency"):
        _plan(
            "goal",
            (
                _step("a"),
                _step("b", status=PlanStepStatus.IN_PROGRESS.value, depends_on=("a",)),
            ),
        )


def test_execution_plan_rejects_completed_with_unmet_dependencies() -> None:
    _require_planning_module("models")
    from agent_foundations.planning.models import PlanStep, PlanStepStatus

    with pytest.raises(ValidationError, match="dependency"):
        _plan(
            "goal",
            (
                _step("a"),
                PlanStep(
                    step_id="b",
                    description="b",
                    status=PlanStepStatus.COMPLETED,
                    depends_on=("a",),
                    evidence_refs=("fact-1",),
                ),
            ),
        )


def test_execution_plan_rejects_negative_replan_count() -> None:
    _require_planning_module("models")

    with pytest.raises(ValidationError, match="replan_count"):
        _plan("goal", (_step("a"),), replan_count=-1)


def test_execution_plan_rejects_negative_max_replans() -> None:
    _require_planning_module("models")

    with pytest.raises(ValidationError, match="max_replans"):
        _plan("goal", (_step("a"),), max_replans=-1)


def test_execution_plan_rejects_replan_count_above_max() -> None:
    _require_planning_module("models")

    with pytest.raises(ValidationError, match="replan_count"):
        _plan("goal", (_step("a"),), replan_count=3, max_replans=2)


def test_execution_plan_accepts_valid_dag() -> None:
    _require_planning_module("models")
    from agent_foundations.planning.models import PlanStep, PlanStepStatus

    plan = _plan(
        "inspect",
        (
            PlanStep(
                step_id="a",
                description="a",
                status=PlanStepStatus.COMPLETED,
                evidence_refs=("fact-a",),
            ),
            _step("b", depends_on=("a",)),
        ),
    )
    assert plan.steps[1].depends_on == ("a",)


def test_cycle_detection_is_deterministic() -> None:
    _require_planning_module("models")

    steps = (
        _step("a", depends_on=("c",)),
        _step("b", depends_on=("a",)),
        _step("c", depends_on=("b",)),
    )
    with pytest.raises(ValidationError, match="cycle") as first:
        _plan("goal", steps)
    with pytest.raises(ValidationError, match="cycle") as second:
        _plan("goal", steps)
    assert first.value.errors()[0]["msg"] == second.value.errors()[0]["msg"]
