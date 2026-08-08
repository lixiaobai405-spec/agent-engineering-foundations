from pathlib import Path

import pytest

from agent_foundations.domain.errors import BinaryFileError, FileTooLargeError
from agent_foundations.tools.filesystem.path_policy import PathPolicy
from agent_foundations.tools.filesystem.read_file import ReadFileTool

FIXTURE_ROOT = Path("tests/fixtures/sample_project").resolve()


@pytest.mark.asyncio
async def test_reads_numbered_line_range() -> None:
    tool = ReadFileTool(PathPolicy(FIXTURE_ROOT))
    result = await tool.execute({"path": "src/auth.py", "start_line": 1, "max_lines": 1})
    assert result.content == "1: def authenticate(token: str) -> bool:"
    assert result.metadata["path"] == "src/auth.py"
    assert result.metadata["start_line"] == 1
    assert result.metadata["returned_lines"] == 1
    assert result.metadata["truncated"] is True


def test_read_lines_returns_complete_bounded_file(tmp_path: Path) -> None:
    lines = [f"line-{number}" for number in range(1, 551)]
    (tmp_path / "long.txt").write_text("\n".join(lines), encoding="utf-8")
    tool = ReadFileTool(PathPolicy(tmp_path), max_bytes=20_000)

    result = tool.read_lines("long.txt")

    assert len(result) == 550
    assert result[-1] == "line-550"


def test_accepts_exact_byte_limit_and_rejects_larger_file(
    tmp_path: Path,
) -> None:
    (tmp_path / "exact.txt").write_bytes(b"1234")
    (tmp_path / "large.txt").write_bytes(b"12345")
    tool = ReadFileTool(PathPolicy(tmp_path), max_bytes=4)

    assert tool.read_lines("exact.txt") == ("1234",)
    with pytest.raises(FileTooLargeError):
        tool.read_lines("large.txt")


@pytest.mark.parametrize(
    "raw",
    [b"a\x00b", b"\xff"],
    ids=["nul-byte", "invalid-utf8"],
)
def test_rejects_binary_or_invalid_utf8(
    tmp_path: Path,
    raw: bytes,
) -> None:
    (tmp_path / "binary.bin").write_bytes(raw)
    tool = ReadFileTool(PathPolicy(tmp_path), max_bytes=100)

    with pytest.raises(BinaryFileError):
        tool.read_lines("binary.bin")


@pytest.mark.asyncio
async def test_returns_failure_for_directory(tmp_path: Path) -> None:
    tool = ReadFileTool(PathPolicy(tmp_path))

    result = await tool.execute({"path": "."})

    assert result.success is False
    assert result.error_code == "not_file"


def test_rejects_non_positive_byte_limit(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="positive"):
        ReadFileTool(PathPolicy(tmp_path), max_bytes=0)
