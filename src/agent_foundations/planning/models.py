from __future__ import annotations

from enum import StrEnum

from pydantic import ConfigDict, Field, field_validator, model_validator

from agent_foundations.domain._model import ValidatedCopyModel


class PlanStepStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"


def _validate_non_blank(value: str, field_name: str) -> str:
    if not value or not value.strip():
        raise ValueError(f"{field_name} must not be blank")
    return value


def _validate_evidence_refs(evidence_refs: tuple[str, ...]) -> None:
    if not evidence_refs:
        raise ValueError("completed step requires evidence_refs")
    for ref in evidence_refs:
        if not ref or not ref.strip():
            raise ValueError("evidence_refs must not contain blank references")


def _validate_steps_structure(steps: tuple[PlanStep, ...]) -> None:
    if not steps:
        raise ValueError("steps must not be empty")

    step_ids = [step.step_id for step in steps]
    if len(step_ids) != len(set(step_ids)):
        raise ValueError("duplicate step_id")

    known_ids = set(step_ids)
    depends_map = {step.step_id: step.depends_on for step in steps}

    for step in steps:
        for dependency in step.depends_on:
            if dependency not in known_ids:
                raise ValueError("depends_on references unknown step_id")

    _validate_no_dependency_cycle(depends_map)

    in_progress_count = sum(
        1 for step in steps if step.status == PlanStepStatus.IN_PROGRESS
    )
    if in_progress_count > 1:
        raise ValueError("only one step may be in_progress")

    status_by_id = {step.step_id: step.status for step in steps}
    for step in steps:
        if step.status == PlanStepStatus.COMPLETED:
            _validate_evidence_refs(step.evidence_refs)
        if step.status in (PlanStepStatus.IN_PROGRESS, PlanStepStatus.COMPLETED):
            for dependency in step.depends_on:
                if status_by_id[dependency] != PlanStepStatus.COMPLETED:
                    raise ValueError("dependency not completed")


def _validate_no_dependency_cycle(depends_map: dict[str, tuple[str, ...]]) -> None:
    visited: set[str] = set()
    visiting: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            raise ValueError("dependency cycle detected")
        if node in visited:
            return
        visiting.add(node)
        for dependency in sorted(depends_map.get(node, ())):
            visit(dependency)
        visiting.remove(node)
        visited.add(node)

    for step_id in sorted(depends_map):
        if step_id not in visited:
            visit(step_id)


class PlanStep(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True)

    step_id: str
    description: str
    status: PlanStepStatus = PlanStepStatus.PENDING
    depends_on: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()

    @field_validator("step_id")
    @classmethod
    def validate_step_id(cls, value: str) -> str:
        return _validate_non_blank(value, "step_id")

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str) -> str:
        return _validate_non_blank(value, "description")

    @field_validator("depends_on")
    @classmethod
    def validate_depends_on(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("depends_on must not contain duplicates")
        return value

    @field_validator("evidence_refs")
    @classmethod
    def validate_evidence_refs(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for ref in value:
            if not ref or not ref.strip():
                raise ValueError("evidence_refs must not contain blank references")
        return value

    @model_validator(mode="after")
    def validate_step_constraints(self) -> PlanStep:
        if self.step_id in self.depends_on:
            raise ValueError("step cannot depend on itself")
        if self.status == PlanStepStatus.COMPLETED:
            _validate_evidence_refs(self.evidence_refs)
        return self


class ExecutionPlan(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True)

    plan_id: str
    version: int = Field(ge=1)
    goal: str
    steps: tuple[PlanStep, ...]
    replan_count: int = Field(ge=0, default=0)
    max_replans: int = Field(ge=0, default=2)

    @field_validator("plan_id")
    @classmethod
    def validate_plan_id(cls, value: str) -> str:
        return _validate_non_blank(value, "plan_id")

    @field_validator("goal")
    @classmethod
    def validate_goal(cls, value: str) -> str:
        return _validate_non_blank(value, "goal")

    @model_validator(mode="after")
    def validate_plan_constraints(self) -> ExecutionPlan:
        if self.replan_count > self.max_replans:
            raise ValueError("replan_count exceeds max_replans")
        _validate_steps_structure(self.steps)
        return self
