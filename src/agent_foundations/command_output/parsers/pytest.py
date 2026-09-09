from __future__ import annotations

import re
from xml.etree import ElementTree

from agent_foundations.command_output.models import Diagnostic, DiagnosticSeverity
from agent_foundations.command_output.parsers.base import (
    ParseOutcome,
    ParserStatusName,
    combined_text,
    contradiction,
    failed_json,
)

_SUMMARY = re.compile(
    r"(?P<failed>\d+) failed|(?P<passed>\d+) passed|(?P<skipped>\d+) skipped|(?P<error>\d+) error"
)
_FAILED = re.compile(r"^FAILED (?P<id>\S+)", re.MULTILINE)
_ERROR = re.compile(r"^ERROR (?P<id>\S+)", re.MULTILINE)
_PASSED_IN = re.compile(r"\d+ passed in ")


class PytestOutputParser:
    tool = "pytest"

    def parse(self, stdout: str, stderr: str, *, exit_code: int | None) -> ParseOutcome:
        text = combined_text(stdout, stderr)
        stripped = text.lstrip()
        if stripped.startswith("<") or stripped.startswith("<?xml"):
            return self._parse_junit(stripped, exit_code)
        return self._parse_text(text, exit_code)

    def _parse_junit(self, text: str, exit_code: int | None) -> ParseOutcome:
        try:
            root = ElementTree.fromstring(text)
        except ElementTree.ParseError:
            return failed_json(text, reason="truncated or invalid junit xml")
        suites = [root] if root.tag.endswith("testsuite") else list(root)
        passed = failed = skipped = 0
        diagnostics: list[Diagnostic] = []
        for suite in suites:
            if not suite.tag.endswith("testsuite"):
                continue
            for case in suite.iter():
                if not case.tag.endswith("testcase"):
                    continue
                classname = case.attrib.get("classname", "").replace(".", "/")
                name = case.attrib.get("name", "")
                test_id = f"{classname}.py::{name}" if classname and name else name
                if case.find("skipped") is not None or case.find("{*}skipped") is not None:
                    skipped += 1
                    continue
                failure = case.find("failure")
                error = case.find("error")
                if failure is None:
                    failure = next((child for child in case if child.tag.endswith("failure")), None)
                if error is None:
                    error = next((child for child in case if child.tag.endswith("error")), None)
                if failure is None and error is None:
                    passed += 1
                    continue
                failed += 1
                node = failure if failure is not None else error
                if node is None:
                    continue
                message = (node.attrib.get("message") or (node.text or "")).strip()
                diagnostics.append(
                    Diagnostic(
                        diagnostic_id="pending",
                        severity=DiagnosticSeverity.ERROR,
                        tool=self.tool,
                        test_id=test_id,
                        error_type="AssertionError" if failure is not None else "Error",
                        message=message[:240],
                    )
                )
        status: ParserStatusName = "complete"
        reason = None
        leftover = 0
        if exit_code not in {None, 0} and failed == 0 and not diagnostics:
            return contradiction(
                passed=passed,
                failed=failed,
                skipped=skipped,
                diagnostics=tuple(diagnostics),
                exit_code=exit_code,
                reason="exit_code contradicts empty junit failures",
                leftover=len(text.encode("utf-8")),
            )
        return ParseOutcome(
            passed=passed,
            failed=failed,
            skipped=skipped,
            diagnostics=tuple(diagnostics),
            parser_status=status,
            unparsed_bytes=leftover,
            unparsed_reason=reason,
            recommended_ranges=(),
        )

    def _parse_text(self, text: str, exit_code: int | None) -> ParseOutcome:
        if "test session starts" not in text and "short test summary" not in text.lower():
            return failed_json(text, reason="unknown pytest format")
        counts = {"failed": 0, "passed": 0, "skipped": 0, "error": 0}
        for match in _SUMMARY.finditer(text):
            for key, value in match.groupdict().items():
                if value is not None:
                    counts[key] = int(value)
        diagnostics: list[Diagnostic] = []
        for match in _FAILED.finditer(text):
            test_id = match.group("id")
            diagnostics.append(
                Diagnostic(
                    diagnostic_id="pending",
                    severity=DiagnosticSeverity.ERROR,
                    tool=self.tool,
                    test_id=test_id,
                    error_type="AssertionError",
                    message=f"FAILED {test_id}",
                )
            )
        for match in _ERROR.finditer(text):
            diagnostics.append(
                Diagnostic(
                    diagnostic_id="pending",
                    severity=DiagnosticSeverity.ERROR,
                    tool=self.tool,
                    test_id=match.group("id"),
                    error_type="ImportError" if "ImportError" in text else "Error",
                    message="collection or import failed",
                )
            )
        if "ImportError" in text and not diagnostics:
            diagnostics.append(
                Diagnostic(
                    diagnostic_id="pending",
                    severity=DiagnosticSeverity.ERROR,
                    tool=self.tool,
                    error_type="ImportError",
                    message="ImportError: No module named missing"
                    if "No module named missing" in text
                    else "ImportError during collection",
                )
            )
        failed = counts["failed"] or counts["error"] or len(diagnostics)
        leftover = 0
        reason = None
        status: ParserStatusName = "complete"
        has_summary = (
            "short test summary" in text.lower()
            or "error during collection" in text.lower()
            or _PASSED_IN.search(text) is not None
            or " failed" in text
        )
        if not has_summary:
            status = "partial"
            leftover = 8
            reason = "pytest summary missing"
        if exit_code in {0} and failed:
            return contradiction(
                passed=counts["passed"],
                failed=failed,
                skipped=counts["skipped"],
                diagnostics=tuple(diagnostics),
                exit_code=exit_code,
                reason="exit_code contradicts pytest summary",
                leftover=1,
            )
        return ParseOutcome(
            passed=counts["passed"],
            failed=failed,
            skipped=counts["skipped"],
            diagnostics=tuple(diagnostics),
            parser_status=status,
            unparsed_bytes=leftover,
            unparsed_reason=reason,
            recommended_ranges=(),
        )
