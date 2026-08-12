from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

from pydantic import ConfigDict, Field, field_validator

from agent_foundations.domain._model import ValidatedCopyModel
from agent_foundations.evals.runner import EvalObservation


class EvalAssertionResult(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True)

    kind: str
    value: str
    passed: bool


class EvalTaskResult(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True)

    task_id: str
    passed: bool
    assertion_results: tuple[EvalAssertionResult, ...]
    observation: EvalObservation | None = None
    error_kind: str | None = None


class EvalSummary(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True)

    total_tasks: int = Field(ge=0)
    passed_tasks: int = Field(ge=0)
    failed_tasks: int = Field(ge=0)
    success_rate: float = Field(ge=0.0, le=1.0)
    total_steps: int = Field(ge=0)
    total_tool_calls: int = Field(ge=0)
    total_policy_decisions: int = Field(ge=0)
    total_input_tokens: int = Field(ge=0)
    total_output_tokens: int = Field(ge=0)
    total_duration_ms: float = Field(ge=0.0)


class EvalReport(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True)

    dataset_id: str
    dataset_version: str
    prompt_version: str
    response_fixture_version: str
    tool_set: tuple[str, ...]
    runtime_revision: str
    environment: tuple[tuple[str, str], ...]
    generated_at: datetime
    results: tuple[EvalTaskResult, ...]
    summary: EvalSummary

    @field_validator("generated_at")
    @classmethod
    def validate_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("generated_at must be timezone-aware")
        return value.astimezone()


def build_summary(results: tuple[EvalTaskResult, ...]) -> EvalSummary:
    total_tasks = len(results)
    passed_tasks = sum(1 for result in results if result.passed)
    failed_tasks = total_tasks - passed_tasks
    success_rate = passed_tasks / total_tasks if total_tasks else 0.0

    total_steps = 0
    total_tool_calls = 0
    total_policy_decisions = 0
    total_input_tokens = 0
    total_output_tokens = 0
    total_duration_ms = 0.0

    for result in results:
        if result.observation is None:
            continue
        observation = result.observation
        total_steps += observation.steps
        total_tool_calls += len(observation.tool_names)
        total_policy_decisions += len(observation.policy_decisions)
        total_input_tokens += observation.input_tokens
        total_output_tokens += observation.output_tokens
        total_duration_ms += observation.duration_ms

    return EvalSummary(
        total_tasks=total_tasks,
        passed_tasks=passed_tasks,
        failed_tasks=failed_tasks,
        success_rate=success_rate,
        total_steps=total_steps,
        total_tool_calls=total_tool_calls,
        total_policy_decisions=total_policy_decisions,
        total_input_tokens=total_input_tokens,
        total_output_tokens=total_output_tokens,
        total_duration_ms=total_duration_ms,
    )


def serialize_report(report: EvalReport) -> str:
    payload = report.model_dump(mode="json")
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write_report_atomic(report: EvalReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = serialize_report(report)
    temp_path: Path | None = None
    file_descriptor = None
    try:
        file_descriptor, temp_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
        temp_path = Path(temp_name)
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as stream:
            file_descriptor = None
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
        temp_path = None
    except Exception:
        if file_descriptor is not None:
            os.close(file_descriptor)
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()
        raise
