from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from time import perf_counter
from typing import cast
from uuid import UUID, uuid4, uuid5

from agent_foundations.context.builder import ContextBuilder
from agent_foundations.context.cache import ContextSourceCache
from agent_foundations.context.compaction import (
    ContextCompactor,
    assign_stable_message_ids,
    build_compaction_request,
    compaction_record_accepted,
    drop_raw_artifact_messages,
    merge_compacted_view,
)
from agent_foundations.context.critical_facts import extract_critical_facts
from agent_foundations.context.fake_compactor import FakeCompactor
from agent_foundations.context.relevance import RelevanceScorer, rank_sources
from agent_foundations.context.repo_map import RepoMapBuilder, RepoMapLimits
from agent_foundations.context.sources import ContextSource
from agent_foundations.domain._freeze import FrozenJSON, to_json_value
from agent_foundations.domain.errors import (
    ContextBudgetExceededError,
    InvalidModelResponseError,
    MaxStepsExceededError,
    ProviderError,
    ToolError,
)
from agent_foundations.domain.messages import Message, Role
from agent_foundations.domain.model import ModelProvider, ModelRequest
from agent_foundations.domain.tool import ToolResult
from agent_foundations.planning.controller import PlanController
from agent_foundations.planning.execution import ExecutionFact, PlanningRequiredError
from agent_foundations.planning.models import ExecutionPlan
from agent_foundations.planning.tools import PLANNING_TOOL_NAMES
from agent_foundations.providers.resilient import ResilientModelProvider
from agent_foundations.runtime.agent import AgentConfig, AgentResult, PlanningMode
from agent_foundations.runtime.coding_budget import evaluate_budget
from agent_foundations.runtime.recovery import (
    approval_pending_answer,
    evaluate_tool_call,
    should_request_model,
)
from agent_foundations.runtime.session import AgentSession, SessionStatus
from agent_foundations.runtime.state_machine import (
    AgentRunPhase,
    AgentRunState,
    CancellationToken,
    CheckpointReason,
    CheckpointSink,
    RunCancelledError,
)
from agent_foundations.runtime.tool_execution import (
    DirectToolCallExecutor,
    ToolCallExecutor,
    ToolExecutionContext,
)
from agent_foundations.runtime.trace import EventSink, TraceEvent
from agent_foundations.tools.filesystem.path_policy import PathPolicy
from agent_foundations.tools.patch.execution import (
    sanitize_trace_message,
    sanitize_trace_payload_for_tool,
)
from agent_foundations.tools.registry import ToolRegistry

_COMMAND_OUTPUT_TOOLS = frozenset(
    {"run_command", "read_command_output", "search_command_output"},
)


def _tool_message_content(name: str, result: ToolResult) -> str:
    dumped = result.model_dump(mode="json")
    if name in _COMMAND_OUTPUT_TOOLS:
        payload = dict(dumped.get("metadata") or {})
        if result.error_code:
            payload = {
                "error_code": result.error_code,
                "content": result.content,
                **payload,
            }
        return json.dumps(payload, ensure_ascii=False)
    return result.model_dump_json()


def _tool_trace_result(name: str, result: ToolResult) -> dict[str, object]:
    dumped = result.model_dump(mode="json")
    if name not in _COMMAND_OUTPUT_TOOLS:
        return dumped
    metadata = dumped.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    return {
        "success": dumped["success"],
        "content": dumped["content"],
        "error_code": dumped["error_code"],
        "metadata": metadata,
    }


_ALLOWED_PLAN_EVENTS = frozenset({
    "plan.created",
    "plan.step.updated",
    "plan.replanned",
})

_PERSISTED_TOOL_PHASES = frozenset({
    AgentRunPhase.MODEL_RESPONSE_PERSISTED,
    AgentRunPhase.TOOL_RESULT_PERSISTED,
    AgentRunPhase.PLAN_PERSISTED,
})


def _safe_raw_response(
    raw_response: dict[str, object] | None,
) -> dict[str, object] | None:
    """Convert raw_response to JSON-safe data, or return a safe fallback marker."""
    if raw_response is None:
        return None
    try:
        frozen = FrozenJSON(raw_response)
    except (ValueError, RecursionError):
        return {"omitted": "non_json_safe"}
    return cast(dict[str, object], to_json_value(frozen))


def _validate_history(history: tuple[Message, ...]) -> None:
    for message in history:
        if message.role not in {Role.USER, Role.ASSISTANT}:
            raise ValueError(
                "history must contain only visible USER and ASSISTANT messages",
            )
        if message.name is not None or message.tool_call_id is not None:
            raise ValueError("history must not contain tool protocol fields")
        if message.tool_calls:
            raise ValueError("history must not contain tool calls")
        if message.role is Role.ASSISTANT:
            if message.content is None or not message.content.strip():
                raise ValueError(
                    "history assistant messages must have visible content",
                )


def _last_assistant_message(messages: tuple[Message, ...]) -> Message | None:
    for message in reversed(messages):
        if message.role == Role.ASSISTANT:
            return message
    return None


class AgentLoop:
    def __init__(
        self,
        provider: ModelProvider,
        registry: ToolRegistry,
        context_builder: ContextBuilder,
        event_sink: EventSink,
        config: AgentConfig,
        tool_executor: ToolCallExecutor | None = None,
        plan_controller: PlanController | None = None,
        compactor: ContextCompactor | None = None,
        conversation_repository: object | None = None,
        conversation_id: str | None = None,
    ) -> None:
        self._provider = provider
        self._registry = registry
        self._context_builder = context_builder
        self._event_sink = event_sink
        self._config = config
        self._tool_executor = tool_executor or DirectToolCallExecutor()
        self._plan_controller = plan_controller
        self._context_cache = ContextSourceCache()
        self._compactor: ContextCompactor = compactor or FakeCompactor()
        self._conversation_repository = conversation_repository
        self._conversation_id = conversation_id

    async def run(
        self,
        root: Path,
        query: str,
        *,
        history: tuple[Message, ...] = (),
        session_id: str | None = None,
        checkpoint_sink: CheckpointSink | None = None,
        cancellation_token: CancellationToken | None = None,
        attempt: int = 1,
        provider_attempts: Mapping[str, int] | None = None,
        plan_snapshot: ExecutionPlan | None = None,
    ) -> AgentResult:
        _validate_history(history)
        session = AgentSession(
            root=root,
            session_id=session_id or str(uuid4()),
        )
        await self._emit(session, 0, "session.started", "started", "Session started")
        session.status = SessionStatus.RUNNING
        session.messages.extend([
            Message(role=Role.SYSTEM, content=self._config.system_prompt),
            *history,
            Message(role=Role.USER, content=query),
        ])
        await self._emit(session, 0, "user.message", "completed", query)

        initial_state = AgentRunState(
            schema_version=1,
            messages=tuple(session.messages),
            next_step=1,
            phase=AgentRunPhase.READY_FOR_MODEL,
            next_tool_index=0,
            plan_snapshot=plan_snapshot,
            attempt=attempt,
            last_committed_tool_fact=None,
            final_answer=None,
            provider_attempts=dict(provider_attempts or {}),
        )
        self._restore_plan_snapshot(initial_state.plan_snapshot)
        return await self._drive(
            session,
            initial_state,
            checkpoint_sink,
            cancellation_token,
        )

    async def resume(
        self,
        root: Path,
        session_id: str,
        state: AgentRunState,
        *,
        checkpoint_sink: CheckpointSink,
        cancellation_token: CancellationToken,
    ) -> AgentResult:
        session = AgentSession(root=root, session_id=session_id)
        session.status = SessionStatus.RUNNING
        session.messages.extend(list(state.messages))
        self._restore_plan_snapshot(state.plan_snapshot)
        await self._emit(session, 0, "session.started", "started", "Session resumed")
        return await self._drive(
            session,
            state,
            checkpoint_sink,
            cancellation_token,
        )

    async def _drive(
        self,
        session: AgentSession,
        state: AgentRunState,
        checkpoint_sink: CheckpointSink | None,
        cancellation_token: CancellationToken | None,
    ) -> AgentResult:
        while state.next_step <= self._config.max_steps:
            await self._check_cancelled(cancellation_token, session)

            if state.phase == AgentRunPhase.FINALIZING:
                return await self._complete_finalizing(
                    session,
                    state,
                    checkpoint_sink,
                    cancellation_token,
                )

            if state.phase == AgentRunPhase.READY_FOR_MODEL:
                if not should_request_model(state.messages):
                    state = await self._transition_to_finalizing(
                        session,
                        state,
                        approval_pending_answer(state.messages),
                        state.next_step,
                    )
                    continue
                state = await self._request_model(
                    session,
                    state,
                    checkpoint_sink,
                    cancellation_token,
                )
                if state.phase == AgentRunPhase.FINALIZING:
                    return await self._complete_finalizing(
                        session,
                        state,
                        checkpoint_sink,
                        cancellation_token,
                    )

            while state.phase in _PERSISTED_TOOL_PHASES:
                await self._check_cancelled(cancellation_token, session)
                state = await self._execute_next_tool(
                    session,
                    state,
                    checkpoint_sink,
                    cancellation_token,
                )
                if state.phase == AgentRunPhase.READY_FOR_MODEL:
                    break

        session.status = SessionStatus.FAILED
        await self._emit(
            session,
            self._config.max_steps,
            "agent.loop.stopped",
            "failed",
            "Maximum steps reached",
        )
        await self._emit(
            session,
            self._config.max_steps,
            "session.failed",
            "failed",
            "Session failed",
        )
        raise MaxStepsExceededError(f"agent exceeded {self._config.max_steps} steps")

    async def _request_model(
        self,
        session: AgentSession,
        state: AgentRunState,
        checkpoint_sink: CheckpointSink | None,
        cancellation_token: CancellationToken | None,
    ) -> AgentRunState:
        await self._check_cancelled(cancellation_token, session)
        step = state.next_step
        sources, snapshot = self._repository_context(session)
        await self._emit(
            session,
            step,
            "context.snapshot",
            "completed",
            "Context sources selected",
            payload=snapshot,
        )
        model_messages, compaction_payload = await self._maybe_compact(session)
        if compaction_payload is not None:
            await self._emit(
                session,
                step,
                "context.compaction",
                "completed",
                "Context compacted",
                payload=compaction_payload,
            )
        try:
            policy: PathPolicy | None
            try:
                policy = PathPolicy(session.root)
            except (OSError, ValueError):
                policy = None
            context = self._context_builder.build(
                model_messages,
                sources=sources,
                policy=policy,
            )
        except ContextBudgetExceededError as exc:
            session.status = SessionStatus.FAILED
            await self._emit(
                session,
                step,
                "session.failed",
                "failed",
                "Context budget exceeded",
                payload={"error": type(exc).__name__},
            )
            raise
        except Exception:
            try:
                context = self._context_builder.build(model_messages)
            except ContextBudgetExceededError as exc:
                session.status = SessionStatus.FAILED
                await self._emit(
                    session,
                    step,
                    "session.failed",
                    "failed",
                    "Context budget exceeded",
                    payload={"error": type(exc).__name__},
                )
                raise
        request = ModelRequest(
            messages=context,
            tools=self._registry.definitions(),
            run_id=UUID(session.session_id),
            request_id=uuid5(
                UUID(session.session_id),
                f"model:{state.next_step}:{state.phase.value}",
            ),
        )
        state_box = {"state": state}
        if isinstance(self._provider, ResilientModelProvider):
            assert request.run_id is not None
            self._provider.hydrate_budget(request.run_id, state.provider_attempts)
            self._provider.attach(
                checkpoint_sink=checkpoint_sink,
                state_box=state_box,
                cancellation_token=cancellation_token,
            )

            async def _trace_retry(payload: dict[str, object]) -> None:
                await self._emit(
                    session,
                    step,
                    "provider.retry",
                    "started",
                    "Retrying provider",
                    payload=payload,
                )

            self._provider.bind_retry_tracer(_trace_retry)
        await self._emit(
            session,
            step,
            "model.request.started",
            "started",
            "Requesting model",
            payload={
                "context": [
                    sanitize_trace_message(message.model_dump(mode="json"))
                    for message in request.messages
                ],
                "tools": [tool.model_dump(mode="json") for tool in request.tools],
            },
        )
        started = perf_counter()
        try:
            response = await self._provider.complete(request)
        except InvalidModelResponseError as exc:
            await self._emit(
                session,
                step,
                "model.response.invalid",
                "failed",
                "Invalid model response",
                payload={
                    "error": type(exc).__name__,
                    "raw_response": _safe_raw_response(
                        getattr(exc, "raw_response", None),
                    ),
                },
            )
            session.messages.append(Message(
                role=Role.ASSISTANT,
                content="INVALID_MODEL_RESPONSE: provider returned an invalid response",
                tool_calls=(),
            ))
            invalid_updates: dict[str, object] = {
                "messages": tuple(session.messages),
                "phase": AgentRunPhase.READY_FOR_MODEL,
                "next_tool_index": 0,
                "next_step": state.next_step + 1,
            }
            if isinstance(self._provider, ResilientModelProvider) and request.run_id is not None:
                invalid_updates["provider_attempts"] = self._provider.budget.snapshot(
                    request.run_id,
                ) or dict(state.provider_attempts)
            persisted = state.model_copy(update=invalid_updates)
            await self._save_checkpoint(
                checkpoint_sink,
                persisted,
                CheckpointReason.MODEL_RESPONSE,
            )
            return persisted
        except ProviderError as exc:
            session.status = SessionStatus.FAILED
            await self._emit(
                session,
                step,
                "session.failed",
                "failed",
                str(exc),
                payload={
                    "error": type(exc).__name__,
                    "raw_response": _safe_raw_response(
                        getattr(exc, "raw_response", None),
                    ),
                },
            )
            raise
        except Exception as exc:
            session.status = SessionStatus.FAILED
            await self._emit(
                session,
                step,
                "session.failed",
                "failed",
                "Unexpected provider failure",
                payload={"error": type(exc).__name__},
            )
            raise
        state = state_box["state"]
        await self._emit(
            session,
            step,
            "model.response.received",
            "completed",
            "Model responded",
            duration_ms=(perf_counter() - started) * 1000,
            payload={
                "content": response.content,
                "tool_calls": [
                    sanitize_trace_payload_for_tool(
                        call.name,
                        call.model_dump(mode="json"),
                    )
                    for call in response.tool_calls
                ],
            },
        )
        await self._check_cancelled(cancellation_token, session)
        session.messages.append(Message(
            role=Role.ASSISTANT,
            content=response.content,
            tool_calls=response.tool_calls,
        ))
        persisted_updates: dict[str, object] = {
            "messages": tuple(session.messages),
            "phase": AgentRunPhase.MODEL_RESPONSE_PERSISTED,
            "next_tool_index": 0,
        }
        if isinstance(self._provider, ResilientModelProvider) and request.run_id is not None:
            persisted_updates["provider_attempts"] = self._provider.budget.snapshot(
                request.run_id,
            ) or dict(state.provider_attempts)
        persisted = state.model_copy(update=persisted_updates)
        await self._save_checkpoint(
            checkpoint_sink,
            persisted,
            CheckpointReason.MODEL_RESPONSE,
        )
        if not response.tool_calls:
            answer = response.content or ""
            return await self._transition_to_finalizing(
                session,
                persisted,
                answer,
                step,
            )
        return persisted

    async def _transition_to_finalizing(
        self,
        session: AgentSession,
        state: AgentRunState,
        answer: str,
        step: int,
    ) -> AgentRunState:
        try:
            self._validate_final_answer_allowed()
        except PlanningRequiredError as exc:
            session.status = SessionStatus.FAILED
            await self._emit(
                session,
                step,
                "session.failed",
                "failed",
                str(exc),
                payload={"error": type(exc).__name__},
            )
            raise
        return state.model_copy(
            update={
                "phase": AgentRunPhase.FINALIZING,
                "final_answer": answer,
            },
        )

    async def _execute_next_tool(
        self,
        session: AgentSession,
        state: AgentRunState,
        checkpoint_sink: CheckpointSink | None,
        cancellation_token: CancellationToken | None,
    ) -> AgentRunState:
        await self._check_cancelled(cancellation_token, session)
        step = state.next_step
        assistant = _last_assistant_message(state.messages)
        if assistant is None:
            raise ValueError("persisted phase requires an assistant message")
        tool_calls = assistant.tool_calls
        if state.next_tool_index >= len(tool_calls):
            if (
                len(tool_calls) == 0
                and state.phase == AgentRunPhase.MODEL_RESPONSE_PERSISTED
            ):
                return await self._transition_to_finalizing(
                    session,
                    state,
                    assistant.content or "",
                    step,
                )
            return state.model_copy(
                update={
                    "phase": AgentRunPhase.READY_FOR_MODEL,
                    "next_tool_index": 0,
                    "next_step": state.next_step + 1,
                },
            )

        call = tool_calls[state.next_tool_index]
        call_payload = call.model_dump(mode="json")
        await self._emit(
            session,
            step,
            "tool.call.requested",
            "started",
            f"Calling {call.name}",
            payload=sanitize_trace_payload_for_tool(
                call.name,
                {
                    "tool_call_id": call.id,
                    "name": call.name,
                    "arguments": call_payload["arguments"],
                },
            ),
        )
        if call.argument_parse_error:
            result = ToolResult(
                success=False,
                content=call.argument_parse_error,
                error_code="INVALID_TOOL_JSON",
            )
        else:
            try:
                tool, normalized = self._registry.validate_call(
                    call.name,
                    call.arguments,
                )
                await self._emit(
                    session,
                    step,
                    "tool.call.validated",
                    "completed",
                    f"Validated {call.name}",
                )
                execution_context = ToolExecutionContext(
                    session_id=session.session_id,
                    root=session.root,
                    tool_call_id=call.id,
                    tool_name=call.name,
                )
                decision = evaluate_tool_call(state.messages, call.name, call.arguments)
                if not decision.allowed:
                    result = ToolResult(
                        success=False,
                        content=decision.message or "recovery blocked",
                        error_code=decision.error_code,
                    )
                elif self._config.coding_budget is not None:
                    budget = evaluate_budget(
                        state.messages,
                        call.name,
                        call.arguments,
                        self._config.coding_budget,
                    )
                    if not budget.allowed:
                        result = ToolResult(
                            success=False,
                            content=budget.message or "budget exceeded",
                            error_code=budget.error_code,
                        )
                    else:
                        result = await self._tool_executor.execute(
                            tool,
                            normalized,
                            execution_context,
                        )
                else:
                    result = await self._tool_executor.execute(
                        tool,
                        normalized,
                        execution_context,
                    )
            except ToolError as exc:
                result = ToolResult(
                    success=False,
                    content=str(exc),
                    error_code=type(exc).__name__,
                )
            except Exception as exc:
                session.status = SessionStatus.FAILED
                await self._emit(
                    session,
                    step,
                    "session.failed",
                    "failed",
                    "Unexpected tool failure",
                    payload={"error": type(exc).__name__},
                )
                raise

        event_type = "tool.call.completed" if result.success else "tool.call.failed"
        await self._emit(
            session,
            step,
            event_type,
            "completed" if result.success else "failed",
            f"{call.name}: {result.error_code or 'ok'}",
            payload={
                "tool_call_id": call.id,
                "name": call.name,
                "result": _tool_trace_result(call.name, result),
            },
        )
        if result.success and call.name in PLANNING_TOOL_NAMES:
            await self._emit_plan_event(session, step, result)

        await self._check_cancelled(cancellation_token, session)

        session.messages.append(Message(
            role=Role.TOOL,
            name=call.name,
            tool_call_id=call.id,
            content=_tool_message_content(call.name, result),
        ))
        fact = ExecutionFact(
            session_id=session.session_id,
            tool_call_id=call.id,
            tool_name=call.name,
            success=result.success,
            error_code=result.error_code,
        )
        next_index = state.next_tool_index + 1
        plan_snapshot = state.plan_snapshot
        phase = AgentRunPhase.TOOL_RESULT_PERSISTED
        reason = CheckpointReason.TOOL_RESULT
        if result.success and call.name in PLANNING_TOOL_NAMES:
            plan_event = result.metadata.get("plan_event")
            if plan_event in _ALLOWED_PLAN_EVENTS and self._plan_controller is not None:
                plan_snapshot = self._plan_controller.snapshot()
                phase = AgentRunPhase.PLAN_PERSISTED
                reason = CheckpointReason.PLAN_UPDATE

        persisted = state.model_copy(
            update={
                "messages": tuple(session.messages),
                "next_tool_index": next_index,
                "phase": phase,
                "last_committed_tool_fact": fact,
                "plan_snapshot": plan_snapshot,
            },
        )
        await self._save_checkpoint(checkpoint_sink, persisted, reason)

        if next_index >= len(tool_calls):
            return persisted.model_copy(
                update={
                    "phase": AgentRunPhase.READY_FOR_MODEL,
                    "next_tool_index": 0,
                    "next_step": state.next_step + 1,
                },
            )
        return persisted

    async def _complete_finalizing(
        self,
        session: AgentSession,
        state: AgentRunState,
        checkpoint_sink: CheckpointSink | None,
        cancellation_token: CancellationToken | None,
    ) -> AgentResult:
        await self._check_cancelled(cancellation_token, session)
        answer = state.final_answer or ""
        step = state.next_step
        final_state = state
        if checkpoint_sink is not None and state.phase != AgentRunPhase.FINALIZING:
            final_state = state.model_copy(
                update={"phase": AgentRunPhase.FINALIZING, "final_answer": answer},
            )
            await self._save_checkpoint(
                checkpoint_sink,
                final_state,
                CheckpointReason.FINALIZING,
            )
        elif checkpoint_sink is not None:
            await self._save_checkpoint(
                checkpoint_sink,
                state,
                CheckpointReason.FINALIZING,
            )
        await self._emit(session, step, "agent.final_answer", "completed", answer)
        session.status = SessionStatus.COMPLETED
        await self._emit(
            session,
            step,
            "session.completed",
            "completed",
            "Session completed",
        )
        return AgentResult(
            session_id=session.session_id,
            answer=answer,
            steps=step,
        )

    async def _save_checkpoint(
        self,
        checkpoint_sink: CheckpointSink | None,
        state: AgentRunState,
        reason: CheckpointReason,
    ) -> None:
        if checkpoint_sink is None:
            return
        await checkpoint_sink.save(state, reason)

    async def _check_cancelled(
        self,
        cancellation_token: CancellationToken | None,
        session: AgentSession | None = None,
    ) -> None:
        if cancellation_token is None:
            return
        if await cancellation_token.is_cancelled():
            if session is not None:
                session.status = SessionStatus.CANCELLED
            raise RunCancelledError("run cancelled")

    def _repository_context(
        self,
        session: AgentSession,
    ) -> tuple[tuple[ContextSource, ...], dict[str, object]]:
        empty: dict[str, object] = {
            "sources": [],
            "truncated": False,
            "cache": "none",
        }
        try:
            policy = PathPolicy(session.root)
            mapper = RepoMapBuilder(cache=self._context_cache, policy=policy)
            repo_map = mapper.build(session.root, RepoMapLimits())
            query = ""
            for message in reversed(session.messages):
                if message.role is Role.USER and message.content:
                    query = message.content
                    break
            scorer = RelevanceScorer()
            ranked = rank_sources(query, repo_map.sources)
            entries: list[dict[str, object]] = []
            for source in ranked:
                entries.append(
                    {
                        "source_id": source.source_id,
                        "kind": source.kind,
                        "provenance": source.provenance,
                        "fingerprint": source.fingerprint,
                        "chars": len(source.content),
                        "score": scorer.score(query, source),
                        "decision": "selected",
                        "truncated": repo_map.truncated,
                    }
                )
            return ranked, {
                "sources": entries,
                "truncated": repo_map.truncated,
                "cache": mapper.last_cache_status,
            }
        except ContextBudgetExceededError:
            raise
        except Exception:
            return (), empty

    def _restore_plan_snapshot(
        self,
        plan_snapshot: object | None,
    ) -> None:
        if plan_snapshot is None or self._plan_controller is None:
            return
        if not isinstance(plan_snapshot, ExecutionPlan):
            raise TypeError("plan_snapshot must be ExecutionPlan")
        self._plan_controller.restore(plan_snapshot)

    def _validate_final_answer_allowed(self) -> None:
        if self._config.planning_mode != PlanningMode.REQUIRED:
            return
        controller = self._plan_controller
        if controller is None or not controller.has_plan:
            raise PlanningRequiredError("plan required before final answer")
        if not controller.all_steps_completed():
            raise PlanningRequiredError("incomplete plan")

    async def _emit_plan_event(
        self,
        session: AgentSession,
        step_id: int,
        result: ToolResult,
    ) -> None:
        plan_event = result.metadata.get("plan_event")
        if plan_event not in _ALLOWED_PLAN_EVENTS:
            return
        payload: dict[str, object] = {}
        if self._plan_controller is not None and self._plan_controller.has_plan:
            snapshot = self._plan_controller.snapshot()
            payload.update(
                {
                    "plan_id": snapshot.plan_id,
                    "version": snapshot.version,
                    "goal": snapshot.goal,
                    "replan_count": snapshot.replan_count,
                    "max_replans": snapshot.max_replans,
                    "steps": [
                        {
                            "step_id": step.step_id,
                            "status": step.status.value,
                            "description": step.description,
                        }
                        for step in snapshot.steps
                    ],
                },
            )
        else:
            for key in (
                "plan_id",
                "version",
                "step_id",
                "status",
                "replan_count",
                "reason",
            ):
                if key in result.metadata:
                    payload[key] = result.metadata[key]
        await self._emit(
            session,
            step_id,
            str(plan_event),
            "completed",
            f"Plan event: {plan_event}",
            payload=payload,
        )

    async def _emit(
        self,
        session: AgentSession,
        step_id: int,
        event_type: str,
        status: str,
        summary: str,
        *,
        duration_ms: float | None = None,
        payload: dict[str, object] | None = None,
    ) -> None:
        await self._event_sink.emit(TraceEvent(
            session_id=session.session_id,
            step_id=step_id,
            event_type=event_type,
            status=status,
            duration_ms=duration_ms,
            summary=summary,
            payload=payload or {},
        ))

    async def _maybe_compact(
        self,
        session: AgentSession,
    ) -> tuple[tuple[Message, ...], dict[str, object] | None]:
        originals = tuple(session.messages)
        if not self._context_builder.needs_compaction(originals):
            return drop_raw_artifact_messages(originals), None
        assigned = assign_stable_message_ids(originals)
        if any(message.message_id is None for message in assigned):
            return drop_raw_artifact_messages(originals), None
        session.messages[:] = list(assigned)
        try:
            facts = extract_critical_facts(assigned)
            request = build_compaction_request(
                assigned,
                budget=self._context_builder.budget,
                critical_facts=facts,
                conversation_id=self._conversation_id,
            )
            record = await self._compactor.compact(request)
            if not compaction_record_accepted(record):
                return drop_raw_artifact_messages(assigned), None
            view = merge_compacted_view(assigned, record)
            source_ids = [str(item) for item in record.source_message_ids]
            payload: dict[str, object] = {
                "schema_version": record.schema_version,
                "message_id_range": source_ids[:1] + source_ids[-1:] if source_ids else [],
                "source_fingerprint": record.source_fingerprint,
                "reason": record.reason.value,
                "original_units": record.original_units,
                "compacted_units": record.compacted_units,
                "critical_fact_fingerprints": [
                    fact.fingerprint for fact in record.critical_facts
                ],
            }
            return drop_raw_artifact_messages(view), payload
        except Exception:
            return drop_raw_artifact_messages(assigned), None
