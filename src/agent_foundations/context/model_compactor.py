from __future__ import annotations

import json

from agent_foundations.context.compaction import (
    CompactionRecord,
    CompactionRequest,
    compaction_record_accepted,
)
from agent_foundations.domain.messages import Message, Role
from agent_foundations.domain.model import ModelProvider, ModelRequest


class InvalidCompactionOutputError(ValueError):
    """FakeProvider/model JSON did not validate as a safe CompactionRecord."""


class ModelCompactor:
    """Adapter: structured FakeProvider JSON in, validated CompactionRecord out."""

    def __init__(self, provider: ModelProvider) -> None:
        self._provider = provider

    async def compact(self, request: CompactionRequest) -> CompactionRecord:
        payload = {
            "conversation_id": request.conversation_id,
            "protected_message_ids": list(request.protected_message_ids),
            "critical_facts": [
                json.loads(fact.model_dump_json()) for fact in request.critical_facts
            ],
            "message_ids": [message.message_id for message in request.messages],
        }
        response = await self._provider.complete(
            ModelRequest(
                messages=(
                    Message(
                        role=Role.USER,
                        content=json.dumps(payload, ensure_ascii=True),
                    ),
                )
            )
        )
        try:
            record = CompactionRecord.model_validate_json(response.content or "")
        except Exception as exc:
            raise InvalidCompactionOutputError("compaction JSON failed schema validation") from exc
        if not compaction_record_accepted(record):
            raise InvalidCompactionOutputError("compaction JSON omitted or altered critical facts")
        return record
