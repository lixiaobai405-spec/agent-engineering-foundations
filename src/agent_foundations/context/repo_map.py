from __future__ import annotations

import ast
import hashlib
import os
import re
import stat
from pathlib import Path

from pydantic import ConfigDict, model_validator

from agent_foundations.context.cache import CacheKey, ContextSourceCache
from agent_foundations.context.sources import ContextSource, ContextSourceKind
from agent_foundations.domain._model import ValidatedCopyModel
from agent_foundations.domain.errors import PathPolicyViolationError
from agent_foundations.execution.workspace import _is_excluded, _is_reparse
from agent_foundations.tools.filesystem.path_policy import PathPolicy
from agent_foundations.tools.patch.models import compute_project_root_fingerprint

_PYTHON_SUFFIXES = {".py"}
_TS_SUFFIXES = {".ts", ".tsx", ".js", ".jsx", ".mts", ".cts", ".mjs", ".cjs"}
_TS_SPEC = re.compile(
    r"""(?:import|export)\s+(?:type\s+)?(?:[\w*{}\s,]+from\s+)?['"]([^'"]+)['"]"""
    r"""|require\(\s*['"]([^'"]+)['"]\s*\)"""
)
_EXTRA_PARTS = frozenset({"command-output"})


class RepoMapLimits(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    max_files: int = 200
    max_file_bytes: int = 65_536
    max_map_chars: int = 8_000
    max_sources: int = 32

    @model_validator(mode="after")
    def _positive(self) -> RepoMapLimits:
        for field_name in ("max_files", "max_file_bytes", "max_map_chars", "max_sources"):
            if int(getattr(self, field_name)) < 1:
                raise ValueError("RepoMapLimits values must be positive integers")
        return self


class RepoMap(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sources: tuple[ContextSource, ...]
    truncated: bool


class RepoMapBuilder:
    def __init__(
        self,
        cache: ContextSourceCache | None = None,
        policy: PathPolicy | None = None,
    ) -> None:
        self._cache = cache if cache is not None else ContextSourceCache()
        self._policy = policy
        self.last_cache_status = "none"

    def build(self, root: Path, limits: RepoMapLimits) -> RepoMap:
        resolved = root.resolve(strict=True)
        policy = self._policy or PathPolicy(resolved)
        fingerprint = compute_project_root_fingerprint(resolved)
        files = _list_files(resolved, policy)
        truncated = len(files) > limits.max_files
        selected_files = files[: limits.max_files]
        sources: list[ContextSource] = []
        visited: set[str] = set()
        hits = 0
        misses = 0
        for relative in selected_files:
            parsed, cache_hit = self._sources_for_file(
                resolved,
                relative,
                limits,
                policy,
                fingerprint,
                visited,
            )
            if cache_hit:
                hits += 1
            else:
                misses += 1
            sources.extend(parsed)
        if hits and misses:
            self.last_cache_status = "mixed"
        elif hits:
            self.last_cache_status = "hit"
        elif misses:
            self.last_cache_status = "miss"
        else:
            self.last_cache_status = "none"
        if len(sources) > limits.max_sources:
            sources = sources[: limits.max_sources]
            truncated = True
        total = 0
        kept: list[ContextSource] = []
        for source in sources:
            size = len(source.content)
            if total + size > limits.max_map_chars:
                truncated = True
                break
            kept.append(source)
            total += size
        return RepoMap(sources=tuple(kept), truncated=truncated)

    def _sources_for_file(
        self,
        root: Path,
        relative: str,
        limits: RepoMapLimits,
        policy: PathPolicy,
        fingerprint: str,
        visited: set[str],
    ) -> tuple[tuple[ContextSource, ...], bool]:
        if relative in visited:
            return (), True
        visited.add(relative)
        path = root / relative
        try:
            metadata = path.stat(follow_symlinks=False)
        except OSError:
            return (), False
        if (
            path.is_symlink()
            or _is_reparse(metadata)
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_size > limits.max_file_bytes
        ):
            return (), False
        try:
            data = path.read_bytes()
        except OSError:
            return (), False
        if b"\x00" in data:
            return (), False
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            return (), False
        digest = hashlib.sha256(data).hexdigest()
        key = CacheKey(
            project_fingerprint=fingerprint,
            relative_path=relative,
            size=metadata.st_size,
            mtime_ns=metadata.st_mtime_ns,
            content_sha256=digest,
        )
        cached = self._cache.lookup(key, policy=policy, relative_path=relative)
        if cached is not None:
            return cached, True
        suffix = Path(relative).suffix.casefold()
        parsed: tuple[ContextSource, ...]
        if suffix in _PYTHON_SUFFIXES:
            parsed = _python_sources(relative, text)
        elif suffix in _TS_SUFFIXES:
            parsed = _ts_sources(relative, text)
        else:
            parsed = (_file_source(relative, "", "text"),)
        self._cache.store(key, parsed)
        return parsed, False


def _list_files(root: Path, policy: PathPolicy) -> list[str]:
    stack = [root]
    files: list[str] = []
    while stack:
        directory = stack.pop()
        try:
            children = tuple(os.scandir(directory))
        except OSError:
            continue
        for child in children:
            relative_path = Path(child.path).relative_to(root)
            if _is_excluded(relative_path) or any(
                part.casefold() in _EXTRA_PARTS for part in relative_path.parts
            ):
                continue
            try:
                metadata = child.stat(follow_symlinks=False)
            except OSError:
                continue
            if child.is_symlink() or _is_reparse(metadata):
                continue
            path = Path(child.path)
            relative = relative_path.as_posix()
            if stat.S_ISDIR(metadata.st_mode):
                stack.append(path)
                continue
            if not stat.S_ISREG(metadata.st_mode):
                continue
            try:
                policy.authorize(relative)
            except PathPolicyViolationError:
                continue
            files.append(relative)
    files.sort()
    return files


def _file_source(relative: str, summary: str, parser: str) -> ContextSource:
    content = f"{relative} {summary}".strip()[:512]
    return _source(f"file:{relative}", "file", content, f"{relative} {parser}")


def _source(
    source_id: str,
    kind: ContextSourceKind,
    content: str,
    provenance: str,
) -> ContextSource:
    return ContextSource(
        source_id=source_id,
        kind=kind,
        content=content,
        priority=0,
        provenance=provenance,
        fingerprint=hashlib.sha256(content.encode("utf-8")).hexdigest(),
    )


def _python_sources(relative: str, text: str) -> tuple[ContextSource, ...]:
    items = [_file_source(relative, "python", "python-ast")]
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return tuple(items)
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            items.append(
                _source(
                    f"symbol:{relative}:{node.name}",
                    "symbol",
                    f"class {node.name}",
                    f"{relative} python-ast",
                )
            )
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    qualified = f"{node.name}.{child.name}"
                    items.append(
                        _source(
                            f"symbol:{relative}:{qualified}",
                            "symbol",
                            f"def {qualified}",
                            f"{relative} python-ast",
                        )
                    )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            items.append(
                _source(
                    f"symbol:{relative}:{node.name}",
                    "symbol",
                    f"def {node.name}",
                    f"{relative} python-ast",
                )
            )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                items.append(
                    _source(
                        f"import:{relative}:{alias.name}",
                        "import",
                        f"import {alias.name}",
                        f"{relative} python-ast",
                    )
                )
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                dotted = f"{node.module}.{alias.name}"
                items.append(
                    _source(
                        f"import:{relative}:{dotted}",
                        "import",
                        f"from {node.module} import {alias.name}",
                        f"{relative} python-ast",
                    )
                )
    return tuple(items)


def _ts_sources(relative: str, text: str) -> tuple[ContextSource, ...]:
    items = [_file_source(relative, "typescript", "ts-import-export")]
    seen: set[str] = set()
    for match in _TS_SPEC.finditer(text):
        specifier = match.group(1) or match.group(2)
        if not specifier or specifier in seen:
            continue
        seen.add(specifier)
        items.append(
            _source(
                f"import:{relative}:{specifier}",
                "import",
                f"import {specifier}",
                f"{relative} ts-import-export",
            )
        )
    return tuple(items)
