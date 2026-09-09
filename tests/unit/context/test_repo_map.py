from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any


def _repo_map() -> Any:
    try:
        spec = importlib.util.find_spec("agent_foundations.context.repo_map")
    except ModuleNotFoundError:
        spec = None
    assert spec is not None, "RepoMapBuilder is missing"
    from agent_foundations.context.repo_map import RepoMapBuilder, RepoMapLimits

    return RepoMapBuilder, RepoMapLimits


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_python_and_ts_map_are_deterministic_and_skip_unsafe_paths(tmp_path: Path) -> None:
    RepoMapBuilder, RepoMapLimits = _repo_map()
    _write(
        tmp_path / "src" / "a.py",
        "from src import b\nclass Alpha:\n    def run(self) -> None:\n        return None\n",
    )
    _write(tmp_path / "src" / "b.py", "from src import a\nclass Beta:\n    pass\n")
    _write(
        tmp_path / "src" / "client.ts",
        "import { Alpha } from './a';\nconst x = require('./b');\nexport { Alpha } from './a';\n",
    )
    _write(tmp_path / "src" / "notes.md", "# notes\n")
    _write(tmp_path / ".env", "SECRET=1\n")
    _write(tmp_path / "id_rsa", "-----BEGIN FAKE PRIVATE KEY-----\n")
    _write(tmp_path / "node_modules" / "pkg" / "index.js", "export const leak = 1;\n")
    _write(tmp_path / ".git" / "config", "[core]\n")
    _write(tmp_path / "venv" / "lib.py", "secret = 1\n")
    _write(tmp_path / "artifacts" / "out.txt", "artifact body\n")
    _write(tmp_path / ".agent-foundations" / "evals" / "run.json", "{}\n")
    (tmp_path / "binary.bin").write_bytes(b"\x00\xffbinary")
    link = tmp_path / "src" / "link.py"
    try:
        link.symlink_to(tmp_path / "src" / "a.py")
        symlink_ok = True
    except OSError:
        symlink_ok = False

    first = RepoMapBuilder().build(tmp_path, RepoMapLimits())
    second = RepoMapBuilder().build(tmp_path, RepoMapLimits())
    ids = [source.source_id for source in first.sources]
    assert ids == [source.source_id for source in second.sources]
    assert any(item.source_id == "symbol:src/a.py:Alpha" for item in first.sources)
    assert any(item.source_id == "symbol:src/a.py:Alpha.run" for item in first.sources)
    assert any(item.kind == "import" and "src.b" in item.source_id for item in first.sources)
    assert any(item.provenance.endswith("python-ast") for item in first.sources)
    assert any(
        item.source_id.startswith("import:src/client.ts:")
        and item.provenance.endswith("ts-import-export")
        for item in first.sources
    )
    assert any(item.source_id == "file:src/notes.md" for item in first.sources)
    joined = "\n".join(item.source_id for item in first.sources)
    assert ".env" not in joined
    assert "id_rsa" not in joined
    assert "node_modules" not in joined
    assert ".git" not in joined
    assert "venv" not in joined
    assert "artifacts" not in joined
    assert ".agent-foundations" not in joined
    assert "binary.bin" not in joined
    if symlink_ok:
        assert "link.py" not in joined
    assert "SECRET=1" not in "".join(item.content for item in first.sources)


def test_cyclic_imports_terminate_and_limits_drop_tail_by_path(tmp_path: Path) -> None:
    RepoMapBuilder, RepoMapLimits = _repo_map()
    _write(tmp_path / "pkg" / "one.py", "from pkg import two\n")
    _write(tmp_path / "pkg" / "two.py", "from pkg import one\n")
    _write(tmp_path / "z_last.py", "VALUE = 1\n")
    _write(tmp_path / "a_first.py", "VALUE = 2\n")
    mapping = RepoMapBuilder().build(
        tmp_path,
        RepoMapLimits(max_files=1, max_file_bytes=65536, max_map_chars=8000, max_sources=8),
    )
    file_ids = [item.source_id for item in mapping.sources if item.kind == "file"]
    assert file_ids
    assert file_ids[0].endswith("a_first.py")
    assert all(not item.source_id.endswith("z_last.py") for item in mapping.sources)
    assert mapping.truncated is True
