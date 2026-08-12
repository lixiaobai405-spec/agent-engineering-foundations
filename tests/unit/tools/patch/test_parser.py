from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from tests.unit.tools.patch_test_helpers import (
    default_limits_dict,
    make_tiny_project,
)


@pytest.fixture
def patch_limits() -> dict[str, int]:
    return default_limits_dict()


@pytest.fixture
def tiny_project(tmp_path: Path) -> Path:
    return make_tiny_project(tmp_path)



def _require_parser() -> None:
    assert importlib.util.find_spec("agent_foundations.tools.patch.parser") is not None


def test_parse_modify_multi_hunk(tmp_path: Path) -> None:
    _require_parser()
    from agent_foundations.tools.patch.parser import parse_unified_diff

    diff = """diff --git a/README.md b/README.md
index abc..def 100644
--- a/README.md
+++ b/README.md
@@ -1,2 +1,3 @@
 # Title
+added
 unchanged
"""
    parsed = parse_unified_diff(diff)
    assert len(parsed.files) == 1
    file = parsed.files[0]
    assert file.path == "README.md"
    assert file.hunk_count == 1
    assert file.add_line_count == 1


def test_parse_create_with_eof_no_newline_marker() -> None:
    _require_parser()
    from agent_foundations.tools.patch.models import PatchOperation
    from agent_foundations.tools.patch.parser import parse_unified_diff

    diff = """diff --git a/new.txt b/new.txt
new file mode 100644
index 0000000..e69de29
--- /dev/null
+++ b/new.txt
@@ -0,0 +1 @@
+only\\ No newline at end of file
"""
    parsed = parse_unified_diff(diff)
    file = parsed.files[0]
    assert file.operation == PatchOperation.CREATE
    line = file.hunks[0].lines[0]
    assert line.missing_newline


def test_parse_git_style_eof_no_newline_on_separate_line() -> None:
    _require_parser()
    from agent_foundations.tools.patch.parser import parse_unified_diff

    diff = """diff --git a/new.txt b/new.txt
new file mode 100644
--- /dev/null
+++ b/new.txt
@@ -0,0 +1 @@
+only
\\ No newline at end of file
"""
    parsed = parse_unified_diff(diff)
    line = parsed.files[0].hunks[0].lines[0]
    assert line.text == "only"
    assert line.missing_newline


def test_rejects_delete_patch() -> None:
    _require_parser()
    from agent_foundations.tools.patch.parser import PatchParseError, parse_unified_diff

    diff = """diff --git a/README.md b/README.md
deleted file mode 100644
--- a/README.md
+++ /dev/null
"""
    with pytest.raises(PatchParseError):
        parse_unified_diff(diff)


def test_rejects_path_traversal_in_header() -> None:
    _require_parser()
    from agent_foundations.tools.patch.parser import PatchParseError, parse_unified_diff

    diff = """diff --git a/../secret b/../secret
--- a/../secret
+++ b/../secret
@@ -1 +1 @@
-x
+y
"""
    with pytest.raises(PatchParseError):
        parse_unified_diff(diff)


def test_parse_error_message_is_bounded() -> None:
    _require_parser()
    from agent_foundations.tools.patch.parser import PatchParseError, parse_unified_diff

    secret = "SUPER_SECRET_SOURCE_LINE_CONTENT"
    diff = """diff --git a/a.txt b/a.txt
--- a/a.txt
+++ b/a.txt
@@ -1 +1 @@
-only
+changed
+extra
"""
    with pytest.raises(PatchParseError) as exc:
        parse_unified_diff(diff)
    assert secret not in str(exc.value)
