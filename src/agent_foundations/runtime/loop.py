from pathlib import Path
from time import perf_counter
from typing import cast
from uuid import uuid4

from agent_foundations.context.builder import ContextBuilder
from agent_foundations.domain._freeze import FrozenJSON, to_json_value
from agent_foundations.domain.errors import (
    ContextBudgetExceededError,
    MaxStepsExceededError,
    ProviderError,
    ToolError,
)
from agent_foundations.domain.messages import Message, Role
from agent_foundations.domain.model import ModelProvider, ModelRequest
from agent_foundations.domain.tool import ToolResult
from agent_foundations.runtime.agent import AgentConfig, AgentResult
from agent_foundations.runtime.session import AgentSession, SessionStatus
from agent_foundations.runtime.tool_execution import (
    DirectToolCallExecutor,
    ToolCallExecutor,
    ToolExecutionContext,
)
from agent_foundations.runtime.trace import EventSink, TraceEvent
from agent_foundations.tools.registry import ToolRegistry


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


class AgentLoop:
    def __init__(
        self,
        provider: ModelProvider,
        registry: ToolRegistry,
        context_builder: ContextBuilder,
        event_sink: EventSink,
        config: AgentConfig,
        tool_executor: ToolCallExecutor | None = None,
    ) -> None:
        self._provider = provider
        self._registry = registry
        self._context_builder = context_builder
        self._event_sink = event_sink
        self._config = config
        self._tool_executor = tool_executor or DirectToolCallExecutor()

    async def run(
        self,
        root: Path,
        query: str,
        *,
        history: tuple[Message, ...] = (),
        session_id: str | None = None,
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

        for step in range(1, self._config.max_steps + 1):
            try:
                context = self._context_builder.build(tuple(session.messages))
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
            )
            await self._emit(
                session, step, "model.request.started", "started", "Requesting model",
                payload={
                    "context": [message.model_dump(mode="json") for message in request.messages],
                    "tools": [tool.model_dump(mode="json") for tool in request.tools],
                },
            )
            started = perf_counter()
            try:
                response = await self._provider.complete(request)
            except ProviderError as exc:
                session.status = SessionStatus.FAILED
                await self._emit(
                    session, step, "session.failed", "failed", str(exc),
                    payload={
                        "error": type(exc).__name__,
                        "raw_response": _safe_raw_response(
                            getattr(exc, "raw_response", None)
                        ),
                    },
                )
                raise
            except Exception as exc:
                session.status = SessionStatus.FAILED
                await self._emit(
                    session, step, "session.failed", "failed",
                    "Unexpected provider failure",
                    payload={"error": type(exc).__name__},
                )
                raise
            await self._emit(
                session, step, "model.response.received", "completed", "Model responded",
                duration_ms=(perf_counter() - started) * 1000,
                payload={
                    "content": response.content,
                    "tool_calls": [
                        call.model_dump(mode="json")
                        for call in response.tool_calls
                    ],
                },
            )
            session.messages.append(Message(
                role=Role.ASSISTANT,
                content=response.content,
                tool_calls=response.tool_calls,
            ))
            if not response.tool_calls:
                answer = response.content or ""
                await self._emit(session, step, "agent.final_answer", "completed", answer)
                session.status = SessionStatus.COMPLETED
                await self._emit(
                    session, step, "session.completed", "completed", "Session completed",
                )
                return AgentResult(
                    session_id=session.session_id, answer=answer, steps=step,
                )

            for call in response.tool_calls:
                call_payload = call.model_dump(mode="json")
                await self._emit(
                    session, step, "tool.call.requested", "started", f"Calling {call.name}",
                    payload={
                        "tool_call_id": call.id,
                        "name": call.name,
                        "arguments": call_payload["arguments"],
                    },
                )
                try:
                    tool, normalized = self._registry.validate_call(
                        call.name,
                        call.arguments,
                    )
                    await self._emit(
                        session, step, "tool.call.validated", "completed",
                        f"Validated {call.name}",
                    )
                    execution_context = ToolExecutionContext(
                        session_id=session.session_id,
                        root=session.root,
                        tool_call_id=call.id,
                        tool_name=call.name,
                    )
                    result = await self._tool_executor.execute(
                        tool,
                        normalized,
                        execution_context,
                    )
                except ToolError as exc:
                    result = ToolResult(
                        success=False, content=str(exc), error_code=type(exc).__name__,
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
                    session, step, event_type, "completed" if result.success else "failed",
                    f"{call.name}: {result.error_code or 'ok'}",
                    payload={
                        "tool_call_id": call.id,
                        "name": call.name,
                        "result": result.model_dump(mode="json"),
                    },
                )
                session.messages.append(Message(
                    role=Role.TOOL,
                    name=call.name,
                    tool_call_id=call.id,
                    content=result.model_dump_json(),
                ))

        session.status = SessionStatus.FAILED
        await self._emit(
            session, self._config.max_steps, "agent.loop.stopped", "failed",
            "Maximum steps reached",
        )
        await self._emit(
            session, self._config.max_steps, "session.failed", "failed",
            "Session failed",
        )
        raise MaxStepsExceededError(f"agent exceeded {self._config.max_steps} steps")

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
