from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import Any

import pytest

from agent_foundations.tools.patch.models import PatchFile, ValidatedPatch
from agent_foundations.tools.patch.validator import parse_and_validate_patch
from tests.unit.tools.patch_test_helpers import sha256_bytes


def _api() -> tuple[Any, ...]:
    assert importlib.util.find_spec("agent_foundations.tools.patch.applier") is not None, (
        "Task 15 atomic patch applier is missing"
    )
    from agent_foundations.tools.patch.applier import (
        PatchApplyError,
        apply_prepared_patch_atomically,
        build_applier_payload,
        prepare_patch,
        verify_prepared_patch,
    )

    return (
        PatchApplyError,
        prepare_patch,
        apply_prepared_patch_atomically,
        build_applier_payload,
        verify_prepared_patch,
    )


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "fixture-project"
    (root / "src").mkdir(parents=True)
    (root / "README.md").write_text("# Before\n", encoding="utf-8", newline="\n")
    (root / "src" / "app.py").write_text(
        "value = 1\n",
        encoding="utf-8",
        newline="\n",
    )
    return root.resolve(strict=True)


def _two_file_patch(root: Path) -> ValidatedPatch:
    diff = """diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -1 +1 @@
-# Before
+# After
diff --git a/src/new.py b/src/new.py
new file mode 100644
--- /dev/null
+++ b/src/new.py
@@ -0,0 +1 @@
+created = True
"""
    return parse_and_validate_patch(
        diff,
        (
            {"path": "README.md", "sha256": sha256_bytes((root / "README.md").read_bytes())},
            {"path": "src/new.py", "sha256": None},
        ),
        root,
    )


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_prepare_patch_renders_modify_and_create_without_writing(tmp_path: Path) -> None:
    _Error, prepare_patch, _apply, build_payload, verify, = _api()
    root = _project(tmp_path)
    patch = _two_file_patch(root)
    before = _snapshot(root)

    prepared = prepare_patch(patch, root)

    assert _snapshot(root) == before
    assert [item.path for item in prepared.files] == ["README.md", "src/new.py"]
    assert prepared.files[0].content == b"# After\n"
    assert prepared.files[1].content == b"created = True\n"
    assert prepared.files[0].before_sha256 == sha256_bytes(b"# Before\n")
    assert prepared.files[1].before_sha256 is None
    assert b"# After" not in build_payload(prepared)
    with pytest.raises(_Error, match="verification"):
        verify(prepared, root)


def test_atomic_applier_rolls_back_all_files_in_reverse_order(
    tmp_path: Path,
) -> None:
    PatchApplyError, prepare_patch, apply_atomically, *_ = _api()
    root = _project(tmp_path)
    prepared = prepare_patch(_two_file_patch(root), root)
    before = _snapshot(root)
    replace_count = 0

    def fail_second_replace(source: Path, target: Path) -> None:
        nonlocal replace_count
        replace_count += 1
        if replace_count == 2:
            raise OSError("injected second replace failure")
        os.replace(source, target)

    with pytest.raises(PatchApplyError) as error:
        apply_atomically(prepared, root, replace_file=fail_second_replace)

    assert error.value.code == "PATCH_ROLLED_BACK"
    assert _snapshot(root) == before
    assert not (root / "src" / "new.py").exists()
    assert tuple(root.glob(".agent-patch-*")) == ()


def test_prepare_rejects_baseline_drift_and_symlink_swap(tmp_path: Path) -> None:
    PatchApplyError, prepare_patch, *_ = _api()
    root = _project(tmp_path)
    patch = _two_file_patch(root)
    (root / "README.md").write_text("drift\n", encoding="utf-8")
    with pytest.raises(PatchApplyError) as drift:
        prepare_patch(patch, root)
    assert drift.value.code == "PATCH_BASELINE_MISMATCH"

    root = _project(tmp_path / "second")
    patch = _two_file_patch(root)
    outside = tmp_path / "outside.md"
    outside.write_text("# Before\n", encoding="utf-8")
    (root / "README.md").unlink()
    try:
        os.symlink(outside, root / "README.md")
    except OSError:
        pytest.skip("symlink creation is unavailable on this Windows host")
    with pytest.raises(PatchApplyError) as swapped:
        prepare_patch(patch, root)
    assert swapped.value.code == "PATCH_PATH_REJECTED"
    assert outside.read_text(encoding="utf-8") == "# Before\n"


@pytest.mark.parametrize("unsafe_path", ["README.md:stream", "src/bad\x01.py"])
def test_prepare_rejects_ads_and_control_character_paths(
    tmp_path: Path,
    unsafe_path: str,
) -> None:
    PatchApplyError, prepare_patch, *_ = _api()
    root = _project(tmp_path)
    patch = _two_file_patch(root)
    first: PatchFile = patch.files[0].model_copy(update={"path": unsafe_path})
    unsafe = patch.model_copy(update={"files": (first, *patch.files[1:])})

    with pytest.raises(PatchApplyError) as error:
        prepare_patch(unsafe, root)

    assert error.value.code == "PATCH_PATH_REJECTED"

