from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

from tests.unit.tools.patch_test_helpers import make_tiny_project, sha256_bytes


@pytest.fixture
def tiny_project(tmp_path: Path) -> Path:
    return make_tiny_project(tmp_path)


def _require_validator() -> None:
    assert importlib.util.find_spec("agent_foundations.tools.patch.validator") is not None


def test_modify_validates_baseline_and_hunks(tiny_project: Path) -> None:
    _require_validator()
    from agent_foundations.tools.patch.models import BaselineEntry
    from agent_foundations.tools.patch.parser import parse_unified_diff
    from agent_foundations.tools.patch.validator import validate_patch_proposal

    path = "README.md"
    content = (tiny_project / path).read_bytes()
    diff = """diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -1 +1 @@
-# Title
+# Title changed
"""
    parsed = parse_unified_diff(diff)
    patch = validate_patch_proposal(
        parsed,
        [BaselineEntry(path=path, sha256=sha256_bytes(content))],
        tiny_project,
    )
    assert patch.files[0].baseline_sha256 == sha256_bytes(content)


def test_rejects_baseline_hash_mismatch(tiny_project: Path) -> None:
    _require_validator()
    from agent_foundations.tools.patch.models import BaselineEntry
    from agent_foundations.tools.patch.parser import parse_unified_diff
    from agent_foundations.tools.patch.validator import (
        PatchValidationError,
        validate_patch_proposal,
    )

    diff = """diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -1 +1 @@
-# Title
+# changed
"""
    parsed = parse_unified_diff(diff)
    with pytest.raises(PatchValidationError, match="baseline hash mismatch"):
        validate_patch_proposal(
            parsed,
            [BaselineEntry(path="README.md", sha256="a" * 64)],
            tiny_project,
        )


def test_create_requires_null_baseline_and_missing_file(tiny_project: Path) -> None:
    _require_validator()
    from agent_foundations.tools.patch.models import BaselineEntry
    from agent_foundations.tools.patch.parser import parse_unified_diff
    from agent_foundations.tools.patch.validator import validate_patch_proposal

    diff = """diff --git a/new.txt b/new.txt
new file mode 100644
--- /dev/null
+++ b/new.txt
@@ -0,0 +1 @@
+hello
"""
    parsed = parse_unified_diff(diff)
    patch = validate_patch_proposal(
        parsed,
        [BaselineEntry(path="new.txt", sha256=None)],
        tiny_project,
    )
    assert patch.files[0].path == "new.txt"


def test_rejects_create_when_target_exists(tiny_project: Path) -> None:
    _require_validator()
    from agent_foundations.tools.patch.models import BaselineEntry
    from agent_foundations.tools.patch.parser import parse_unified_diff
    from agent_foundations.tools.patch.validator import (
        PatchValidationError,
        validate_patch_proposal,
    )

    diff = """diff --git a/README.md b/README.md
new file mode 100644
--- /dev/null
+++ b/README.md
@@ -0,0 +1 @@
+x
"""
    parsed = parse_unified_diff(diff)
    with pytest.raises(PatchValidationError):
        validate_patch_proposal(
            parsed,
            [BaselineEntry(path="README.md", sha256=None)],
            tiny_project,
        )


def test_rejects_windows_ads_path() -> None:
    _require_validator()
    from agent_foundations.tools.patch.parser import PatchParseError, parse_unified_diff

    diff = """diff --git a/secret:ads b/secret:ads
--- a/secret:ads
+++ b/secret:ads
@@ -1 +1 @@
-x
+y
"""
    with pytest.raises(PatchParseError):
        parse_unified_diff(diff)


def test_deterministic_patch_id(tiny_project: Path) -> None:
    _require_validator()
    from agent_foundations.tools.patch.models import BaselineEntry
    from agent_foundations.tools.patch.validator import parse_and_validate_patch

    path = "README.md"
    content = (tiny_project / path).read_bytes()
    diff = """diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -1 +1 @@
-# Title
+# Title2
"""
    baselines = [BaselineEntry(path=path, sha256=sha256_bytes(content))]
    first = parse_and_validate_patch(diff, baselines, tiny_project)
    second = parse_and_validate_patch(diff, baselines, tiny_project)
    assert first.patch_id == second.patch_id


def test_reparse_walk_rejects_symlink_ancestor(tiny_project: Path) -> None:
    _require_validator()
    from agent_foundations.tools.patch.validator import (
        PatchValidationError,
        _walk_parents_not_reparse,
    )

    if os.name != "nt":
        link_parent = tiny_project / "linked"
        link_parent.mkdir()
        target = tiny_project / "real"
        target.mkdir()
        try:
            os.symlink(target, link_parent / "alias", target_is_directory=True)
        except OSError:
            pytest.skip("symlink creation not permitted")
        with pytest.raises(PatchValidationError):
            _walk_parents_not_reparse(tiny_project, link_parent / "alias")


def test_rejects_nul_bytes_in_added_lines(tiny_project: Path) -> None:
    _require_validator()
    from agent_foundations.tools.patch.models import BaselineEntry
    from agent_foundations.tools.patch.parser import parse_unified_diff
    from agent_foundations.tools.patch.validator import (
        PatchValidationError,
        validate_patch_proposal,
    )

    diff = """diff --git a/new.txt b/new.txt
new file mode 100644
--- /dev/null
+++ b/new.txt
@@ -0,0 +1 @@
+binary\x00content
"""
    parsed = parse_unified_diff(diff)
    with pytest.raises(PatchValidationError, match="binary content rejected"):
        validate_patch_proposal(
            parsed,
            [BaselineEntry(path="new.txt", sha256=None)],
            tiny_project,
        )


def test_rejects_symlink_modify_target(tiny_project: Path) -> None:
    _require_validator()
    from agent_foundations.tools.patch.models import BaselineEntry
    from agent_foundations.tools.patch.parser import parse_unified_diff
    from agent_foundations.tools.patch.validator import (
        PatchValidationError,
        validate_patch_proposal,
    )

    real = tiny_project / "real.txt"
    real.write_text("line\n", encoding="utf-8", newline="\n")
    link = tiny_project / "via-link.txt"
    try:
        os.symlink(real, link)
    except OSError:
        pytest.skip("symlink creation not permitted")
    diff = """diff --git a/via-link.txt b/via-link.txt
--- a/via-link.txt
+++ b/via-link.txt
@@ -1 +1 @@
-line
+changed
"""
    parsed = parse_unified_diff(diff)
    with pytest.raises(PatchValidationError, match="reparse"):
        validate_patch_proposal(
            parsed,
            [BaselineEntry(path="via-link.txt", sha256=sha256_bytes(real.read_bytes()))],
            tiny_project,
        )


def test_rejects_duplicate_target_path_in_patch(tiny_project: Path) -> None:
    _require_validator()
    from agent_foundations.tools.patch.models import BaselineEntry
    from agent_foundations.tools.patch.parser import parse_unified_diff
    from agent_foundations.tools.patch.validator import (
        PatchValidationError,
        validate_patch_proposal,
    )

    target = tiny_project / "a.txt"
    target.write_text("one\n", encoding="utf-8", newline="\n")
    content_hash = sha256_bytes(target.read_bytes())
    diff = """diff --git a/a.txt b/a.txt
--- a/a.txt
+++ b/a.txt
@@ -1 +1 @@
-one
+two
diff --git a/a.txt b/a.txt
--- a/a.txt
+++ b/a.txt
@@ -1 +1 @@
-two
+three
"""
    parsed = parse_unified_diff(diff)
    with pytest.raises(PatchValidationError, match="duplicate path"):
        validate_patch_proposal(
            parsed,
            [BaselineEntry(path="a.txt", sha256=content_hash)],
            tiny_project,
        )


def test_rejects_overlapping_modify_hunks(tiny_project: Path) -> None:
    _require_validator()
    from agent_foundations.tools.patch.models import BaselineEntry
    from agent_foundations.tools.patch.parser import parse_unified_diff
    from agent_foundations.tools.patch.validator import (
        PatchValidationError,
        validate_patch_proposal,
    )

    path = "README.md"
    content = (tiny_project / path).read_bytes()
    diff = """diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -1 +1 @@
-# Title
+# first
@@ -1 +1 @@
-# Title
+# second
"""
    parsed = parse_unified_diff(diff)
    with pytest.raises(PatchValidationError, match="overlapping hunk"):
        validate_patch_proposal(
            parsed,
            [BaselineEntry(path=path, sha256=sha256_bytes(content))],
            tiny_project,
        )


def test_rejects_create_hunk_with_remove_lines(tiny_project: Path) -> None:
    _require_validator()
    from agent_foundations.tools.patch.models import BaselineEntry
    from agent_foundations.tools.patch.parser import parse_unified_diff
    from agent_foundations.tools.patch.validator import (
        PatchValidationError,
        validate_patch_proposal,
    )

    diff = """diff --git a/new.txt b/new.txt
new file mode 100644
--- /dev/null
+++ b/new.txt
@@ -1 +1 @@
-ghost
+hello
"""
    parsed = parse_unified_diff(diff)
    with pytest.raises(PatchValidationError, match="create hunk"):
        validate_patch_proposal(
            parsed,
            [BaselineEntry(path="new.txt", sha256=None)],
            tiny_project,
        )


def test_rejects_out_of_bounds_zero_length_insertion(tiny_project: Path) -> None:
    _require_validator()
    from agent_foundations.tools.patch.models import BaselineEntry
    from agent_foundations.tools.patch.parser import parse_unified_diff
    from agent_foundations.tools.patch.validator import (
        PatchValidationError,
        validate_patch_proposal,
    )

    path = "README.md"
    content = (tiny_project / path).read_bytes()
    diff = """diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -999,0 +1000 @@
+impossible
"""
    parsed = parse_unified_diff(diff)
    with pytest.raises(PatchValidationError, match="invalid insertion position"):
        validate_patch_proposal(
            parsed,
            [BaselineEntry(path=path, sha256=sha256_bytes(content))],
            tiny_project,
        )


def test_accepts_zero_length_insertion_on_empty_file(tiny_project: Path) -> None:
    _require_validator()
    from agent_foundations.tools.patch.models import BaselineEntry
    from agent_foundations.tools.patch.parser import parse_unified_diff
    from agent_foundations.tools.patch.validator import validate_patch_proposal

    path = "empty.txt"
    (tiny_project / path).write_bytes(b"")
    diff = """diff --git a/empty.txt b/empty.txt
--- a/empty.txt
+++ b/empty.txt
@@ -0,0 +1 @@
+first line
"""
    parsed = parse_unified_diff(diff)
    patch = validate_patch_proposal(
        parsed,
        [BaselineEntry(path=path, sha256=sha256_bytes(b""))],
        tiny_project,
    )
    assert patch.files[0].path == path


def test_accepts_zero_length_insertion_before_first_line(tiny_project: Path) -> None:
    _require_validator()
    from agent_foundations.tools.patch.models import BaselineEntry
    from agent_foundations.tools.patch.parser import parse_unified_diff
    from agent_foundations.tools.patch.validator import validate_patch_proposal

    path = "README.md"
    content = (tiny_project / path).read_bytes()
    diff = """diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -0,0 +1 @@
+zero
"""
    parsed = parse_unified_diff(diff)
    patch = validate_patch_proposal(
        parsed,
        [BaselineEntry(path=path, sha256=sha256_bytes(content))],
        tiny_project,
    )
    assert patch.files[0].hunks[0].old_start == 0


def test_rejects_duplicate_zero_length_insertion_at_same_position(tiny_project: Path) -> None:
    _require_validator()
    from agent_foundations.tools.patch.models import BaselineEntry
    from agent_foundations.tools.patch.parser import parse_unified_diff
    from agent_foundations.tools.patch.validator import (
        PatchValidationError,
        validate_patch_proposal,
    )

    path = "README.md"
    content = (tiny_project / path).read_bytes()
    diff = """diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -1,0 +1,1 @@
+first
@@ -1,0 +2,1 @@
+second
"""
    parsed = parse_unified_diff(diff)
    with pytest.raises(PatchValidationError, match="duplicate insertion position"):
        validate_patch_proposal(
            parsed,
            [BaselineEntry(path=path, sha256=sha256_bytes(content))],
            tiny_project,
        )
