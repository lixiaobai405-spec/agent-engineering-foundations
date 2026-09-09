from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from uuid import UUID, uuid4

from agent_foundations.domain.errors import (
    InvalidModelResponseError,
    ProviderError,
    ProviderRateLimitError,
    ProviderTemporaryError,
    ProviderTimeoutError,
)
from agent_foundations.domain.model import ModelProvider, ModelRequest, ModelResponse
from agent_foundations.runtime.provider_attempt_budget import (
    AttemptReservation,
    ProviderAttemptBudget,
    ProviderAttemptExhaustedError,
)
from agent_foundations.runtime.rate_limit import (
    AsyncioSleeper,
    Clock,
    MonotonicClock,
    Sleeper,
    TokenBucketRateLimiter,
)
from agent_foundations.runtime.state_machine import (
    AgentRunState,
    CancellationToken,
    CheckpointReason,
    CheckpointSink,
    RunCancelledError,
)

_RETRYABLE = (
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderTemporaryError,
    InvalidModelResponseError,
)


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 0.25
    max_delay_seconds: float = 2.0
    max_retry_after_seconds: float = 10.0


def model_request_fingerprint(request: ModelRequest) -> str:
    payload = {
        "messages": [message.model_dump(mode="json") for message in request.messages],
        "tools": [tool.model_dump(mode="json") for tool in request.tools],
    }
    canonical = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_retry_delay(
    policy: RetryPolicy,
    attempt_index: int,
    error: BaseException,
) -> float:
    delay = min(
        policy.max_delay_seconds,
        policy.base_delay_seconds * (2 ** (attempt_index - 1)),
    )
    retry_after = getattr(error, "retry_after_seconds", None)
    if isinstance(error, ProviderRateLimitError) and retry_after is not None:
        delay = min(
            policy.max_retry_after_seconds,
            max(delay, float(retry_after)),
        )
    return float(min(delay, policy.max_retry_after_seconds))


class ResilientModelProvider:
    def __init__(
        self,
        inner: ModelProvider,
        *,
        policy: RetryPolicy | None = None,
        budget: ProviderAttemptBudget | None = None,
        limiter: TokenBucketRateLimiter | None = None,
        clock: Clock | None = None,
        sleeper: Sleeper | None = None,
        cancellation_token: CancellationToken | None = None,
    ) -> None:
        self._inner = inner
        self._policy = policy or RetryPolicy()
        self.budget = budget or ProviderAttemptBudget(
            max_attempts=self._policy.max_attempts,
        )
        self._clock: Clock = clock or MonotonicClock()
        self._sleeper: Sleeper = sleeper or AsyncioSleeper()
        self._limiter = limiter or TokenBucketRateLimiter(
            clock=self._clock,
            sleeper=self._sleeper,
        )
        self._cancellation_token = cancellation_token
        self._retry_tracer: Callable[[dict[str, object]], Awaitable[None] | None] | None = None
        self._checkpoint_sink: CheckpointSink | None = None
        self._state_box: dict[str, AgentRunState] | None = None

    def bind_retry_tracer(
        self,
        tracer: Callable[[dict[str, object]], Awaitable[None] | None],
    ) -> None:
        self._retry_tracer = tracer

    def attach(
        self,
        *,
        checkpoint_sink: CheckpointSink | None,
        state_box: dict[str, AgentRunState],
        cancellation_token: CancellationToken | None = None,
    ) -> None:
        self._checkpoint_sink = checkpoint_sink
        self._state_box = state_box
        if cancellation_token is not None:
            self._cancellation_token = cancellation_token

    def hydrate_budget(self, run_id: UUID, attempts: Mapping[str, int]) -> None:
        hydrate = getattr(self.budget, "hydrate", None)
        if callable(hydrate):
            hydrate(run_id, attempts)

    async def complete(self, request: ModelRequest) -> ModelResponse:
        run_id = request.run_id or uuid4()
        request_id = request.request_id or uuid4()
        while True:
            await self._raise_if_cancelled()
            reservation = await self.budget.reserve_async(run_id, request_id)
            await self._persist_reservation(reservation)
            await self._limiter.acquire()
            await self._raise_if_cancelled()
            try:
                return await self._inner.complete(request)
            except (asyncio.CancelledError, RunCancelledError):
                raise
            except ProviderAttemptExhaustedError:
                raise
            except _RETRYABLE as exc:
                if reservation.remaining == 0:
                    raise
                delay = compute_retry_delay(self._policy, reservation.attempt_index, exc)
                await self._emit_retry(request, exc, reservation, delay)
                await self._raise_if_cancelled()
                await self._sleeper.sleep(delay)
            except ProviderError:
                raise

    async def _persist_reservation(self, reservation: AttemptReservation) -> None:
        from agent_foundations.runtime.provider_attempt_budget import (
            DurableProviderAttemptBudget,
        )

        if isinstance(self.budget, DurableProviderAttemptBudget):
            return
        if self._checkpoint_sink is None or self._state_box is None:
            return
        state = self._state_box["state"]
        attempts = dict(state.provider_attempts)
        attempts[str(reservation.request_id)] = reservation.attempt_index
        new_state = state.model_copy(update={"provider_attempts": attempts})
        self._state_box["state"] = new_state
        await self._checkpoint_sink.save(new_state, CheckpointReason.PROVIDER_ATTEMPT)

    async def _raise_if_cancelled(self) -> None:
        token = self._cancellation_token
        if token is not None and await token.is_cancelled():
            raise RunCancelledError()

    async def _emit_retry(
        self,
        request: ModelRequest,
        error: BaseException,
        reservation: AttemptReservation,
        delay: float,
    ) -> None:
        if self._retry_tracer is None:
            return
        payload: dict[str, object] = {
            "request_fingerprint": model_request_fingerprint(request),
            "error_type": type(error).__name__,
            "attempt_index": reservation.attempt_index,
            "delay_seconds": delay,
            "remaining": reservation.remaining,
        }
        result = self._retry_tracer(payload)
        if inspect.isawaitable(result):
            await result
