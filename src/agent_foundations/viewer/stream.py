import asyncio
from collections.abc import AsyncGenerator

from agent_foundations.runtime.trace import TraceEvent


class EventBroker:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[TraceEvent]]] = {}

    async def publish(self, event: TraceEvent) -> None:
        targets: set[asyncio.Queue[TraceEvent]] = set()
        session_queues = self._subscribers.get(event.session_id)
        if session_queues:
            targets |= session_queues
        global_queues = self._subscribers.get("*")
        if global_queues:
            targets |= global_queues
        for queue in targets:
            await queue.put(event)

    async def subscribe(self, session_id: str = "*") -> AsyncGenerator[TraceEvent, None]:
        queue: asyncio.Queue[TraceEvent] = asyncio.Queue(maxsize=256)
        self._subscribers.setdefault(session_id, set()).add(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            subscribers = self._subscribers.get(session_id)
            if subscribers is not None:
                subscribers.discard(queue)
                if not subscribers:
                    del self._subscribers[session_id]


def encode_sse(event: TraceEvent) -> str:
    return f"event: {event.event_type}\ndata: {event.model_dump_json()}\n\n"
