from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from agent_foundations.command_output.models import Diagnostic, OutputRange

ParserStatusName = Literal["complete", "partial", "failed"]


@dataclass(frozen=True)
class ParseOutcome:
    passed: int | None
    failed: int | None
    skipped: int | None
    diagnostics: tuple[Diagnostic, ...]
    parser_status: ParserStatusName
    unparsed_bytes: int
    unparsed_reason: str | None
    recommended_ranges: tuple[OutputRange, ...]


class OutputParser(Protocol):
    tool: str

    def parse(
        self,
        stdout: str,
        stderr: str,
        *,
        exit_code: int | None,
    ) -> ParseOutcome: ...


def combined_text(stdout: str, stderr: str) -> str:
    if stdout and stderr:
        return stdout + "\n" + stderr
    return stdout or stderr


def failed_json(text: str, *, reason: str) -> ParseOutcome:
    return ParseOutcome(
        passed=None,
        failed=None,
        skipped=None,
        diagnostics=(),
        parser_status="failed",
        unparsed_bytes=len(text.encode("utf-8")),
        unparsed_reason=reason,
        recommended_ranges=(
            OutputRange(stream="stdout", start_line=1, line_count=1, reason=reason),
        ),
    )


def contradiction(
    *,
    passed: int | None,
    failed: int | None,
    skipped: int | None,
    diagnostics: tuple[Diagnostic, ...],
    exit_code: int | None,
    reason: str,
    leftover: int,
) -> ParseOutcome:
    status: ParserStatusName = "partial"
    if leftover and not diagnostics:
        status = "failed"
    return ParseOutcome(
        passed=passed,
        failed=failed,
        skipped=skipped,
        diagnostics=diagnostics,
        parser_status=status,
        unparsed_bytes=max(leftover, 1),
        unparsed_reason=reason,
        recommended_ranges=(
            OutputRange(stream="stdout", start_line=1, line_count=8, reason=reason),
        ),
    )
