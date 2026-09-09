from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import ConfigDict, Field, ValidationError

from agent_foundations.command_output.audit import CommandOutputAuditRepository
from agent_foundations.command_output.models import (
    ARTIFACT_ID_PATTERN,
    ParserStatus,
    RetentionStatus,
)
from agent_foundations.command_output.repository import (
    CommandArtifactNotFoundError,
    CommandArtifactRepository,
)
from agent_foundations.command_output.sanitize import sanitize_streams
from agent_foundations.command_output.store import CommandArtifactStore
from agent_foundations.domain._model import ValidatedCopyModel
from agent_foundations.domain.tool import ToolResult

MAX_LINES_PER_READ = 200
DEFAULT_START_LINE_COUNT = 40
MAX_BYTES_PER_READ = 64 * 1024
MAX_LINES_PER_RUN = 1000
MAX_BYTES_PER_RUN = 256 * 1024
MAX_SEARCH_HITS = 50
_FORBIDDEN_SELECTOR_KEYS = frozenset(
    {"path", "byte_offset", "glob", "regex", "sql", "offset", "file"}
)
_SELECTOR_SHAPE_KEYS = frozenset(
    {"diagnostic_id", "stream", "tail_lines", "start_line", "line_count"}
)
_SELECTOR_SHAPE_HINT = (
    "allowed shapes: {diagnostic_id}; {stream, tail_lines}; "
    "{stream, start_line, line_count}"
)
_READABLE = frozenset({RetentionStatus.ACTIVE, RetentionStatus.RETAINED})


class AccessError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class StartLineSelector(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    stream: Literal["stdout", "stderr"]
    start_line: int = Field(ge=1)
    line_count: int = Field(ge=1, le=MAX_LINES_PER_READ)


class AroundDiagnosticSelector(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    diagnostic_id: str = Field(min_length=1, max_length=64)


class TailSelector(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    stream: Literal["stdout", "stderr"]
    tail_lines: int = Field(ge=1, le=MAX_LINES_PER_READ)


class SanitizedOutputPage(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    artifact_id: str
    stream: Literal["stdout", "stderr"]
    start_line: int
    line_count: int
    lines: tuple[str, ...]
    truncated: bool
    parser_warning: str | None
    byte_count: int


class SearchHit(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    stream: Literal["stdout", "stderr"]
    line: int
    text: str


class SanitizedSearchResult(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    artifact_id: str
    query: str
    hits: tuple[SearchHit, ...]
    parser_warning: str | None


def parse_selector(
    payload: dict[str, Any],
) -> StartLineSelector | AroundDiagnosticSelector | TailSelector:
    if not isinstance(payload, dict):
        raise AccessError("SELECTOR_INVALID", "selector must be an object")
    if _FORBIDDEN_SELECTOR_KEYS.intersection(payload):
        raise AccessError(
            "SELECTOR_INVALID",
            "selector must not include path, offset, glob, regex, or SQL; "
            + _SELECTOR_SHAPE_HINT,
        )
    cleaned = {
        key: value
        for key, value in payload.items()
        if key in _SELECTOR_SHAPE_KEYS
    }
    keys = set(cleaned)
    if keys == {"stream", "start_line"}:
        cleaned = {**cleaned, "line_count": DEFAULT_START_LINE_COUNT}
        keys = set(cleaned)
    try:
        if keys == {"diagnostic_id"}:
            return AroundDiagnosticSelector.model_validate(cleaned)
        if keys == {"stream", "tail_lines"}:
            return TailSelector.model_validate(cleaned)
        if keys == {"stream", "start_line", "line_count"}:
            return StartLineSelector.model_validate(cleaned)
    except ValidationError as exc:
        raise AccessError("SELECTOR_INVALID", "selector fields are invalid") from exc
    raise AccessError(
        "SELECTOR_INVALID",
        "selector must match one of " + _SELECTOR_SHAPE_HINT,
    )


class CommandOutputAccessService:
    def __init__(
        self,
        store: CommandArtifactStore,
        repository: CommandArtifactRepository,
    ) -> None:
        self._store = store
        self._repository = repository
        self._audit = CommandOutputAuditRepository(repository._database)
        self._used_lines: dict[str, int] = {}
        self._used_bytes: dict[str, int] = {}

    @staticmethod
    def validate_artifact_id(artifact_id: str) -> str:
        if ARTIFACT_ID_PATTERN.fullmatch(artifact_id) is None:
            raise AccessError("SELECTOR_INVALID", "artifact_id is malformed")
        if ":" in artifact_id or any(ord(ch) < 32 for ch in artifact_id):
            raise AccessError("SELECTOR_INVALID", "artifact_id contains unsafe syntax")
        return artifact_id

    @staticmethod
    def require_reason(reason: str) -> str:
        cleaned = reason.strip()
        if not cleaned:
            raise AccessError("REASON_REQUIRED", "reason is required")
        if len(cleaned) > 240:
            raise AccessError("REASON_REQUIRED", "reason exceeds 240 characters")
        return cleaned

    def read(
        self,
        *,
        current_run_id: str,
        artifact_id: str,
        selector: StartLineSelector | AroundDiagnosticSelector | TailSelector,
        reason: str,
        project_root: Path,
        parser_status: ParserStatus | None = None,
        charge_budget: bool = True,
        audit_decision: str = "allow",
    ) -> SanitizedOutputPage:
        reason = self.require_reason(reason)
        artifact_id = self.validate_artifact_id(artifact_id)
        stdout, stderr, metadata = self._load_sanitized(
            current_run_id,
            artifact_id,
            project_root,
        )
        stream, start, lines = self._slice(selector, stdout, stderr)
        encoded = "\n".join(lines).encode("utf-8")
        if len(encoded) > MAX_BYTES_PER_READ or len(lines) > MAX_LINES_PER_READ:
            raise AccessError("OUTPUT_BUDGET_EXCEEDED", "single read exceeds 200 lines or 64 KiB")
        if charge_budget:
            self._consume_budget(current_run_id, len(lines), len(encoded))
        warning = _parser_warning(parser_status or metadata.parser_status)
        page = SanitizedOutputPage(
            artifact_id=artifact_id,
            stream=stream,
            start_line=start,
            line_count=len(lines),
            lines=lines,
            truncated=False,
            parser_warning=warning,
            byte_count=len(encoded),
        )
        self._audit.record(
            run_id=current_run_id,
            artifact_id=artifact_id,
            selector_json=selector.model_dump_json(),
            reason=reason,
            returned_bytes=page.byte_count,
            returned_lines=page.line_count,
            decision=audit_decision,
        )
        return page

    def search(
        self,
        *,
        current_run_id: str,
        artifact_id: str,
        query: str,
        reason: str,
        project_root: Path,
        parser_status: ParserStatus | None = None,
    ) -> SanitizedSearchResult:
        reason = self.require_reason(reason)
        artifact_id = self.validate_artifact_id(artifact_id)
        needle = query.strip()
        if not needle or any(token in needle for token in ("SELECT ", "*", ".*", "/")):
            raise AccessError("SELECTOR_INVALID", "search query is invalid")
        stdout, stderr, metadata = self._load_sanitized(
            current_run_id,
            artifact_id,
            project_root,
        )
        hits: list[SearchHit] = []
        for stream_name, text in (("stdout", stdout), ("stderr", stderr)):
            stream = cast(Literal["stdout", "stderr"], stream_name)
            for index, line in enumerate(text.split("\n"), start=1):
                if needle in line:
                    hits.append(SearchHit(stream=stream, line=index, text=line[:240]))
                if len(hits) >= MAX_SEARCH_HITS:
                    break
            if len(hits) >= MAX_SEARCH_HITS:
                break
        payload = "\n".join(hit.text for hit in hits).encode("utf-8")
        self._consume_budget(current_run_id, len(hits), len(payload))
        result = SanitizedSearchResult(
            artifact_id=artifact_id,
            query=needle,
            hits=tuple(hits),
            parser_warning=_parser_warning(parser_status or metadata.parser_status),
        )
        self._audit.record(
            run_id=current_run_id,
            artifact_id=artifact_id,
            selector_json=json.dumps({"query": needle}),
            reason=reason,
            returned_bytes=len(payload),
            returned_lines=len(hits),
            decision="allow",
        )
        return result

    def _load_sanitized(
        self,
        current_run_id: str,
        artifact_id: str,
        project_root: Path,
    ) -> tuple[str, str, Any]:
        try:
            metadata = self._repository.fetch_artifact(artifact_id)
        except CommandArtifactNotFoundError as exc:
            raise AccessError("ARTIFACT_NOT_READABLE", "artifact does not exist") from exc
        if str(metadata.run_id) != str(current_run_id):
            raise AccessError("ARTIFACT_SCOPE_DENIED", "artifact is outside the current run")
        if metadata.retention_status not in _READABLE:
            raise AccessError("ARTIFACT_NOT_READABLE", "artifact is not readable")
        directory = self._store.directory_for(artifact_id)
        stdout_text, stderr_text = sanitize_streams(
            stdout=(directory / "stdout").read_bytes(),
            stderr=(directory / "stderr").read_bytes(),
            project_root=project_root,
        )
        return stdout_text, stderr_text, metadata

    def _slice(
        self,
        selector: StartLineSelector | AroundDiagnosticSelector | TailSelector,
        stdout: str,
        stderr: str,
    ) -> tuple[Literal["stdout", "stderr"], int, tuple[str, ...]]:
        if isinstance(selector, StartLineSelector):
            source = stdout if selector.stream == "stdout" else stderr
            lines = source.split("\n")
            start = selector.start_line
            chosen = tuple(lines[start - 1 : start - 1 + selector.line_count])
            return selector.stream, start, chosen
        if isinstance(selector, TailSelector):
            source = stdout if selector.stream == "stdout" else stderr
            lines = source.split("\n")
            chosen = tuple(lines[-selector.tail_lines :])
            start = max(1, len(lines) - len(chosen) + 1)
            return selector.stream, start, chosen
        combined = (("stdout", stdout), ("stderr", stderr))
        for stream, text in combined:
            lines = text.split("\n")
            for index, line in enumerate(lines):
                if selector.diagnostic_id in line:
                    begin = max(0, index - 3)
                    chosen = tuple(lines[begin : begin + 8])
                    if stream in {"stdout", "stderr"}:
                        return cast(Literal["stdout", "stderr"], stream), begin + 1, chosen
        raise AccessError("SELECTOR_INVALID", "diagnostic_id was not found")

    def _consume_budget(self, run_id: str, lines: int, nbytes: int) -> None:
        next_lines = self._used_lines.get(run_id, 0) + lines
        next_bytes = self._used_bytes.get(run_id, 0) + nbytes
        if next_lines > MAX_LINES_PER_RUN or next_bytes > MAX_BYTES_PER_RUN:
            raise AccessError("OUTPUT_BUDGET_EXCEEDED", "run output budget exceeded")
        self._used_lines[run_id] = next_lines
        self._used_bytes[run_id] = next_bytes


class CommandOutputGateway:
    def __init__(
        self,
        store: CommandArtifactStore,
        repository: CommandArtifactRepository,
        trace_path: Path | None = None,
    ) -> None:
        self._service = CommandOutputAccessService(store, repository)
        self._consumed: set[str] = set()
        self._trace_path = trace_path

    async def execute(
        self,
        *,
        current_run_id: str,
        artifact_id: str,
        selector: dict[str, Any],
        reason: str,
    ) -> ToolResult:
        try:
            parsed = parse_selector(selector)
            fingerprint = self._fingerprint(current_run_id, artifact_id, parsed, "read")
            if fingerprint in self._consumed:
                raise AccessError("ARTIFACT_SCOPE_DENIED", "capability already consumed")
            page = self._service.read(
                current_run_id=current_run_id,
                artifact_id=artifact_id,
                selector=parsed,
                reason=reason,
                project_root=Path("."),
            )
            self._consumed.add(fingerprint)
            self._trace(current_run_id, artifact_id, reason, "allow", page.line_count)
            return ToolResult(
                success=True,
                content="command output page ready",
                metadata=page.model_dump(mode="json"),
            )
        except AccessError as exc:
            self._trace(current_run_id, artifact_id, reason, exc.code, 0)
            return ToolResult(success=False, content=str(exc)[:240], error_code=exc.code)

    async def search(
        self,
        *,
        current_run_id: str,
        artifact_id: str,
        query: str,
        reason: str,
    ) -> ToolResult:
        try:
            result = self._service.search(
                current_run_id=current_run_id,
                artifact_id=artifact_id,
                query=query,
                reason=reason,
                project_root=Path("."),
            )
            self._trace(current_run_id, artifact_id, reason, "allow", len(result.hits))
            payload = result.model_dump(mode="json")
            return ToolResult(success=True, content="command output search ready", metadata=payload)
        except AccessError as exc:
            self._trace(current_run_id, artifact_id, reason, exc.code, 0)
            return ToolResult(success=False, content=str(exc)[:240], error_code=exc.code)

    def _fingerprint(
        self,
        run_id: str,
        artifact_id: str,
        selector: StartLineSelector | AroundDiagnosticSelector | TailSelector,
        operation: str,
    ) -> str:
        return f"{run_id}|{artifact_id}|{selector.model_dump_json()}|{operation}"

    def _trace(
        self,
        run_id: str,
        artifact_id: str,
        reason: str,
        decision: str,
        line_count: int,
    ) -> None:
        if self._trace_path is None:
            return
        payload = {
            "run_id": run_id,
            "artifact_id": artifact_id,
            "reason": reason,
            "decision": decision,
            "line_count": line_count,
        }
        self._trace_path.parent.mkdir(parents=True, exist_ok=True)
        with self._trace_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload) + "\n")


def _parser_warning(status: ParserStatus) -> str | None:
    if status is ParserStatus.COMPLETE:
        return None
    return "parser_status is not complete; prefer a precise failing test node id"


@dataclass
class DownloadTicket:
    ticket_id: str
    conversation_id: str
    run_id: str
    artifact_id: str
    expires_at: datetime
    consumed: bool = False


class CommandOutputDownloadTicketStore:
    def __init__(self, *, ttl: timedelta = timedelta(seconds=60)) -> None:
        self._ttl = ttl
        self._tickets: dict[str, DownloadTicket] = {}

    def issue(
        self,
        *,
        conversation_id: str,
        run_id: str,
        artifact_id: str,
        now: datetime | None = None,
    ) -> DownloadTicket:
        issued = now or datetime.now(UTC)
        ticket = DownloadTicket(
            ticket_id=secrets.token_urlsafe(24),
            conversation_id=conversation_id,
            run_id=run_id,
            artifact_id=artifact_id,
            expires_at=issued + self._ttl,
        )
        self._tickets[ticket.ticket_id] = ticket
        return ticket

    def consume(
        self,
        ticket_id: str,
        *,
        conversation_id: str,
        run_id: str,
        artifact_id: str,
        now: datetime | None = None,
    ) -> DownloadTicket:
        ticket = self._tickets.get(ticket_id)
        current = now or datetime.now(UTC)
        if ticket is None:
            raise AccessError("ARTIFACT_SCOPE_DENIED", "download ticket is invalid")
        if ticket.consumed or current >= ticket.expires_at:
            raise AccessError("ARTIFACT_SCOPE_DENIED", "download ticket is not reusable")
        if (
            ticket.conversation_id != conversation_id
            or ticket.run_id != run_id
            or ticket.artifact_id != artifact_id
        ):
            raise AccessError("ARTIFACT_SCOPE_DENIED", "download ticket ownership mismatch")
        ticket.consumed = True
        return ticket


class CommandOutputAccessExecutor:
    def __init__(
        self,
        store: CommandArtifactStore,
        repository: CommandArtifactRepository,
        *,
        profile: Any,
        policy: Any,
        issuer: Any,
        consumer: Any,
        project_root: Path,
        downstream: Any | None = None,
    ) -> None:
        self._service = CommandOutputAccessService(store, repository)
        self._profile = profile
        self._policy = policy
        self._issuer = issuer
        self._consumer = consumer
        self._project_root = project_root
        self._downstream = downstream

    async def execute(
        self,
        tool: Any,
        arguments: dict[str, Any],
        context: Any,
    ) -> ToolResult:
        name = getattr(tool, "name", "")
        if name not in {"read_command_output", "search_command_output"}:
            if self._downstream is None:
                return ToolResult(
                    success=False,
                    content="controlled execution required",
                    error_code="CONTROLLED_EXECUTION_REQUIRED",
                )
            result = await self._downstream.execute(tool, arguments, context)
            if not isinstance(result, ToolResult):
                return ToolResult(
                    success=False,
                    content="controlled execution required",
                    error_code="CONTROLLED_EXECUTION_REQUIRED",
                )
            return result
        try:
            reason = self._service.require_reason(str(arguments.get("reason", "")))
            artifact_id = self._service.validate_artifact_id(str(arguments.get("artifact_id", "")))
            if name == "read_command_output":
                selector_payload = arguments.get("selector")
                if not isinstance(selector_payload, dict):
                    raise AccessError("SELECTOR_INVALID", "selector must be an object")
                parsed = parse_selector(selector_payload)
                operation = "read"
                identifier = f"{artifact_id}:{parsed.model_dump_json()}"[:256]
            else:
                parsed = None
                operation = "search"
                identifier = f"{artifact_id}:search:{arguments.get('query', '')}"[:256]
            from agent_foundations.security.models import (
                PolicyRequest,
                PolicyResource,
                ResourceScope,
            )
            from agent_foundations.tools.command.read_output import READ_COMMAND_OUTPUT_MANIFEST
            from agent_foundations.tools.command.search_output import SEARCH_COMMAND_OUTPUT_MANIFEST

            manifest = (
                READ_COMMAND_OUTPUT_MANIFEST
                if operation == "read"
                else SEARCH_COMMAND_OUTPUT_MANIFEST
            )
            policy_request = PolicyRequest(
                profile_version=self._profile.version,
                run_id=context.session_id,
                tool_call_id=context.tool_call_id,
                tool_name=name,
                manifest=manifest,
                resource=PolicyResource(
                    kind="command_artifact",
                    scope=ResourceScope.PROJECT_INTERNAL,
                    identifier=identifier,
                ),
                operation=operation,
            )
            outcome = self._policy.decide(self._profile, policy_request)
            from agent_foundations.security.models import PolicyDecision

            if outcome.decision is PolicyDecision.DENY:
                return ToolResult(
                    success=False,
                    content=outcome.reason_code,
                    error_code="POLICY_DENIED",
                )
            if outcome.decision is PolicyDecision.ASK:
                return ToolResult(
                    success=False,
                    content="approval is pending",
                    error_code="APPROVAL_REQUIRED",
                )
            issued = await self._issuer.issue(policy_request, outcome, None)
            await self._consumer.consume(issued.capability_id, policy_request)
            if operation == "read":
                if parsed is None:
                    raise AccessError("SELECTOR_INVALID", "selector must be an object")
                page = self._service.read(
                    current_run_id=context.session_id,
                    artifact_id=artifact_id,
                    selector=parsed,
                    reason=reason,
                    project_root=self._project_root,
                )
                payload = page.model_dump(mode="json")
            else:
                result = self._service.search(
                    current_run_id=context.session_id,
                    artifact_id=artifact_id,
                    query=str(arguments.get("query", "")),
                    reason=reason,
                    project_root=self._project_root,
                )
                payload = result.model_dump(mode="json")
            return ToolResult(
                success=True,
                content=json.dumps(
                    {key: value for key, value in payload.items() if key != "lines"},
                    ensure_ascii=False,
                )[:240],
                metadata=payload,
            )
        except AccessError as exc:
            return ToolResult(success=False, content=str(exc)[:240], error_code=exc.code)
