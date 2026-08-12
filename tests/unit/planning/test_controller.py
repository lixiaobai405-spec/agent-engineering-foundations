from __future__ import annotations

import importlib.util
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from agent_foundations.planning.models import PlanStep


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


def test_create_starts_at_version_one() -> None:
    _require_planning_module("controller")
    from agent_foundations.planning.controller import PlanController

    controller = PlanController(plan_id_factory=lambda: "fixed-plan")
    plan = controller.create("inspect", (_step("read", "read file"),))

    assert plan.version == 1
    assert plan.replan_count == 0
    assert plan.max_replans == 2
    assert plan.plan_id == "fixed-plan"


def test_create_rejects_second_plan() -> None:
    _require_planning_module("controller")
    from agent_foundations.planning.controller import PlanController, PlanError

    controller = PlanController(plan_id_factory=lambda: "fixed-plan")
    controller.create("inspect", (_step("read"),))

    with pytest.raises(PlanError, match="already exists"):
        controller.create("again", (_step("other"),))


def test_completed_step_requires_recorded_execution_fact() -> None:
    _require_planning_module("controller")
    from agent_foundations.planning.controller import PlanController, PlanTransitionError
    from agent_foundations.planning.models import PlanStep, PlanStepStatus

    controller = PlanController()
    plan = controller.create("inspect", (PlanStep(step_id="read", description="read"),))
    plan = controller.transition(
        plan.version,
        "read",
        PlanStepStatus.IN_PROGRESS,
        (),
    )
    with pytest.raises(PlanTransitionError, match="evidence"):
        controller.transition(
            plan.version,
            "read",
            PlanStepStatus.COMPLETED,
            (),
        )


def test_completed_step_rejects_blank_evidence_ref() -> None:
    _require_planning_module("controller")
    from agent_foundations.planning.controller import PlanController, PlanTransitionError
    from agent_foundations.planning.models import PlanStep, PlanStepStatus

    controller = PlanController()
    plan = controller.create("inspect", (PlanStep(step_id="read", description="read"),))
    plan = controller.transition(
        plan.version,
        "read",
        PlanStepStatus.IN_PROGRESS,
        (),
    )
    with pytest.raises(PlanTransitionError, match="blank"):
        controller.transition(
            plan.version,
            "read",
            PlanStepStatus.COMPLETED,
            ("",),
        )


def test_completed_step_rejects_whitespace_evidence_ref() -> None:
    _require_planning_module("controller")
    from agent_foundations.planning.controller import PlanController, PlanTransitionError
    from agent_foundations.planning.models import PlanStep, PlanStepStatus

    controller = PlanController()
    plan = controller.create("inspect", (PlanStep(step_id="read", description="read"),))
    plan = controller.transition(
        plan.version,
        "read",
        PlanStepStatus.IN_PROGRESS,
        (),
    )
    with pytest.raises(PlanTransitionError, match="blank"):
        controller.transition(
            plan.version,
            "read",
            PlanStepStatus.COMPLETED,
            ("  ",),
        )


def test_transition_allows_valid_status_changes() -> None:
    _require_planning_module("controller")
    from agent_foundations.planning.controller import PlanController
    from agent_foundations.planning.models import PlanStepStatus

    controller = PlanController(plan_id_factory=lambda: "plan-1")
    plan = controller.create("goal", (_step("a"), _step("b", depends_on=("a",))))

    plan = controller.transition(plan.version, "a", PlanStepStatus.IN_PROGRESS, ())
    assert plan.steps[0].status == PlanStepStatus.IN_PROGRESS

    plan = controller.transition(plan.version, "a", PlanStepStatus.COMPLETED, ("fact-a",))
    assert plan.steps[0].status == PlanStepStatus.COMPLETED
    assert plan.steps[0].evidence_refs == ("fact-a",)

    plan = controller.transition(plan.version, "b", PlanStepStatus.IN_PROGRESS, ())
    plan = controller.transition(plan.version, "b", PlanStepStatus.BLOCKED, ())
    plan = controller.transition(plan.version, "b", PlanStepStatus.PENDING, ())
    plan = controller.transition(plan.version, "b", PlanStepStatus.IN_PROGRESS, ())
    plan = controller.transition(plan.version, "b", PlanStepStatus.COMPLETED, ("fact-b",))
    assert plan.steps[1].evidence_refs == ("fact-b",)


def test_transition_rejects_illegal_jump() -> None:
    _require_planning_module("controller")
    from agent_foundations.planning.controller import PlanController, PlanTransitionError
    from agent_foundations.planning.models import PlanStepStatus

    controller = PlanController()
    plan = controller.create("goal", (_step("a"),))

    with pytest.raises(PlanTransitionError, match="transition"):
        controller.transition(plan.version, "a", PlanStepStatus.COMPLETED, ("fact",))


def test_transition_rejects_unknown_step() -> None:
    _require_planning_module("controller")
    from agent_foundations.planning.controller import PlanController, PlanTransitionError
    from agent_foundations.planning.models import PlanStepStatus

    controller = PlanController()
    plan = controller.create("goal", (_step("a"),))

    with pytest.raises(PlanTransitionError, match="step_id"):
        controller.transition(plan.version, "missing", PlanStepStatus.IN_PROGRESS, ())


def test_transition_rejects_no_op_status() -> None:
    _require_planning_module("controller")
    from agent_foundations.planning.controller import PlanController, PlanTransitionError
    from agent_foundations.planning.models import PlanStepStatus

    controller = PlanController()
    plan = controller.create("goal", (_step("a"),))

    with pytest.raises(PlanTransitionError, match="no-op"):
        controller.transition(plan.version, "a", PlanStepStatus.PENDING, ())


def test_transition_rejects_second_in_progress_step() -> None:
    _require_planning_module("controller")
    from agent_foundations.planning.controller import PlanController, PlanTransitionError
    from agent_foundations.planning.models import PlanStepStatus

    controller = PlanController()
    plan = controller.create("goal", (_step("a"), _step("b")))
    plan = controller.transition(plan.version, "a", PlanStepStatus.IN_PROGRESS, ())

    with pytest.raises(PlanTransitionError, match="in_progress"):
        controller.transition(plan.version, "b", PlanStepStatus.IN_PROGRESS, ())


def test_transition_rejects_unmet_dependency_for_in_progress() -> None:
    _require_planning_module("controller")
    from agent_foundations.planning.controller import PlanController, PlanTransitionError
    from agent_foundations.planning.models import PlanStepStatus

    controller = PlanController()
    plan = controller.create("goal", (_step("a"), _step("b", depends_on=("a",))))

    with pytest.raises(PlanTransitionError, match="dependency"):
        controller.transition(plan.version, "b", PlanStepStatus.IN_PROGRESS, ())


def test_transition_rejects_modifying_completed_step() -> None:
    _require_planning_module("controller")
    from agent_foundations.planning.controller import PlanController, PlanTransitionError
    from agent_foundations.planning.models import PlanStepStatus

    controller = PlanController()
    plan = controller.create("goal", (_step("a"),))
    plan = controller.transition(plan.version, "a", PlanStepStatus.IN_PROGRESS, ())
    plan = controller.transition(plan.version, "a", PlanStepStatus.COMPLETED, ("fact",))

    with pytest.raises(PlanTransitionError, match="completed"):
        controller.transition(plan.version, "a", PlanStepStatus.BLOCKED, ())


def test_transition_without_plan_raises() -> None:
    _require_planning_module("controller")
    from agent_foundations.planning.controller import PlanController, PlanTransitionError
    from agent_foundations.planning.models import PlanStepStatus

    controller = PlanController()

    with pytest.raises(PlanTransitionError, match="no plan"):
        controller.transition(1, "a", PlanStepStatus.IN_PROGRESS, ())


def test_version_conflict_does_not_mutate_state() -> None:
    _require_planning_module("controller")
    from agent_foundations.planning.controller import PlanController, PlanVersionConflictError
    from agent_foundations.planning.models import PlanStepStatus

    controller = PlanController(plan_id_factory=lambda: "plan-1")
    plan = controller.create("goal", (_step("a"),))

    with pytest.raises(PlanVersionConflictError, match="version"):
        controller.transition(99, "a", PlanStepStatus.IN_PROGRESS, ())

    assert controller.current_plan is plan
    assert controller.current_plan.version == 1
    assert controller.current_plan.steps[0].status == PlanStepStatus.PENDING


def test_successful_transition_increments_version_by_one() -> None:
    _require_planning_module("controller")
    from agent_foundations.planning.controller import PlanController
    from agent_foundations.planning.models import PlanStepStatus

    controller = PlanController()
    plan = controller.create("goal", (_step("a"),))
    updated = controller.transition(plan.version, "a", PlanStepStatus.IN_PROGRESS, ())

    assert updated.version == plan.version + 1


def test_replan_requires_non_blank_reason() -> None:
    _require_planning_module("controller")
    from agent_foundations.planning.controller import PlanController, PlanError

    controller = PlanController()
    plan = controller.create("goal", (_step("a"), _step("b")))

    with pytest.raises(PlanError, match="reason"):
        controller.replan(plan.version, "   ", (_step("c"),))


def test_replan_preserves_completed_steps_and_evidence() -> None:
    _require_planning_module("controller")
    from agent_foundations.planning.controller import PlanController
    from agent_foundations.planning.models import PlanStepStatus

    controller = PlanController(plan_id_factory=lambda: "plan-1")
    plan = controller.create(
        "goal",
        (
            _step("a"),
            _step("b", depends_on=("a",)),
            _step("c"),
        ),
    )
    plan = controller.transition(plan.version, "a", PlanStepStatus.IN_PROGRESS, ())
    plan = controller.transition(plan.version, "a", PlanStepStatus.COMPLETED, ("fact-a",))
    plan = controller.transition(plan.version, "c", PlanStepStatus.IN_PROGRESS, ())

    replanned = controller.replan(
        plan.version,
        "blocked path",
        (_step("d", depends_on=("a",)),),
    )

    assert replanned.steps[0].step_id == "a"
    assert replanned.steps[0].status == PlanStepStatus.COMPLETED
    assert replanned.steps[0].evidence_refs == ("fact-a",)
    assert tuple(step.step_id for step in replanned.steps) == ("a", "d")
    assert replanned.goal == "goal"
    assert replanned.plan_id == "plan-1"
    assert replanned.max_replans == 2


def test_replan_replaces_non_completed_steps_only() -> None:
    _require_planning_module("controller")
    from agent_foundations.planning.controller import PlanController
    from agent_foundations.planning.models import PlanStepStatus

    controller = PlanController()
    plan = controller.create("goal", (_step("pending"), _step("blocked"), _step("done")))
    plan = controller.transition(plan.version, "blocked", PlanStepStatus.BLOCKED, ())
    plan = controller.transition(plan.version, "done", PlanStepStatus.IN_PROGRESS, ())
    plan = controller.transition(plan.version, "done", PlanStepStatus.COMPLETED, ("fact-done",))

    replanned = controller.replan(
        plan.version,
        "new approach",
        (_step("replacement"),),
    )

    assert tuple(step.step_id for step in replanned.steps) == ("done", "replacement")
    assert replanned.steps[0].evidence_refs == ("fact-done",)
    assert replanned.steps[1].status == PlanStepStatus.PENDING


def test_replan_rejects_non_pending_replacement_steps() -> None:
    _require_planning_module("controller")
    from agent_foundations.planning.controller import PlanController, PlanError
    from agent_foundations.planning.models import PlanStep, PlanStepStatus

    controller = PlanController()
    plan = controller.create("goal", (_step("a"),))

    with pytest.raises(PlanError, match="PENDING"):
        controller.replan(
            plan.version,
            "reason",
            (
                PlanStep(
                    step_id="b",
                    description="b",
                    status=PlanStepStatus.IN_PROGRESS,
                ),
            ),
        )


def test_replan_rejects_replacement_steps_with_evidence() -> None:
    _require_planning_module("controller")
    from agent_foundations.planning.controller import PlanController, PlanError

    controller = PlanController()
    plan = controller.create("goal", (_step("a"),))

    with pytest.raises(PlanError, match="evidence"):
        controller.replan(plan.version, "reason", (_step("b", evidence_refs=("fact",)),))


def test_replan_validates_combined_dag() -> None:
    _require_planning_module("controller")
    from agent_foundations.planning.controller import PlanController, PlanError
    from agent_foundations.planning.models import PlanStepStatus

    controller = PlanController()
    plan = controller.create("goal", (_step("a"),))
    plan = controller.transition(plan.version, "a", PlanStepStatus.IN_PROGRESS, ())
    plan = controller.transition(plan.version, "a", PlanStepStatus.COMPLETED, ("fact-a",))

    with pytest.raises(PlanError, match="depends_on"):
        controller.replan(plan.version, "bad dag", (_step("b", depends_on=("missing",)),))


def test_replan_increments_version_and_replan_count() -> None:
    _require_planning_module("controller")
    from agent_foundations.planning.controller import PlanController

    controller = PlanController()
    plan = controller.create("goal", (_step("a"),))
    replanned = controller.replan(plan.version, "first", (_step("b"),))

    assert replanned.version == plan.version + 1
    assert replanned.replan_count == 1


def test_replan_limit_enforced_without_partial_update() -> None:
    _require_planning_module("controller")
    from agent_foundations.planning.controller import PlanController, PlanReplanLimitError

    controller = PlanController()
    plan = controller.create("goal", (_step("a"),))
    plan = controller.replan(plan.version, "first", (_step("b"),))
    plan = controller.replan(plan.version, "second", (_step("c"),))

    with pytest.raises(PlanReplanLimitError):
        controller.replan(plan.version, "third", (_step("d"),))

    assert controller.current_plan.version == plan.version
    assert controller.current_plan.replan_count == 2
    assert tuple(step.step_id for step in controller.current_plan.steps) == ("c",)


def test_replan_version_conflict_does_not_mutate_state() -> None:
    _require_planning_module("controller")
    from agent_foundations.planning.controller import PlanController, PlanVersionConflictError

    controller = PlanController()
    plan = controller.create("goal", (_step("a"),))

    with pytest.raises(PlanVersionConflictError, match="version"):
        controller.replan(0, "reason", (_step("b"),))

    assert controller.current_plan is plan


def test_last_replan_reason_available_after_successful_replan() -> None:
    _require_planning_module("controller")
    from agent_foundations.planning.controller import PlanController

    controller = PlanController()
    plan = controller.create("goal", (_step("a"),))
    controller.replan(plan.version, "need new steps", (_step("b"),))

    assert controller.last_replan_reason == "need new steps"
