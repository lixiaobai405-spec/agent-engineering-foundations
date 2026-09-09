from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from enum import StrEnum
from typing import Any
from uuid import UUID

from agent_foundations.command_output.models import ARTIFACT_ID_PATTERN
from agent_foundations.domain._model import ValidatedCopyModel
from agent_foundations.domain.messages import Message

_LABELS: dict[str, str] = {
    "GOAL": "user_goal",
    "DECISION": "user_decision",
    "PLAN_TODO": "plan_todo",
    "PATH": "path_ref",
    "LINE": "line_ref",
    "TEST": "test_id",
    "RUN_ID": "run_id",
    "EFFECT_ID": "effect_id",
    "ARTIFACT_ID": "artifact_id",
    "DIAGNOSTIC_ID": "diagnostic_id",
    "POLICY": "policy_status",
    "APPROVAL": "approval_status",
    "CAPABILITY": "capability_status",
    "FAILED_GATE": "failed_gate",
    "EXIT": "exit_code",
    "PARSER": "parser_warning",
    "OPEN": "open_item",
    "SAFETY": "safety_constraint",
    "DENIAL": "user_denial",
    "DENY": "user_denial",
}
_LABEL_RE = re.compile(
    rf"^({'|'.join(_LABELS)}):\s*(\S.*)$",
    re.MULTILINE,
)
_MAX_VALUE = 240


class CriticalFactKind(StrEnum):
    USER_GOAL = "user_goal"
    USER_DECISION = "user_decision"
    PLAN_TODO = "plan_todo"
    PATH_REF = "path_ref"
    LINE_REF = "line_ref"
    TEST_ID = "test_id"
    RUN_ID = "run_id"
    EFFECT_ID = "effect_id"
    ARTIFACT_ID = "artifact_id"
    DIAGNOSTIC_ID = "diagnostic_id"
    POLICY_STATUS = "policy_status"
    APPROVAL_STATUS = "approval_status"
    CAPABILITY_STATUS = "capability_status"
    FAILED_GATE = "failed_gate"
    EXIT_CODE = "exit_code"
    PARSER_WARNING = "parser_warning"
    OPEN_ITEM = "open_item"
    SAFETY_CONSTRAINT = "safety_constraint"
    USER_DENIAL = "user_denial"


class CriticalFact(ValidatedCopyModel):
    kind: CriticalFactKind
    value: str
    source_message_ids: tuple[UUID, ...]
    fingerprint: str


def critical_fact_fingerprint(
    kind: CriticalFactKind,
    value: str,
    source_message_ids: tuple[UUID, ...],
) -> str:
    joined_ids = ",".join(sorted(str(item) for item in source_message_ids))
    payload = f"{kind.value}\n{value}\n{joined_ids}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def extract_critical_facts(messages: Sequence[Message]) -> tuple[CriticalFact, ...]:
    collected: list[tuple[CriticalFactKind, str, UUID]] = []
    for message in messages:
        source_id = _parse_message_uuid(message)
        if source_id is None:
            continue
        text = message.content or ""
        for match in _LABEL_RE.finditer(text):
            kind = CriticalFactKind(_LABELS[match.group(1)])
            value = _normalize_value(match.group(2))
            if value is not None:
                collected.append((kind, value, source_id))
        payload = parse_command_feedback_payload(text)
        if payload is None:
            continue
        artifact = _normalize_value(str(payload.get("artifact_id", "")))
        if artifact is not None:
            collected.append((CriticalFactKind.ARTIFACT_ID, artifact, source_id))
        if payload.get("exit_code") is not None:
            exit_value = _normalize_value(str(payload["exit_code"]))
            if exit_value is not None:
                collected.append((CriticalFactKind.EXIT_CODE, exit_value, source_id))
        parser_status = payload.get("parser_status")
        if parser_status in {"partial", "failed"}:
            warning = _normalize_value(str(parser_status))
            if warning is not None:
                collected.append((CriticalFactKind.PARSER_WARNING, warning, source_id))
        diagnostics = payload.get("diagnostics") or []
        if isinstance(diagnostics, list):
            for diagnostic in diagnostics:
                if not isinstance(diagnostic, dict):
                    continue
                diag_id = diagnostic.get("diagnostic_id")
                if isinstance(diag_id, str):
                    normalized = _normalize_value(diag_id)
                    if normalized is not None:
                        collected.append((CriticalFactKind.DIAGNOSTIC_ID, normalized, source_id))
                test_id = diagnostic.get("test_id")
                if isinstance(test_id, str):
                    normalized = _normalize_value(test_id)
                    if normalized is not None:
                        collected.append((CriticalFactKind.TEST_ID, normalized, source_id))
                file_name = diagnostic.get("file")
                line = diagnostic.get("line")
                if isinstance(file_name, str) and isinstance(line, int):
                    line_ref = _normalize_value(f"{file_name}:{line}")
                    if line_ref is not None:
                        collected.append((CriticalFactKind.LINE_REF, line_ref, source_id))
    return _dedupe(collected)


def _dedupe(
    collected: list[tuple[CriticalFactKind, str, UUID]],
) -> tuple[CriticalFact, ...]:
    grouped: dict[tuple[CriticalFactKind, str], list[UUID]] = {}
    for kind, value, source_id in collected:
        key = (kind, value)
        ids = grouped.setdefault(key, [])
        if source_id not in ids:
            ids.append(source_id)
    facts: list[CriticalFact] = []
    for (kind, value), source_ids in grouped.items():
        id_tuple = tuple(source_ids)
        facts.append(
            CriticalFact(
                kind=kind,
                value=value,
                source_message_ids=id_tuple,
                fingerprint=critical_fact_fingerprint(kind, value, id_tuple),
            )
        )
    return tuple(facts)


def _parse_message_uuid(message: Message) -> UUID | None:
    raw = message.message_id
    if raw is None:
        return None
    try:
        return UUID(raw)
    except ValueError:
        return None


def _normalize_value(value: str) -> str | None:
    text = " ".join(value.split())
    if not text or "fixture-secret" in text:
        return None
    if len(text) > _MAX_VALUE:
        text = text[:_MAX_VALUE]
    return text


def parse_command_feedback_payload(content: str) -> dict[str, Any] | None:
    stripped = content.strip()
    if not stripped.startswith("{"):
        return None
    try:
        payload: Any = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    artifact = payload.get("artifact_id")
    if not isinstance(artifact, str) or ARTIFACT_ID_PATTERN.fullmatch(artifact) is None:
        return None
    if "parser_status" not in payload or "exit_code" not in payload:
        return None
    return payload
