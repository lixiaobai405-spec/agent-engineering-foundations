from __future__ import annotations

import json
import re

from agent_foundations.command_output.models import Diagnostic, DiagnosticSeverity
from agent_foundations.command_output.parsers.base import (
    ParseOutcome,
    ParserStatusName,
    combined_text,
    failed_json,
)

_TEXT_SUMMARY = re.compile(
    r"Tests\s+(?:(?P<failed>\d+) failed)?(?:\s*\|\s*)?(?:(?P<passed>\d+) passed)?"
    r"(?:\s*\|\s*)?(?:(?P<skipped>\d+) skipped)?"
)
_FAIL = re.compile(r"FAIL\s+(?P<id>\S+)")


class VitestOutputParser:
    tool = "vitest"

    def parse(self, stdout: str, stderr: str, *, exit_code: int | None) -> ParseOutcome:
        text = combined_text(stdout, stderr).strip()
        if text.startswith("{"):
            return self._parse_json(text, exit_code)
        return self._parse_text(text, exit_code)

    def _parse_json(self, text: str, exit_code: int | None) -> ParseOutcome:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return failed_json(text, reason="truncated or invalid vitest json")
        if not isinstance(payload, dict):
            return failed_json(text, reason="unknown vitest json version")
        diagnostics: list[Diagnostic] = []
        test_results = payload.get("testResults")
        if isinstance(test_results, list):
            for suite in test_results:
                if not isinstance(suite, dict):
                    continue
                assertions = suite.get("assertionResults")
                if not isinstance(assertions, list):
                    continue
                for item in assertions:
                    if not isinstance(item, dict):
                        continue
                    status = str(item.get("status") or "")
                    if status != "failed":
                        continue
                    title = item.get("fullName") or item.get("title") or "unknown"
                    diagnostics.append(
                        Diagnostic(
                            diagnostic_id="pending",
                            severity=DiagnosticSeverity.ERROR,
                            tool=self.tool,
                            test_id=str(title),
                            message=str(item.get("failureMessages") or title)[:240],
                        )
                    )
        failed = payload.get("numFailedTests")
        passed = payload.get("numPassedTests")
        skipped = payload.get("numPendingTests") or payload.get("numTodoTests")
        if not isinstance(failed, int):
            failed = len(diagnostics)
        if not isinstance(passed, int):
            passed = None
        if not isinstance(skipped, int):
            skipped = None
        return ParseOutcome(
            passed=passed,
            failed=failed,
            skipped=skipped,
            diagnostics=tuple(diagnostics),
            parser_status="complete",
            unparsed_bytes=0,
            unparsed_reason=None,
            recommended_ranges=(),
        )

    def _parse_text(self, text: str, exit_code: int | None) -> ParseOutcome:
        diagnostics = []
        for match in _FAIL.finditer(text):
            diagnostics.append(
                Diagnostic(
                    diagnostic_id="pending",
                    severity=DiagnosticSeverity.ERROR,
                    tool=self.tool,
                    test_id=match.group("id"),
                    message=f"FAIL {match.group('id')}",
                )
            )
        summary = _TEXT_SUMMARY.search(text)
        if summary is None:
            status: ParserStatusName = "partial" if diagnostics else "failed"
            return ParseOutcome(
                passed=None,
                failed=len(diagnostics) or None,
                skipped=None,
                diagnostics=tuple(diagnostics),
                parser_status=status,
                unparsed_bytes=len(text.encode("utf-8")) if not diagnostics else 8,
                unparsed_reason="vitest summary missing",
                recommended_ranges=(),
            )
        failed = int(summary.group("failed") or 0)
        passed = int(summary.group("passed") or 0)
        skipped = int(summary.group("skipped") or 0)
        if exit_code in {0} and failed:
            return ParseOutcome(
                passed=passed,
                failed=failed,
                skipped=skipped,
                diagnostics=tuple(diagnostics),
                parser_status="partial",
                unparsed_bytes=1,
                unparsed_reason="exit_code contradicts vitest summary",
                recommended_ranges=(),
            )
        return ParseOutcome(
            passed=passed,
            failed=failed,
            skipped=skipped,
            diagnostics=tuple(diagnostics),
            parser_status="complete",
            unparsed_bytes=0,
            unparsed_reason=None,
            recommended_ranges=(),
        )
