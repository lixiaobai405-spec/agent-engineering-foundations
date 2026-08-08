import json
from pathlib import Path

import pytest

from agent_foundations.tools.filesystem.list_directory import ListDirectoryTool
from agent_foundations.tools.filesystem.path_policy import PathPolicy

FIXTURE_ROOT = Path("tests/fixtures/sample_project").resolve()


@pytest.mark.asyncio
async def test_lists_relative_entries_in_stable_order() -> None:
    tool = ListDirectoryTool(PathPolicy(FIXTURE_ROOT), max_entries=10)

    result = await tool.execute({"path": "."})
    payload = json.loads(result.content)

    assert result.success is True
    assert payload["path"] == "."
    assert payload["entries"] == [
        {"name": "src", "type": "directory"},
        {"name": "README.md", "type": "file"},
    ]
    assert payload["truncated"] is False


@pytest.mark.asyncio
async def test_limits_entries_and_hides_sensitive_children(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    for name in ("a.txt", "b.txt", "c.txt"):
        (tmp_path / name).write_text(name, encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET=blocked", encoding="utf-8")
    tool = ListDirectoryTool(PathPolicy(tmp_path), max_entries=2)

    result = await tool.execute({"path": "."})
    payload = json.loads(result.content)

    assert payload["entries"] == [
        {"name": "src", "type": "directory"},
        {"name": "a.txt", "type": "file"},
    ]
    assert payload["truncated"] is True
    assert ".env" not in result.content


@pytest.mark.asyncio
async def test_returns_failure_for_file_path() -> None:
    tool = ListDirectoryTool(PathPolicy(FIXTURE_ROOT))

    result = await tool.execute({"path": "README.md"})

    assert result.success is False
    assert result.error_code == "not_directory"


def test_rejects_non_positive_entry_limit() -> None:
    with pytest.raises(ValueError, match="positive"):
        ListDirectoryTool(PathPolicy(FIXTURE_ROOT), max_entries=0)
