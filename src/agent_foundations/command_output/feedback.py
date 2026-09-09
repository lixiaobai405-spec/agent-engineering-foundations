from __future__ import annotations

import hashlib
from typing import Any, Literal

from agent_foundations.command_output.models import (
    CommandFeedback,
    Diagnostic,
    DiagnosticSeverity,
    OutputRange,
)
from agent_foundations.tools.command.models import CommandCategory

_ParserStatus = Literal["complete", "partial", "failed"]


def diagnostic_fingerprint(diagnostic: Diagnostic) -> str:
    payload = "|".join(
        [
            diagnostic.tool,
            diagnostic.file or "",
            str(diagnostic.line or ""),
            diagnostic.test_id or "",
            diagnostic.error_code or "",
            " ".join(diagnostic.message.split()),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def sort_diagnostics(diagnostics: tuple[Diagnostic, ...]) -> tuple[Diagnostic, ...]:
    indexed = list(enumerate(diagnostics))
    indexed.sort(key=lambda item: (_rank(item[1]), item[0]))
    return tuple(item[1] for item in indexed)


def build_command_feedback(
    *,
    command_category: CommandCategory,
    argv_display: tuple[str, ...],
    cwd: str,
    exit_code: int | None,
    timed_out: bool,
    cancelled: bool,
    output_truncated: bool,
    passed: int | None,
    failed: int | None,
    skipped: int | None,
    diagnostics: tuple[Diagnostic, ...],
    parser_status: _ParserStatus,
    unparsed_bytes: int,
    unparsed_reason: str | None,
    recommended_ranges: tuple[OutputRange, ...],
    artifact_id: str,
    stdout_bytes: int,
    stderr_bytes: int,
    raw_sha256: str,
) -> CommandFeedback:
    unique, repeated = _dedupe(diagnostics)
    ordered = sort_diagnostics(unique)
    status = parser_status
    reason = unparsed_reason
    leftover = unparsed_bytes
    if timed_out or cancelled or output_truncated:
        if status == "complete":
            status = "partial"
            leftover = max(leftover, 1)
            reason = reason or "command did not finish cleanly"
    if status == "complete":
        leftover = 0
        reason = None
    return CommandFeedback(
        command_category=command_category,
        argv_display=argv_display,
        cwd=cwd,
        exit_code=exit_code,
        timed_out=timed_out,
        cancelled=cancelled,
        output_truncated=output_truncated,
        passed=passed,
        failed=failed,
        skipped=skipped,
        diagnostics=ordered,
        repeated_diagnostics=repeated,
        parser_status=status,
        unparsed_bytes=leftover,
        unparsed_reason=reason,
        recommended_ranges=recommended_ranges,
        artifact_id=artifact_id,
        stdout_bytes=stdout_bytes,
        stderr_bytes=stderr_bytes,
        raw_sha256=raw_sha256,
    )


def _dedupe(diagnostics: tuple[Diagnostic, ...]) -> tuple[tuple[Diagnostic, ...], int]:
    seen: dict[str, Diagnostic] = {}
    repeated = 0
    for diagnostic in diagnostics:
        key = diagnostic_fingerprint(diagnostic)
        if key in seen:
            repeated += 1
            continue
        seen[key] = diagnostic.model_copy(update={"diagnostic_id": key[:16]})
    return tuple(seen.values()), repeated


def _rank(diagnostic: Diagnostic) -> tuple[int, str]:
    error_type = (diagnostic.error_type or "").lower()
    message = diagnostic.message.lower()
    if diagnostic.severity is DiagnosticSeverity.WARNING:
        return (5, diagnostic.message)
    if diagnostic.severity is DiagnosticSeverity.INFO:
        return (6, diagnostic.message)
    if any(
        token in error_type or token in message
        for token in ("import", "module not found", "modulenotfound", "no module")
    ):
        return (0, diagnostic.message)
    if any(
        token in error_type or token in message
        for token in ("syntax", "collect", "compile", "parse error")
    ):
        return (1, diagnostic.message)
    if diagnostic.test_id is None:
        return (2, diagnostic.message)
    if any(token in message for token in ("teardown", "cascade", "dependency failed")):
        return (4, diagnostic.message)
    return (3, diagnostic.message)


def feedback_as_metadata(feedback: CommandFeedback) -> dict[str, Any]:
    payload = feedback.model_dump(mode="json")
    payload["command_category"] = feedback.command_category.value
    return payload
