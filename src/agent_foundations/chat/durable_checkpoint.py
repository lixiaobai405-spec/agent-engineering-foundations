from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from agent_foundations.durable.repository import (
    CheckpointNotFoundError,
    DurableRunRepository,
)
from agent_foundations.planning.models import ExecutionPlan
from agent_foundations.runtime.state_machine import (
    AgentRunState,
    CheckpointReason,
    CheckpointSink,
)


class ChatRepositoryCheckpointSink:
    """Persist AgentLoop checkpoints through DurableRunRepository without a lease."""

    def __init__(
        self,
        repository: DurableRunRepository,
        run_id: str,
        state_version: int,
    ) -> None:
        self._repository = repository
        self._run_id = run_id
        self._state_version = state_version

    async def save(self, state: AgentRunState, reason: CheckpointReason) -> None:
        await self._repository.save_checkpoint(
            self._run_id,
            self._state_version,
            state,
        )
        self._state_version += 1
        _ = reason


def execution_plan_to_chat_view(plan: ExecutionPlan) -> dict[str, Any]:
    return {
        "plan_id": plan.plan_id,
        "version": plan.version,
        "goal": plan.goal,
        "replan_count": plan.replan_count,
        "max_replans": plan.max_replans,
        "steps": [
            {
                "step_id": step.step_id,
                "status": step.status.value,
                "description": step.description,
            }
            for step in plan.steps
        ],
    }


async def load_latest_conversation_plan(
    repository: DurableRunRepository,
    session_ids: Sequence[str],
    *,
    exclude_session_id: str | None = None,
) -> ExecutionPlan | None:
    for session_id in reversed(list(session_ids)):
        if exclude_session_id is not None and session_id == exclude_session_id:
            continue
        try:
            checkpoint = await repository.load_latest_checkpoint(session_id)
        except CheckpointNotFoundError:
            continue
        snapshot = checkpoint.state.plan_snapshot
        if snapshot is not None:
            return snapshot
    return None


async def load_provider_attempts(
    repository: DurableRunRepository,
    run_id: str,
) -> dict[str, int]:
    try:
        checkpoint = await repository.load_latest_checkpoint(run_id)
    except CheckpointNotFoundError:
        return {}
    return {key: int(value) for key, value in checkpoint.state.provider_attempts.items()}


async def make_chat_checkpoint_sink(
    repository: DurableRunRepository,
    run_id: str,
) -> CheckpointSink:
    run = await repository.get_run(run_id)
    return ChatRepositoryCheckpointSink(repository, run_id, run.state_version)
