from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from agent_foundations.evals.models import EvalTask, EvalTaskSet
    from agent_foundations.evals.runner import EvalObservation, OfflineEvalRunner


FIXED_TIME = datetime(2026, 8, 9, 12, 0, 0, tzinfo=UTC)


def _require_eval_module(module_name: str) -> None:
    package_spec = importlib.util.find_spec("agent_foundations.evals")
    assert package_spec is not None, "agent_foundations.evals package must exist"
    module_spec = importlib.util.find_spec(f"agent_foundations.evals.{module_name}")
    assert module_spec is not None, f"agent_foundations.evals.{module_name} must exist"


def _task(task_id: str, *, project_fixture: str = "sample_project") -> EvalTask:
    from agent_foundations.evals.models import EvalAssertion, EvalAssertionKind, EvalTask

    return EvalTask(
        task_id=task_id,
        project_fixture=project_fixture,
        prompt=f"Prompt for {task_id}",
        assertions=(
            EvalAssertion(kind=EvalAssertionKind.ANSWER_CONTAINS, value="ok"),
        ),
        max_steps=3,
    )


def _task_set(*task_ids: str) -> EvalTaskSet:
    from agent_foundations.evals.models import EvalTaskSet

    return EvalTaskSet(
        schema_version=1,
        dataset_id="offline-dataset",
        dataset_version="v1",
        tasks=tuple(_task(task_id) for task_id in task_ids),
    )


class ScriptedEvalAgent:
    def __init__(
        self,
        outcomes: dict[str, EvalObservation | Exception],
        *,
        seen_roots: list[Path] | None = None,
    ) -> None:
        self._outcomes = outcomes
        self.seen_roots = seen_roots if seen_roots is not None else []

    async def run(self, task: EvalTask, project_root: Path) -> EvalObservation:
        self.seen_roots.append(project_root)
        outcome = self._outcomes[task.task_id]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _observation(
    *,
    answer: str = "ok",
    steps: int = 1,
    tool_names: tuple[str, ...] = ("read_file",),
    policy_decisions: tuple[str, ...] = (),
    error_code: str | None = None,
    input_tokens: int = 1,
    output_tokens: int = 1,
    duration_ms: float = 1.0,
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


def _runner(
    tmp_path: Path,
    *,
    environment: tuple[tuple[str, str], ...] = (("platform", "test"),),
) -> OfflineEvalRunner:
    _require_eval_module("runner")
    from agent_foundations.evals.runner import OfflineEvalRunner

    fixture_root = tmp_path / "fixtures"
    (fixture_root / "sample_project").mkdir(parents=True)
    return OfflineEvalRunner(
        fixture_root=fixture_root,
        prompt_version="prompt-v1",
        response_fixture_version="responses-v1",
        tool_set=("list_directory", "read_file", "search_text"),
        runtime_revision="working-tree",
        environment=environment,
        clock=lambda: FIXED_TIME,
    )


@pytest.mark.asyncio
async def test_runner_records_one_failure_without_skipping_later_tasks(
    tmp_path: Path,
) -> None:
    _require_eval_module("runner")
    task_set = _task_set("first", "second")
    outcomes: dict[str, EvalObservation | Exception] = {
        "first": RuntimeError("boom"),
        "second": _observation(),
    }
    report = await _runner(tmp_path).run(task_set, ScriptedEvalAgent(outcomes))

    assert [result.task_id for result in report.results] == ["first", "second"]
    assert report.results[0].passed is False
    assert report.results[1].passed is True


@pytest.mark.asyncio
async def test_runner_executes_tasks_in_declaration_order(tmp_path: Path) -> None:
    order: list[str] = []

    class RecordingAgent:
        async def run(self, task: EvalTask, project_root: Path) -> EvalObservation:
            order.append(task.task_id)
            return _observation()

    task_set = _task_set("alpha", "beta", "gamma")
    await _runner(tmp_path).run(task_set, RecordingAgent())

    assert order == ["alpha", "beta", "gamma"]


@pytest.mark.asyncio
async def test_runner_resolves_project_root_from_fixture_root(tmp_path: Path) -> None:
    seen_roots: list[Path] = []
    task_set = _task_set("root-check")
    outcomes: dict[str, EvalObservation | Exception] = {"root-check": _observation()}
    agent = ScriptedEvalAgent(outcomes, seen_roots=seen_roots)
    runner = _runner(tmp_path)

    await runner.run(task_set, agent)

    expected = (tmp_path / "fixtures" / "sample_project").resolve()
    assert seen_roots == [expected]


@pytest.mark.asyncio
async def test_runner_report_metadata_comes_from_explicit_inputs(tmp_path: Path) -> None:
    environment = (("python", "3.12"), ("platform", "test"))
    outcomes: dict[str, EvalObservation | Exception] = {"meta": _observation()}
    report = await _runner(tmp_path, environment=environment).run(
        _task_set("meta"),
        ScriptedEvalAgent(outcomes),
    )

    assert report.dataset_id == "offline-dataset"
    assert report.dataset_version == "v1"
    assert report.prompt_version == "prompt-v1"
    assert report.response_fixture_version == "responses-v1"
    assert report.tool_set == ("list_directory", "read_file", "search_text")
    assert report.runtime_revision == "working-tree"
    assert report.environment == environment
    assert report.generated_at == FIXED_TIME


@pytest.mark.asyncio
async def test_runner_does_not_call_git_or_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_git(*args: object, **kwargs: object) -> None:
        raise AssertionError("git must not be called")

    def fail_getenv(name: str, default: object | None = None) -> object | None:
        if name == "AGENT_API_KEY":
            raise AssertionError("credentials must not be read")
        return default

    monkeypatch.setattr("subprocess.run", fail_git)
    monkeypatch.setattr("os.getenv", fail_getenv)

    outcomes: dict[str, EvalObservation | Exception] = {"safe": _observation()}
    report = await _runner(tmp_path).run(
        _task_set("safe"),
        ScriptedEvalAgent(outcomes),
    )
    assert report.results[0].passed is True


@pytest.mark.asyncio
async def test_failed_task_records_stable_error_kind_without_traceback(tmp_path: Path) -> None:
    outcomes: dict[str, EvalObservation | Exception] = {
        "broken": ValueError("do not leak details"),
    }
    report = await _runner(tmp_path).run(
        _task_set("broken"),
        ScriptedEvalAgent(outcomes),
    )

    failed = report.results[0]
    assert failed.passed is False
    assert failed.error_kind == "ValueError"
    assert failed.observation is None
    assert "traceback" not in str(failed.model_dump()).lower()
