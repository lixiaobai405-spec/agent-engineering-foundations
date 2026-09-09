from dataclasses import dataclass
from enum import StrEnum

from agent_foundations.runtime.coding_budget import CodingBudgetLimits


class PlanningMode(StrEnum):
    DISABLED = "disabled"
    REQUIRED = "required"


@dataclass(frozen=True)
class AgentConfig:
    max_steps: int = 10
    planning_mode: PlanningMode = PlanningMode.DISABLED
    system_prompt: str = (
        "You are a read-only coding agent. Use only the supplied tools. "
        "Never claim to modify files, run commands, or access paths outside the project."
    )
    coding_budget: CodingBudgetLimits | None = None

    def __post_init__(self) -> None:
        if self.max_steps < 1:
            raise ValueError("max_steps must be positive")
        budget = self.coding_budget
        if budget is None:
            return
        for label, value in (
            ("max_patch_repairs", budget.max_patch_repairs),
            ("max_same_argv_command_runs", budget.max_same_argv_command_runs),
            ("max_artifact_reads", budget.max_artifact_reads),
        ):
            if value >= self.max_steps:
                raise ValueError(f"{label} must be strictly less than max_steps")


@dataclass(frozen=True)
class AgentResult:
    session_id: str
    answer: str
    steps: int
