from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4

from agent_foundations.domain.tool import Tool, ToolResult
from agent_foundations.durable.effects import (
    EffectResolutionRequiredError,
    SideEffectLedger,
)
from agent_foundations.durable.faults import CrashPoint, FaultInjector, InjectedCrash
from agent_foundations.durable.models import EffectStatus, SideEffectIntent, SideEffectRecord


@dataclass(frozen=True)
class ToolExecutionContext:
    session_id: str
    root: Path
    tool_call_id: str
    tool_name: str


@runtime_checkable
class ToolCallExecutor(Protocol):
    async def execute(
        self,
        tool: Tool,
        arguments: dict[str, Any],
        context: ToolExecutionContext,
    ) -> ToolResult: ...


class DirectToolCallExecutor:
    async def execute(
        self,
        tool: Tool,
        arguments: dict[str, Any],
        context: ToolExecutionContext,
    ) -> ToolResult:
        return await tool.execute(arguments)


@runtime_checkable
class SideEffectClassifier(Protocol):
    def describe(
        self,
        tool: Tool,
        arguments: Mapping[str, Any],
        context: ToolExecutionContext,
    ) -> SideEffectIntent | None: ...


@runtime_checkable
class EffectObserver(Protocol):
    def on_effect_event(self, event: Mapping[str, Any]) -> None: ...


class IdempotentToolCallExecutor:
    def __init__(
        self,
        downstream: ToolCallExecutor,
        classifier: SideEffectClassifier,
        ledger: SideEffectLedger,
        *,
        execution_owner_id: str | None = None,
        fault_injector: FaultInjector | None = None,
        observer: EffectObserver | None = None,
    ) -> None:
        self._downstream = downstream
        self._classifier = classifier
        self._ledger = ledger
        self._execution_owner_id = execution_owner_id or str(uuid4())
        self._fault_injector = fault_injector or FaultInjector()
        self._observer = observer
        self._locks: dict[str, asyncio.Lock] = {}

    async def execute(
        self,
        tool: Tool,
        arguments: dict[str, Any],
        context: ToolExecutionContext,
    ) -> ToolResult:
        intent = self._classifier.describe(tool, arguments, context)
        if intent is None:
            return await self._downstream.execute(tool, arguments, context)

        self._fault_injector.hit(CrashPoint.BEFORE_INTENT)
        record = await self._ledger.prepare(intent, context, arguments)
        self._emit_event(record)
        self._fault_injector.hit(CrashPoint.AFTER_INTENT)

        terminal = await self._handle_existing_record(record)
        if terminal is not None:
            return terminal

        lock = self._lock_for(record.idempotency_key)
        async with lock:
            terminal = await self._handle_existing_record(
                await self._ledger.get(
                    context.session_id,
                    context.tool_call_id,
                    context.tool_name,
                ) or record,
            )
            if terminal is not None:
                return terminal

            record = await self._ledger.claim(
                record.effect_id,
                EffectStatus.INTENT_RECORDED,
                self._execution_owner_id,
            )
            self._emit_event(record)
            self._fault_injector.hit(CrashPoint.AFTER_CLAIM)

            try:
                result = await self._downstream.execute(tool, arguments, context)
            except InjectedCrash:
                raise
            except Exception:
                record = await self._ledger.mark_unknown(
                    record.effect_id,
                    self._execution_owner_id,
                    "downstream_exception",
                )
                self._emit_event(record)
                raise

            self._fault_injector.hit(CrashPoint.AFTER_EXECUTE)

            if result.success:
                record = await self._ledger.commit(
                    record.effect_id,
                    self._execution_owner_id,
                    result,
                )
            else:
                record = await self._ledger.fail(
                    record.effect_id,
                    self._execution_owner_id,
                    result,
                )
            self._emit_event(record)
            self._fault_injector.hit(CrashPoint.AFTER_COMMIT)
            return record.result or result

    async def _handle_existing_record(
        self,
        record: SideEffectRecord,
    ) -> ToolResult | None:
        if record.status == EffectStatus.COMMITTED:
            assert record.result is not None
            return record.result
        if record.status == EffectStatus.FAILED:
            if record.result is not None:
                return record.result
            return ToolResult(
                success=False,
                content="failed side effect",
                error_code=record.error_code,
            )
        if record.status in {EffectStatus.UNKNOWN, EffectStatus.ROLLED_BACK}:
            raise EffectResolutionRequiredError(
                f"side effect requires reconciliation: {record.status.value}",
            )
        if record.status == EffectStatus.EXECUTING:
            if record.execution_owner_id != self._execution_owner_id:
                record = await self._ledger.mark_unknown(
                    record.effect_id,
                    record.execution_owner_id,
                    "stale_executor",
                )
                self._emit_event(record)
                raise EffectResolutionRequiredError("stale executing side effect")
        return None

    def _lock_for(self, idempotency_key: str) -> asyncio.Lock:
        lock = self._locks.get(idempotency_key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[idempotency_key] = lock
        return lock

    def _emit_event(self, record: Any) -> None:
        if self._observer is None:
            return
        self._observer.on_effect_event({
            "effect_id": record.effect_id,
            "run_id": record.run_id,
            "tool_call_id": record.tool_call_id,
            "tool_name": record.tool_name,
            "status": record.status.value,
            "intent_summary": record.intent_summary,
            "error_code": record.error_code,
        })
