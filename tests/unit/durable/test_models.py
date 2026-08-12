from __future__ import annotations

import importlib.util
import io
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import pytest
from pydantic import ValidationError

if TYPE_CHECKING:
    from agent_foundations.durable.models import DurableRun, RunCheckpoint, RunState
    from agent_foundations.planning.execution import ExecutionFact
    from agent_foundations.planning.models import ExecutionPlan


RUN_ID = "22222222-2222-4222-8222-222222222222"
CHECKPOINT_ID = "33333333-3333-4333-8333-333333333333"
PROJECT_ROOT = "/tmp/project"
NOW = datetime(2026, 8, 2, 12, 0, 0, tzinfo=UTC)


def _require_durable_models() -> None:
    package_spec = importlib.util.find_spec("agent_foundations.durable")
    assert package_spec is not None, "agent_foundations.durable package must exist"
    module_spec = importlib.util.find_spec("agent_foundations.durable.models")
    assert module_spec is not None, "agent_foundations.durable.models must exist"


def _sample_fact() -> ExecutionFact:
    from agent_foundations.planning.execution import ExecutionFact

    return ExecutionFact(
        session_id=RUN_ID,
        tool_call_id="call-1",
        tool_name="read_file",
        success=True,
    )


def _sample_plan() -> ExecutionPlan:
    from agent_foundations.planning.models import ExecutionPlan, PlanStep

    return ExecutionPlan(
        plan_id="plan-1",
        version=1,
        goal="study runtime",
        steps=(PlanStep(step_id="read", description="Read README"),),
    )


def _sample_run_state(
    *,
    plan_snapshot: ExecutionPlan | None = None,
    last_committed_tool_fact: ExecutionFact | None = None,
) -> RunState:
    from agent_foundations.domain.messages import Message, Role
    from agent_foundations.durable.models import RunState

    return RunState(
        schema_version=1,
        messages=(Message(role=Role.USER, content="hello"),),
        next_step=1,
        plan_snapshot=plan_snapshot,
        attempt=1,
        last_committed_tool_fact=last_committed_tool_fact,
    )


def _sample_durable_run(**updates: Any) -> DurableRun:
    from agent_foundations.durable.models import DurableRun, DurableRunStatus

    return DurableRun(
        run_id=updates.get("run_id", RUN_ID),
        project_root=updates.get("project_root", PROJECT_ROOT),
        status=updates.get("status", DurableRunStatus.CREATED),
        schema_version=updates.get("schema_version", 1),
        state_version=updates.get("state_version", 0),
        attempt=updates.get("attempt", 1),
        created_at=updates.get("created_at", NOW),
        updated_at=updates.get("updated_at", NOW),
    )


def _sample_checkpoint(state: RunState | None = None) -> RunCheckpoint:
    from agent_foundations.durable.models import RunCheckpoint

    return RunCheckpoint(
        checkpoint_id=CHECKPOINT_ID,
        run_id=RUN_ID,
        sequence=1,
        schema_version=1,
        state=state or _sample_run_state(),
        created_at=NOW,
    )


def test_durable_run_status_has_seven_stable_values() -> None:
    _require_durable_models()
    from agent_foundations.durable.models import DurableRunStatus

    assert tuple(DurableRunStatus) == (
        "created",
        "running",
        "paused",
        "waiting_approval",
        "completed",
        "failed",
        "cancelled",
    )


def test_run_state_is_frozen() -> None:
    _require_durable_models()
    state = _sample_run_state()

    with pytest.raises(ValidationError):
        state.next_step = 2


def test_durable_run_is_frozen() -> None:
    _require_durable_models()
    from agent_foundations.durable.models import DurableRunStatus

    run = _sample_durable_run()

    with pytest.raises(ValidationError):
        run.status = DurableRunStatus.RUNNING


def test_run_checkpoint_is_frozen() -> None:
    _require_durable_models()
    checkpoint = _sample_checkpoint()

    with pytest.raises(ValidationError):
        checkpoint.sequence = 2


def test_run_state_model_copy_revalidates_invalid_update() -> None:
    _require_durable_models()
    state = _sample_run_state()

    with pytest.raises(ValidationError, match="next_step"):
        state.model_copy(update={"next_step": 0})


def test_durable_run_rejects_invalid_uuid() -> None:
    _require_durable_models()

    with pytest.raises(ValidationError, match="run_id"):
        _sample_durable_run(run_id="not-a-uuid")


def test_durable_run_rejects_naive_datetime() -> None:
    _require_durable_models()
    naive = datetime(2026, 8, 2, 12, 0, 0)

    with pytest.raises(ValidationError, match="timezone-aware"):
        _sample_durable_run(created_at=naive)


def test_durable_run_rejects_blank_project_root() -> None:
    _require_durable_models()

    with pytest.raises(ValidationError, match="project_root"):
        _sample_durable_run(project_root="   ")


def test_run_state_rejects_next_step_below_one() -> None:
    _require_durable_models()
    from agent_foundations.durable.models import RunState

    with pytest.raises(ValidationError, match="next_step"):
        RunState(
            schema_version=1,
            messages=(),
            next_step=0,
            attempt=1,
        )


def test_run_state_rejects_attempt_below_one() -> None:
    _require_durable_models()
    from agent_foundations.durable.models import RunState

    with pytest.raises(ValidationError, match="attempt"):
        RunState(
            schema_version=1,
            messages=(),
            next_step=1,
            attempt=0,
        )


def test_durable_run_rejects_negative_state_version() -> None:
    _require_durable_models()

    with pytest.raises(ValidationError, match="state_version"):
        _sample_durable_run(state_version=-1)


def test_run_checkpoint_rejects_sequence_below_one() -> None:
    _require_durable_models()
    from agent_foundations.durable.models import RunCheckpoint

    with pytest.raises(ValidationError, match="sequence"):
        RunCheckpoint(
            checkpoint_id=CHECKPOINT_ID,
            run_id=RUN_ID,
            sequence=0,
            schema_version=1,
            state=_sample_run_state(),
            created_at=NOW,
        )


def test_run_state_round_trips_messages_plan_and_fact() -> None:
    _require_durable_models()
    from agent_foundations.domain.messages import Message, Role
    from agent_foundations.domain.tool import ToolCall
    from agent_foundations.durable.models import RunState

    plan = _sample_plan()
    fact = _sample_fact()
    state = RunState(
        schema_version=1,
        messages=(
            Message(
                role=Role.ASSISTANT,
                content=None,
                tool_calls=(
                    ToolCall(id="call-1", name="read_file", arguments={"path": "README.md"}),
                ),
            ),
        ),
        next_step=2,
        plan_snapshot=plan,
        attempt=2,
        last_committed_tool_fact=fact,
    )
    restored = RunState.model_validate_json(state.model_dump_json())
    assert restored == state


def test_nested_tool_arguments_are_recursively_frozen() -> None:
    _require_durable_models()
    from agent_foundations.domain.messages import Message, Role
    from agent_foundations.domain.tool import ToolCall
    from agent_foundations.durable.models import RunState

    state = RunState(
        schema_version=1,
        messages=(
            Message(
                role=Role.ASSISTANT,
                tool_calls=(
                    ToolCall(
                        id="call-1",
                        name="read_file",
                        arguments={"nested": {"path": "README.md"}},
                    ),
                ),
            ),
        ),
        next_step=1,
        attempt=1,
    )
    tool_call = state.messages[0].tool_calls[0]
    with pytest.raises((TypeError, ValueError)):
        tool_call.arguments["nested"] = {"path": "changed"}  # type: ignore[index]


def test_run_state_rejects_schema_version_99() -> None:
    _require_durable_models()
    from agent_foundations.durable.models import RunState

    with pytest.raises(ValidationError, match="schema_version"):
        RunState.model_validate(
            {
                "schema_version": 99,
                "messages": [],
                "next_step": 1,
                "attempt": 1,
            },
        )


def test_durable_run_rejects_schema_version_99() -> None:
    _require_durable_models()

    with pytest.raises(ValidationError, match="schema_version"):
        _sample_durable_run(schema_version=99)


def test_run_checkpoint_rejects_schema_version_99() -> None:
    _require_durable_models()
    from agent_foundations.durable.models import RunCheckpoint

    with pytest.raises(ValidationError, match="schema_version"):
        RunCheckpoint(
            checkpoint_id=CHECKPOINT_ID,
            run_id=RUN_ID,
            sequence=1,
            schema_version=99,  # type: ignore[arg-type]
            state=_sample_run_state(),
            created_at=NOW,
        )


def test_run_state_rejects_extra_fields() -> None:
    _require_durable_models()
    from agent_foundations.durable.models import RunState

    with pytest.raises(ValidationError, match="extra"):
        RunState.model_validate(
            {
                "schema_version": 1,
                "messages": [],
                "next_step": 1,
                "attempt": 1,
                "api_key": "placeholder-not-real",
            },
        )


def test_run_state_rejects_open_file_handle_in_tool_arguments() -> None:
    _require_durable_models()
    from agent_foundations.domain.messages import Message, Role
    from agent_foundations.domain.tool import ToolCall
    from agent_foundations.durable.models import RunState

    with pytest.raises(ValidationError):
        RunState(
            schema_version=1,
            messages=(
                Message(
                    role=Role.ASSISTANT,
                    tool_calls=(
                        ToolCall(
                            id="call-1",
                            name="read_file",
                            arguments={"handle": io.StringIO("data")},
                        ),
                    ),
                ),
            ),
            next_step=1,
            attempt=1,
        )
