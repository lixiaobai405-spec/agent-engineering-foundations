from __future__ import annotations

import json
import re

from agent_foundations.command_output.models import Diagnostic, DiagnosticSeverity
from agent_foundations.command_output.parsers.base import (
    ParseOutcome,
    combined_text,
    failed_json,
)

_TEXT = re.compile(
    r"^(?P<file>\S+):(?P<line>\d+):(?P<col>\d+):\s+(?P<code>[A-Z]\d+)\s+(?P<message>.*)$",
    re.MULTILINE,
)


class RuffOutputParser:
    tool = "ruff"

    def parse(self, stdout: str, stderr: str, *, exit_code: int | None) -> ParseOutcome:
        text = combined_text(stdout, stderr).strip()
        if text.startswith("["):
            return self._parse_json(text, exit_code)
        return self._parse_text(text, exit_code)

    def _parse_json(self, text: str, exit_code: int | None) -> ParseOutcome:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return failed_json(text, reason="truncated or invalid ruff json")
        if not isinstance(payload, list):
            return failed_json(text, reason="unknown ruff json version")
        diagnostics = tuple(_from_json_item(item, self.tool) for item in payload)
        failed = len(diagnostics)
        if exit_code not in {None, 0} and failed == 0:
            return ParseOutcome(
                passed=0,
                failed=0,
                skipped=0,
                diagnostics=(),
                parser_status="partial",
                unparsed_bytes=len(text.encode("utf-8")),
                unparsed_reason="exit_code contradicts empty ruff json",
                recommended_ranges=(),
            )
        return ParseOutcome(
            passed=0 if failed else 1,
            failed=failed,
            skipped=0,
            diagnostics=diagnostics,
            parser_status="complete",
            unparsed_bytes=0,
            unparsed_reason=None,
            recommended_ranges=(),
        )

    def _parse_text(self, text: str, exit_code: int | None) -> ParseOutcome:
        if "All checks passed" in text:
            if exit_code not in {None, 0}:
                return ParseOutcome(
                    passed=1,
                    failed=0,
                    skipped=0,
                    diagnostics=(),
                    parser_status="partial",
                    unparsed_bytes=1,
                    unparsed_reason="exit_code contradicts ruff success text",
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
        diagnostics = []
        for match in _TEXT.finditer(text):
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
        if not diagnostics:
            return failed_json(text, reason="unknown ruff text format")
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


def _from_json_item(item: object, tool: str) -> Diagnostic:
    if not isinstance(item, dict):
        return Diagnostic(
            diagnostic_id="pending",
            severity=DiagnosticSeverity.ERROR,
            tool=tool,
            message="invalid ruff diagnostic",
        )
    location = item.get("location") if isinstance(item.get("location"), dict) else {}
    return Diagnostic(
        diagnostic_id="pending",
        severity=DiagnosticSeverity.ERROR,
        tool=tool,
        file=str(item.get("filename") or "") or None,
        line=location.get("row") if isinstance(location, dict) else None,
        column=location.get("column") if isinstance(location, dict) else None,
        error_code=str(item["code"]) if item.get("code") else None,
        message=str(item.get("message") or "")[:240],
    )
