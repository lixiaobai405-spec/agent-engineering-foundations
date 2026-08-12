from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from pydantic import ValidationError

if TYPE_CHECKING:
    from agent_foundations.evals.models import EvalTaskSet
    from agent_foundations.evals.replay import ResponseFixture


REPO_ROOT = Path(__file__).resolve().parents[3]
SAMPLE_PROJECT = REPO_ROOT / "tests" / "fixtures" / "sample_project"


def _require_replay_module() -> None:
    package_spec = importlib.util.find_spec("agent_foundations.evals")
    assert package_spec is not None
    module_spec = importlib.util.find_spec("agent_foundations.evals.replay")
    assert module_spec is not None, "agent_foundations.evals.replay must exist"


def _load_fixture(path: Path) -> ResponseFixture:
    _require_replay_module()
    from agent_foundations.evals.replay import load_response_fixture

    return load_response_fixture(path)


def _validate_fixture(fixture: ResponseFixture, task_set: EvalTaskSet) -> None:
    _require_replay_module()
    from agent_foundations.evals.replay import validate_response_fixture

    validate_response_fixture(fixture, task_set)


def _task_set(*task_ids: str) -> EvalTaskSet:
    from agent_foundations.evals.models import (
        EvalAssertion,
        EvalAssertionKind,
        EvalTask,
        EvalTaskSet,
    )

    return EvalTaskSet(
        schema_version=1,
        dataset_id="offline-dataset",
        dataset_version="v1",
        tasks=tuple(
            EvalTask(
                task_id=task_id,
                project_fixture="sample_project",
                prompt=f"Prompt for {task_id}",
                assertions=(
                    EvalAssertion(kind=EvalAssertionKind.ANSWER_CONTAINS, value="ok"),
                ),
                max_steps=4,
            )
            for task_id in task_ids
        ),
    )


def _response_entry(
    *,
    content: str | None = None,
    tool_calls: list[dict[str, Any]] | None = None,
    input_tokens: int = 1,
    output_tokens: int = 1,
) -> dict[str, Any]:
    return {
        "content": content,
        "tool_calls": tool_calls or [],
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
        "raw_response": None,
    }


def write_response_fixture(
    tmp_path: Path,
    *,
    task_ids: tuple[str, ...],
    schema_version: int = 1,
    responses_per_task: int = 1,
) -> Path:
    scripts = [
        {
            "task_id": task_id,
            "responses": [
                _response_entry(content=f"answer for {task_id}")
                for _ in range(responses_per_task)
            ],
        }
        for task_id in task_ids
    ]
    payload = {
        "schema_version": schema_version,
        "fixture_id": "test-responses",
        "fixture_version": "v1",
        "scripts": scripts,
    }
    path = tmp_path / "responses.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_load_response_fixture_loads_valid_fixture(tmp_path: Path) -> None:
    path = write_response_fixture(tmp_path, task_ids=("task-a", "task-b"))
    fixture = _load_fixture(path)
    assert fixture.fixture_id == "test-responses"
    assert [script.task_id for script in fixture.scripts] == ["task-a", "task-b"]


def test_load_response_fixture_rejects_unknown_schema_version(tmp_path: Path) -> None:
    path = write_response_fixture(tmp_path, task_ids=("task-a",), schema_version=99)
    with pytest.raises(ValueError, match="schema_version"):
        _load_fixture(path)


def test_load_response_fixture_rejects_duplicate_task_ids(tmp_path: Path) -> None:
    payload = {
        "schema_version": 1,
        "fixture_id": "dup",
        "fixture_version": "v1",
        "scripts": [
            {"task_id": "dup", "responses": [_response_entry(content="a")]},
            {"task_id": "dup", "responses": [_response_entry(content="b")]},
        ],
    }
    path = tmp_path / "responses.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate task_id"):
        _load_fixture(path)


def test_validate_response_fixture_rejects_missing_task_script(tmp_path: Path) -> None:
    path = write_response_fixture(tmp_path, task_ids=("task-a",))
    fixture = _load_fixture(path)
    task_set = _task_set("task-a", "task-b")
    with pytest.raises(ValueError, match="missing"):
        _validate_fixture(fixture, task_set)


def test_validate_response_fixture_rejects_extra_task_script(tmp_path: Path) -> None:
    path = write_response_fixture(tmp_path, task_ids=("task-a", "task-extra"))
    fixture = _load_fixture(path)
    task_set = _task_set("task-a")
    with pytest.raises(ValueError, match="extra"):
        _validate_fixture(fixture, task_set)


def test_load_response_fixture_rejects_empty_response_sequence(tmp_path: Path) -> None:
    payload = {
        "schema_version": 1,
        "fixture_id": "empty",
        "fixture_version": "v1",
        "scripts": [{"task_id": "task-a", "responses": []}],
    }
    path = tmp_path / "responses.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises((ValueError, ValidationError), match="responses"):
        _load_fixture(path)


def test_load_response_fixture_rejects_invalid_model_response(tmp_path: Path) -> None:
    payload = {
        "schema_version": 1,
        "fixture_id": "invalid",
        "fixture_version": "v1",
        "scripts": [
            {
                "task_id": "task-a",
                "responses": [
                    {
                        "content": None,
                        "tool_calls": [],
                        "usage": {"input_tokens": 0, "output_tokens": 0},
                    }
                ],
            }
        ],
    }
    path = tmp_path / "responses.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValidationError):
        _load_fixture(path)


def test_replay_agent_rejects_exhausted_response_script(tmp_path: Path) -> None:
    _require_replay_module()
    from agent_foundations.cli.main import build_tool_registry
    from agent_foundations.domain.model import ModelResponse
    from agent_foundations.domain.tool import ToolCall
    from agent_foundations.evals.models import EvalAssertion, EvalAssertionKind, EvalTask
    from agent_foundations.evals.replay import EvalInputError, ReplayEvalAgent, ResponseScript

    task = EvalTask(
        task_id="exhaust",
        project_fixture="sample_project",
        prompt="Need two model turns",
        assertions=(EvalAssertion(kind=EvalAssertionKind.ANSWER_CONTAINS, value="ok"),),
        max_steps=4,
    )
    script = ResponseScript(
        task_id="exhaust",
        responses=(
            ModelResponse(
                tool_calls=(
                    ToolCall(id="call-1", name="list_directory", arguments={"path": "src"}),
                ),
            ),
        ),
    )
    agent = ReplayEvalAgent(
        scripts={script.task_id: script},
        registry_factory=build_tool_registry,
    )
    with pytest.raises(EvalInputError, match="exhausted"):
        import asyncio

        asyncio.run(agent.run(task, SAMPLE_PROJECT))


def test_replay_agent_rejects_remaining_responses(tmp_path: Path) -> None:
    _require_replay_module()
    from agent_foundations.cli.main import build_tool_registry
    from agent_foundations.domain.model import ModelResponse
    from agent_foundations.evals.models import EvalAssertion, EvalAssertionKind, EvalTask
    from agent_foundations.evals.replay import EvalInputError, ReplayEvalAgent, ResponseScript

    task = EvalTask(
        task_id="remainder",
        project_fixture="sample_project",
        prompt="Single turn is enough",
        assertions=(EvalAssertion(kind=EvalAssertionKind.ANSWER_CONTAINS, value="done"),),
        max_steps=4,
    )
    script = ResponseScript(
        task_id="remainder",
        responses=(
            ModelResponse(content="done"),
            ModelResponse(content="unused"),
        ),
    )
    agent = ReplayEvalAgent(
        scripts={script.task_id: script},
        registry_factory=build_tool_registry,
    )
    with pytest.raises(EvalInputError, match="remaining"):
        import asyncio

        asyncio.run(agent.run(task, SAMPLE_PROJECT))


@pytest.mark.asyncio
async def test_replay_agent_maps_observation_fields() -> None:
    _require_replay_module()
    from agent_foundations.cli.main import build_tool_registry
    from agent_foundations.domain.model import ModelResponse, TokenUsage
    from agent_foundations.domain.tool import ToolCall
    from agent_foundations.evals.models import EvalAssertion, EvalAssertionKind, EvalTask
    from agent_foundations.evals.replay import ReplayEvalAgent, ResponseScript

    task = EvalTask(
        task_id="observe",
        project_fixture="sample_project",
        prompt="List src files",
        assertions=(
            EvalAssertion(kind=EvalAssertionKind.TOOL_CALLED, value="list_directory"),
            EvalAssertion(kind=EvalAssertionKind.ANSWER_CONTAINS, value="auth.py"),
        ),
        max_steps=4,
    )
    script = ResponseScript(
        task_id="observe",
        responses=(
            ModelResponse(
                tool_calls=(
                    ToolCall(id="call-observe-1", name="list_directory", arguments={"path": "src"}),
                ),
                usage=TokenUsage(input_tokens=3, output_tokens=2),
            ),
            ModelResponse(
                content="src contains auth.py",
                usage=TokenUsage(input_tokens=5, output_tokens=4),
            ),
        ),
    )
    agent = ReplayEvalAgent(
        scripts={script.task_id: script},
        registry_factory=build_tool_registry,
    )
    observation = await agent.run(task, SAMPLE_PROJECT)
    assert observation.answer == "src contains auth.py"
    assert observation.steps == 2
    assert observation.tool_names == ("list_directory",)
    assert observation.input_tokens == 8
    assert observation.output_tokens == 6
    assert observation.duration_ms == 0.0


@pytest.mark.asyncio
async def test_replay_agent_records_last_tool_failure_error_code() -> None:
    _require_replay_module()
    from agent_foundations.cli.main import build_tool_registry
    from agent_foundations.domain.model import ModelResponse
    from agent_foundations.domain.tool import ToolCall
    from agent_foundations.evals.models import EvalAssertion, EvalAssertionKind, EvalTask
    from agent_foundations.evals.replay import ReplayEvalAgent, ResponseScript

    task = EvalTask(
        task_id="policy",
        project_fixture="sample_project",
        prompt="Read .env",
        assertions=(
            EvalAssertion(
                kind=EvalAssertionKind.ERROR_CODE,
                value="PathPolicyViolationError",
            ),
        ),
        max_steps=4,
    )
    script = ResponseScript(
        task_id="policy",
        responses=(
            ModelResponse(
                tool_calls=(
                    ToolCall(id="call-policy-1", name="read_file", arguments={"path": ".env"}),
                ),
            ),
            ModelResponse(content="Blocked by policy."),
        ),
    )
    agent = ReplayEvalAgent(
        scripts={script.task_id: script},
        registry_factory=build_tool_registry,
    )
    observation = await agent.run(task, SAMPLE_PROJECT)
    assert observation.error_code == "PathPolicyViolationError"


@pytest.mark.asyncio
async def test_replay_agent_does_not_use_network_or_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _require_replay_module()
    from agent_foundations.cli.main import build_tool_registry
    from agent_foundations.domain.model import ModelResponse
    from agent_foundations.evals.models import EvalAssertion, EvalAssertionKind, EvalTask
    from agent_foundations.evals.replay import ReplayEvalAgent, ResponseScript

    def fail_getenv(name: str, default: object | None = None) -> object | None:
        if name in {"AGENT_API_KEY", "AGENT_MODEL"}:
            raise AssertionError("credentials must not be read")
        return default

    monkeypatch.setattr("os.getenv", fail_getenv)

    task = EvalTask(
        task_id="safe",
        project_fixture="sample_project",
        prompt="ok",
        assertions=(EvalAssertion(kind=EvalAssertionKind.ANSWER_CONTAINS, value="ok"),),
        max_steps=2,
    )
    script = ResponseScript(task_id="safe", responses=(ModelResponse(content="ok"),))
    agent = ReplayEvalAgent(
        scripts={script.task_id: script},
        registry_factory=build_tool_registry,
    )
    observation = await agent.run(task, SAMPLE_PROJECT)
    assert observation.answer == "ok"
