from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from agent_foundations.durable.models import DurableRun, DurableRunStatus
from agent_foundations.durable.repository import DurableRunRepository
from agent_foundations.runtime.tool_execution import DirectToolCallExecutor, ToolExecutionContext
from agent_foundations.tools.filesystem.path_policy import PathPolicy
from agent_foundations.tools.filesystem.read_file import ReadFileTool
from agent_foundations.tools.patch.applier import apply_prepared_patch_atomically, prepare_patch
from agent_foundations.tools.patch.execution import (
    PatchProposalExecutor,
    sanitize_validate_patch_arguments,
)
from agent_foundations.tools.patch.repository import PatchProposalRepository
from agent_foundations.tools.patch.structured import _line_texts
from agent_foundations.tools.patch.validate_patch import ValidatePatchTool

RUN_ID = "22222222-2222-4222-8222-222222222222"
NOW = datetime(2026, 8, 29, 4, 0, tzinfo=UTC)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    (root / "README.md").write_bytes(b"# Title\n")
    return root.resolve(strict=True)


async def _executor(
    tmp_path: Path,
    root: Path,
) -> tuple[PatchProposalExecutor, ToolExecutionContext]:
    db_path = tmp_path / "app.sqlite3"
    durable = DurableRunRepository(db_path)
    await durable.initialize()
    await durable.create_run(
        DurableRun(
            run_id=RUN_ID,
            project_root=str(root),
            status=DurableRunStatus.CREATED,
            schema_version=1,
            state_version=0,
            attempt=1,
            created_at=NOW,
            updated_at=NOW,
        ),
    )
    repo = PatchProposalRepository.from_path(db_path)
    await repo.initialize()
    executor = PatchProposalExecutor(DirectToolCallExecutor(), repo)
    context = ToolExecutionContext(
        session_id=RUN_ID,
        root=root,
        tool_call_id="call-validate",
        tool_name="validate_patch",
    )
    return executor, context


def _readme_change(root: Path, *, expected: str | None = None) -> dict[str, Any]:
    digest = expected if expected is not None else _sha256((root / "README.md").read_bytes())
    return {
        "path": "README.md",
        "expected_sha256": digest,
        "start_line": 1,
        "old_lines": ["# Title"],
        "new_lines": ["# Title", "world"],
    }


@pytest.mark.asyncio
async def test_changes_compile_to_validated_patch_and_apply_writes_file(
    tmp_path: Path,
) -> None:
    root = _project(tmp_path)
    before = (root / "README.md").read_bytes()
    executor, context = await _executor(tmp_path, root)
    tool = ValidatePatchTool()

    result = await executor.execute(tool, {"changes": [_readme_change(root)]}, context)

    assert result.success is True
    patch_id = str(result.metadata["patch_id"])
    repo = PatchProposalRepository.from_path(tmp_path / "app.sqlite3")
    patch = await repo.get(RUN_ID, patch_id)
    apply_prepared_patch_atomically(prepare_patch(patch, root), root)

    assert (root / "README.md").read_bytes() == b"# Title\nworld\n"
    assert before == b"# Title\n"


@pytest.mark.asyncio
async def test_wrong_expected_sha256_does_not_write_file(tmp_path: Path) -> None:
    root = _project(tmp_path)
    executor, context = await _executor(tmp_path, root)
    tool = ValidatePatchTool()
    wrong = "0" * 64

    result = await executor.execute(
        tool,
        {"changes": [_readme_change(root, expected=wrong)]},
        context,
    )

    assert result.success is False
    assert result.error_code == "PATCH_BASELINE_MISMATCH"
    assert (root / "README.md").read_bytes() == b"# Title\n"


@pytest.mark.asyncio
async def test_old_lines_mismatch_does_not_write_file(tmp_path: Path) -> None:
    root = _project(tmp_path)
    executor, context = await _executor(tmp_path, root)
    tool = ValidatePatchTool()
    change = _readme_change(root)
    change["old_lines"] = ["not the actual line"]

    result = await executor.execute(tool, {"changes": [change]}, context)

    assert result.success is False
    assert result.error_code == "PATCH_VALIDATION_ERROR"
    assert (root / "README.md").read_bytes() == b"# Title\n"


@pytest.mark.asyncio
async def test_diff_and_changes_together_are_rejected(tmp_path: Path) -> None:
    root = _project(tmp_path)
    executor, context = await _executor(tmp_path, root)
    tool = ValidatePatchTool()
    baselines = [{"path": "README.md", "sha256": _sha256(b"# Title\n")}]

    result = await executor.execute(
        tool,
        {
            "diff": "diff --git a/README.md b/README.md\n",
            "baselines": baselines,
            "changes": [_readme_change(root)],
        },
        context,
    )

    assert result.success is False
    assert result.error_code == "PATCH_INVALID_ARGUMENTS"
    assert (root / "README.md").read_bytes() == b"# Title\n"


@pytest.mark.asyncio
async def test_diff_plus_baselines_path_still_validates(tmp_path: Path) -> None:
    root = _project(tmp_path)
    executor, context = await _executor(tmp_path, root)
    tool = ValidatePatchTool()
    diff = """diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -1 +1,2 @@
-# Title
+# Title
+world
"""
    result = await executor.execute(
        tool,
        {
            "diff": diff,
            "baselines": [{"path": "README.md", "sha256": _sha256(b"# Title\n")}],
        },
        context,
    )

    assert result.success is True
    assert result.metadata["file_count"] == 1


def test_structured_matching_lines_equal_read_lines_on_crlf(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    raw = b"alpha\r\nbeta\r\n"
    (root / "notes.txt").write_bytes(raw)
    lines = ReadFileTool(PathPolicy(root)).read_lines("notes.txt")
    assert lines == ("alpha", "beta")
    assert all("\r" not in line and "\n" not in line for line in lines)
    assert tuple(_line_texts(raw)) == lines


def test_empty_file_is_zero_utf8_lines(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    (root / "empty.txt").write_bytes(b"")
    assert ReadFileTool(PathPolicy(root)).read_lines("empty.txt") == ()
    assert _line_texts(b"") == []


async def _validate_line_replace(
    tmp_path: Path,
    *,
    filename: str,
    raw: bytes,
    new_second: str,
) -> tuple[Any, Path]:
    root = tmp_path / "project"
    root.mkdir()
    target = root / filename
    target.write_bytes(raw)
    reader = ReadFileTool(PathPolicy(root))
    old_lines = list(reader.read_lines(filename))
    executor, context = await _executor(tmp_path, root)
    tool = ValidatePatchTool()
    result = await executor.execute(
        tool,
        {
            "changes": [
                {
                    "path": filename,
                    "expected_sha256": _sha256(raw),
                    "start_line": 1,
                    "old_lines": old_lines,
                    "new_lines": [old_lines[0], new_second],
                }
            ]
        },
        context,
    )
    return result, target


@pytest.mark.asyncio
async def test_crlf_read_lines_validate_and_apply_preserves_crlf(tmp_path: Path) -> None:
    result, target = await _validate_line_replace(
        tmp_path,
        filename="notes.txt",
        raw=b"alpha\r\nbeta\r\n",
        new_second="gamma",
    )
    assert result.success is True, result.error_code
    patch_id = str(result.metadata["patch_id"])
    repo = PatchProposalRepository.from_path(tmp_path / "app.sqlite3")
    patch = await repo.get(RUN_ID, patch_id)
    apply_prepared_patch_atomically(prepare_patch(patch, target.parent), target.parent)
    assert target.read_bytes() == b"alpha\r\ngamma\r\n"


@pytest.mark.asyncio
async def test_lf_without_trailing_newline_apply_keeps_lf(tmp_path: Path) -> None:
    result, target = await _validate_line_replace(
        tmp_path,
        filename="notes.txt",
        raw=b"alpha\nbeta",
        new_second="gamma",
    )
    assert result.success is True, result.error_code
    patch_id = str(result.metadata["patch_id"])
    repo = PatchProposalRepository.from_path(tmp_path / "app.sqlite3")
    patch = await repo.get(RUN_ID, patch_id)
    apply_prepared_patch_atomically(prepare_patch(patch, target.parent), target.parent)
    assert target.read_bytes() == b"alpha\ngamma"


@pytest.mark.asyncio
async def test_crlf_without_trailing_newline_apply_keeps_crlf(tmp_path: Path) -> None:
    result, target = await _validate_line_replace(
        tmp_path,
        filename="notes.txt",
        raw=b"alpha\r\nbeta",
        new_second="gamma",
    )
    assert result.success is True, result.error_code
    patch_id = str(result.metadata["patch_id"])
    repo = PatchProposalRepository.from_path(tmp_path / "app.sqlite3")
    patch = await repo.get(RUN_ID, patch_id)
    apply_prepared_patch_atomically(prepare_patch(patch, target.parent), target.parent)
    assert target.read_bytes() == b"alpha\r\ngamma"


def test_sanitize_validate_patch_arguments_covers_changes_without_file_body() -> None:
    arguments = {
        "changes": [
            {
                "path": "README.md",
                "expected_sha256": "a" * 64,
                "start_line": 1,
                "old_lines": ["# Title", "SECRET_LINE_MUST_NOT_LEAK"],
                "new_lines": ["world"],
            }
        ]
    }

    sanitized = sanitize_validate_patch_arguments(arguments)

    assert sanitized["redacted"] is True
    assert sanitized["change_count"] == 1
    dumped = str(sanitized)
    assert "SECRET_LINE_MUST_NOT_LEAK" not in dumped
    assert "old_lines" not in dumped
    assert "new_lines" not in dumped
    assert "# Title" not in dumped
