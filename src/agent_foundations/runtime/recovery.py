"""Deterministic tool-recovery policy derived from transcript Tool results."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from agent_foundations.domain._freeze import to_json_value
from agent_foundations.domain.messages import Message, Role

RECOVERY_READ_REQUIRED = "RECOVERY_READ_REQUIRED"
RECOVERY_IDENTICAL_PAYLOAD_BLOCKED = "RECOVERY_IDENTICAL_PAYLOAD_BLOCKED"
RECOVERY_RETRY_BLOCKED = "RECOVERY_RETRY_BLOCKED"
RECOVERY_FEEDBACK_READ_REQUIRED = "RECOVERY_FEEDBACK_READ_REQUIRED"

STALE_ERROR_CODES = frozenset({"PATCH_BASELINE_MISMATCH", "PATCH_VALIDATION_ERROR"})
PARSE_ERROR_CODES = frozenset({"PATCH_PARSE_ERROR", "PATCH_INVALID_ARGUMENTS"})
HARD_STOP_ERROR_CODES = frozenset({
    "PATCH_PATH_REJECTED",
    "POLICY_DENIED",
    "APPROVAL_DENIED",
})
AWAITING_APPROVAL_STATUSES = frozenset({"waiting_approval"})
_RECOVERY_ERROR_CODES = frozenset({
    RECOVERY_READ_REQUIRED,
    RECOVERY_IDENTICAL_PAYLOAD_BLOCKED,
    RECOVERY_RETRY_BLOCKED,
    RECOVERY_FEEDBACK_READ_REQUIRED,
})
_COMMAND_OUTPUT_TOOLS = frozenset(
    {"run_command", "read_command_output", "search_command_output"},
)
_PATCH_WRITE_TOOLS = frozenset({"validate_patch", "apply_patch"})
_DIFF_PATH_RE = re.compile(r"^(?:--- |\+\+\+ |diff --git )(?:[ab]/)?(.+)$")


@dataclass(frozen=True)
class RecoveryDecision:
    allowed: bool
    error_code: str | None = None
    message: str = ""


@dataclass
class _Obligation:
    stale_paths: frozenset[str] | None = None
    parse_blocked: set[str] = field(default_factory=set)
    hard_stop: set[tuple[str, str]] = field(default_factory=set)
    feedback_artifact: str | None = None
    feedback_argv: tuple[str, ...] | None = None
    last_error_code: str | None = None


@dataclass(frozen=True)
class _Turn:
    name: str
    arguments: Mapping[str, Any]
    error_code: str | None
    metadata: Mapping[str, Any]
    success: bool


def canonical_payload_digest(tool_name: str, arguments: Mapping[str, Any]) -> str:
    payload = to_json_value(arguments)
    if not isinstance(payload, dict):
        payload = {}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    material = f"{tool_name}{canonical}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def evaluate_tool_call(
    messages: Sequence[Message],
    tool_name: str,
    arguments: Mapping[str, Any],
) -> RecoveryDecision:
    obligation = _derive_obligation(messages)
    digest = canonical_payload_digest(tool_name, arguments)
    if obligation.stale_paths and tool_name in _PATCH_WRITE_TOOLS:
        return RecoveryDecision(
            allowed=False,
            error_code=RECOVERY_READ_REQUIRED,
            message="read the stale path before validate_patch or apply_patch",
        )
    if digest in obligation.parse_blocked:
        return RecoveryDecision(
            allowed=False,
            error_code=RECOVERY_IDENTICAL_PAYLOAD_BLOCKED,
            message="identical parse-failed payload is blocked",
        )
    if (tool_name, digest) in obligation.hard_stop:
        return RecoveryDecision(
            allowed=False,
            error_code=RECOVERY_RETRY_BLOCKED,
            message="identical denied payload is blocked",
        )
    if (
        tool_name == "run_command"
        and obligation.feedback_artifact is not None
        and _argv(arguments) == obligation.feedback_argv
    ):
        return RecoveryDecision(
            allowed=False,
            error_code=RECOVERY_FEEDBACK_READ_REQUIRED,
            message="read command output before retrying the same argv",
        )
    return RecoveryDecision(allowed=True)


def should_request_model(
    messages: Sequence[Message],
    run_status: str | None = None,
) -> bool:
    if run_status is not None and run_status in AWAITING_APPROVAL_STATUSES:
        return False
    obligation = _derive_obligation(messages)
    return obligation.last_error_code != "APPROVAL_REQUIRED"


def approval_pending_answer(messages: Sequence[Message]) -> str:
    for message in reversed(messages):
        if message.role is not Role.TOOL or not message.content:
            continue
        try:
            data = json.loads(message.content)
        except json.JSONDecodeError:
            text = message.content.strip()
            return text or "approval is pending"
        if isinstance(data, dict):
            content = data.get("content")
            if isinstance(content, str) and content.strip():
                return content.strip()
        break
    return "approval is pending"


def _derive_obligation(messages: Sequence[Message]) -> _Obligation:
    obligation = _Obligation()
    for turn in _iter_turns(messages):
        obligation.last_error_code = turn.error_code
        if (
            turn.name == "read_file"
            and turn.success
            and obligation.stale_paths is not None
        ):
            path = turn.arguments.get("path")
            if isinstance(path, str) and path in obligation.stale_paths:
                obligation.stale_paths = None
        if (
            turn.name in {"read_command_output", "search_command_output"}
            and turn.success
            and obligation.feedback_artifact is not None
        ):
            artifact_id = turn.arguments.get("artifact_id")
            if artifact_id == obligation.feedback_artifact:
                obligation.feedback_artifact = None
                obligation.feedback_argv = None
        if turn.error_code in _RECOVERY_ERROR_CODES:
            continue
        if turn.name in _PATCH_WRITE_TOOLS and turn.error_code in STALE_ERROR_CODES:
            obligation.stale_paths = _patch_paths(turn)
        if turn.error_code in PARSE_ERROR_CODES:
            obligation.parse_blocked.add(canonical_payload_digest(turn.name, turn.arguments))
        if turn.error_code in HARD_STOP_ERROR_CODES:
            obligation.hard_stop.add(
                (turn.name, canonical_payload_digest(turn.name, turn.arguments)),
            )
        if turn.name == "run_command":
            if _command_needs_feedback(turn):
                artifact_id = turn.metadata.get("artifact_id")
                argv = _argv(turn.arguments)
                if isinstance(artifact_id, str) and artifact_id and argv is not None:
                    obligation.feedback_artifact = artifact_id
                    obligation.feedback_argv = argv
            else:
                obligation.feedback_artifact = None
                obligation.feedback_argv = None
    return obligation


def _iter_turns(messages: Sequence[Message]) -> list[_Turn]:
    pending: dict[str, tuple[str, Mapping[str, Any]]] = {}
    turns: list[_Turn] = []
    for message in messages:
        if message.role is Role.ASSISTANT:
            for call in message.tool_calls:
                pending[call.id] = (call.name, call.arguments)
            continue
        if message.role is not Role.TOOL or message.tool_call_id is None:
            continue
        recorded = pending.get(message.tool_call_id)
        if recorded is None:
            continue
        name, arguments = recorded
        error_code, metadata, success = _parse_result(name, message.content)
        turns.append(
            _Turn(
                name=name,
                arguments=arguments,
                error_code=error_code,
                metadata=metadata,
                success=success,
            ),
        )
    return turns


def _parse_result(
    name: str,
    content: str | None,
) -> tuple[str | None, Mapping[str, Any], bool]:
    if not content:
        return None, {}, False
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return None, {}, False
    if not isinstance(data, dict):
        return None, {}, False
    if name in _COMMAND_OUTPUT_TOOLS:
        raw_error = data.get("error_code")
        error_code = str(raw_error) if isinstance(raw_error, str) else None
        return error_code, data, error_code is None
    raw_error = data.get("error_code")
    error_code = str(raw_error) if isinstance(raw_error, str) else None
    metadata = data.get("metadata")
    meta = metadata if isinstance(metadata, dict) else {}
    return error_code, meta, bool(data.get("success"))


def _patch_paths(turn: _Turn) -> frozenset[str]:
    paths: set[str] = set()
    _collect_paths(turn.arguments.get("changes"), paths)
    _collect_paths(turn.arguments.get("baselines"), paths)
    diff = turn.arguments.get("diff")
    if isinstance(diff, str):
        for line in diff.splitlines():
            match = _DIFF_PATH_RE.match(line)
            if match is None:
                continue
            raw = match.group(1).split("\t", 1)[0].strip()
            if " b/" in raw:
                raw = raw.split(" b/", 1)[-1]
            if raw and raw != "/dev/null":
                paths.add(raw)
    files = turn.metadata.get("files")
    _collect_paths(files, paths)
    return frozenset(paths)


def _collect_paths(value: object, paths: set[str]) -> None:
    if not isinstance(value, (list, tuple)):
        return
    for item in value:
        if isinstance(item, Mapping):
            path = item.get("path")
            if isinstance(path, str) and path:
                paths.add(path)


def _argv(arguments: Mapping[str, Any]) -> tuple[str, ...] | None:
    gate_id = arguments.get("gate_id")
    if isinstance(gate_id, str) and gate_id:
        parts: list[str] = [gate_id]
        flags = arguments.get("flags")
        if isinstance(flags, (list, tuple)):
            parts.extend(str(item) for item in flags)
        target = arguments.get("target")
        if isinstance(target, str) and target:
            parts.append(target)
        return tuple(parts)
    raw = arguments.get("argv")
    if isinstance(raw, (list, tuple)):
        return tuple(str(item) for item in raw)
    return None


def _command_needs_feedback(turn: _Turn) -> bool:
    artifact_id = turn.metadata.get("artifact_id")
    if not isinstance(artifact_id, str) or not artifact_id:
        return False
    exit_code = turn.metadata.get("exit_code")
    timed_out = bool(turn.metadata.get("timed_out"))
    failed = turn.metadata.get("failed")
    failed_count = failed if isinstance(failed, int) else 0
    if exit_code not in {0, None}:
        return True
    if timed_out:
        return True
    return failed_count > 0
