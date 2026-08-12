from __future__ import annotations

import importlib.util
from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError

if TYPE_CHECKING:
    from agent_foundations.evals.models import EvalAssertion, EvalTask


def _require_eval_module(module_name: str) -> None:
    package_spec = importlib.util.find_spec("agent_foundations.evals")
    assert package_spec is not None, "agent_foundations.evals package must exist"
    module_spec = importlib.util.find_spec(f"agent_foundations.evals.{module_name}")
    assert module_spec is not None, f"agent_foundations.evals.{module_name} must exist"


def _sample_assertion() -> EvalAssertion:
    from agent_foundations.evals.models import EvalAssertion, EvalAssertionKind

    return EvalAssertion(kind=EvalAssertionKind.ANSWER_CONTAINS, value="auth.py")


def _sample_task() -> EvalTask:
    from agent_foundations.evals.models import EvalTask

    return EvalTask(
        task_id="sample-task",
        project_fixture="sample_project",
        prompt="Where is authenticate defined?",
        assertions=(_sample_assertion(),),
        max_steps=5,
    )


def test_eval_models_are_frozen() -> None:
    _require_eval_module("models")
    task = _sample_task()

    with pytest.raises(ValidationError):
        task.task_id = "changed"


def test_eval_task_model_copy_revalidates_invalid_update() -> None:
    _require_eval_module("models")
    task = _sample_task()

    with pytest.raises(ValidationError):
        task.model_copy(update={"max_steps": 0})


def test_eval_task_rejects_empty_assertions() -> None:
    _require_eval_module("models")
    from agent_foundations.evals.models import EvalTask

    with pytest.raises(ValidationError, match="assertions"):
        EvalTask(
            task_id="empty-assertions",
            project_fixture="sample_project",
            prompt="noop",
            assertions=(),
            max_steps=3,
        )
