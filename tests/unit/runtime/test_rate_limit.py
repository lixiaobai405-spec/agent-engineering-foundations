from __future__ import annotations

import asyncio
import importlib.util
from typing import Any

import pytest


def _require_rate_limit() -> None:
    spec = importlib.util.find_spec("agent_foundations.runtime.rate_limit")
    assert spec is not None, "agent_foundations.runtime.rate_limit must exist"


def _load() -> Any:
    _require_rate_limit()
    from agent_foundations.runtime.rate_limit import (
        FakeClock,
        FakeSleeper,
        TokenBucketRateLimiter,
    )

    return FakeClock, FakeSleeper, TokenBucketRateLimiter


@pytest.mark.asyncio
async def test_acquire_is_immediate_when_tokens_available() -> None:
    FakeClock, FakeSleeper, TokenBucketRateLimiter = _load()
    clock = FakeClock()
    sleeper = FakeSleeper(clock)
    limiter = TokenBucketRateLimiter(
        capacity=8,
        refill_per_second=8.0,
        clock=clock,
        sleeper=sleeper,
    )
    await limiter.acquire()
    await limiter.acquire(cost=1)
    assert sleeper.delays == []
    assert sleeper.real_sleeps == 0
    assert clock.monotonic() == 0.0


@pytest.mark.asyncio
async def test_acquire_waits_with_injected_clock_and_no_real_sleep() -> None:
    FakeClock, FakeSleeper, TokenBucketRateLimiter = _load()
    clock = FakeClock()
    sleeper = FakeSleeper(clock)
    limiter = TokenBucketRateLimiter(
        capacity=1,
        refill_per_second=2.0,
        clock=clock,
        sleeper=sleeper,
    )
    limiter._tokens = 0.0
    await limiter.acquire(cost=1)
    assert sleeper.delays == [0.5]
    assert sleeper.real_sleeps == 0
    assert clock.monotonic() == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_acquire_is_fifo_when_contended() -> None:
    FakeClock, FakeSleeper, TokenBucketRateLimiter = _load()
    clock = FakeClock()
    entered = asyncio.Event()
    release = asyncio.Event()

    class GateSleeper:
        def __init__(self) -> None:
            self.delays: list[float] = []
            self.real_sleeps = 0

        async def sleep(self, seconds: float) -> None:
            self.delays.append(seconds)
            entered.set()
            await release.wait()
            clock.advance(seconds)

    sleeper = GateSleeper()
    limiter = TokenBucketRateLimiter(
        capacity=1,
        refill_per_second=1.0,
        clock=clock,
        sleeper=sleeper,
    )
    limiter._tokens = 0.0
    order: list[str] = []

    async def first() -> None:
        await limiter.acquire()
        order.append("a")

    async def second() -> None:
        await entered.wait()
        await limiter.acquire()
        order.append("b")

    task_a = asyncio.create_task(first())
    await entered.wait()
    task_b = asyncio.create_task(second())
    release.set()
    await asyncio.gather(task_a, task_b)
    assert order == ["a", "b"]
    assert sleeper.real_sleeps == 0


@pytest.mark.asyncio
async def test_acquire_cancellation_releases_waiter() -> None:
    FakeClock, _FakeSleeper, TokenBucketRateLimiter = _load()
    clock = FakeClock()
    entered = asyncio.Event()

    class HangSleeper:
        def __init__(self) -> None:
            self.delays: list[float] = []
            self.real_sleeps = 0

        async def sleep(self, seconds: float) -> None:
            self.delays.append(seconds)
            entered.set()
            await asyncio.Event().wait()

    sleeper = HangSleeper()
    limiter = TokenBucketRateLimiter(
        capacity=1,
        refill_per_second=1.0,
        clock=clock,
        sleeper=sleeper,
    )
    limiter._tokens = 0.0
    task = asyncio.create_task(limiter.acquire())
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    limiter._tokens = 1.0
    await limiter.acquire()
    assert sleeper.real_sleeps == 0
