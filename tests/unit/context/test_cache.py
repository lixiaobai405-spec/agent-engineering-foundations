from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
from typing import Any

from agent_foundations.tools.filesystem.path_policy import PathPolicy
from agent_foundations.tools.patch.models import compute_project_root_fingerprint


def _cache() -> Any:
    try:
        spec = importlib.util.find_spec("agent_foundations.context.cache")
    except ModuleNotFoundError:
        spec = None
    assert spec is not None, "context cache is missing"
    from agent_foundations.context.cache import CacheKey, ContextSourceCache
    from agent_foundations.context.sources import ContextSource

    return CacheKey, ContextSourceCache, ContextSource


def _file_source(ContextSource: Any, relative: str, content: str) -> Any:
    return ContextSource(
        source_id=f"file:{relative}",
        kind="file",
        content=content,
        priority=0,
        provenance=f"{relative} python-ast",
        fingerprint=hashlib.sha256(content.encode("utf-8")).hexdigest(),
    )


def test_cache_hit_miss_invalidation_and_policy_recheck(tmp_path: Path) -> None:
    CacheKey, ContextSourceCache, ContextSource = _cache()
    target = tmp_path / "src" / "mod.py"
    target.parent.mkdir()
    target.write_text("class Foo:\n    pass\n", encoding="utf-8")
    stat = target.stat()
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    key = CacheKey(
        project_fingerprint=compute_project_root_fingerprint(tmp_path),
        relative_path="src/mod.py",
        size=stat.st_size,
        mtime_ns=stat.st_mtime_ns,
        content_sha256=digest,
    )
    cache = ContextSourceCache(max_entries=2)
    policy = PathPolicy(tmp_path)
    stored = (_file_source(ContextSource, "src/mod.py", "class Foo:\n    pass\n"),)
    cache.store(key, stored)
    hit = cache.lookup(key, policy=policy, relative_path="src/mod.py")
    assert hit is not None
    assert hit[0].source_id == "file:src/mod.py"

    drifted = CacheKey(
        project_fingerprint="0" * 64,
        relative_path=key.relative_path,
        size=key.size,
        mtime_ns=key.mtime_ns,
        content_sha256=key.content_sha256,
    )
    assert cache.lookup(drifted, policy=policy, relative_path="src/mod.py") is None

    target.write_text(
        "class Foo:\n    def bar(self) -> None:\n        return None\n",
        encoding="utf-8",
    )
    changed = target.stat()
    changed_key = CacheKey(
        project_fingerprint=key.project_fingerprint,
        relative_path=key.relative_path,
        size=changed.st_size,
        mtime_ns=changed.st_mtime_ns,
        content_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
    )
    assert cache.lookup(changed_key, policy=policy, relative_path="src/mod.py") is None

    poison = CacheKey(
        project_fingerprint=key.project_fingerprint,
        relative_path=".env",
        size=1,
        mtime_ns=1,
        content_sha256="a" * 64,
    )
    cache.store(poison, (_file_source(ContextSource, ".env", "SECRET=1\n"),))
    assert cache.lookup(poison, policy=policy, relative_path=".env") is None
    other = CacheKey(
        project_fingerprint=key.project_fingerprint,
        relative_path="src/other.py",
        size=2,
        mtime_ns=2,
        content_sha256="b" * 64,
    )
    cache.store(other, (_file_source(ContextSource, "src/other.py", "x"),))
    third = CacheKey(
        project_fingerprint=key.project_fingerprint,
        relative_path="src/third.py",
        size=3,
        mtime_ns=3,
        content_sha256="c" * 64,
    )
    cache.store(third, (_file_source(ContextSource, "src/third.py", "y"),))
    assert cache.lookup(key, policy=policy, relative_path="src/mod.py") is None
