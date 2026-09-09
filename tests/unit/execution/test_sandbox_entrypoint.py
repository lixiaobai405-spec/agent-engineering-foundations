from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ENTRYPOINT = _REPO_ROOT / "docker" / "sandbox-entrypoint.sh"


def _entrypoint_text() -> str:
    return _ENTRYPOINT.read_text(encoding="utf-8")


def test_entrypoint_keeps_non_interpreting_exec_and_forbids_store_copy() -> None:
    text = _entrypoint_text()
    assert 'exec "$@"' in text
    assert "eval" not in text
    assert "sh -c" not in text
    assert 'cp -a "$SANDBOX_NODE_MODULES"' not in text
    assert "cp -a ${SANDBOX_NODE_MODULES}" not in text
    assert "cp -a $SANDBOX_NODE_MODULES" not in text


def test_entrypoint_does_not_root_symlink_node_modules_store() -> None:
    text = _entrypoint_text()
    assert 'ln -s "$SANDBOX_NODE_MODULES" /workspace/node_modules' not in text
    assert "ln -s ${SANDBOX_NODE_MODULES} /workspace/node_modules" not in text
    assert "ln -s $SANDBOX_NODE_MODULES /workspace/node_modules" not in text


def test_entrypoint_makes_writable_node_modules_dir_and_links_store_entries() -> None:
    text = _entrypoint_text()
    assert "SANDBOX_NODE_MODULES" in text
    assert "mkdir /workspace/node_modules" in text or "mkdir -p /workspace/node_modules" in text
    assert "for " in text
    assert "ln -s" in text
    assert "basename" in text
    assert ".bin" in text or "/.[!.]*" in text
