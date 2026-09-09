from __future__ import annotations

import importlib.util
from typing import Any

import pytest
from pydantic import ValidationError


def _models() -> tuple[Any, ...]:
    try:
        spec = importlib.util.find_spec("agent_foundations.tools.git.models")
    except ModuleNotFoundError:
        spec = None
    assert spec is not None, "git read models are missing"
    from agent_foundations.tools.git.models import (
        DEFAULT_DIFF_MAX_BYTES,
        GitDiffResult,
        GitLogEntry,
        GitLogResult,
        GitStatusEntry,
        GitStatusResult,
    )

    return (
        DEFAULT_DIFF_MAX_BYTES,
        GitDiffResult,
        GitLogEntry,
        GitLogResult,
        GitStatusEntry,
        GitStatusResult,
    )


def test_status_diff_log_models_reject_extra_git_fields() -> None:
    _, GitDiffResult, GitLogEntry, GitLogResult, GitStatusEntry, GitStatusResult = _models()
    entry = GitStatusEntry(path="src/a.py", index_status="M", worktree_status=" ")
    status = GitStatusResult(entries=(entry,), untracked=(), staged=("src/a.py",))
    diff = GitDiffResult(
        path="src/a.py",
        staged=False,
        patch="diff --git a/src/a.py b/src/a.py\n",
        truncated=False,
        byte_count=28,
    )
    log = GitLogResult(
        entries=(GitLogEntry(commit="a" * 40, subject="init"),),
    )
    assert status.entries[0].path == "src/a.py"
    assert diff.truncated is False
    assert log.entries[0].commit == "a" * 40
    with pytest.raises(ValidationError):
        GitStatusEntry.model_validate(
            {**entry.model_dump(), "ref": "HEAD"},
        )
    with pytest.raises(ValidationError):
        GitDiffResult.model_validate({**diff.model_dump(), "format": "raw"})
    with pytest.raises(ValidationError):
        GitLogEntry.model_validate({**log.entries[0].model_dump(), "pretty": "%H"})


def test_diff_max_bytes_default_is_200000() -> None:
    default_max, *_ = _models()
    assert default_max == 200000
