from __future__ import annotations

from enum import StrEnum
from typing import Literal, Protocol, runtime_checkable

from pydantic import ConfigDict, Field, model_validator

from agent_foundations.domain._model import ValidatedCopyModel
from agent_foundations.domain.messages import Message, Role
from agent_foundations.planning.execution import ExecutionFact
from agent_foundations.planning.models import ExecutionPlan


class AgentRunPhase(StrEnum):
    READY_FOR_MODEL = "ready_for_model"
    MODEL_RESPONSE_PERSISTED = "model_response_persisted"
    TOOL_RESULT_PERSISTED = "tool_result_persisted"
    PLAN_PERSISTED = "plan_persisted"
    FINALIZING = "finalizing"


class CheckpointReason(StrEnum):
    MODEL_RESPONSE = "model_response"
    TOOL_RESULT = "tool_result"
    PLAN_UPDATE = "plan_update"
    FINALIZING = "finalizing"
    RETRY_STARTED = "retry_started"


class RunCancelledError(RuntimeError):
    """Cancellation token was set before a provider or tool boundary."""


class AgentRunState(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1]
    messages: tuple[Message, ...]
    next_step: int = Field(ge=1)
    phase: AgentRunPhase = AgentRunPhase.READY_FOR_MODEL
    next_tool_index: int = Field(default=0, ge=0)
    plan_snapshot: ExecutionPlan | None = None
    attempt: int = Field(ge=1)
    last_committed_tool_fact: ExecutionFact | None = None
    final_answer: str | None = None

    @model_validator(mode="after")
    def validate_phase_constraints(self) -> AgentRunState:
        if self.phase == AgentRunPhase.READY_FOR_MODEL and self.next_tool_index != 0:
            raise ValueError("READY_FOR_MODEL requires next_tool_index == 0")
        if self.phase == AgentRunPhase.FINALIZING:
            if self.final_answer is None or not self.final_answer.strip():
                raise ValueError("FINALIZING requires non-empty final_answer")
        if self.phase in {
            AgentRunPhase.MODEL_RESPONSE_PERSISTED,
            AgentRunPhase.TOOL_RESULT_PERSISTED,
            AgentRunPhase.PLAN_PERSISTED,
        }:
            _validate_tool_index_for_messages(self.messages, self.next_tool_index)
        return self

    def to_checkpoint_state(self) -> AgentRunState:
        return self.model_copy()


def _validate_tool_index_for_messages(
    messages: tuple[Message, ...],
    next_tool_index: int,
) -> None:
    assistant = _last_assistant_message(messages)
    if assistant is None:
        raise ValueError("persisted phase requires an assistant message")
    tool_count = len(assistant.tool_calls)
    if next_tool_index > tool_count:
        raise ValueError("next_tool_index exceeds assistant tool_calls length")


def _last_assistant_message(messages: tuple[Message, ...]) -> Message | None:
    for message in reversed(messages):
        if message.role == Role.ASSISTANT:
            return message
    return None


@runtime_checkable
class CheckpointSink(Protocol):
    async def save(
        self,
        state: AgentRunState,
        reason: CheckpointReason,
    ) -> None: ...


@runtime_checkable
class CancellationToken(Protocol):
    async def is_cancelled(self) -> bool: ...
