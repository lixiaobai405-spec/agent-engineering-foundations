from __future__ import annotations

import asyncio
import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

import pytest

from agent_foundations.domain.errors import ProviderTimeoutError
from agent_foundations.domain.messages import Message, Role
from agent_foundations.domain.model import ModelRequest, ModelResponse
from agent_foundations.runtime.state_machine import AgentRunPhase, AgentRunState, CheckpointReason

RUN_ID = "22222222-2222-4222-8222-222222222222"
REQUEST_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
NOW = datetime(2026, 8, 2, 12, 0, 0, tzinfo=UTC)
PROJECT_ROOT = "/tmp/project"


def _require_modules() -> None:
    for name in (
        "agent_foundations.providers.resilient",
        "agent_foundations.runtime.provider_attempt_budget",
        "agent_foundations.runtime.rate_limit",
        "agent_foundations.durable.repository",
    ):
        spec = importlib.util.find_spec(name)
        assert spec is not None, f"{name} must exist"


def _sample_state() -> AgentRunState:
    return AgentRunState(
        schema_version=1,
        messages=(Message(role=Role.USER, content="hello"),),
        next_step=1,
        phase=AgentRunPhase.READY_FOR_MODEL,
        next_tool_index=0,
        attempt=1,
        provider_attempts={},
    )


def _sample_run() -> Any:
    from agent_foundations.durable.models import DurableRun, DurableRunStatus

    return DurableRun(
        run_id=RUN_ID,
        project_root=PROJECT_ROOT,
        status=DurableRunStatus.CREATED,
        schema_version=1,
        state_version=0,
        attempt=1,
        created_at=NOW,
        updated_at=NOW,
    )


async def _open_repository(path: Path) -> Any:
    from agent_foundations.durable.repository import DurableRunRepository

    repository = DurableRunRepository(path)
    await repository.initialize()
    await repository.create_run(_sample_run())
    await repository.save_checkpoint(RUN_ID, 0, _sample_state())
    return repository


@pytest.mark.asyncio
async def test_crash_before_reserve_leaves_attempt_count_unchanged(tmp_path: Path) -> None:
    _require_modules()
    repository = await _open_repository(tmp_path / "app.sqlite3")
    before = await repository.load_latest_checkpoint(RUN_ID)
    assert before.state.provider_attempts == {}
    run_before = await repository.get_run(RUN_ID)
    restarted = type(repository)(tmp_path / "app.sqlite3")
    after = await restarted.load_latest_checkpoint(RUN_ID)
    run_after = await restarted.get_run(RUN_ID)
    assert after.state.provider_attempts == {}
    assert run_after.attempt == run_before.attempt == 1
    assert run_after.state_version == run_before.state_version


@pytest.mark.asyncio
async def test_crash_after_reserve_keeps_consumed_attempt(tmp_path: Path) -> None:
    _require_modules()
    from agent_foundations.runtime.provider_attempt_budget import AttemptReservation

    repository = await _open_repository(tmp_path / "app.sqlite3")
    reservation = await repository.reserve_provider_attempt(RUN_ID, REQUEST_ID, max_attempts=3)
    assert isinstance(reservation, AttemptReservation)
    assert reservation.attempt_index == 1
    assert reservation.remaining == 2
    run_after_reserve = await repository.get_run(RUN_ID)
    assert run_after_reserve.attempt == 1
    restarted = type(repository)(tmp_path / "app.sqlite3")
    checkpoint = await restarted.load_latest_checkpoint(RUN_ID)
    run = await restarted.get_run(RUN_ID)
    assert checkpoint.state.provider_attempts[str(REQUEST_ID)] == 1
    assert run.attempt == 1
    assert run.state_version == run_after_reserve.state_version


@pytest.mark.asyncio
async def test_restart_continues_remaining_budget(tmp_path: Path) -> None:
    _require_modules()
    repository = await _open_repository(tmp_path / "app.sqlite3")
    await repository.reserve_provider_attempt(RUN_ID, REQUEST_ID, max_attempts=3)
    await repository.reserve_provider_attempt(RUN_ID, REQUEST_ID, max_attempts=3)
    restarted = type(repository)(tmp_path / "app.sqlite3")
    third = await restarted.reserve_provider_attempt(RUN_ID, REQUEST_ID, max_attempts=3)
    assert third.attempt_index == 3
    assert third.remaining == 0
    checkpoint = await restarted.load_latest_checkpoint(RUN_ID)
    assert checkpoint.state.provider_attempts[str(REQUEST_ID)] == 3


@pytest.mark.asyncio
async def test_exhausted_budget_does_not_call_inner_provider(tmp_path: Path) -> None:
    _require_modules()
    from agent_foundations.providers.resilient import ResilientModelProvider, RetryPolicy
    from agent_foundations.runtime.provider_attempt_budget import (
        DurableProviderAttemptBudget,
        ProviderAttemptExhaustedError,
    )
    from agent_foundations.runtime.rate_limit import FakeClock, FakeSleeper, TokenBucketRateLimiter

    repository = await _open_repository(tmp_path / "app.sqlite3")
    for _ in range(3):
        await repository.reserve_provider_attempt(RUN_ID, REQUEST_ID, max_attempts=3)

    class ForbiddenProvider:
        calls = 0

        async def complete(self, request: ModelRequest) -> ModelResponse:
            self.calls += 1
            return ModelResponse(content="should-not-run")

    inner = ForbiddenProvider()
    clock = FakeClock()
    sleeper = FakeSleeper(clock)
    provider = ResilientModelProvider(
        inner,
        policy=RetryPolicy(max_attempts=3),
        budget=DurableProviderAttemptBudget(repository, max_attempts=3),
        limiter=TokenBucketRateLimiter(
            capacity=8, refill_per_second=8.0, clock=clock, sleeper=sleeper,
        ),
        clock=clock,
        sleeper=sleeper,
    )
    with pytest.raises(ProviderAttemptExhaustedError):
        await provider.complete(
            ModelRequest(
                messages=(Message(role=Role.USER, content="inspect"),),
                run_id=UUID(RUN_ID),
                request_id=REQUEST_ID,
            )
        )
    assert inner.calls == 0
    run = await repository.get_run(RUN_ID)
    assert run.attempt == 1


@pytest.mark.asyncio
async def test_concurrent_same_request_serializes_reserve(tmp_path: Path) -> None:
    _require_modules()
    repository = await _open_repository(tmp_path / "app.sqlite3")

    async def once() -> int:
        reservation = await repository.reserve_provider_attempt(
            RUN_ID, REQUEST_ID, max_attempts=3,
        )
        return int(reservation.attempt_index)

    first, second = await asyncio.gather(once(), once())
    assert sorted([first, second]) == [1, 2]
    checkpoint = await repository.load_latest_checkpoint(RUN_ID)
    assert checkpoint.state.provider_attempts[str(REQUEST_ID)] == 2
    run = await repository.get_run(RUN_ID)
    assert run.attempt == 1


@pytest.mark.asyncio
async def test_begin_retry_resets_provider_attempts_not_crash_resume(tmp_path: Path) -> None:
    _require_modules()
    from datetime import timedelta

    from agent_foundations.durable.lease import LeaseManager
    from agent_foundations.durable.models import DurableRunStatus, RunLease
    from agent_foundations.durable.repository import DurableRunRepository

    repository = await _open_repository(tmp_path / "app.sqlite3")
    await repository.reserve_provider_attempt(RUN_ID, REQUEST_ID, max_attempts=3)
    await repository.reserve_provider_attempt(RUN_ID, REQUEST_ID, max_attempts=3)
    crashed = await repository.load_latest_checkpoint(RUN_ID)
    assert crashed.state.provider_attempts[str(REQUEST_ID)] == 2
    await repository.transition_status(
        RUN_ID, DurableRunStatus.CREATED, DurableRunStatus.RUNNING,
    )
    await repository.transition_status(
        RUN_ID, DurableRunStatus.RUNNING, DurableRunStatus.FAILED,
    )
    manager = LeaseManager(repository)
    lease = await manager.acquire(RUN_ID, "owner-1", timedelta(seconds=60))
    assert isinstance(lease, RunLease)
    run = await repository.get_run(RUN_ID)
    retry = await repository.begin_retry(
        RUN_ID,
        run.state_version,
        crashed.state,
        lease=lease,
        checked_at=datetime.now(UTC),
    )
    assert retry.state.provider_attempts == {}
    assert retry.state.attempt == 2
    refreshed = await repository.get_run(RUN_ID)
    assert refreshed.attempt == 2
    assert isinstance(repository, DurableRunRepository)


@pytest.mark.asyncio
async def test_logical_request_id_is_stable_across_crash_for_same_step() -> None:
    _require_modules()
    run_id = UUID(RUN_ID)
    first = uuid5(run_id, f"model:1:{AgentRunPhase.READY_FOR_MODEL.value}")
    second = uuid5(run_id, f"model:1:{AgentRunPhase.READY_FOR_MODEL.value}")
    assert first == second
    other_step = uuid5(run_id, f"model:2:{AgentRunPhase.READY_FOR_MODEL.value}")
    assert other_step != first


@pytest.mark.asyncio
async def test_wrapper_retries_timeout_then_succeeds_without_real_sleep(
    tmp_path: Path,
) -> None:
    _require_modules()
    from agent_foundations.providers.resilient import ResilientModelProvider, RetryPolicy
    from agent_foundations.runtime.provider_attempt_budget import DurableProviderAttemptBudget
    from agent_foundations.runtime.rate_limit import FakeClock, FakeSleeper, TokenBucketRateLimiter

    repository = await _open_repository(tmp_path / "app.sqlite3")

    class Flaky:
        def __init__(self) -> None:
            self.calls = 0

        async def complete(self, request: ModelRequest) -> ModelResponse:
            self.calls += 1
            if self.calls == 1:
                raise ProviderTimeoutError("timed out")
            return ModelResponse(content="recovered")

    inner = Flaky()
    clock = FakeClock()
    sleeper = FakeSleeper(clock)
    provider = ResilientModelProvider(
        inner,
        policy=RetryPolicy(max_attempts=3),
        budget=DurableProviderAttemptBudget(repository, max_attempts=3),
        limiter=TokenBucketRateLimiter(
            capacity=8, refill_per_second=8.0, clock=clock, sleeper=sleeper,
        ),
        clock=clock,
        sleeper=sleeper,
    )
    result = await provider.complete(
        ModelRequest(
            messages=(Message(role=Role.USER, content="inspect"),),
            run_id=UUID(RUN_ID),
            request_id=REQUEST_ID,
        )
    )
    assert result.content == "recovered"
    assert inner.calls == 2
    assert sleeper.real_sleeps == 0
    checkpoint = await repository.load_latest_checkpoint(RUN_ID)
    assert checkpoint.state.provider_attempts[str(REQUEST_ID)] == 2
    assert CheckpointReason.PROVIDER_ATTEMPT.value == "provider_attempt"
