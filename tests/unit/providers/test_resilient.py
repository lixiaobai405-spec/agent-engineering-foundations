from __future__ import annotations

import asyncio
import importlib.util
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest

from agent_foundations.domain.errors import (
    FakeModelExhaustedError,
    InvalidModelResponseError,
    ProviderAuthenticationError,
    ProviderError,
    ProviderRateLimitError,
    ProviderTimeoutError,
)
from agent_foundations.domain.messages import Message, Role
from agent_foundations.domain.model import ModelRequest, ModelResponse
from agent_foundations.domain.tool import ToolCall

RUN_ID = UUID("22222222-2222-4222-8222-222222222222")
REQUEST_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
REQUEST_ID_B = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")


def _require_resilient() -> None:
    spec = importlib.util.find_spec("agent_foundations.providers.resilient")
    assert spec is not None, "agent_foundations.providers.resilient must exist"


def _load_resilient() -> Any:
    _require_resilient()
    from agent_foundations.providers.resilient import ResilientModelProvider, RetryPolicy

    return ResilientModelProvider, RetryPolicy


def _load_clock_sleeper() -> Any:
    spec = importlib.util.find_spec("agent_foundations.runtime.rate_limit")
    assert spec is not None, "agent_foundations.runtime.rate_limit must exist"
    from agent_foundations.runtime.rate_limit import FakeClock, FakeSleeper

    return FakeClock, FakeSleeper


def _load_budget() -> Any:
    spec = importlib.util.find_spec("agent_foundations.runtime.provider_attempt_budget")
    assert spec is not None, "agent_foundations.runtime.provider_attempt_budget must exist"
    from agent_foundations.runtime.provider_attempt_budget import ProviderAttemptBudget

    return ProviderAttemptBudget


def _request(*, request_id: UUID = REQUEST_ID) -> ModelRequest:
    return ModelRequest(
        messages=(Message(role=Role.USER, content="inspect"),),
        run_id=RUN_ID,
        request_id=request_id,
    )


class ScriptedProvider:
    def __init__(self, outcomes: list[ModelResponse | BaseException]) -> None:
        self._outcomes = list(outcomes)
        self.calls = 0
        self.requests: list[ModelRequest] = []

    async def complete(self, request: ModelRequest) -> ModelResponse:
        self.calls += 1
        self.requests.append(request)
        if not self._outcomes:
            raise AssertionError("scripted provider exhausted unexpectedly")
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def _ok(content: str = "ok") -> ModelResponse:
    return ModelResponse(content=content)


def _wrap(
    inner: ScriptedProvider,
    *,
    max_attempts: int = 3,
    retry_after_cap: float = 10.0,
    tracer: Any = None,
    cancellation: Any = None,
) -> Any:
    ResilientModelProvider, RetryPolicy = _load_resilient()
    FakeClock, FakeSleeper = _load_clock_sleeper()
    ProviderAttemptBudget = _load_budget()
    from agent_foundations.runtime.rate_limit import TokenBucketRateLimiter

    clock = FakeClock()
    sleeper = FakeSleeper(clock)
    policy = RetryPolicy(
        max_attempts=max_attempts,
        base_delay_seconds=0.25,
        max_delay_seconds=2.0,
        max_retry_after_seconds=retry_after_cap,
    )
    limiter = TokenBucketRateLimiter(
        capacity=8,
        refill_per_second=8.0,
        clock=clock,
        sleeper=sleeper,
    )
    provider = ResilientModelProvider(
        inner,
        policy=policy,
        budget=ProviderAttemptBudget(max_attempts=max_attempts),
        limiter=limiter,
        clock=clock,
        sleeper=sleeper,
        cancellation_token=cancellation,
    )
    if tracer is not None:
        provider.bind_retry_tracer(tracer)
    return provider, sleeper, clock


@pytest.mark.asyncio
async def test_retries_transient_errors_with_bounded_backoff() -> None:
    inner = ScriptedProvider(
        [
            ProviderTimeoutError("timed out"),
            ProviderRateLimitError("rate limit"),
            _ok("recovered"),
        ]
    )
    provider, sleeper, _clock = _wrap(inner)
    result = await provider.complete(_request())
    assert result.content == "recovered"
    assert inner.calls == 3
    assert sleeper.delays == [0.25, 0.5]
    assert sleeper.real_sleeps == 0


@pytest.mark.asyncio
async def test_retry_after_is_capped() -> None:
    _require_resilient()
    inner = ScriptedProvider(
        [
            ProviderRateLimitError("rate limit", retry_after_seconds=30.0),
            _ok("later"),
        ]
    )
    provider, sleeper, _clock = _wrap(inner, retry_after_cap=10.0)
    result = await provider.complete(_request())
    assert result.content == "later"
    assert inner.calls == 2
    assert sleeper.delays == [10.0]
    assert sleeper.real_sleeps == 0


@pytest.mark.asyncio
async def test_success_stops_without_extra_sleep_or_reserve() -> None:
    inner = ScriptedProvider([_ok("first-try")])
    provider, sleeper, _clock = _wrap(inner)
    result = await provider.complete(_request())
    assert result.content == "first-try"
    assert inner.calls == 1
    assert sleeper.delays == []
    assert provider.budget.snapshot(RUN_ID)[str(REQUEST_ID)] == 1


@pytest.mark.asyncio
async def test_non_retryable_errors_fail_after_single_attempt() -> None:
    cases: list[BaseException] = [
        ProviderAuthenticationError("provider authentication failed"),
        ProviderError("provider returned HTTP 400"),
        FakeModelExhaustedError("fake model response script is exhausted"),
    ]
    for error in cases:
        inner = ScriptedProvider([error, _ok("should-not-run")])
        provider, sleeper, _clock = _wrap(inner)
        with pytest.raises(type(error)):
            await provider.complete(_request(request_id=uuid4()))
        assert inner.calls == 1
        assert sleeper.delays == []


@pytest.mark.asyncio
async def test_invalid_model_response_retries_then_raises_to_loop() -> None:
    error = InvalidModelResponseError("provider returned an invalid response")
    inner = ScriptedProvider(
        [
            error,
            InvalidModelResponseError("provider returned an invalid response"),
            InvalidModelResponseError("provider returned an invalid response"),
            _ok("should-not-run"),
        ]
    )
    provider, sleeper, _clock = _wrap(inner)
    with pytest.raises(InvalidModelResponseError, match="invalid response"):
        await provider.complete(_request())
    assert inner.calls == 3
    assert sleeper.delays == [0.25, 0.5]


@pytest.mark.asyncio
async def test_invalid_model_response_retries_until_success() -> None:
    inner = ScriptedProvider(
        [
            InvalidModelResponseError("provider returned an invalid response"),
            _ok("recovered"),
        ]
    )
    provider, sleeper, _clock = _wrap(inner)
    result = await provider.complete(_request())
    assert result.content == "recovered"
    assert inner.calls == 2
    assert sleeper.delays == [0.25]


@pytest.mark.asyncio
async def test_cancellation_during_sleep_does_not_call_inner_again() -> None:
    class CancelOnSleep:
        def __init__(self) -> None:
            self.delays: list[float] = []
            self.real_sleeps = 0

        async def sleep(self, seconds: float) -> None:
            self.delays.append(seconds)
            raise asyncio.CancelledError()

    _require_resilient()
    from agent_foundations.providers.resilient import ResilientModelProvider, RetryPolicy
    from agent_foundations.runtime.provider_attempt_budget import ProviderAttemptBudget
    from agent_foundations.runtime.rate_limit import FakeClock, TokenBucketRateLimiter

    inner = ScriptedProvider(
        [
            ProviderTimeoutError("timed out"),
            _ok("should-not-run"),
        ]
    )
    clock = FakeClock()
    sleeper = CancelOnSleep()
    provider = ResilientModelProvider(
        inner,
        policy=RetryPolicy(max_attempts=3),
        budget=ProviderAttemptBudget(max_attempts=3),
        limiter=TokenBucketRateLimiter(
            capacity=8, refill_per_second=8.0, clock=clock, sleeper=sleeper,
        ),
        clock=clock,
        sleeper=sleeper,
    )
    with pytest.raises(asyncio.CancelledError):
        await provider.complete(_request())
    assert inner.calls == 1
    assert sleeper.delays == [0.25]
    assert sleeper.real_sleeps == 0


@pytest.mark.asyncio
async def test_no_response_cache_returns_second_inner_result() -> None:
    inner = ScriptedProvider(
        [
            ModelResponse(
                content=None,
                tool_calls=(ToolCall(id="c1", name="read_file", arguments={"path": "a"}),),
            ),
            ModelResponse(content="second-content"),
        ]
    )
    provider, sleeper, _clock = _wrap(inner)
    first = await provider.complete(_request())
    second = await provider.complete(_request(request_id=REQUEST_ID_B))
    assert first.tool_calls[0].name == "read_file"
    assert second.content == "second-content"
    assert inner.calls == 2
    assert sleeper.delays == []


@pytest.mark.asyncio
async def test_retry_trace_omits_raw_prompt_and_includes_fingerprint() -> None:
    traces: list[dict[str, object]] = []

    async def tracer(payload: dict[str, object]) -> None:
        traces.append(payload)

    inner = ScriptedProvider(
        [
            ProviderTimeoutError("timed out"),
            _ok("ok"),
        ]
    )
    provider, sleeper, _clock = _wrap(inner, tracer=tracer)
    await provider.complete(_request())
    assert len(traces) == 1
    payload = traces[0]
    assert payload["error_type"] == "ProviderTimeoutError"
    assert payload["attempt_index"] == 1
    assert payload["delay_seconds"] == 0.25
    assert payload["remaining"] == 2
    fingerprint = payload["request_fingerprint"]
    assert isinstance(fingerprint, str)
    assert len(fingerprint) == 64
    joined = " ".join(str(value) for value in payload.values())
    assert "inspect" not in joined
    assert "api_key" not in joined
    assert sleeper.real_sleeps == 0


def test_cli_build_provider_disables_sdk_retries_and_wraps(monkeypatch: pytest.MonkeyPatch) -> None:
    _require_resilient()
    spec = importlib.util.find_spec("agent_foundations.cli.main")
    assert spec is not None
    from agent_foundations.cli import main
    from agent_foundations.providers.resilient import ResilientModelProvider

    captured: dict[str, object] = {}

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)
            self.chat = SimpleNamespace(completions=SimpleNamespace())

    monkeypatch.setenv("AGENT_API_KEY", "test-key")
    monkeypatch.setenv("AGENT_MODEL", "test-model")
    monkeypatch.setenv("AGENT_BASE_URL", "https://custom.example/v1")
    monkeypatch.setattr(main, "AsyncOpenAI", FakeClient)
    provider = main.build_provider()
    assert captured["api_key"] == "test-key"
    assert captured["base_url"] == "https://custom.example/v1"
    assert captured["timeout"] == 60.0
    assert captured["max_retries"] == 0
    assert isinstance(provider, ResilientModelProvider)
    assert type(provider).__name__ != "OpenAICompatibleProvider"


@pytest.mark.asyncio
async def test_temporary_provider_errors_are_retryable() -> None:
    _require_resilient()
    from agent_foundations.domain.errors import ProviderTemporaryError

    inner = ScriptedProvider(
        [
            ProviderTemporaryError("provider connection failed"),
            _ok("after-temp"),
        ]
    )
    provider, sleeper, _clock = _wrap(inner)
    result = await provider.complete(_request())
    assert result.content == "after-temp"
    assert inner.calls == 2
    assert sleeper.delays == [0.25]
