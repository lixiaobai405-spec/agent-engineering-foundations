from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from agent_foundations.context.budget import ContextBudget
from agent_foundations.domain.messages import Message, Role

_CORPUS = Path("tests/fixtures/context/compaction-cases-v1.json")
_ARTIFACT_LEAK = "fixture-secret"
_ARTIFACT_PATH = ".agent-foundations/command-output/coa_abcdefghijklmnopqrstuv/stdout.bin"


def _load(module_name: str) -> Any:
    spec = importlib.util.find_spec(module_name)
    assert spec is not None, f"missing module {module_name}"
    return importlib.import_module(module_name)


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


def _corpus_case(case_id: str) -> dict[str, Any]:
    corpus = json.loads(_CORPUS.read_text(encoding="utf-8"))
    return next(item for item in corpus["cases"] if item["id"] == case_id)


def _corpus_messages(case_id: str) -> tuple[Message, ...]:
    case = _corpus_case(case_id)
    return tuple(
        _message(
            role=Role(item["role"]),
            content=item["content"],
            message_id=item["message_id"],
        )
        for item in case["messages"]
    )


def _history_with_recent_turn() -> tuple[Message, ...]:
    return (
        _message(
            role=Role.SYSTEM,
            content="You are a coding agent.",
            message_id="cccccccc-cccc-4ccc-8ccc-ccccccccccc1",
        ),
        _message(
            role=Role.USER,
            content="old chatter about the weather " * 20,
            message_id="cccccccc-cccc-4ccc-8ccc-ccccccccccc2",
        ),
        _message(
            role=Role.ASSISTANT,
            content="old assistant chatter " * 20,
            message_id="cccccccc-cccc-4ccc-8ccc-ccccccccccc3",
        ),
        _message(
            role=Role.USER,
            content="GOAL: keep-recent-turn",
            message_id="cccccccc-cccc-4ccc-8ccc-ccccccccccc4",
        ),
        _message(
            role=Role.ASSISTANT,
            content="working on it",
            message_id="cccccccc-cccc-4ccc-8ccc-ccccccccccc5",
        ),
        _message(
            role=Role.TOOL,
            content='{"command_category":"lint","argv_display":["ruff"],"cwd":".",'
            '"exit_code":0,"timed_out":false,"cancelled":false,"output_truncated":false,'
            '"passed":null,"failed":null,"skipped":null,"diagnostics":[],'
            '"repeated_diagnostics":0,"parser_status":"complete","unparsed_bytes":0,'
            '"unparsed_reason":null,"recommended_ranges":[],'
            '"artifact_id":"coa_abcdefghijklmnopqrstuv","stdout_bytes":1,"stderr_bytes":0,'
            '"raw_sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}',
            tool_call_id="call-recent",
            message_id="cccccccc-cccc-4ccc-8ccc-ccccccccccc6",
        ),
    )


@pytest.mark.asyncio
async def test_fake_compactor_keeps_all_corpus_facts() -> None:
    facts_mod = _load("agent_foundations.context.critical_facts")
    compaction = _load("agent_foundations.context.compaction")
    fake_mod = _load("agent_foundations.context.fake_compactor")
    case = _corpus_case("all-critical-kinds")
    messages = _corpus_messages(case["id"])
    facts = facts_mod.extract_critical_facts(messages)
    request = compaction.build_compaction_request(
        messages,
        budget=ContextBudget(max_chars=200, compaction_trigger_chars=200),
        critical_facts=facts,
        conversation_id="dddddddd-dddd-4ddd-8ddd-dddddddddddd",
    )
    record = await fake_mod.FakeCompactor().compact(request)
    expected_values = {item["value"] for item in case["expected_facts"]}
    for value in expected_values:
        assert value in record.summary
    assert compaction.compaction_record_accepted(record) is True
    assert record.schema_version == 1
    reasons = {
        compaction.CompactionReason.BUDGET,
        compaction.CompactionReason.REPEATED_TOOL_OUTPUT,
    }
    assert record.reason in reasons
    assert record.compacted_units < record.original_units or record.original_units == 0


@pytest.mark.asyncio
async def test_malicious_summary_omitting_fact_is_rejected() -> None:
    facts_mod = _load("agent_foundations.context.critical_facts")
    compaction = _load("agent_foundations.context.compaction")
    messages = _corpus_messages("all-critical-kinds")
    facts = facts_mod.extract_critical_facts(messages)
    request = compaction.build_compaction_request(
        messages,
        budget=ContextBudget(max_chars=200),
        critical_facts=facts,
    )
    record = await _MaliciousCompactor().compact(request)
    assert compaction.compaction_record_accepted(record) is False
    fallback = compaction.compacted_or_original(messages, record)
    assert fallback == messages
    assert all(message.content != record.summary for message in fallback)


@pytest.mark.asyncio
async def test_tampered_summary_is_rejected() -> None:
    facts_mod = _load("agent_foundations.context.critical_facts")
    compaction = _load("agent_foundations.context.compaction")
    fake_mod = _load("agent_foundations.context.fake_compactor")
    messages = _corpus_messages("cross-turn-decision")
    facts = facts_mod.extract_critical_facts(messages)
    request = compaction.build_compaction_request(
        messages,
        budget=ContextBudget(max_chars=80),
        critical_facts=facts,
    )
    honest = await fake_mod.FakeCompactor().compact(request)
    tampered = honest.model_copy(
        update={
            "summary": honest.summary.replace(
                "use-fake-compactor-default",
                "use-host-full-access",
            ),
        },
    )
    assert compaction.compaction_record_accepted(tampered) is False


def test_recent_turn_and_system_are_incompressible() -> None:
    compaction = _load("agent_foundations.context.compaction")
    messages = _history_with_recent_turn()
    protected = set(compaction.incompressible_message_ids(messages))
    assert messages[0].message_id in protected
    assert messages[3].message_id in protected
    assert messages[4].message_id in protected
    assert messages[5].message_id in protected
    assert messages[1].message_id not in protected
    assert messages[2].message_id not in protected


def test_should_not_compact_current_turn_only() -> None:
    compaction = _load("agent_foundations.context.compaction")
    messages = (
        _message(
            role=Role.SYSTEM,
            content="sys " * 40,
            message_id="eeeeeeee-eeee-4eee-8eee-eeeeeeeeeee1",
        ),
        _message(
            role=Role.USER,
            content="GOAL: huge-current-turn " * 40,
            message_id="eeeeeeee-eeee-4eee-8eee-eeeeeeeeeee2",
        ),
    )
    budget = ContextBudget(max_chars=20, compaction_trigger_chars=20)
    assert compaction.should_compact(messages, budget) is False


def test_budget_trigger_compacts_old_history() -> None:
    compaction = _load("agent_foundations.context.compaction")
    messages = _history_with_recent_turn()
    budget = ContextBudget(max_chars=80, compaction_trigger_chars=80)
    assert compaction.should_compact(messages, budget) is True
    tiny = ContextBudget(max_chars=10_000, compaction_trigger_chars=10_000)
    assert compaction.should_compact(messages, tiny) is False


def test_source_fingerprint_is_stable() -> None:
    compaction = _load("agent_foundations.context.compaction")
    messages = _corpus_messages("cross-turn-decision")
    compactable = compaction.compactable_messages(messages)
    ids = tuple(UUID(message.message_id) for message in compactable if message.message_id)
    first = compaction.messages_source_fingerprint(compactable)
    second = compaction.messages_source_fingerprint(compactable)
    assert first == second
    assert len(first) == 64
    payload = "\n".join(
        f"{message.message_id}\n{message.role.value}\n{message.content or ''}"
        for message in compactable
    )
    expected = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    assert first == expected
    assert set(ids)


def test_raw_artifact_never_enters_compaction_request() -> None:
    compaction = _load("agent_foundations.context.compaction")
    facts_mod = _load("agent_foundations.context.critical_facts")
    leak = _message(
        role=Role.TOOL,
        content=f"raw bytes at {_ARTIFACT_PATH} secret={_ARTIFACT_LEAK}",
        tool_call_id="call-raw",
        message_id="ffffffff-ffff-4fff-8fff-fffffffffff1",
    )
    safe = _message(
        role=Role.TOOL,
        content='{"command_category":"test","argv_display":["pytest"],"cwd":".",'
        '"exit_code":1,"timed_out":false,"cancelled":false,"output_truncated":false,'
        '"passed":0,"failed":1,"skipped":0,"diagnostics":[],'
        '"repeated_diagnostics":0,"parser_status":"partial","unparsed_bytes":8,'
        '"unparsed_reason":"truncated","recommended_ranges":[],'
        '"artifact_id":"coa_abcdefghijklmnopqrstuv","stdout_bytes":32,"stderr_bytes":0,'
        '"raw_sha256":"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"}',
        tool_call_id="call-fb",
        message_id="ffffffff-ffff-4fff-8fff-fffffffffff2",
    )
    user = _message(
        role=Role.USER,
        content="GOAL: scan-leakage",
        message_id="ffffffff-ffff-4fff-8fff-fffffffffff3",
    )
    messages = (
        _message(
            role=Role.SYSTEM,
            content="sys",
            message_id="ffffffff-ffff-4fff-8fff-fffffffffff0",
        ),
        leak,
        safe,
        user,
    )
    request = compaction.build_compaction_request(
        messages,
        budget=ContextBudget(max_chars=100),
        critical_facts=facts_mod.extract_critical_facts(messages),
    )
    dumped = json.dumps(
        [message.model_dump(mode="json") for message in request.messages],
        ensure_ascii=True,
    )
    assert _ARTIFACT_LEAK not in dumped
    assert _ARTIFACT_PATH not in dumped
    assert "coa_abcdefghijklmnopqrstuv" in dumped


@pytest.mark.asyncio
async def test_compaction_does_not_mutate_original_messages() -> None:
    facts_mod = _load("agent_foundations.context.critical_facts")
    compaction = _load("agent_foundations.context.compaction")
    fake_mod = _load("agent_foundations.context.fake_compactor")
    messages = _history_with_recent_turn()
    original = tuple(message.content for message in messages)
    request = compaction.build_compaction_request(
        messages,
        budget=ContextBudget(max_chars=80),
        critical_facts=facts_mod.extract_critical_facts(messages),
    )
    record = await fake_mod.FakeCompactor().compact(request)
    view = compaction.merge_compacted_view(messages, record)
    assert tuple(message.content for message in messages) == original
    assert any(message.content == record.summary for message in view)
    assert view[-1].content == messages[-1].content
    assert (messages[1].content or "") not in " ".join(
        message.content or "" for message in view
    )


def test_repeated_tool_output_reason_is_available() -> None:
    compaction = _load("agent_foundations.context.compaction")
    assert compaction.CompactionReason.REPEATED_TOOL_OUTPUT.value == "repeated_tool_output"
    assert compaction.CompactionReason.BUDGET.value == "budget"


def test_assign_stable_message_ids_does_not_replace_existing() -> None:
    compaction = _load("agent_foundations.context.compaction")
    existing = _message(
        role=Role.USER,
        content="hello",
        message_id="12345678-1234-4234-8234-1234567890ab",
    )
    missing = _message(role=Role.USER, content="later")
    assigned = compaction.assign_stable_message_ids((existing, missing))
    assert assigned[0].message_id == existing.message_id
    assert assigned[1].message_id
    assert assigned[1].message_id != assigned[0].message_id
    again = compaction.assign_stable_message_ids(assigned)
    assert again[1].message_id == assigned[1].message_id


class _MaliciousCompactor:
    async def compact(self, request: Any) -> Any:
        compaction = _load("agent_foundations.context.compaction")
        compactable = compaction.compactable_messages(request.messages)
        ids = tuple(UUID(message.message_id) for message in compactable if message.message_id)
        return compaction.CompactionRecord(
            schema_version=1,
            source_message_ids=ids,
            source_fingerprint=compaction.messages_source_fingerprint(compactable),
            reason=compaction.CompactionReason.BUDGET,
            summary="harmless weather summary with no facts",
            critical_facts=request.critical_facts,
            original_units=sum(len(message.content or "") for message in compactable),
            compacted_units=len("harmless weather summary with no facts"),
        )
