from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from agent_foundations.evals.reporting import EvalReport


FIXED_TIME = datetime(2026, 8, 9, 12, 0, 0, tzinfo=UTC)


def _require_eval_module(module_name: str) -> None:
    package_spec = importlib.util.find_spec("agent_foundations.evals")
    assert package_spec is not None, "agent_foundations.evals package must exist"
    module_spec = importlib.util.find_spec(f"agent_foundations.evals.{module_name}")
    assert module_spec is not None, f"agent_foundations.evals.{module_name} must exist"


def _sample_report(*, generated_at: datetime = FIXED_TIME) -> EvalReport:
    _require_eval_module("reporting")
    from agent_foundations.evals.reporting import (
        EvalAssertionResult,
        EvalReport,
        EvalSummary,
        EvalTaskResult,
    )
    from agent_foundations.evals.runner import EvalObservation

    observation = EvalObservation(
        answer="ok",
        steps=2,
        tool_names=("read_file",),
        policy_decisions=("allow",),
        input_tokens=3,
        output_tokens=4,
        duration_ms=10.0,
    )
    passed = EvalTaskResult(
        task_id="task-a",
        passed=True,
        assertion_results=(
            EvalAssertionResult(kind="answer_contains", value="ok", passed=True),
        ),
        observation=observation,
        error_kind=None,
    )
    failed = EvalTaskResult(
        task_id="task-b",
        passed=False,
        assertion_results=(
            EvalAssertionResult(kind="answer_contains", value="missing", passed=False),
        ),
        observation=observation,
        error_kind=None,
    )
    summary = EvalSummary(
        total_tasks=2,
        passed_tasks=1,
        failed_tasks=1,
        success_rate=0.5,
        total_steps=4,
        total_tool_calls=2,
        total_policy_decisions=2,
        total_input_tokens=6,
        total_output_tokens=8,
        total_duration_ms=20.0,
    )
    return EvalReport(
        dataset_id="test-dataset",
        dataset_version="v1",
        prompt_version="prompt-v1",
        response_fixture_version="responses-v1",
        tool_set=("list_directory", "read_file", "search_text"),
        runtime_revision="working-tree",
        environment=(("python", "3.12"),),
        generated_at=generated_at,
        results=(passed, failed),
        summary=summary,
    )


def _serialize_report(report: EvalReport) -> str:
    _require_eval_module("reporting")
    from agent_foundations.evals.reporting import serialize_report

    return serialize_report(report)


def _write_report_atomic(report: EvalReport, path: Path) -> None:
    _require_eval_module("reporting")
    from agent_foundations.evals.reporting import write_report_atomic

    write_report_atomic(report, path)


def test_summary_metrics_match_task_results() -> None:
    _require_eval_module("reporting")
    from agent_foundations.evals.reporting import build_summary

    report = _sample_report()
    rebuilt = build_summary(report.results)

    assert rebuilt == report.summary
    assert report.summary.total_tasks == 2
    assert report.summary.passed_tasks == 1
    assert report.summary.failed_tasks == 1
    assert report.summary.success_rate == 0.5


def test_same_inputs_produce_semantically_equal_json_except_generated_at() -> None:
    first = _serialize_report(_sample_report(generated_at=FIXED_TIME))
    second = _serialize_report(
        _sample_report(generated_at=datetime(2026, 8, 9, 13, 0, 0, tzinfo=UTC))
    )

    first_payload = json.loads(first)
    second_payload = json.loads(second)
    first_payload.pop("generated_at")
    second_payload.pop("generated_at")

    assert first_payload == second_payload
    assert first.endswith("\n")
    assert list(first_payload) == sorted(first_payload)


def test_write_report_atomic_replaces_target(tmp_path: Path) -> None:
    target = tmp_path / "report.json"
    target.write_text('{"old": true}\n', encoding="utf-8")

    _write_report_atomic(_sample_report(), target)

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["dataset_id"] == "test-dataset"
    assert payload["summary"]["total_tasks"] == 2


def test_write_report_atomic_preserves_existing_file_on_replace_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "report.json"
    original = '{"stable": true}\n'
    target.write_text(original, encoding="utf-8")

    def fail_replace(src: str, dst: str) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr("agent_foundations.evals.reporting.os.replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        _write_report_atomic(_sample_report(), target)

    assert target.read_text(encoding="utf-8") == original
    leftover = list(tmp_path.glob("*.tmp"))
    assert leftover == []
