import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest


def _require_eval_module(module_name: str) -> None:
    package_spec = importlib.util.find_spec("agent_foundations.evals")
    assert package_spec is not None, "agent_foundations.evals package must exist"
    module_spec = importlib.util.find_spec(f"agent_foundations.evals.{module_name}")
    assert module_spec is not None, f"agent_foundations.evals.{module_name} must exist"


def _load_task_set(path: Path, *, fixture_root: Path) -> Any:
    _require_eval_module("task_sets")
    from agent_foundations.evals.task_sets import load_task_set

    return load_task_set(path, fixture_root=fixture_root)


def write_task_set(
    tmp_path: Path,
    *,
    task_ids: tuple[str, ...],
    schema_version: int = 1,
    project_fixture: str = "sample_project",
) -> Path:
    tasks = [
        {
            "task_id": task_id,
            "project_fixture": project_fixture,
            "prompt": f"Prompt for {task_id}",
            "assertions": [{"kind": "answer_contains", "value": "expected"}],
            "max_steps": 5,
            "tags": ["phase-1"],
        }
        for task_id in task_ids
    ]
    payload = {
        "schema_version": schema_version,
        "dataset_id": "test-dataset",
        "dataset_version": "v1",
        "tasks": tasks,
    }
    path = tmp_path / "task-set.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_load_task_set_rejects_unknown_schema_version(tmp_path: Path) -> None:
    path = write_task_set(tmp_path, task_ids=("task-a",), schema_version=99)
    with pytest.raises(ValueError, match="schema_version"):
        _load_task_set(path, fixture_root=tmp_path)


def test_load_task_set_rejects_duplicate_task_ids(tmp_path: Path) -> None:
    path = write_task_set(tmp_path, task_ids=("duplicate", "duplicate"))
    with pytest.raises(ValueError, match="duplicate task_id"):
        _load_task_set(path, fixture_root=tmp_path)


def test_load_task_set_rejects_absolute_project_fixture(tmp_path: Path) -> None:
    absolute_fixture = str((tmp_path / "sample_project").resolve())
    path = write_task_set(
        tmp_path,
        task_ids=("absolute-fixture",),
        project_fixture=absolute_fixture,
    )
    with pytest.raises(ValueError, match="project_fixture"):
        _load_task_set(path, fixture_root=tmp_path)


def test_load_task_set_rejects_parent_traversal_project_fixture(tmp_path: Path) -> None:
    path = write_task_set(
        tmp_path,
        task_ids=("traversal-fixture",),
        project_fixture="../outside",
    )
    with pytest.raises(ValueError, match="project_fixture"):
        _load_task_set(path, fixture_root=tmp_path)


def test_load_task_set_loads_valid_task_set_deterministically(tmp_path: Path) -> None:
    fixture_root = tmp_path / "fixtures"
    project_dir = fixture_root / "sample_project"
    project_dir.mkdir(parents=True)
    path = write_task_set(tmp_path, task_ids=("task-a", "task-b"))

    first = _load_task_set(path, fixture_root=fixture_root)
    second = _load_task_set(path, fixture_root=fixture_root)

    assert first == second
    assert isinstance(first.tasks, tuple)
    assert isinstance(first.tasks[0].assertions, tuple)
    assert isinstance(first.tasks[0].tags, tuple)
    assert [task.task_id for task in first.tasks] == ["task-a", "task-b"]


def test_phase_1_task_set_fixture_loads_deterministically() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    fixture_root = repo_root / "tests" / "fixtures"
    task_set_path = fixture_root / "evals" / "phase-1-tasks-v1.json"

    first = _load_task_set(task_set_path, fixture_root=fixture_root)
    second = _load_task_set(task_set_path, fixture_root=fixture_root)

    assert first == second
    assert first.schema_version == 1
    assert first.dataset_id == "phase-1-readonly"
    assert len(first.tasks) >= 5
