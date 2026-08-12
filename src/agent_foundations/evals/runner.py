from __future__ import annotations

import math
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from pydantic import ConfigDict, Field, field_validator

from agent_foundations.domain._model import ValidatedCopyModel
from agent_foundations.evals.models import EvalTask, EvalTaskSet

if TYPE_CHECKING:
    from agent_foundations.evals.reporting import EvalReport


class EvalObservation(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True)

    answer: str
    steps: int = Field(ge=0)
    tool_names: tuple[str, ...]
    policy_decisions: tuple[str, ...] = ()
    error_code: str | None = None
    input_tokens: int = Field(ge=0, default=0)
    output_tokens: int = Field(ge=0, default=0)
    duration_ms: float = Field(default=0.0)

    @field_validator("duration_ms")
    @classmethod
    def validate_finite_non_negative_duration(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("duration_ms must be a finite number")
        if value < 0:
            raise ValueError("duration_ms must be greater than or equal to 0")
        return value


class EvalAgent(Protocol):
    async def run(self, task: EvalTask, project_root: Path) -> EvalObservation: ...


class OfflineEvalRunner:
    def __init__(
        self,
        *,
        fixture_root: Path,
        prompt_version: str,
        response_fixture_version: str,
        tool_set: tuple[str, ...],
        runtime_revision: str,
        environment: tuple[tuple[str, str], ...] = (),
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._fixture_root = fixture_root.resolve()
        self._prompt_version = prompt_version
        self._response_fixture_version = response_fixture_version
        self._tool_set = tool_set
        self._runtime_revision = runtime_revision
        self._environment = environment
        self._clock = clock or (lambda: datetime.now().astimezone())

    async def run(self, task_set: EvalTaskSet, agent: EvalAgent) -> EvalReport:
        from agent_foundations.evals.reporting import EvalReport, build_summary
        from agent_foundations.evals.scoring import build_failed_task_result, score_task

        results = []
        for task in task_set.tasks:
            project_root = (self._fixture_root / task.project_fixture).resolve()
            try:
                observation = await agent.run(task, project_root)
                result = score_task(task, observation)
            except Exception as exc:
                from agent_foundations.evals.replay import EvalInputError

                if isinstance(exc, EvalInputError):
                    raise
                result = build_failed_task_result(task, type(exc).__name__)
            results.append(result)

        results_tuple = tuple(results)
        return EvalReport(
            dataset_id=task_set.dataset_id,
            dataset_version=task_set.dataset_version,
            prompt_version=self._prompt_version,
            response_fixture_version=self._response_fixture_version,
            tool_set=self._tool_set,
            runtime_revision=self._runtime_revision,
            environment=self._environment,
            generated_at=self._clock(),
            results=results_tuple,
            summary=build_summary(results_tuple),
        )
