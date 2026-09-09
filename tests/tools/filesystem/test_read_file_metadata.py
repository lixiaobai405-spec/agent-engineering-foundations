from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from agent_foundations.tools.filesystem.path_policy import PathPolicy
from agent_foundations.tools.filesystem.read_file import ReadFileTool


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


@pytest.mark.asyncio
async def test_read_file_metadata_includes_full_file_sha256_size_and_utf8(
    tmp_path: Path,
) -> None:
    raw = b"alpha\nbeta\n"
    (tmp_path / "notes.txt").write_bytes(raw)
    tool = ReadFileTool(PathPolicy(tmp_path))

    result = await tool.execute({"path": "notes.txt"})

    assert result.success is True
    assert result.metadata["path"] == "notes.txt"
    assert result.metadata["start_line"] == 1
    assert result.metadata["returned_lines"] == 2
    assert result.metadata["truncated"] is False
    assert result.metadata["encoding"] == "utf-8"
    assert result.metadata["size_bytes"] == len(raw)
    assert result.metadata["sha256"] == _sha256(raw)
    assert len(result.metadata["sha256"]) == 64
    assert result.metadata["sha256"] == result.metadata["sha256"].lower()


@pytest.mark.asyncio
async def test_truncated_read_still_returns_full_file_sha256(tmp_path: Path) -> None:
    raw = b"one\ntwo\nthree\n"
    (tmp_path / "story.txt").write_bytes(raw)
    tool = ReadFileTool(PathPolicy(tmp_path))

    result = await tool.execute({"path": "story.txt", "start_line": 1, "max_lines": 1})

    assert result.success is True
    assert result.metadata["returned_lines"] == 1
    assert result.metadata["truncated"] is True
    assert result.metadata["encoding"] == "utf-8"
    assert result.metadata["size_bytes"] == len(raw)
    assert result.metadata["sha256"] == _sha256(raw)
    assert result.metadata["sha256"] != _sha256(b"one\n")
