from __future__ import annotations

import importlib.util
from typing import Any

from agent_foundations.tools.command.models import CommandCategory


def _require_feedback() -> Any:
    try:
        spec = importlib.util.find_spec("agent_foundations.command_output.feedback")
    except ModuleNotFoundError:
        spec = None
    assert spec is not None, "command output feedback is missing"
    from agent_foundations.command_output.feedback import (
        build_command_feedback,
        diagnostic_fingerprint,
        sort_diagnostics,
    )
    from agent_foundations.command_output.models import (
        CommandFeedback,
        Diagnostic,
        DiagnosticSeverity,
        OutputRange,
    )

    return (
        build_command_feedback,
        diagnostic_fingerprint,
        sort_diagnostics,
        CommandFeedback,
        Diagnostic,
        DiagnosticSeverity,
        OutputRange,
    )


def test_command_feedback_contract_and_complete_unparsed_bytes() -> None:
    (
        build_command_feedback,
        _fingerprint,
        _sort,
        CommandFeedback,
        Diagnostic,
        DiagnosticSeverity,
        OutputRange,
    ) = _require_feedback()
    feedback = build_command_feedback(
        command_category=CommandCategory.TEST,
        argv_display=("python", "-m", "pytest", "tests", "-q"),
        cwd=".",
        exit_code=0,
        timed_out=False,
        cancelled=False,
        output_truncated=False,
        passed=1,
        failed=0,
        skipped=0,
        diagnostics=(),
        parser_status="complete",
        unparsed_bytes=0,
        unparsed_reason=None,
        recommended_ranges=(),
        artifact_id="coa_AAAAAAAAAAAAAAAAAAAAAA",
        stdout_bytes=4,
        stderr_bytes=0,
        raw_sha256="a" * 64,
    )
    assert isinstance(feedback, CommandFeedback)
    assert feedback.parser_status == "complete"
    assert feedback.unparsed_bytes == 0
    assert feedback.unparsed_reason is None
    assert feedback.cwd == "."
    assert not str(feedback.cwd).startswith("/")
    assert DiagnosticSeverity.ERROR.value == "error"
    assert OutputRange(stream="stdout", start_line=1, line_count=1, reason="sample")


def test_timeout_cancel_truncated_cannot_be_complete() -> None:
    build_command_feedback, *_rest = _require_feedback()
    for flag in ("timed_out", "cancelled", "output_truncated"):
        kwargs = {
            "command_category": CommandCategory.TEST,
            "argv_display": ("python", "-m", "pytest", "tests"),
            "cwd": ".",
            "exit_code": None,
            "timed_out": False,
            "cancelled": False,
            "output_truncated": False,
            "passed": None,
            "failed": None,
            "skipped": None,
            "diagnostics": (),
            "parser_status": "complete",
            "unparsed_bytes": 0,
            "unparsed_reason": None,
            "recommended_ranges": (),
            "artifact_id": "coa_AAAAAAAAAAAAAAAAAAAAAA",
            "stdout_bytes": 1,
            "stderr_bytes": 0,
            "raw_sha256": "b" * 64,
            flag: True,
        }
        feedback = build_command_feedback(**kwargs)
        assert feedback.parser_status in {"partial", "failed"}
        assert feedback.parser_status != "complete"


def test_fingerprint_is_stable_and_bounded_context_is_redacted() -> None:
    (
        _build,
        diagnostic_fingerprint,
        _sort,
        _Feedback,
        Diagnostic,
        DiagnosticSeverity,
        _Range,
    ) = _require_feedback()
    first = Diagnostic(
        diagnostic_id="pending",
        severity=DiagnosticSeverity.ERROR,
        tool="pytest",
        file="tests/test_ok.py",
        line=3,
        column=None,
        test_id="tests/test_ok.py::test_ok",
        error_type="AssertionError",
        error_code=None,
        message="assert 1 == 2",
        expected="2",
        actual="1",
        context=tuple(f"line-{index}-{'y' * 300}" for index in range(12)),
    )
    left = diagnostic_fingerprint(first)
    right = diagnostic_fingerprint(first)
    assert left == right
    assert len(first.context) <= 8
    assert all(len(line) <= 240 for line in first.context)
    assert all("sk-test_placeholder_not_real" not in line for line in first.context)


def test_duplicate_fingerprint_collapses_and_sort_order_is_fixed() -> None:
    (
        build_command_feedback,
        _fingerprint,
        sort_diagnostics,
        _Feedback,
        Diagnostic,
        DiagnosticSeverity,
        _Range,
    ) = _require_feedback()
    warning = Diagnostic(
        diagnostic_id="w",
        severity=DiagnosticSeverity.WARNING,
        tool="ruff",
        file="src/a.py",
        line=1,
        message="unused",
    )
    env = Diagnostic(
        diagnostic_id="e",
        severity=DiagnosticSeverity.ERROR,
        tool="pytest",
        error_type="ImportError",
        message="No module named missing",
        test_id=None,
    )
    fail = Diagnostic(
        diagnostic_id="f",
        severity=DiagnosticSeverity.ERROR,
        tool="pytest",
        test_id="tests/test_a.py::test_a",
        message="assert False",
    )
    compile_error = Diagnostic(
        diagnostic_id="c",
        severity=DiagnosticSeverity.ERROR,
        tool="pytest",
        error_type="SyntaxError",
        message="invalid syntax",
        file="tests/test_b.py",
        line=1,
    )
    ordered = sort_diagnostics((warning, fail, compile_error, env))
    kinds = [item.error_type or item.test_id or item.message for item in ordered]
    assert kinds[0] == "No module named missing" or ordered[0].error_type == "ImportError"
    assert ordered[-1].severity is DiagnosticSeverity.WARNING
    duplicate = fail.model_copy(update={"context": ("stack-again",)})
    feedback = build_command_feedback(
        command_category=CommandCategory.TEST,
        argv_display=("python", "-m", "pytest", "tests"),
        cwd=".",
        exit_code=1,
        timed_out=False,
        cancelled=False,
        output_truncated=False,
        passed=0,
        failed=1,
        skipped=0,
        diagnostics=(fail, duplicate),
        parser_status="complete",
        unparsed_bytes=0,
        unparsed_reason=None,
        recommended_ranges=(),
        artifact_id="coa_AAAAAAAAAAAAAAAAAAAAAA",
        stdout_bytes=10,
        stderr_bytes=0,
        raw_sha256="c" * 64,
    )
    assert feedback.repeated_diagnostics >= 1
    assert len(feedback.diagnostics) == 1
    assert feedback.diagnostics[0].test_id == "tests/test_a.py::test_a"
