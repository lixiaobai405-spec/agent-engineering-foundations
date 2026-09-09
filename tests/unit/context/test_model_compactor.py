from __future__ import annotations

import importlib
import importlib.util
import json
from typing import Any
from uuid import UUID

import pytest

from agent_foundations.context.budget import ContextBudget
from agent_foundations.domain.messages import Message, Role
from agent_foundations.domain.model import ModelResponse
from agent_foundations.providers.fake import FakeModelProvider

_SYS = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaa01"
_OLD = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaa02"
_NEW = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaa03"


def _load(module_name: str) -> Any:
    spec = importlib.util.find_spec(module_name)
    assert spec is not None, f"missing module {module_name}"
    return importlib.import_module(module_name)


def _message(*, role: Role, content: str, message_id: str) -> Message:
    return Message(role=role, content=content, message_id=message_id)


def _sample(goal: str) -> tuple[Message, ...]:
    return (
        _message(role=Role.SYSTEM, content="sys", message_id=_SYS),
        _message(role=Role.USER, content="old chatter " * 30, message_id=_OLD),
        _message(role=Role.USER, content=f"GOAL: {goal}", message_id=_NEW),
    )


@pytest.mark.asyncio
async def test_model_compactor_accepts_valid_fake_provider_json() -> None:
    compaction = _load("agent_foundations.context.compaction")
    facts_mod = _load("agent_foundations.context.critical_facts")
    model_mod = _load("agent_foundations.context.model_compactor")
    messages = _sample("valid-json")
    facts = facts_mod.extract_critical_facts(messages)
    request = compaction.build_compaction_request(
        messages,
        budget=ContextBudget(max_chars=80),
        critical_facts=facts,
    )
    compactable = compaction.compactable_messages(request.messages)
    source_ids = tuple(
        UUID(message.message_id)
        for message in compactable
        if message.message_id
    )
    record = compaction.CompactionRecord(
        schema_version=1,
        source_message_ids=source_ids,
        source_fingerprint=compaction.messages_source_fingerprint(compactable),
        reason=compaction.CompactionReason.BUDGET,
        summary="GOAL: valid-json\nuser_goal: valid-json",
        critical_facts=facts,
        original_units=100,
        compacted_units=20,
    )
    payload = json.loads(record.model_dump_json())
    provider = FakeModelProvider([ModelResponse(content=json.dumps(payload))])
    adapter = model_mod.ModelCompactor(provider)
    result = await adapter.compact(request)
    assert result.schema_version == 1
    assert "valid-json" in result.summary
    assert provider.requests
    dumped = json.dumps(provider.requests[0].messages[0].model_dump(mode="json"))
    assert "fixture-secret" not in dumped


@pytest.mark.asyncio
async def test_model_compactor_rejects_invalid_json() -> None:
    compaction = _load("agent_foundations.context.compaction")
    facts_mod = _load("agent_foundations.context.critical_facts")
    model_mod = _load("agent_foundations.context.model_compactor")
    request = compaction.build_compaction_request(
        _sample("invalid"),
        budget=ContextBudget(max_chars=80),
        critical_facts=facts_mod.extract_critical_facts(_sample("invalid")),
    )
    provider = FakeModelProvider([ModelResponse(content="not-json")])
    adapter = model_mod.ModelCompactor(provider)
    with pytest.raises(model_mod.InvalidCompactionOutputError):
        await adapter.compact(request)


@pytest.mark.asyncio
async def test_model_compactor_rejects_record_missing_critical_fact() -> None:
    compaction = _load("agent_foundations.context.compaction")
    facts_mod = _load("agent_foundations.context.critical_facts")
    model_mod = _load("agent_foundations.context.model_compactor")
    messages = _sample("must-keep")
    facts = facts_mod.extract_critical_facts(messages)
    request = compaction.build_compaction_request(
        messages,
        budget=ContextBudget(max_chars=80),
        critical_facts=facts,
    )
    compactable = compaction.compactable_messages(request.messages)
    lying = {
        "schema_version": 1,
        "source_message_ids": [message.message_id for message in compactable],
        "source_fingerprint": compaction.messages_source_fingerprint(compactable),
        "reason": "budget",
        "summary": "harmless weather",
        "critical_facts": [json.loads(fact.model_dump_json()) for fact in facts],
        "original_units": 10,
        "compacted_units": 4,
    }
    provider = FakeModelProvider([ModelResponse(content=json.dumps(lying))])
    adapter = model_mod.ModelCompactor(provider)
    with pytest.raises(model_mod.InvalidCompactionOutputError):
        await adapter.compact(request)
