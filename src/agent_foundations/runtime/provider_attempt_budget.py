from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from threading import Lock
from typing import Protocol, runtime_checkable
from uuid import UUID

from agent_foundations.domain.errors import ProviderError


class ProviderAttemptExhaustedError(ProviderError):
    pass


@dataclass(frozen=True)
class AttemptReservation:
    run_id: UUID
    request_id: UUID
    attempt_index: int
    remaining: int


@runtime_checkable
class _DurableAttemptRepository(Protocol):
    async def reserve_provider_attempt(
        self,
        run_id: str,
        request_id: UUID,
        max_attempts: int,
    ) -> AttemptReservation: ...


class ProviderAttemptBudget:
    def __init__(self, max_attempts: int = 3) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        self._max_attempts = max_attempts
        self._consumed: dict[str, dict[str, int]] = {}
        self._lock = Lock()

    def hydrate(self, run_id: UUID, attempts: Mapping[str, int]) -> None:
        with self._lock:
            self._consumed[str(run_id)] = {
                key: int(value) for key, value in attempts.items()
            }

    def snapshot(self, run_id: UUID) -> dict[str, int]:
        with self._lock:
            return dict(self._consumed.get(str(run_id), {}))

    def reserve(self, run_id: UUID, request_id: UUID) -> AttemptReservation:
        key = str(request_id)
        run_key = str(run_id)
        with self._lock:
            current = self._consumed.setdefault(run_key, {})
            consumed = current.get(key, 0)
            if consumed >= self._max_attempts:
                raise ProviderAttemptExhaustedError(
                    f"provider attempt budget exhausted for request {request_id}"
                )
            consumed += 1
            current[key] = consumed
            return AttemptReservation(
                run_id=run_id,
                request_id=request_id,
                attempt_index=consumed,
                remaining=self._max_attempts - consumed,
            )

    async def reserve_async(self, run_id: UUID, request_id: UUID) -> AttemptReservation:
        return self.reserve(run_id, request_id)


class DurableProviderAttemptBudget(ProviderAttemptBudget):
    def __init__(
        self,
        repository: _DurableAttemptRepository,
        max_attempts: int = 3,
    ) -> None:
        super().__init__(max_attempts=max_attempts)
        self._repository = repository

    def hydrate(self, run_id: UUID, attempts: Mapping[str, int]) -> None:
        return None

    def reserve(self, run_id: UUID, request_id: UUID) -> AttemptReservation:
        raise RuntimeError("DurableProviderAttemptBudget.reserve is async-only")

    async def reserve_async(self, run_id: UUID, request_id: UUID) -> AttemptReservation:
        return await self._repository.reserve_provider_attempt(
            str(run_id),
            request_id,
            self._max_attempts,
        )
