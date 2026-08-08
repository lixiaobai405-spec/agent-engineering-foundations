import asyncio
import json
import re
from collections.abc import Iterable
from pathlib import Path
from urllib.parse import urlparse

import httpx

from agent_foundations.runtime.redaction import Redactor
from agent_foundations.runtime.trace import EventSink, TraceEvent

_SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


def _validate_session_id(session_id: str) -> str:
    if not _SESSION_ID_PATTERN.fullmatch(session_id):
        raise ValueError(f"invalid session_id: {session_id!r}")
    return session_id


def _validate_viewer_url(viewer_url: str) -> str:
    normalized = viewer_url.rstrip("/")
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"invalid viewer_url: {viewer_url!r}")
    if parsed.hostname != "127.0.0.1":
        raise ValueError(f"invalid viewer_url: {viewer_url!r}")
    return normalized


class JsonlEventSink:
    def __init__(self, trace_dir: Path, redactor: Redactor) -> None:
        self._trace_dir = trace_dir.resolve()
        self._redactor = redactor
        self._lock = asyncio.Lock()

    async def emit(self, event: TraceEvent) -> None:
        session_id = _validate_session_id(event.session_id)
        path = self._trace_dir / f"{session_id}.jsonl"
        if path.resolve().parent != self._trace_dir:
            raise ValueError(f"invalid session_id: {session_id!r}")

        data = self._redactor.redact(event.model_dump(mode="json"))
        line = json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n"
        async with self._lock:
            await asyncio.to_thread(self._append, path, line)

    @staticmethod
    def _append(path: Path, line: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="") as handle:
            handle.write(line)


class CompositeEventSink:
    def __init__(self, sinks: Iterable[EventSink]) -> None:
        self._sinks = tuple(sinks)

    async def emit(self, event: TraceEvent) -> None:
        for sink in self._sinks:
            await sink.emit(event)


class LiveEventSink:
    def __init__(
        self,
        viewer_url: str,
        redactor: Redactor,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._viewer_url = _validate_viewer_url(viewer_url)
        self._redactor = redactor
        self._client = client

    async def emit(self, event: TraceEvent) -> None:
        data = self._redactor.redact(event.model_dump(mode="json"))
        try:
            if self._client is not None:
                response = await self._client.post(
                    f"{self._viewer_url}/api/events",
                    json=data,
                    timeout=2.0,
                    follow_redirects=False,
                )
            else:
                async with httpx.AsyncClient(follow_redirects=False) as client:
                    response = await client.post(
                        f"{self._viewer_url}/api/events",
                        json=data,
                        timeout=2.0,
                        follow_redirects=False,
                    )
            response.raise_for_status()
        except httpx.HTTPError:
            return None
