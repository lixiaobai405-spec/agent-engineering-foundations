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

_TEXT = re.compile(
    r"^(?P<file>\S+):(?P<line>\d+):(?:(?P<col>\d+):)?\s+"
    r"(?P<severity>error|note|warning):\s+(?P<message>.*?)"
    r"(?:\s+\[(?P<code>[^\]]+)\])?$",
    re.MULTILINE,
)
_FOUND = re.compile(r"Found (?P<n>\d+) error")
_SUCCESS = "Success: no issues found"


class MypyOutputParser:
    tool = "mypy"

    def parse(self, stdout: str, stderr: str, *, exit_code: int | None) -> ParseOutcome:
        text = combined_text(stdout, stderr).strip()
        if text.startswith("["):
            return self._parse_json(text, exit_code)
        return self._parse_text(text, exit_code)

    def _parse_json(self, text: str, exit_code: int | None) -> ParseOutcome:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return failed_json(text, reason="truncated or invalid mypy json")
        if not isinstance(payload, list):
            return failed_json(text, reason="unknown mypy json version")
        diagnostics = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            diagnostics.append(
                Diagnostic(
                    diagnostic_id="pending",
                    severity=DiagnosticSeverity.ERROR,
                    tool=self.tool,
                    file=str(item.get("file") or "") or None,
                    line=item.get("line") if isinstance(item.get("line"), int) else None,
                    column=item.get("column") if isinstance(item.get("column"), int) else None,
                    error_code=str(item["code"]) if item.get("code") else None,
                    message=str(item.get("message") or "")[:240],
                )
            )
        return ParseOutcome(
            passed=0 if diagnostics else 1,
            failed=len(diagnostics),
            skipped=0,
            diagnostics=tuple(diagnostics),
            parser_status="complete",
            unparsed_bytes=0,
            unparsed_reason=None,
            recommended_ranges=(),
        )

    def _parse_text(self, text: str, exit_code: int | None) -> ParseOutcome:
        diagnostics = []
        for match in _TEXT.finditer(text):
            if match.group("severity") == "note":
                continue
            diagnostics.append(
                Diagnostic(
                    diagnostic_id="pending",
                    severity=DiagnosticSeverity.ERROR,
                    tool=self.tool,
                    file=match.group("file"),
                    line=int(match.group("line")),
                    column=int(match.group("col")) if match.group("col") else None,
                    error_code=match.group("code"),
                    message=match.group("message").strip()[:240],
                )
            )
        if _SUCCESS in text:
            if exit_code not in {None, 0}:
                return ParseOutcome(
                    passed=1,
                    failed=0,
                    skipped=0,
                    diagnostics=(),
                    parser_status="partial",
                    unparsed_bytes=1,
                    unparsed_reason="exit_code contradicts mypy success summary",
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
        found = _FOUND.search(text)
        if found is None:
            status: ParserStatusName = "partial" if diagnostics else "failed"
            return ParseOutcome(
                passed=None,
                failed=len(diagnostics) or None,
                skipped=None,
                diagnostics=tuple(diagnostics),
                parser_status=status,
                unparsed_bytes=len(text.encode("utf-8")) if not diagnostics else 8,
                unparsed_reason="mypy summary missing",
                recommended_ranges=(),
            )
        return ParseOutcome(
            passed=0 if diagnostics else 1,
            failed=len(diagnostics),
            skipped=0,
            diagnostics=tuple(diagnostics),
            parser_status="complete",
            unparsed_bytes=0,
            unparsed_reason=None,
            recommended_ranges=(),
        )
