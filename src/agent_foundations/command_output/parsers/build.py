from __future__ import annotations

import json
import re

from agent_foundations.command_output.models import Diagnostic, DiagnosticSeverity
from agent_foundations.command_output.parsers.base import (
    ParseOutcome,
    combined_text,
    failed_json,
)

_VITE = re.compile(r"Could not resolve ['\"](?P<mod>[^'\"]+)['\"]")
_PIP = re.compile(r"(?P<pkg>\S+)\s+has requirement")
_PIP_NO = "No broken requirements found"


class BuildOutputParser:
    tool = "build"

    def parse(self, stdout: str, stderr: str, *, exit_code: int | None) -> ParseOutcome:
        text = combined_text(stdout, stderr).strip()
        if text.startswith("{") or text.startswith("["):
            try:
                json.loads(text)
            except json.JSONDecodeError:
                return failed_json(text, reason="truncated or invalid build json")
            return failed_json(text, reason="unknown build json version")
        if _PIP_NO in text:
            if exit_code not in {None, 0}:
                return ParseOutcome(
                    passed=1,
                    failed=0,
                    skipped=0,
                    diagnostics=(),
                    parser_status="partial",
                    unparsed_bytes=1,
                    unparsed_reason="exit_code contradicts pip-check success",
                    recommended_ranges=(),
                )
            return ParseOutcome(
                passed=1,
                failed=0,
                skipped=0,
                diagnostics=(),
                parser_status="complete",
                unparsed_bytes=0,
                unparsed_reason=None,
                recommended_ranges=(),
            )
        diagnostics: list[Diagnostic] = []
        for match in _VITE.finditer(text):
            diagnostics.append(
                Diagnostic(
                    diagnostic_id="pending",
                    severity=DiagnosticSeverity.ERROR,
                    tool=self.tool,
                    error_type="resolve",
                    message=f"Could not resolve '{match.group('mod')}'",
                )
            )
        for _match in _PIP.finditer(text):
            diagnostics.append(
                Diagnostic(
                    diagnostic_id="pending",
                    severity=DiagnosticSeverity.ERROR,
                    tool=self.tool,
                    error_type="dependency",
                    message=text.strip().splitlines()[0][:240],
                )
            )
        if "built in" in text.lower() and not diagnostics:
            return ParseOutcome(
                passed=1,
                failed=0,
                skipped=0,
                diagnostics=(),
                parser_status="complete",
                unparsed_bytes=0,
                unparsed_reason=None,
                recommended_ranges=(),
            )
        if not diagnostics:
            return failed_json(text, reason="unknown build format")
        return ParseOutcome(
            passed=0,
            failed=len(diagnostics),
            skipped=0,
            diagnostics=tuple(diagnostics),
            parser_status="complete",
            unparsed_bytes=0,
            unparsed_reason=None,
            recommended_ranges=(),
        )
