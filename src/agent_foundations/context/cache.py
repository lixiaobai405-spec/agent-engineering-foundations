from __future__ import annotations

from collections import OrderedDict
from typing import NamedTuple

from agent_foundations.context.sources import ContextSource, source_relative_path
from agent_foundations.domain.errors import PathPolicyViolationError
from agent_foundations.tools.filesystem.path_policy import PathPolicy

DEFAULT_CACHE_ENTRIES = 256


class CacheKey(NamedTuple):
    project_fingerprint: str
    relative_path: str
    size: int
    mtime_ns: int
    content_sha256: str


class ContextSourceCache:
    def __init__(self, max_entries: int = DEFAULT_CACHE_ENTRIES) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be a positive integer")
        self._max_entries = max_entries
        self._items: OrderedDict[CacheKey, tuple[ContextSource, ...]] = OrderedDict()

    def store(self, key: CacheKey, sources: tuple[ContextSource, ...]) -> None:
        relative = key.relative_path.casefold()
        if (
            relative == ".env"
            or relative.startswith(".env.")
            or "credential" in relative
            or relative.endswith(".key")
        ):
            return
        self._items[key] = sources
        self._items.move_to_end(key)
        while len(self._items) > self._max_entries:
            self._items.popitem(last=False)

    def lookup(
        self,
        key: CacheKey,
        *,
        policy: PathPolicy,
        relative_path: str,
    ) -> tuple[ContextSource, ...] | None:
        try:
            policy.authorize(relative_path)
        except PathPolicyViolationError:
            self._items.pop(key, None)
            return None
        stored = self._items.get(key)
        if stored is None:
            return None
        for source in stored:
            try:
                policy.authorize(source_relative_path(source.source_id))
            except (PathPolicyViolationError, ValueError):
                self._items.pop(key, None)
                return None
        self._items.move_to_end(key)
        return stored
