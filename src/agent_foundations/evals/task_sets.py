import json
from pathlib import Path

from agent_foundations.evals.models import EvalTaskSet


def load_task_set(path: Path, *, fixture_root: Path) -> EvalTaskSet:
    raw = json.loads(path.read_text(encoding="utf-8"))
    schema_version = raw.get("schema_version")
    if schema_version != 1:
        raise ValueError(f"unsupported schema_version: {schema_version!r}")

    task_set = EvalTaskSet.model_validate(raw)
    seen_task_ids: set[str] = set()
    resolved_fixture_root = fixture_root.resolve()

    for task in task_set.tasks:
        if task.task_id in seen_task_ids:
            raise ValueError(f"duplicate task_id: {task.task_id}")
        seen_task_ids.add(task.task_id)

        normalized_fixture = Path(task.project_fixture).as_posix()
        resolved_project = (resolved_fixture_root / normalized_fixture).resolve()
        if not resolved_project.is_relative_to(resolved_fixture_root):
            raise ValueError("project_fixture must be a safe relative path")

    return task_set
