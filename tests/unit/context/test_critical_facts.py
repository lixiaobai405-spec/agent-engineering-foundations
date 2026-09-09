from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
from typing import Any
from uuid import UUID

from agent_foundations.domain.messages import Message, Role


def _message(
    *,
    role: Role,
    content: str,
    message_id: str | None = None,
    tool_call_id: str | None = None,
) -> Message:
    payload: dict[str, object] = {"role": role, "content": content}
    if tool_call_id is not None:
        payload["tool_call_id"] = tool_call_id
    if message_id is not None:
        payload["message_id"] = message_id
    try:
        return Message(**payload)  # type: ignore[arg-type]
    except Exception as exc:
        raise AssertionError(
            "Message must accept optional message_id without breaking constructors"
        ) from exc

_CORPUS = Path("tests/fixtures/context/compaction-cases-v1.json")
_REQUIRED_KINDS = (
    "user_goal",
    "user_decision",
    "plan_todo",
    "path_ref",
    "line_ref",
    "test_id",
    "run_id",
    "effect_id",
    "artifact_id",
    "diagnostic_id",
    "policy_status",
    "approval_status",
    "capability_status",
    "failed_gate",
    "exit_code",
    "parser_warning",
    "open_item",
    "safety_constraint",
    "user_denial",
)


def _load(module_name: str) -> Any:
    spec = importlib.util.find_spec(module_name)
    assert spec is not None, f"missing module {module_name}"
    return importlib.import_module(module_name)


def _messages_from_payload(payload: list[dict[str, str]]) -> tuple[Message, ...]:
    return tuple(
        _message(
            role=Role(item["role"]),
            content=item["content"],
            message_id=item["message_id"],
        )
        for item in payload
    )


def test_critical_fact_kind_covers_required_categories() -> None:
    module = _load("agent_foundations.context.critical_facts")
    kind_enum = module.CriticalFactKind
    values = {item.value for item in kind_enum}
    assert set(_REQUIRED_KINDS) <= values


def test_extract_critical_facts_from_labeled_corpus() -> None:
    module = _load("agent_foundations.context.critical_facts")
    corpus = json.loads(_CORPUS.read_text(encoding="utf-8"))
    case = next(item for item in corpus["cases"] if item["id"] == "all-critical-kinds")
    messages = _messages_from_payload(case["messages"])
    facts = module.extract_critical_facts(messages)
    extracted = {(fact.kind.value, fact.value) for fact in facts}
    expected = {(item["kind"], item["value"]) for item in case["expected_facts"]}
    assert expected <= extracted
    for fact in facts:
        assert "\n" not in fact.value
        assert "fixture-secret" not in fact.value
        assert len(fact.value) <= 240
        assert fact.source_message_ids


def test_extract_preserves_cross_turn_decisions() -> None:
    module = _load("agent_foundations.context.critical_facts")
    corpus = json.loads(_CORPUS.read_text(encoding="utf-8"))
    case = next(item for item in corpus["cases"] if item["id"] == "cross-turn-decision")
    facts = module.extract_critical_facts(_messages_from_payload(case["messages"]))
    extracted = {(fact.kind.value, fact.value) for fact in facts}
    expected = {(item["kind"], item["value"]) for item in case["expected_facts"]}
    assert expected <= extracted


def test_critical_fact_fingerprint_is_stable_sha256() -> None:
    module = _load("agent_foundations.context.critical_facts")
    source_id = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa2")
    kind = module.CriticalFactKind.USER_GOAL
    value = "compact-old-history"
    expected = hashlib.sha256(
        f"{kind.value}\n{value}\n{source_id}".encode()
    ).hexdigest()
    fact = module.CriticalFact(
        kind=kind,
        value=value,
        source_message_ids=(source_id,),
        fingerprint=expected,
    )
    assert fact.fingerprint == expected
    rebuilt = module.critical_fact_fingerprint(kind, value, (source_id,))
    assert rebuilt == expected


def test_command_feedback_json_yields_artifact_exit_and_parser_warning() -> None:
    module = _load("agent_foundations.context.critical_facts")
    feedback = (
        '{"command_category":"lint","argv_display":["ruff","check","."],"cwd":".",'
        '"exit_code":1,"timed_out":false,"cancelled":false,"output_truncated":false,'
        '"passed":null,"failed":null,"skipped":null,"diagnostics":[],'
        '"repeated_diagnostics":0,"parser_status":"partial","unparsed_bytes":12,'
        '"unparsed_reason":"truncated","recommended_ranges":[],'
        '"artifact_id":"coa_abcdefghijklmnopqrstuv","stdout_bytes":4,"stderr_bytes":0,'
        '"raw_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}'
    )
    message = _message(
        role=Role.TOOL,
        content=feedback,
        tool_call_id="call-1",
        message_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa9",
    )
    facts = module.extract_critical_facts((message,))
    extracted = {(fact.kind.value, fact.value) for fact in facts}
    assert ("artifact_id", "coa_abcdefghijklmnopqrstuv") in extracted
    assert ("exit_code", "1") in extracted
    assert ("parser_warning", "partial") in extracted
    assert all("unparsed" not in fact.value for fact in facts)
