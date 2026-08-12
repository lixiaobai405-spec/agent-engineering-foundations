from __future__ import annotations

import importlib.util
import math
from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError

if TYPE_CHECKING:
    from agent_foundations.evals.models import EvalAssertion, EvalAssertionKind, EvalTask
    from agent_foundations.evals.reporting import EvalTaskResult
    from agent_foundations.evals.runner import EvalObservation


def _require_eval_module(module_name: str) -> None:
    package_spec = importlib.util.find_spec("agent_foundations.evals")
    assert package_spec is not None, "agent_foundations.evals package must exist"
    module_spec = importlib.util.find_spec(f"agent_foundations.evals.{module_name}")
    assert module_spec is not None, f"agent_foundations.evals.{module_name} must exist"


def _assertion(kind: EvalAssertionKind, value: str) -> EvalAssertion:
    from agent_foundations.evals.models import EvalAssertion

    return EvalAssertion(kind=kind, value=value)


def _observation(
    *,
    answer: str = "The authenticate function lives in src/auth.py",
    steps: int = 2,
    tool_names: tuple[str, ...] = ("search_text", "read_file"),
    policy_decisions: tuple[str, ...] = ("allow",),
    error_code: str | None = None,
    input_tokens: int = 10,
    output_tokens: int = 5,
    duration_ms: float = 12.5,
) -> EvalObservation:
    from agent_foundations.evals.runner import EvalObservation

    return EvalObservation(
        answer=answer,
        steps=steps,
        tool_names=tool_names,
        policy_decisions=policy_decisions,
        error_code=error_code,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        duration_ms=duration_ms,
    )


def _score_task(task: EvalTask, observation: EvalObservation) -> EvalTaskResult:
    _require_eval_module("scoring")
    from agent_foundations.evals.scoring import score_task

    return score_task(task, observation)


def _task(*assertions: EvalAssertion) -> EvalTask:
    from agent_foundations.evals.models import EvalTask

    return EvalTask(
        task_id="score-task",
        project_fixture="sample_project",
        prompt="Inspect auth",
        assertions=assertions,
        max_steps=5,
    )


@pytest.mark.parametrize(
    ("kind", "value", "error_code", "expected"),
    [
        ("answer_contains", "auth.py", None, True),
        ("answer_contains", "missing", None, False),
        ("answer_excludes", "secret", None, True),
        ("answer_excludes", "auth.py", None, False),
        ("tool_called", "read_file", None, True),
        ("tool_called", "list_directory", None, False),
        ("tool_not_called", "list_directory", None, True),
        ("tool_not_called", "read_file", None, False),
        ("error_code", "PathPolicyViolationError", "PathPolicyViolationError", True),
        ("error_code", "RuntimeError", "PathPolicyViolationError", False),
    ],
)
def test_score_assertion_kind_branches(
    kind: str,
    value: str,
    error_code: str | None,
    expected: bool,
) -> None:
    _require_eval_module("scoring")
    from agent_foundations.evals.models import EvalAssertionKind
    from agent_foundations.evals.scoring import score_assertion

    assertion = _assertion(EvalAssertionKind(kind), value)
    observation = _observation(error_code=error_code)
    assert score_assertion(assertion, observation) is expected


def test_task_passes_only_when_all_assertions_pass() -> None:
    _require_eval_module("scoring")
    from agent_foundations.evals.models import EvalAssertionKind

    task = _task(
        _assertion(EvalAssertionKind.ANSWER_CONTAINS, "auth.py"),
        _assertion(EvalAssertionKind.TOOL_CALLED, "read_file"),
    )
    passed_result = _score_task(task, _observation())
    failed_result = _score_task(task, _observation(tool_names=("search_text",)))

    assert passed_result.passed is True
    assert failed_result.passed is False
    assert all(score.passed for score in passed_result.assertion_results)
    assert failed_result.assertion_results[-1].passed is False


def test_assertion_results_preserve_declaration_order() -> None:
    _require_eval_module("scoring")
    from agent_foundations.evals.models import EvalAssertionKind

    task = _task(
        _assertion(EvalAssertionKind.ANSWER_CONTAINS, "first"),
        _assertion(EvalAssertionKind.ANSWER_CONTAINS, "second"),
        _assertion(EvalAssertionKind.TOOL_CALLED, "read_file"),
    )
    result = _score_task(task, _observation(answer="first second"))

    assert [item.value for item in result.assertion_results] == [
        "first",
        "second",
        "read_file",
    ]


@pytest.mark.parametrize(
    ("steps", "input_tokens", "output_tokens"),
    [
        (-1, 0, 0),
        (2, -1, 0),
        (2, 0, -1),
    ],
    ids=["steps", "input_tokens", "output_tokens"],
)
def test_observation_rejects_negative_metrics(
    steps: int,
    input_tokens: int,
    output_tokens: int,
) -> None:
    _require_eval_module("runner")
    from agent_foundations.evals.runner import EvalObservation

    with pytest.raises(ValidationError):
        EvalObservation(
            answer="ok",
            steps=steps,
            tool_names=(),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )


@pytest.mark.parametrize("duration_ms", [math.nan, math.inf, -math.inf])
def test_observation_rejects_non_finite_duration(duration_ms: float) -> None:
    _require_eval_module("runner")
    from agent_foundations.evals.runner import EvalObservation

    with pytest.raises(ValidationError, match="finite"):
        EvalObservation(
            answer="ok",
            steps=1,
            tool_names=(),
            duration_ms=duration_ms,
        )


@pytest.mark.parametrize(
    "duration_ms",
    ["nan", "inf", "-inf", "NaN", "INF", "-INF"],
)
def test_observation_rejects_non_finite_duration_strings(duration_ms: str) -> None:
    _require_eval_module("runner")
    from agent_foundations.evals.runner import EvalObservation

    with pytest.raises(ValidationError, match="finite"):
        EvalObservation.model_validate(
            {
                "answer": "ok",
                "steps": 1,
                "tool_names": [],
                "duration_ms": duration_ms,
            }
        )
