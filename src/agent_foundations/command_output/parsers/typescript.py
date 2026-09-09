from __future__ import annotations

import re

from agent_foundations.command_output.models import Diagnostic, DiagnosticSeverity
from agent_foundations.command_output.parsers.base import (
    ParseOutcome,
    combined_text,
    failed_json,
)

_ERROR = re.compile(
    r"^(?P<file>\S+)\((?P<line>\d+),(?P<col>\d+)\):\s+error\s+"
    r"(?P<code>TS\d+):\s+(?P<message>.*)$",
    re.MULTILINE,
)
_FOUND = re.compile(r"Found (?P<n>\d+) error")
_SUCCESS = re.compile(r"Found 0 errors")


class TypeScriptOutputParser:
    tool = "tsc"

    def parse(self, stdout: str, stderr: str, *, exit_code: int | None) -> ParseOutcome:
        text = combined_text(stdout, stderr)
        diagnostics = []
        for match in _ERROR.finditer(text):
            diagnostics.append(
                Diagnostic(
                    diagnostic_id="pending",
                    severity=DiagnosticSeverity.ERROR,
                    tool=self.tool,
                    file=match.group("file"),
                    line=int(match.group("line")),
                    column=int(match.group("col")),
                    error_code=match.group("code"),
                    message=match.group("message").strip()[:240],
                )
            )
        found = _FOUND.search(text)
        if found is None and _SUCCESS.search(text) is None:
            if not diagnostics:
                return failed_json(text, reason="unknown typescript format")
            return ParseOutcome(
                passed=None,
                failed=len(diagnostics),
                skipped=None,
                diagnostics=tuple(diagnostics),
                parser_status="partial",
                unparsed_bytes=8,
                unparsed_reason="typescript summary missing",
                recommended_ranges=(),
            )
        if _SUCCESS.search(text) is not None:
            error_count = 0
        elif found is not None:
            error_count = int(found.group("n"))
        else:
            error_count = len(diagnostics)
        if exit_code not in {None, 0} and error_count == 0:
            return ParseOutcome(
                passed=1,
                failed=0,
                skipped=0,
                diagnostics=(),
                parser_status="partial",
                unparsed_bytes=1,
                unparsed_reason="exit_code contradicts typescript success summary",
                recommended_ranges=(),
            )
        return ParseOutcome(
            passed=0 if error_count else 1,
            failed=error_count,
            skipped=0,
            diagnostics=tuple(diagnostics),
            parser_status="complete",
            unparsed_bytes=0,
            unparsed_reason=None,
            recommended_ranges=(),
        )
