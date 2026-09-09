from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from enum import StrEnum
from typing import Literal, Protocol, runtime_checkable
from uuid import UUID, uuid4

from pydantic import ConfigDict

from agent_foundations.context.budget import ContextBudget
from agent_foundations.context.critical_facts import CriticalFact, parse_command_feedback_payload
from agent_foundations.domain._model import ValidatedCopyModel
from agent_foundations.domain.messages import Message, Role

_SUMMARY_HEADER = "[compacted history]"
_ARTIFACT_PATH_RE = re.compile(r"command-output|/coa_[A-Za-z0-9_-]{22}/|\.agent-foundations")


class CompactionReason(StrEnum):
    BUDGET = "budget"
    REPEATED_TOOL_OUTPUT = "repeated_tool_output"


class CompactionRecord(ValidatedCopyModel):
    schema_version: Literal[1]
    source_message_ids: tuple[UUID, ...]
    source_fingerprint: str
    reason: CompactionReason
    summary: str
    critical_facts: tuple[CriticalFact, ...]
    original_units: int
    compacted_units: int


class CompactionRequest(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    conversation_id: str | None = None
    messages: tuple[Message, ...]
    budget: ContextBudget
    critical_facts: tuple[CriticalFact, ...]
    protected_message_ids: tuple[str, ...]
    reason: CompactionReason = CompactionReason.BUDGET


@runtime_checkable
class ContextCompactor(Protocol):
    async def compact(self, request: CompactionRequest) -> CompactionRecord: ...


def incompressible_message_ids(messages: Sequence[Message]) -> tuple[str, ...]:
    protected: list[str] = []
    recent_start = _recent_turn_start(messages)
    for index, message in enumerate(messages):
        if message.message_id is None:
            continue
        if message.role is Role.SYSTEM or index >= recent_start:
            protected.append(message.message_id)
    return tuple(protected)


def compactable_messages(messages: Sequence[Message]) -> tuple[Message, ...]:
    protected = set(incompressible_message_ids(messages))
    return tuple(
        message
        for message in messages
        if message.message_id is not None and message.message_id not in protected
    )


def should_compact(messages: Sequence[Message], budget: ContextBudget) -> bool:
    trigger = budget.compaction_trigger_chars or budget.max_chars
    total = sum(len(message.content or "") for message in messages)
    return total > trigger and bool(compactable_messages(messages))


def messages_source_fingerprint(messages: Sequence[Message]) -> str:
    payload = "\n".join(
        f"{message.message_id}\n{message.role.value}\n{message.content or ''}"
        for message in messages
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def assign_stable_message_ids(messages: Sequence[Message]) -> tuple[Message, ...]:
    assigned: list[Message] = []
    for message in messages:
        if message.message_id:
            assigned.append(message)
            continue
        assigned.append(message.model_copy(update={"message_id": str(uuid4())}))
    return tuple(assigned)


def build_compaction_request(
    messages: Sequence[Message],
    *,
    budget: ContextBudget,
    critical_facts: tuple[CriticalFact, ...],
    conversation_id: str | None = None,
) -> CompactionRequest:
    safe_messages = tuple(
        message for message in messages if _allowed_in_compactor(message)
    )
    reason = CompactionReason.BUDGET
    compactable = compactable_messages(safe_messages)
    tool_contents = [
        message.content
        for message in compactable
        if message.role is Role.TOOL and message.content
    ]
    if tool_contents and len(tool_contents) != len(set(tool_contents)):
        reason = CompactionReason.REPEATED_TOOL_OUTPUT
    return CompactionRequest(
        conversation_id=conversation_id,
        messages=safe_messages,
        budget=budget,
        critical_facts=critical_facts,
        protected_message_ids=incompressible_message_ids(messages),
        reason=reason,
    )


def compaction_record_accepted(record: CompactionRecord) -> bool:
    summary = record.summary
    for fact in record.critical_facts:
        if fact.value not in summary and not _alias_present(fact, summary):
            return False
    return True


def compacted_or_original(
    messages: Sequence[Message],
    record: CompactionRecord,
) -> tuple[Message, ...]:
    if compaction_record_accepted(record):
        return merge_compacted_view(messages, record)
    return tuple(messages)


def merge_compacted_view(
    messages: Sequence[Message],
    record: CompactionRecord,
) -> tuple[Message, ...]:
    protected = set(incompressible_message_ids(messages))
    system = tuple(message for message in messages if message.role is Role.SYSTEM)
    summary = Message(
        role=Role.SYSTEM,
        content=record.summary,
        message_id=str(uuid4()),
    )
    recent = tuple(
        message
        for message in messages
        if message.role is not Role.SYSTEM and message.message_id in protected
    )
    return system + (summary,) + recent


def _recent_turn_start(messages: Sequence[Message]) -> int:
    for index in range(len(messages) - 1, -1, -1):
        if messages[index].role is Role.USER:
            return index
    return len(messages)


def drop_raw_artifact_messages(messages: Sequence[Message]) -> tuple[Message, ...]:
    return tuple(
        message
        for message in messages
        if not _is_raw_artifact_tool(message)
    )


def _is_raw_artifact_tool(message: Message) -> bool:
    if message.role is not Role.TOOL:
        return False
    content = message.content or ""
    return "fixture-secret" in content or _ARTIFACT_PATH_RE.search(content) is not None


def _allowed_in_compactor(message: Message) -> bool:
    if message.role is not Role.TOOL:
        return True
    content = message.content or ""
    if "fixture-secret" in content or _ARTIFACT_PATH_RE.search(content):
        return False
    if _looks_like_command_feedback(content):
        return True
    return False


def _looks_like_command_feedback(content: str) -> bool:
    return parse_command_feedback_payload(content) is not None


def _alias_present(fact: CriticalFact, summary: str) -> bool:
    aliases = {
        f"{fact.kind.value}={fact.value}",
        f"{fact.kind.value}: {fact.value}",
    }
    return any(alias in summary for alias in aliases)
