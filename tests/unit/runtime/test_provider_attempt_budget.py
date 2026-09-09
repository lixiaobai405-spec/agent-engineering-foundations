from __future__ import annotations

import importlib.util
from threading import Thread
from typing import Any
from uuid import UUID, uuid4

import pytest

RUN_ID = UUID("22222222-2222-4222-8222-222222222222")
REQUEST_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")


def _require_budget() -> None:
    spec = importlib.util.find_spec("agent_foundations.runtime.provider_attempt_budget")
    assert spec is not None, "agent_foundations.runtime.provider_attempt_budget must exist"


def _load() -> Any:
    _require_budget()
    from agent_foundations.runtime.provider_attempt_budget import (
        AttemptReservation,
        ProviderAttemptBudget,
        ProviderAttemptExhaustedError,
    )

    return AttemptReservation, ProviderAttemptBudget, ProviderAttemptExhaustedError


def test_reserve_increments_before_attempt_and_tracks_remaining() -> None:
    _AttemptReservation, ProviderAttemptBudget, _exhausted = _load()
    budget = ProviderAttemptBudget(max_attempts=3)
    first = budget.reserve(RUN_ID, REQUEST_ID)
    assert first.run_id == RUN_ID
    assert first.request_id == REQUEST_ID
    assert first.attempt_index == 1
    assert first.remaining == 2
    second = budget.reserve(RUN_ID, REQUEST_ID)
    assert second.attempt_index == 2
    assert second.remaining == 1
    third = budget.reserve(RUN_ID, REQUEST_ID)
    assert third.attempt_index == 3
    assert third.remaining == 0


def test_reserve_fails_when_exhausted_without_incrementing_further() -> None:
    _AttemptReservation, ProviderAttemptBudget, ProviderAttemptExhaustedError = _load()
    budget = ProviderAttemptBudget(max_attempts=2)
    budget.reserve(RUN_ID, REQUEST_ID)
    budget.reserve(RUN_ID, REQUEST_ID)
    with pytest.raises(ProviderAttemptExhaustedError):
        budget.reserve(RUN_ID, REQUEST_ID)
    snapshot = budget.snapshot(RUN_ID)
    assert snapshot[str(REQUEST_ID)] == 2


def test_hydrate_from_checkpoint_does_not_reset_consumed_counts() -> None:
    _AttemptReservation, ProviderAttemptBudget, ProviderAttemptExhaustedError = _load()
    budget = ProviderAttemptBudget(max_attempts=3)
    budget.hydrate(RUN_ID, {str(REQUEST_ID): 2})
    reservation = budget.reserve(RUN_ID, REQUEST_ID)
    assert reservation.attempt_index == 3
    assert reservation.remaining == 0
    with pytest.raises(ProviderAttemptExhaustedError):
        budget.reserve(RUN_ID, REQUEST_ID)


def test_begin_retry_style_reset_is_explicit_empty_mapping() -> None:
    _AttemptReservation, ProviderAttemptBudget, _exhausted = _load()
    budget = ProviderAttemptBudget(max_attempts=3)
    budget.hydrate(RUN_ID, {str(REQUEST_ID): 3})
    budget.hydrate(RUN_ID, {})
    reservation = budget.reserve(RUN_ID, REQUEST_ID)
    assert reservation.attempt_index == 1
    assert reservation.remaining == 2


def test_concurrent_same_request_does_not_double_reserve() -> None:
    _AttemptReservation, ProviderAttemptBudget, ProviderAttemptExhaustedError = _load()
    budget = ProviderAttemptBudget(max_attempts=1)
    errors: list[BaseException] = []
    results: list[int] = []

    def worker() -> None:
        try:
            reservation = budget.reserve(RUN_ID, REQUEST_ID)
            results.append(reservation.attempt_index)
        except ProviderAttemptExhaustedError as exc:
            errors.append(exc)

    threads = [Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert results == [1]
    assert len(errors) == 1
    assert budget.snapshot(RUN_ID)[str(REQUEST_ID)] == 1


def test_independent_request_ids_have_independent_budgets() -> None:
    _AttemptReservation, ProviderAttemptBudget, _exhausted = _load()
    budget = ProviderAttemptBudget(max_attempts=1)
    other = uuid4()
    first = budget.reserve(RUN_ID, REQUEST_ID)
    second = budget.reserve(RUN_ID, other)
    assert first.attempt_index == 1
    assert second.attempt_index == 1
