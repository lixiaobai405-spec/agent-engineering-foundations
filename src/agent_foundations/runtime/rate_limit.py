from __future__ import annotations

import asyncio
import time
from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    def monotonic(self) -> float: ...


@runtime_checkable
class Sleeper(Protocol):
    async def sleep(self, seconds: float) -> None: ...


class MonotonicClock:
    def monotonic(self) -> float:
        return time.monotonic()


class AsyncioSleeper:
    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


class FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self._now = start

    def monotonic(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


class FakeSleeper:
    def __init__(self, clock: FakeClock | None = None) -> None:
        self.delays: list[float] = []
        self.real_sleeps = 0
        self._clock = clock

    async def sleep(self, seconds: float) -> None:
        self.delays.append(seconds)
        if self._clock is not None:
            self._clock.advance(seconds)


class TokenBucketRateLimiter:
    def __init__(
        self,
        capacity: int = 8,
        refill_per_second: float = 8.0,
        clock: Clock | None = None,
        sleeper: Sleeper | None = None,
    ) -> None:
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        if refill_per_second < 0:
            raise ValueError("refill_per_second must be >= 0")
        self._capacity = float(capacity)
        self._refill_per_second = float(refill_per_second)
        self._clock: Clock = clock or MonotonicClock()
        self._sleeper: Sleeper = sleeper or AsyncioSleeper()
        self._tokens = float(capacity)
        self._last = self._clock.monotonic()
        self._lock = asyncio.Lock()

    def _refill(self) -> None:
        now = self._clock.monotonic()
        elapsed = max(0.0, now - self._last)
        self._last = now
        self._tokens = min(
            self._capacity,
            self._tokens + elapsed * self._refill_per_second,
        )

    async def acquire(self, cost: int = 1) -> None:
        if cost < 1:
            raise ValueError("cost must be >= 1")
        if cost > self._capacity:
            raise ValueError("cost exceeds capacity")
        async with self._lock:
            while True:
                self._refill()
                if self._tokens >= cost:
                    self._tokens -= cost
                    return
                if self._refill_per_second <= 0:
                    delay = 0.0
                else:
                    delay = (cost - self._tokens) / self._refill_per_second
                await self._sleeper.sleep(delay)
