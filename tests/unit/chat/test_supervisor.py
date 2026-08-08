from __future__ import annotations

import asyncio
from typing import Any

import pytest

from agent_foundations.chat.errors import ChatConflictError


def _require_supervisor() -> Any:
    try:
        from agent_foundations.chat.supervisor import RunSupervisor
    except ImportError as exc:
        raise AssertionError(f"RunSupervisor module missing: {exc}") from exc
    return RunSupervisor



@pytest.mark.asyncio
async def test_supervisor_one_active_task_per_conversation() -> None:
    RunSupervisor = _require_supervisor()
    supervisor = RunSupervisor()
    started = asyncio.Event()
    release = asyncio.Event()
    first_factory_calls = 0
    second_factory_calls = 0

    async def long_run() -> None:
        nonlocal first_factory_calls
        first_factory_calls += 1
        started.set()
        await release.wait()

    async def blocked_second_run() -> None:
        nonlocal second_factory_calls
        second_factory_calls += 1

    await supervisor.start("conversation-a", long_run)
    await started.wait()
    assert first_factory_calls == 1
    assert supervisor.is_active("conversation-a") is True

    with pytest.raises(ChatConflictError):
        await supervisor.start("conversation-a", blocked_second_run)
    assert second_factory_calls == 0

    release.set()
    for _ in range(20):
        if not supervisor.is_active("conversation-a"):
            break
        await asyncio.sleep(0)
    assert supervisor.is_active("conversation-a") is False
    await supervisor.shutdown()


@pytest.mark.asyncio
async def test_supervisor_allows_concurrent_conversations() -> None:
    RunSupervisor = _require_supervisor()
    supervisor = RunSupervisor()
    started_a = asyncio.Event()
    started_b = asyncio.Event()
    release = asyncio.Event()

    async def run_a() -> None:
        started_a.set()
        await release.wait()

    async def run_b() -> None:
        started_b.set()
        await release.wait()

    await supervisor.start("conversation-a", run_a)
    await supervisor.start("conversation-b", run_b)
    await asyncio.wait_for(started_a.wait(), timeout=1)
    await asyncio.wait_for(started_b.wait(), timeout=1)
    assert supervisor.is_active("conversation-a") is True
    assert supervisor.is_active("conversation-b") is True
    release.set()
    await supervisor.shutdown()
    assert supervisor.is_active("conversation-a") is False
    assert supervisor.is_active("conversation-b") is False


@pytest.mark.asyncio
async def test_supervisor_done_callback_removes_only_identical_task() -> None:
    RunSupervisor = _require_supervisor()
    supervisor = RunSupervisor()
    defer_done_callbacks = asyncio.Event()
    original_on_done = supervisor._on_done

    def delayed_on_done(
        conversation_id: str,
        task: asyncio.Task[None],
    ) -> None:
        asyncio.create_task(_delayed(conversation_id, task))

    async def _delayed(
        conversation_id: str,
        task: asyncio.Task[None],
    ) -> None:
        await defer_done_callbacks.wait()
        original_on_done(conversation_id, task)

    supervisor._on_done = delayed_on_done

    first_started = asyncio.Event()
    first_release = asyncio.Event()
    second_started = asyncio.Event()
    second_release = asyncio.Event()

    async def first_run() -> None:
        first_started.set()
        await first_release.wait()

    async def second_run() -> None:
        second_started.set()
        await second_release.wait()

    await supervisor.start("conversation-a", first_run)
    await first_started.wait()
    first_release.set()
    for _ in range(50):
        if not supervisor.is_active("conversation-a"):
            break
        await asyncio.sleep(0)

    await supervisor.start("conversation-a", second_run)
    await second_started.wait()
    assert supervisor.is_active("conversation-a") is True

    defer_done_callbacks.set()
    await asyncio.sleep(0)
    assert supervisor.is_active("conversation-a") is True

    second_release.set()
    await supervisor.shutdown()
    assert supervisor.is_active("conversation-a") is False


@pytest.mark.asyncio
async def test_supervisor_consumes_task_exceptions() -> None:
    RunSupervisor = _require_supervisor()
    supervisor = RunSupervisor()
    loop = asyncio.get_running_loop()
    logged: list[dict[str, Any]] = []
    previous_handler = loop.get_exception_handler()

    def exception_handler(
        active_loop: asyncio.AbstractEventLoop,
        context: dict[str, Any],
    ) -> None:
        logged.append(context)
        if previous_handler is not None:
            previous_handler(active_loop, context)

    loop.set_exception_handler(exception_handler)

    async def boom() -> None:
        raise RuntimeError("supervised boom")

    try:
        await supervisor.start("conversation-a", boom)
        for _ in range(50):
            if not supervisor.is_active("conversation-a"):
                break
            await asyncio.sleep(0)
        await asyncio.sleep(0.05)
    finally:
        loop.set_exception_handler(previous_handler)

    assert not any(
        "Task exception was never retrieved" in str(context)
        for context in logged
    )
    assert supervisor.is_active("conversation-a") is False
    await supervisor.shutdown()


@pytest.mark.asyncio
async def test_supervisor_cancelled_task_does_not_reraise_via_exception() -> None:
    RunSupervisor = _require_supervisor()
    supervisor = RunSupervisor()
    started = asyncio.Event()

    async def hang() -> None:
        started.set()
        await asyncio.Event().wait()

    await supervisor.start("conversation-a", hang)
    await started.wait()
    await supervisor.shutdown()
    assert supervisor.is_active("conversation-a") is False


@pytest.mark.asyncio
async def test_supervisor_shutdown_cancels_all_active_tasks() -> None:
    RunSupervisor = _require_supervisor()
    supervisor = RunSupervisor()
    started_events = [asyncio.Event(), asyncio.Event()]

    async def hang(index: int) -> None:
        started_events[index].set()
        await asyncio.Event().wait()

    await supervisor.start("conversation-a", lambda: hang(0))
    await supervisor.start("conversation-b", lambda: hang(1))
    await started_events[0].wait()
    await started_events[1].wait()
    await supervisor.shutdown()
    assert supervisor.is_active("conversation-a") is False
    assert supervisor.is_active("conversation-b") is False


@pytest.mark.asyncio
async def test_supervisor_shutdown_rejects_start_during_and_after_shutdown() -> None:
    RunSupervisor = _require_supervisor()
    supervisor = RunSupervisor()
    started = asyncio.Event()
    release = asyncio.Event()
    first_factory_calls = 0
    second_factory_calls = 0
    third_factory_calls = 0

    async def long_run() -> None:
        nonlocal first_factory_calls
        first_factory_calls += 1
        started.set()
        await release.wait()

    async def second_run() -> None:
        nonlocal second_factory_calls
        second_factory_calls += 1

    async def third_run() -> None:
        nonlocal third_factory_calls
        third_factory_calls += 1

    await supervisor.start("conversation-a", long_run)
    await started.wait()
    assert first_factory_calls == 1

    shutdown_task = asyncio.create_task(supervisor.shutdown())
    for _ in range(50):
        if not supervisor.is_active("conversation-a"):
            break
        await asyncio.sleep(0)

    with pytest.raises(ChatConflictError):
        await supervisor.start("conversation-a", second_run)
    assert second_factory_calls == 0

    release.set()
    await shutdown_task
    assert supervisor.is_active("conversation-a") is False

    with pytest.raises(ChatConflictError):
        await supervisor.start("conversation-a", third_run)
    assert third_factory_calls == 0
