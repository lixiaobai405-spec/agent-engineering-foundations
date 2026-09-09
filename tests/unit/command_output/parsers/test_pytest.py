from __future__ import annotations

import importlib.util
from typing import Any

from tests.unit.command_output.parsers import FIXTURE_ROOT


def _parser() -> Any:
    try:
        spec = importlib.util.find_spec("agent_foundations.command_output.parsers.pytest")
    except ModuleNotFoundError:
        spec = None
    assert spec is not None, "pytest output parser is missing"
    from agent_foundations.command_output.parsers.pytest import PytestOutputParser

    return PytestOutputParser()


def test_pytest_text_keeps_all_failed_test_ids_and_skip_counts() -> None:
    outcome = _parser().parse(
        (FIXTURE_ROOT / "pytest" / "text-fail-skip.txt").read_text(encoding="utf-8"),
        "",
        exit_code=1,
    )
    assert outcome.passed == 1
    assert outcome.failed == 1
    assert outcome.skipped == 1
    assert outcome.parser_status == "complete"
    ids = {item.test_id for item in outcome.diagnostics if item.test_id}
    assert "tests/test_a.py::test_fail" in ids


def test_pytest_junit_and_two_failures_preserve_both_ids() -> None:
    parser = _parser()
    junit = parser.parse(
        (FIXTURE_ROOT / "pytest" / "junit-fail-skip.xml").read_text(encoding="utf-8"),
        "",
        exit_code=1,
    )
    assert junit.failed == 1
    two = parser.parse(
        (FIXTURE_ROOT / "pytest" / "text-two-failures.txt").read_text(encoding="utf-8"),
        "",
        exit_code=1,
    )
    ids = {item.test_id for item in two.diagnostics if item.test_id}
    assert ids == {"tests/test_a.py::test_one", "tests/test_a.py::test_two"}


def test_pytest_collection_import_and_unknown_are_not_complete_success() -> None:
    parser = _parser()
    imported = parser.parse(
        (FIXTURE_ROOT / "pytest" / "text-collection-import.txt").read_text(encoding="utf-8"),
        "",
        exit_code=2,
    )
    assert imported.parser_status in {"partial", "complete"}
    assert any(
        "ImportError" in (item.error_type or "") or "missing" in item.message
        for item in imported.diagnostics
    )
    unknown = parser.parse(
        (FIXTURE_ROOT / "pytest" / "text-unknown.txt").read_text(encoding="utf-8"),
        "",
        exit_code=1,
    )
    assert unknown.parser_status in {"partial", "failed"}
    assert unknown.unparsed_bytes > 0
