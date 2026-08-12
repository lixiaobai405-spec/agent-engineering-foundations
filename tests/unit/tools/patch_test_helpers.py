from __future__ import annotations

import hashlib
from pathlib import Path

SAMPLE_DIFF_SECRET = "UNIQUE_PATCH_PREVIEW_SECRET_SNIPPET_XYZ"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def default_limits_dict() -> dict[str, int]:
    return {
        "max_patch_bytes": 256000,
        "max_files": 32,
        "max_hunks": 256,
        "max_file_bytes": 1000000,
    }


def make_tiny_project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    src = root / "src"
    src.mkdir(parents=True)
    (root / "README.md").write_text("# Title\n", encoding="utf-8", newline="\n")
    (src / "auth.py").write_text(
        f"def token():\n    return '{SAMPLE_DIFF_SECRET}'\n",
        encoding="utf-8",
        newline="\n",
    )
    return root.resolve()
