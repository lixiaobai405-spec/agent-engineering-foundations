from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent_foundations.runtime.tool_execution import ToolExecutionContext

from agent_foundations.domain._freeze import FrozenJSON, to_json_value
from agent_foundations.domain.tool import ToolResult
from agent_foundations.durable.models import EffectStatus, SideEffectIntent, SideEffectRecord
from agent_foundations.durable.repository import (
    DurableRepositoryError,
    DurableRunRepository,
    IdempotencyConflictError,
)

__all__ = [
    "EffectResolutionRequiredError",
    "IdempotencyConflictError",
    "SideEffectLedger",
    "compute_idempotency_key",
    "compute_intent_digest",
    "normalize_tool_arguments",
]


Clock = Callable[[], datetime]


class SideEffectError(DurableRepositoryError):
    """Base side-effect ledger error."""


class EffectResolutionRequiredError(SideEffectError):
    """Effect requires manual reconciliation before retry."""


def canonical_json_dumps(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def normalize_tool_arguments(arguments: Mapping[str, Any]) -> dict[str, Any]:
    normalized = to_json_value(FrozenJSON(dict(arguments)))
    if not isinstance(normalized, dict):
        raise ValueError("tool arguments must normalize to a JSON object")
    return normalized


def compute_intent_digest(
    run_id: str,
    tool_call_id: str,
    tool_name: str,
    operation: str,
    resource_key: str,
    arguments: Mapping[str, Any],
) -> str:
    payload = {
        "run_id": run_id,
        "tool_call_id": tool_call_id,
        "tool_name": tool_name,
        "operation": operation,
        "resource_key": resource_key,
        "arguments": normalize_tool_arguments(arguments),
    }
    digest_input = canonical_json_dumps(payload)
    return hashlib.sha256(digest_input.encode("utf-8")).hexdigest()


def compute_idempotency_key(
    run_id: str,
    tool_call_id: str,
    tool_name: str,
    intent_digest: str,
) -> str:
    payload = {
        "run_id": run_id,
        "tool_call_id": tool_call_id,
        "tool_name": tool_name,
        "intent_digest": intent_digest,
    }
    key_input = canonical_json_dumps(payload)
    return hashlib.sha256(key_input.encode("utf-8")).hexdigest()


class SideEffectLedger:
    def __init__(
        self,
        repository: DurableRunRepository,
        *,
        clock: Clock | None = None,
    ) -> None:
        self._repository = repository
        self._clock: Clock = clock or (lambda: datetime.now(UTC))

    async def prepare(
        self,
        intent: SideEffectIntent,
        context: ToolExecutionContext,
        arguments: Mapping[str, Any],
    ) -> SideEffectRecord:
        digest = compute_intent_digest(
            context.session_id,
            context.tool_call_id,
            context.tool_name,
            intent.operation,
            intent.resource_key,
            arguments,
        )
        key = compute_idempotency_key(
            context.session_id,
            context.tool_call_id,
            context.tool_name,
            digest,
        )
        return await self._repository.prepare_side_effect(
            run_id=context.session_id,
            tool_call_id=context.tool_call_id,
            tool_name=context.tool_name,
            intent=intent,
            intent_digest=digest,
            idempotency_key=key,
            checked_at=self._clock().astimezone(UTC),
        )

    async def claim(
        self,
        effect_id: str,
        expected_status: EffectStatus,
        execution_owner_id: str,
    ) -> SideEffectRecord:
        return await self._repository.transition_side_effect(
            effect_id,
            expected_status,
            EffectStatus.EXECUTING,
            execution_owner_id=execution_owner_id,
            checked_at=self._clock().astimezone(UTC),
        )

    async def commit(
        self,
        effect_id: str,
        execution_owner_id: str,
        result: ToolResult,
    ) -> SideEffectRecord:
        return await self._repository.transition_side_effect(
            effect_id,
            EffectStatus.EXECUTING,
            EffectStatus.COMMITTED,
            execution_owner_id=execution_owner_id,
            result=result,
            checked_at=self._clock().astimezone(UTC),
        )

    async def fail(
        self,
        effect_id: str,
        execution_owner_id: str,
        result: ToolResult,
    ) -> SideEffectRecord:
        return await self._repository.transition_side_effect(
            effect_id,
            EffectStatus.EXECUTING,
            EffectStatus.FAILED,
            execution_owner_id=execution_owner_id,
            result=result,
            checked_at=self._clock().astimezone(UTC),
        )

    async def mark_unknown(
        self,
        effect_id: str,
        expected_owner_id: str | None,
        error_code: str,
    ) -> SideEffectRecord:
        return await self._repository.transition_side_effect(
            effect_id,
            EffectStatus.EXECUTING,
            EffectStatus.UNKNOWN,
            expected_owner_id=expected_owner_id,
            error_code=error_code,
            checked_at=self._clock().astimezone(UTC),
        )

    async def get(
        self,
        run_id: str,
        tool_call_id: str,
        tool_name: str,
    ) -> SideEffectRecord | None:
        return await self._repository.get_side_effect(run_id, tool_call_id, tool_name)
