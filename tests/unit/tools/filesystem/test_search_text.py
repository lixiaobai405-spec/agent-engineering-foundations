import json
from pathlib import Path

import pytest

from agent_foundations.domain.errors import InvalidToolArgumentsError
from agent_foundations.tools.filesystem.path_policy import PathPolicy
from agent_foundations.tools.filesystem.search_text import SearchTextTool
from agent_foundations.tools.registry import ToolRegistry

FIXTURE_ROOT = Path("tests/fixtures/sample_project").resolve()


@pytest.mark.asyncio
async def test_searches_text_with_relative_locations() -> None:
    tool = SearchTextTool(PathPolicy(FIXTURE_ROOT), max_matches=10)
    result = await tool.execute(
        {"query": "token", "path": ".", "glob": "src/*.py"}
    )
    payload = json.loads(result.content)
    assert payload["matches"] == [
        {"path": "src/auth.py", "line": 1, "text": "def authenticate(token: str) -> bool:"},
        {"path": "src/auth.py", "line": 2, "text": "    return token == \"demo-token\""},
    ]
    assert payload["scanned_files"] == 1
    assert payload["truncated"] is False


@pytest.mark.asyncio
async def test_searches_unicode_text_with_casefolding(tmp_path: Path) -> None:
    (tmp_path / "unicode.txt").write_text("Straße", encoding="utf-8")
    tool = SearchTextTool(PathPolicy(tmp_path), max_matches=10)

    result = await tool.execute(
        {"query": "STRASSE", "path": ".", "glob": "unicode.txt"}
    )
    payload = json.loads(result.content)

    assert payload["matches"] == [
        {"path": "unicode.txt", "line": 1, "text": "Straße"}
    ]


@pytest.mark.asyncio
async def test_registry_rejects_empty_glob(tmp_path: Path) -> None:
    registry = ToolRegistry([SearchTextTool(PathPolicy(tmp_path))])

    with pytest.raises(InvalidToolArgumentsError):
        await registry.execute("search_text", {"query": "needle", "glob": ""})


@pytest.mark.asyncio
async def test_searches_after_line_500_and_skips_sensitive_files(
    tmp_path: Path,
) -> None:
    source = tmp_path / "src"
    source.mkdir()
    lines = ["ordinary"] * 520 + ["late needle"]
    (source / "long.py").write_text("\n".join(lines), encoding="utf-8")
    (tmp_path / ".env").write_text(
        "SECRET=must-never-be-readable",
        encoding="utf-8",
    )
    tool = SearchTextTool(
        PathPolicy(tmp_path),
        max_matches=10,
        max_files=10,
    )

    result = await tool.execute(
        {"query": "needle", "path": ".", "glob": "src/*.py"}
    )
    payload = json.loads(result.content)

    assert payload["matches"] == [
        {"path": "src/long.py", "line": 521, "text": "late needle"}
    ]
    assert "must-never-be-readable" not in result.content


@pytest.mark.asyncio
async def test_stops_after_file_budget(tmp_path: Path) -> None:
    for name in ("a.py", "b.py", "c.py"):
        (tmp_path / name).write_text("needle", encoding="utf-8")
    tool = SearchTextTool(
        PathPolicy(tmp_path),
        max_matches=10,
        max_files=2,
    )

    result = await tool.execute({"query": "needle", "path": "."})
    payload = json.loads(result.content)

    assert payload["scanned_files"] == 2
    assert payload["truncated"] is True


@pytest.mark.asyncio
async def test_stops_after_match_budget(tmp_path: Path) -> None:
    for name in ("a.py", "b.py", "c.py"):
        (tmp_path / name).write_text("needle\nneedle\n", encoding="utf-8")
    tool = SearchTextTool(PathPolicy(tmp_path), max_matches=3)

    result = await tool.execute({"query": "needle", "path": "."})
    payload = json.loads(result.content)

    assert len(payload["matches"]) == 3
    assert payload["truncated"] is True


@pytest.mark.asyncio
async def test_exact_match_budget_is_not_marked_truncated(tmp_path: Path) -> None:
    (tmp_path / "source.py").write_text("needle\nneedle", encoding="utf-8")
    tool = SearchTextTool(PathPolicy(tmp_path), max_matches=2)

    result = await tool.execute({"query": "needle", "path": "."})
    payload = json.loads(result.content)

    assert len(payload["matches"]) == 2
    assert payload["truncated"] is False


@pytest.mark.asyncio
async def test_binary_file_is_skipped_and_counted(tmp_path: Path) -> None:
    (tmp_path / "good.py").write_text("needle", encoding="utf-8")
    (tmp_path / "bad.bin").write_bytes(b"\x00needle\x00")
    tool = SearchTextTool(PathPolicy(tmp_path), max_matches=10)

    result = await tool.execute({"query": "needle", "path": "."})
    payload = json.loads(result.content)

    assert payload["scanned_files"] == 2
    assert payload["skipped_files"] == 1
    assert len(payload["matches"]) == 1
    assert payload["matches"][0]["path"] == "good.py"


@pytest.mark.asyncio
async def test_oversized_file_is_skipped_and_counted(tmp_path: Path) -> None:
    (tmp_path / "small.py").write_text("needle", encoding="utf-8")
    (tmp_path / "large.py").write_text("x" * 200 + "needle", encoding="utf-8")
    tool = SearchTextTool(PathPolicy(tmp_path), max_matches=10, max_file_bytes=10)

    result = await tool.execute({"query": "needle", "path": "."})
    payload = json.loads(result.content)

    assert payload["skipped_files"] == 1
    assert len(payload["matches"]) == 1
    assert payload["matches"][0]["path"] == "small.py"


@pytest.mark.asyncio
async def test_traversal_order_is_stable(tmp_path: Path) -> None:
    names = ["Z.py", "a.py", "B.py"]
    for name in names:
        (tmp_path / name).write_text("needle", encoding="utf-8")
    tool = SearchTextTool(PathPolicy(tmp_path), max_matches=10)

    result = await tool.execute({"query": "needle", "path": "."})
    payload = json.loads(result.content)

    paths = [m["path"] for m in payload["matches"]]
    assert paths == sorted(paths, key=str.casefold)


def test_rejects_non_positive_limits(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="positive"):
        SearchTextTool(PathPolicy(tmp_path), max_matches=0)
    with pytest.raises(ValueError, match="positive"):
        SearchTextTool(PathPolicy(tmp_path), max_files=0)
    with pytest.raises(ValueError, match="positive"):
        SearchTextTool(PathPolicy(tmp_path), max_file_bytes=0)
