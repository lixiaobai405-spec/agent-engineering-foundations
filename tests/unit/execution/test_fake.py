from __future__ import annotations

import asyncio
import importlib.util
from typing import Any
from uuid import uuid4

import pytest


def _execution() -> tuple[Any, ...]:
    assert importlib.util.find_spec("agent_foundations.execution") is not None, (
        "Task 14 execution package is missing"
    )
    assert importlib.util.find_spec("agent_foundations.execution.fake") is not None, (
        "Task 14 FakeBackend is missing"
    )
    from agent_foundations.execution.backend import ExecutionConflictError
    from agent_foundations.execution.fake import FakeBackend
    from agent_foundations.execution.models import ExecutionRequest, ExecutionResult

    return FakeBackend, ExecutionConflictError, ExecutionRequest, ExecutionResult


def _request(execution_id: str | None = None) -> Any:
    *_prefix, ExecutionRequest, _ExecutionResult = _execution()
    return ExecutionRequest(
        execution_id=execution_id or str(uuid4()),
        run_id=str(uuid4()),
        capability_id=str(uuid4()),
        argv=("python", "-V"),
        cwd=".",
        mount_mode="read_only",
        timeout_seconds=5,
        max_output_bytes=1024,
    )


@pytest.mark.asyncio
async def test_fake_backend_returns_scripted_results_and_records_order() -> None:
    FakeBackend, _Conflict, _Request, ExecutionResult = _execution()
    first = _request()
    second = _request()
    backend = FakeBackend(
        results={
            first.execution_id: ExecutionResult(
                execution_id=first.execution_id,
                exit_code=0,
                stdout=b"first",
                stderr=b"",
                timed_out=False,
                cancelled=False,
                output_truncated=False,
            ),
            second.execution_id: ExecutionResult(
                execution_id=second.execution_id,
                exit_code=9,
                stdout=b"",
                stderr=b"second",
                timed_out=False,
                cancelled=False,
                output_truncated=True,
            ),
        }
    )

    assert (await backend.execute(first)).stdout == b"first"
    result = await backend.execute(second)
    assert result.exit_code == 9
    assert result.output_truncated is True
    assert backend.requests == [first, second]


@pytest.mark.asyncio
async def test_fake_backend_blocks_without_sleep_and_rejects_duplicate_active_id() -> None:
    FakeBackend, ExecutionConflictError, *_ = _execution()
    request = _request()
    backend = FakeBackend(block=True)
    first = asyncio.create_task(backend.execute(request))
    await backend.wait_until_active(request.execution_id)

    with pytest.raises(ExecutionConflictError):
        await backend.execute(request)

    backend.release(request.execution_id)
    assert (await first).exit_code == 0
    assert backend.active_execution_ids == ()


@pytest.mark.asyncio
async def test_fake_backend_cancel_is_exact_idempotent_and_cleans_up() -> None:
    FakeBackend, _Conflict, *_ = _execution()
    request = _request()
    backend = FakeBackend(block=True)
    running = asyncio.create_task(backend.execute(request))
    await backend.wait_until_active(request.execution_id)

    await backend.cancel(str(uuid4()))
    await backend.cancel(request.execution_id)
    await backend.cancel(request.execution_id)
    result = await running

    assert result.cancelled is True
    assert result.timed_out is False
    assert result.exit_code is None
    assert backend.active_execution_ids == ()


@pytest.mark.asyncio
async def test_fake_backend_can_script_timeout_without_side_effects() -> None:
    FakeBackend, _Conflict, _Request, ExecutionResult = _execution()
    request = _request()
    backend = FakeBackend(
        results={
            request.execution_id: ExecutionResult(
                execution_id=request.execution_id,
                exit_code=None,
                stdout=b"partial",
                stderr=b"",
                timed_out=True,
                cancelled=False,
                output_truncated=False,
            )
        }
    )

    assert (await backend.execute(request)).timed_out is True
    assert backend.requests == [request]
