from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any

from agent_foundations.chat.errors import ChatConflictError


class RunSupervisor:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._closed = False
        self._shutting_down = False

    async def start(
        self,
        conversation_id: str,
        run_factory: Callable[[], Coroutine[Any, Any, None]],
    ) -> None:
        async with self._lock:
            if self._closed or self._shutting_down:
                raise ChatConflictError("supervisor is closed")
            existing = self._tasks.get(conversation_id)
            if existing is not None and not existing.done():
                raise ChatConflictError(
                    f"active run already exists for conversation: {conversation_id}",
                )
            task = asyncio.create_task(
                run_factory(),
                name=f"chat-run:{conversation_id}",
            )
            self._tasks[conversation_id] = task

            def _done_callback(
                done: asyncio.Task[None],
                cid: str = conversation_id,
            ) -> None:
                self._on_done(cid, done)

            task.add_done_callback(_done_callback)

    def is_active(self, conversation_id: str) -> bool:
        task = self._tasks.get(conversation_id)
        return task is not None and not task.done()

    async def shutdown(self) -> None:
        async with self._lock:
            if self._closed:
                return
            self._shutting_down = True
            tasks = list(self._tasks.values())
            self._tasks.clear()

        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        async with self._lock:
            self._shutting_down = False
            self._closed = True

    def _on_done(self, conversation_id: str, task: asyncio.Task[None]) -> None:
        current = self._tasks.get(conversation_id)
        if current is task:
            del self._tasks[conversation_id]
        if task.cancelled():
            return
        task.exception()
