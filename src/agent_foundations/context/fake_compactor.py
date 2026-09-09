from __future__ import annotations

from uuid import UUID

from agent_foundations.context.compaction import (
    CompactionReason,
    CompactionRecord,
    CompactionRequest,
    compactable_messages,
    messages_source_fingerprint,
)


class FakeCompactor:
    """Deterministic, in-process compactor used by tests and production default."""

    async def compact(self, request: CompactionRequest) -> CompactionRecord:
        compactable = compactable_messages(request.messages)
        facts = tuple(
            sorted(request.critical_facts, key=lambda fact: (fact.kind.value, fact.value))
        )
        lines = [_SUMMARY_HEADER, *[f"{fact.kind.value}: {fact.value}" for fact in facts]]
        summary = "\n".join(lines)
        ids = tuple(
            UUID(message.message_id)
            for message in compactable
            if message.message_id is not None
        )
        original_units = sum(len(message.content or "") for message in compactable)
        return CompactionRecord(
            schema_version=1,
            source_message_ids=ids,
            source_fingerprint=messages_source_fingerprint(compactable),
            reason=request.reason if compactable else CompactionReason.BUDGET,
            summary=summary,
            critical_facts=request.critical_facts,
            original_units=original_units,
            compacted_units=len(summary),
        )


_SUMMARY_HEADER = "[compacted history]"
