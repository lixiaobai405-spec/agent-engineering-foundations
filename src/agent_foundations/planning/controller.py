from __future__ import annotations

from collections.abc import Callable
from uuid import uuid4

from agent_foundations.planning.models import (
    ExecutionPlan,
    PlanStep,
    PlanStepStatus,
    _validate_evidence_refs,
    _validate_steps_structure,
)


class PlanError(ValueError):
    """Base planning domain error."""


class PlanTransitionError(PlanError):
    """Invalid plan transition or controller state."""


class PlanVersionConflictError(PlanError):
    """Expected plan version does not match current version."""


class PlanReplanLimitError(PlanError):
    """Replan limit has been reached."""


_ALLOWED_TRANSITIONS: frozenset[tuple[PlanStepStatus, PlanStepStatus]] = frozenset(
    {
        (PlanStepStatus.PENDING, PlanStepStatus.IN_PROGRESS),
        (PlanStepStatus.PENDING, PlanStepStatus.BLOCKED),
        (PlanStepStatus.IN_PROGRESS, PlanStepStatus.COMPLETED),
        (PlanStepStatus.IN_PROGRESS, PlanStepStatus.BLOCKED),
        (PlanStepStatus.BLOCKED, PlanStepStatus.PENDING),
    }
)


class PlanController:
    def __init__(self, *, plan_id_factory: Callable[[], str] | None = None) -> None:
        self._plan_id_factory = plan_id_factory or (lambda: str(uuid4()))
        self._plan: ExecutionPlan | None = None
        self._last_replan_reason: str | None = None

    @property
    def current_plan(self) -> ExecutionPlan:
        if self._plan is None:
            raise PlanTransitionError("no plan exists")
        return self._plan

    @property
    def last_replan_reason(self) -> str | None:
        return self._last_replan_reason

    @property
    def has_plan(self) -> bool:
        return self._plan is not None

    def all_steps_completed(self) -> bool:
        if self._plan is None:
            return False
        return all(
            step.status == PlanStepStatus.COMPLETED for step in self._plan.steps
        )

    def snapshot(self) -> ExecutionPlan:
        if self._plan is None:
            raise PlanTransitionError("no plan exists")
        return self._plan.model_copy()

    def create(self, goal: str, steps: tuple[PlanStep, ...]) -> ExecutionPlan:
        if self._plan is not None:
            raise PlanError("plan already exists")
        plan = ExecutionPlan(
            plan_id=self._plan_id_factory(),
            version=1,
            goal=goal,
            steps=steps,
            replan_count=0,
            max_replans=2,
        )
        self._plan = plan
        return plan

    def transition(
        self,
        expected_version: int,
        step_id: str,
        target: PlanStepStatus,
        evidence_refs: tuple[str, ...],
    ) -> ExecutionPlan:
        plan = self._require_version(expected_version)
        step_index = self._find_step_index(plan, step_id)
        current_step = plan.steps[step_index]

        if current_step.status == PlanStepStatus.COMPLETED:
            raise PlanTransitionError("cannot modify completed step")
        if target == current_step.status:
            raise PlanTransitionError("no-op transition")
        if (current_step.status, target) not in _ALLOWED_TRANSITIONS:
            raise PlanTransitionError("illegal transition")

        if target == PlanStepStatus.IN_PROGRESS:
            if self._count_in_progress(plan) > 0:
                raise PlanTransitionError("only one step may be in_progress")
            self._ensure_dependencies_completed(plan, current_step.depends_on)

        if target == PlanStepStatus.COMPLETED:
            if current_step.status != PlanStepStatus.IN_PROGRESS:
                raise PlanTransitionError("illegal transition")
            try:
                _validate_evidence_refs(evidence_refs)
            except ValueError as exc:
                raise PlanTransitionError(str(exc)) from exc
            self._ensure_dependencies_completed(plan, current_step.depends_on)

        update: dict[str, object] = {"status": target}
        if target == PlanStepStatus.COMPLETED:
            update["evidence_refs"] = evidence_refs

        updated_step = current_step.model_copy(update=update)
        new_steps = list(plan.steps)
        new_steps[step_index] = updated_step

        new_plan = ExecutionPlan(
            plan_id=plan.plan_id,
            version=plan.version + 1,
            goal=plan.goal,
            steps=tuple(new_steps),
            replan_count=plan.replan_count,
            max_replans=plan.max_replans,
        )
        self._plan = new_plan
        return new_plan

    def replan(
        self,
        expected_version: int,
        reason: str,
        replacement_pending_steps: tuple[PlanStep, ...],
    ) -> ExecutionPlan:
        plan = self._require_version(expected_version)
        if not reason or not reason.strip():
            raise PlanError("replan reason must not be blank")
        if plan.replan_count >= plan.max_replans:
            raise PlanReplanLimitError("replan limit reached")

        for step in replacement_pending_steps:
            if step.status != PlanStepStatus.PENDING:
                raise PlanError("replacement steps must be PENDING")
            if step.evidence_refs:
                raise PlanError("replacement steps must not carry evidence")

        completed_steps = tuple(
            step for step in plan.steps if step.status == PlanStepStatus.COMPLETED
        )
        combined_steps = completed_steps + replacement_pending_steps
        try:
            _validate_steps_structure(combined_steps)
        except ValueError as exc:
            raise PlanError(str(exc)) from exc

        new_plan = ExecutionPlan(
            plan_id=plan.plan_id,
            version=plan.version + 1,
            goal=plan.goal,
            steps=combined_steps,
            replan_count=plan.replan_count + 1,
            max_replans=plan.max_replans,
        )
        self._plan = new_plan
        self._last_replan_reason = reason
        return new_plan

    def _require_version(self, expected_version: int) -> ExecutionPlan:
        if self._plan is None:
            raise PlanTransitionError("no plan exists")
        if expected_version != self._plan.version:
            raise PlanVersionConflictError(
                f"version conflict: expected {expected_version}, "
                f"current {self._plan.version}"
            )
        return self._plan

    def _find_step_index(self, plan: ExecutionPlan, step_id: str) -> int:
        for index, step in enumerate(plan.steps):
            if step.step_id == step_id:
                return index
        raise PlanTransitionError("unknown step_id")

    def _count_in_progress(self, plan: ExecutionPlan) -> int:
        return sum(
            1 for step in plan.steps if step.status == PlanStepStatus.IN_PROGRESS
        )

    def _ensure_dependencies_completed(
        self,
        plan: ExecutionPlan,
        depends_on: tuple[str, ...],
    ) -> None:
        status_by_id = {step.step_id: step.status for step in plan.steps}
        for dependency in depends_on:
            if status_by_id[dependency] != PlanStepStatus.COMPLETED:
                raise PlanTransitionError("dependency not completed")

    def restore(self, snapshot: ExecutionPlan) -> ExecutionPlan:
        if self._plan is None:
            self._plan = snapshot.model_copy()
            return self._plan
        if self._plan == snapshot:
            return self._plan
        raise PlanError("plan snapshot conflicts with existing plan")
