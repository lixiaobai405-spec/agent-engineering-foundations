from __future__ import annotations

import asyncio
import importlib.util
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from agent_foundations.domain.messages import Message, Role
from agent_foundations.domain.model import ModelRequest, ModelResponse
from agent_foundations.runtime.state_machine import (
    AgentRunPhase,
    AgentRunState,
    RunCancelledError,
)

RUN_ID = "22222222-2222-4222-8222-222222222222"
PROJECT_ROOT = str(Path("tests/fixtures/sample_project").resolve())
NOW = datetime(2026, 8, 2, 12, 0, 0, tzinfo=UTC)
OWNER_A = "worker-a"
OWNER_B = "worker-b"
TTL = timedelta(seconds=30)


class FakeClock:
    def __init__(self, current: datetime) -> None:
        self._current = current.astimezone(UTC)

    def __call__(self) -> datetime:
        return self._current

    def advance(self, delta: timedelta) -> None:
        self._current = self._current + delta


def _require_controller() -> None:
    assert importlib.util.find_spec("agent_foundations.durable.controller") is not None


async def _open_stack(
    path: Path,
    clock: FakeClock,
) -> tuple[Any, Any, Any]:
    from agent_foundations.durable.lease import LeaseManager
    from agent_foundations.durable.repository import DurableRunRepository

    repository = DurableRunRepository(path)
    await repository.initialize()
    manager = LeaseManager(repository, clock=clock)
    return repository, manager, clock


def _sample_durable_run(**updates: Any) -> Any:
    from agent_foundations.durable.models import DurableRun, DurableRunStatus

    return DurableRun(
        run_id=updates.get("run_id", RUN_ID),
        project_root=updates.get("project_root", PROJECT_ROOT),
        status=updates.get("status", DurableRunStatus.CREATED),
        schema_version=1,
        state_version=updates.get("state_version", 0),
        attempt=updates.get("attempt", 1),
        created_at=updates.get("created_at", NOW),
        updated_at=updates.get("updated_at", NOW),
    )


def _initial_state(**updates: Any) -> AgentRunState:
    messages = updates.pop(
        "messages",
        (
            Message(role=Role.SYSTEM, content="system"),
            Message(role=Role.USER, content="query"),
        ),
    )
    return AgentRunState(
        schema_version=1,
        messages=messages,
        next_step=updates.pop("next_step", 1),
        phase=updates.pop("phase", AgentRunPhase.READY_FOR_MODEL),
        next_tool_index=updates.pop("next_tool_index", 0),
        plan_snapshot=updates.pop("plan_snapshot", None),
        attempt=updates.pop("attempt", 1),
        last_committed_tool_fact=updates.pop("last_committed_tool_fact", None),
        final_answer=updates.pop("final_answer", None),
    )


async def _seed_run_with_checkpoint(
    repository: Any,
    *,
    status: Any,
    state: AgentRunState,
) -> tuple[Any, Any]:
    from agent_foundations.durable.models import DurableRunStatus

    run = _sample_durable_run(status=DurableRunStatus.CREATED)
    await repository.create_run(run)
    checkpoint = await repository.save_checkpoint(run.run_id, 0, state)
    run = await repository.get_run(run.run_id)
    if status == DurableRunStatus.CREATED:
        return run, checkpoint
    run = await repository.transition_status(
        run.run_id,
        DurableRunStatus.CREATED,
        DurableRunStatus.RUNNING,
    )
    if status == DurableRunStatus.RUNNING:
        return run, checkpoint
    run = await repository.transition_status(
        run.run_id,
        DurableRunStatus.RUNNING,
        status,
    )
    return run, checkpoint


class RecordingProvider:
    def __init__(self, responses: list[ModelResponse]) -> None:
        self._responses = responses
        self.requests: list[ModelRequest] = []

    async def complete(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        if not self._responses:
            raise RuntimeError("no more responses")
        return self._responses.pop(0)


def _build_loop_factory(
    provider: RecordingProvider,
) -> Callable[[Any], Any]:
    from agent_foundations.context.budget import ContextBudget
    from agent_foundations.context.builder import ContextBuilder
    from agent_foundations.runtime.agent import AgentConfig
    from agent_foundations.runtime.loop import AgentLoop
    from agent_foundations.runtime.trace import InMemoryEventSink
    from tests.unit.tools.registry_helpers import readonly_tool_registry

    def factory(_run: Any) -> AgentLoop:
        root = Path(PROJECT_ROOT)
        return AgentLoop(
            provider=provider,
            registry=readonly_tool_registry(root),
            context_builder=ContextBuilder(ContextBudget()),
            event_sink=InMemoryEventSink(),
            config=AgentConfig(max_steps=5),
        )

    return factory


@pytest.mark.asyncio
async def test_resume_acquires_lease_and_continues_from_checkpoint(tmp_path: Path) -> None:
    _require_controller()
    from agent_foundations.durable.controller import DurableRunController
    from agent_foundations.durable.models import DurableRunStatus

    clock = FakeClock(NOW)
    repository, manager, _ = await _open_stack(tmp_path / "db.sqlite3", clock)
    state = _initial_state()
    run, _ = await _seed_run_with_checkpoint(
        repository,
        status=DurableRunStatus.PAUSED,
        state=state,
    )
    provider = RecordingProvider([ModelResponse(content="final answer")])
    controller = DurableRunController(
        repository,
        manager,
        _build_loop_factory(provider),
        lease_ttl=TTL,
        clock=clock,
    )
    result = await controller.resume(run.run_id, OWNER_A)
    assert result.answer == "final answer"
    updated = await repository.get_run(run.run_id)
    assert updated.status == DurableRunStatus.COMPLETED


@pytest.mark.asyncio
async def test_active_lease_second_owner_rejected(tmp_path: Path) -> None:
    _require_controller()
    from agent_foundations.durable.controller import ControllerRejectedError, DurableRunController
    from agent_foundations.durable.models import DurableRunStatus

    clock = FakeClock(NOW)
    repository, manager, _ = await _open_stack(tmp_path / "db.sqlite3", clock)
    state = _initial_state()
    run, _ = await _seed_run_with_checkpoint(
        repository,
        status=DurableRunStatus.PAUSED,
        state=state,
    )
    await manager.acquire(run.run_id, OWNER_A, TTL)
    provider = RecordingProvider([ModelResponse(content="unused")])
    controller = DurableRunController(
        repository,
        manager,
        _build_loop_factory(provider),
        lease_ttl=TTL,
        clock=clock,
    )
    with pytest.raises(ControllerRejectedError, match="active lease"):
        await controller.resume(run.run_id, OWNER_B)


@pytest.mark.asyncio
async def test_expired_lease_takeover_allows_resume(tmp_path: Path) -> None:
    _require_controller()
    from agent_foundations.durable.controller import DurableRunController
    from agent_foundations.durable.models import DurableRunStatus

    clock = FakeClock(NOW)
    repository, manager, _ = await _open_stack(tmp_path / "db.sqlite3", clock)
    state = _initial_state()
    run, _ = await _seed_run_with_checkpoint(
        repository,
        status=DurableRunStatus.RUNNING,
        state=state,
    )
    await manager.acquire(run.run_id, OWNER_A, TTL)
    clock.advance(TTL + timedelta(seconds=1))
    provider = RecordingProvider([ModelResponse(content="after takeover")])
    controller = DurableRunController(
        repository,
        manager,
        _build_loop_factory(provider),
        lease_ttl=TTL,
        clock=clock,
    )
    result = await controller.resume(run.run_id, OWNER_B)
    assert result.answer == "after takeover"


@pytest.mark.asyncio
async def test_takeover_rejects_old_owner_checkpoint(tmp_path: Path) -> None:
    _require_controller()
    from agent_foundations.durable.lease import LeaseTokenMismatchError
    from agent_foundations.durable.models import DurableRunStatus
    from agent_foundations.durable.repository import LeaseWriteRejectedError

    clock = FakeClock(NOW)
    repository, manager, _ = await _open_stack(tmp_path / "db.sqlite3", clock)
    state = _initial_state()
    run, _ = await _seed_run_with_checkpoint(
        repository,
        status=DurableRunStatus.RUNNING,
        state=state,
    )
    old_lease = await manager.acquire(run.run_id, OWNER_A, TTL)
    clock.advance(TTL + timedelta(seconds=1))
    await manager.takeover_expired(run.run_id, OWNER_B, TTL)
    updated = await repository.get_run(run.run_id)
    with pytest.raises(LeaseWriteRejectedError):
        await repository.save_checkpoint(
            run.run_id,
            updated.state_version,
            state,
            lease=old_lease,
            checked_at=clock(),
            expected_status=DurableRunStatus.RUNNING,
        )
    with pytest.raises(LeaseTokenMismatchError):
        await manager.renew(old_lease, TTL)


@pytest.mark.asyncio
async def test_retry_only_failed_and_increments_attempt(tmp_path: Path) -> None:
    _require_controller()
    from agent_foundations.durable.controller import ControllerRejectedError, DurableRunController
    from agent_foundations.durable.models import DurableRunStatus

    clock = FakeClock(NOW)
    repository, manager, _ = await _open_stack(tmp_path / "db.sqlite3", clock)
    messages = (
        Message(role=Role.SYSTEM, content="system"),
        Message(role=Role.USER, content="query"),
        Message(role=Role.ASSISTANT, content="partial"),
    )
    state = _initial_state(messages=messages, next_step=2)
    run, _ = await _seed_run_with_checkpoint(
        repository,
        status=DurableRunStatus.FAILED,
        state=state,
    )
    provider = RecordingProvider([ModelResponse(content="retry ok")])
    controller = DurableRunController(
        repository,
        manager,
        _build_loop_factory(provider),
        lease_ttl=TTL,
        clock=clock,
    )
    with pytest.raises(ControllerRejectedError):
        await controller.resume(run.run_id, OWNER_A)
    result = await controller.retry(run.run_id, OWNER_A)
    assert result.answer == "retry ok"
    updated = await repository.get_run(run.run_id)
    assert updated.attempt == 2
    checkpoint = await repository.load_latest_checkpoint(run.run_id)
    assert checkpoint.state.attempt == 2
    assert checkpoint.state.messages[2].content == "partial"
    assert checkpoint.state.messages[-1].content == "retry ok"


@pytest.mark.asyncio
async def test_begin_retry_rolls_back_on_failure(tmp_path: Path) -> None:
    _require_controller()
    from agent_foundations.durable.models import DurableRunStatus
    from agent_foundations.durable.repository import StateVersionConflictError

    clock = FakeClock(NOW)
    repository, manager, _ = await _open_stack(tmp_path / "db.sqlite3", clock)
    state = _initial_state()
    run, _ = await _seed_run_with_checkpoint(
        repository,
        status=DurableRunStatus.FAILED,
        state=state,
    )
    lease = await manager.acquire(run.run_id, OWNER_A, TTL)
    with pytest.raises(StateVersionConflictError):
        await repository.begin_retry(
            run.run_id,
            run.state_version + 1,
            state,
            lease=lease,
            checked_at=clock(),
        )
    updated = await repository.get_run(run.run_id)
    assert updated.status == DurableRunStatus.FAILED
    assert updated.attempt == 1
    assert updated.state_version == 1


@pytest.mark.asyncio
async def test_cancel_stops_before_next_provider_call(tmp_path: Path) -> None:
    _require_controller()
    from agent_foundations.durable.controller import DurableRunController
    from agent_foundations.durable.models import DurableRunStatus

    clock = FakeClock(NOW)
    repository, manager, _ = await _open_stack(tmp_path / "db.sqlite3", clock)
    state = _initial_state()
    run, _ = await _seed_run_with_checkpoint(
        repository,
        status=DurableRunStatus.RUNNING,
        state=state,
    )
    provider = RecordingProvider([ModelResponse(content="never")])
    controller = DurableRunController(
        repository,
        manager,
        _build_loop_factory(provider),
        lease_ttl=TTL,
        clock=clock,
    )
    task = asyncio.create_task(controller.resume(run.run_id, OWNER_A))
    await asyncio.sleep(0)
    await controller.cancel(run.run_id, "user-1")
    with pytest.raises(RunCancelledError):
        await task
    assert len(provider.requests) == 0
    updated = await repository.get_run(run.run_id)
    assert updated.status == DurableRunStatus.CANCELLED


@pytest.mark.asyncio
async def test_completed_and_cancelled_cannot_resume_or_retry(tmp_path: Path) -> None:
    _require_controller()
    from agent_foundations.durable.controller import ControllerRejectedError, DurableRunController
    from agent_foundations.durable.models import DurableRunStatus

    clock = FakeClock(NOW)
    repository, manager, _ = await _open_stack(tmp_path / "db.sqlite3", clock)
    state = _initial_state(phase=AgentRunPhase.FINALIZING, final_answer="done")
    for status in (DurableRunStatus.COMPLETED, DurableRunStatus.CANCELLED):
        run_id = str(uuid4())
        run = _sample_durable_run(run_id=run_id, status=DurableRunStatus.CREATED)
        await repository.create_run(run)
        await repository.save_checkpoint(run_id, 0, state)
        if status == DurableRunStatus.COMPLETED:
            await repository.transition_status(
                run_id,
                DurableRunStatus.CREATED,
                DurableRunStatus.RUNNING,
            )
            await repository.transition_status(
                run_id,
                DurableRunStatus.RUNNING,
                DurableRunStatus.COMPLETED,
            )
        else:
            await repository.cancel_run(run_id)
        controller = DurableRunController(
            repository,
            manager,
            _build_loop_factory(RecordingProvider([])),
            lease_ttl=TTL,
            clock=clock,
        )
        with pytest.raises(ControllerRejectedError):
            await controller.resume(run_id, OWNER_A)
        with pytest.raises(ControllerRejectedError):
            await controller.retry(run_id, OWNER_A)


@pytest.mark.asyncio
async def test_crash_preserves_lease_until_takeover(tmp_path: Path) -> None:
    _require_controller()
    from agent_foundations.durable.controller import DurableRunController
    from agent_foundations.durable.models import DurableRunStatus

    clock = FakeClock(NOW)
    repository, manager, _ = await _open_stack(tmp_path / "db.sqlite3", clock)
    state = _initial_state()

    class CrashProvider(RecordingProvider):
        async def complete(self, request: ModelRequest) -> ModelResponse:
            raise SimulatedCrash("simulated crash")

    class SimulatedCrash(BaseException):
        pass

    provider = CrashProvider([])
    run, _ = await _seed_run_with_checkpoint(
        repository,
        status=DurableRunStatus.PAUSED,
        state=state,
    )
    controller = DurableRunController(
        repository,
        manager,
        _build_loop_factory(provider),
        lease_ttl=TTL,
        clock=clock,
    )
    with pytest.raises(SimulatedCrash):
        await controller.resume(run.run_id, OWNER_A)
    from agent_foundations.durable.lease import LeaseConflictError

    with pytest.raises(LeaseConflictError):
        await manager.acquire(run.run_id, OWNER_B, TTL)
    clock.advance(TTL + timedelta(seconds=1))
    takeover = await manager.takeover_expired(run.run_id, "worker-c", TTL)
    assert takeover.owner_id == "worker-c"


@pytest.mark.asyncio
async def test_cancel_rejects_blank_requested_by(tmp_path: Path) -> None:
    _require_controller()
    from agent_foundations.durable.controller import ControllerRejectedError, DurableRunController

    clock = FakeClock(NOW)
    repository, manager, _ = await _open_stack(tmp_path / "db.sqlite3", clock)
    run = _sample_durable_run()
    await repository.create_run(run)
    controller = DurableRunController(
        repository,
        manager,
        _build_loop_factory(RecordingProvider([])),
        lease_ttl=TTL,
        clock=clock,
    )
    with pytest.raises(ControllerRejectedError):
        await controller.cancel(run.run_id, "  ")


@pytest.mark.asyncio
async def test_resume_rejects_missing_run(tmp_path: Path) -> None:
    _require_controller()
    from agent_foundations.durable.controller import DurableRunController
    from agent_foundations.durable.repository import DurableRunNotFoundError

    clock = FakeClock(NOW)
    repository, manager, _ = await _open_stack(tmp_path / "db.sqlite3", clock)
    controller = DurableRunController(
        repository,
        manager,
        _build_loop_factory(RecordingProvider([])),
        lease_ttl=TTL,
        clock=clock,
    )
    with pytest.raises(DurableRunNotFoundError):
        await controller.resume(RUN_ID, OWNER_A)
