# Milestone 2 Read-only Coding Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Foundations 之上实现具备严格项目根目录边界、三个只读工具、最大步数保护、OpenAI-compatible Provider 和 CLI 的可运行 Agent。

**Architecture:** `PathPolicy` 是所有文件工具必须经过的安全门；`AgentLoop` 只依赖 ModelProvider、ToolRegistry、ContextBuilder 和 EventSink。CLI 负责读取非敏感配置并组装依赖，核心循环不导入 Typer、Rich、OpenAI SDK 或具体文件工具。

**Tech Stack:** Python 3.12、Pydantic 2、OpenAI Python SDK、Typer、Rich、pytest、pytest-asyncio、Anaconda

---

## 前置条件与文件结构

先完成 [Milestone 1](2026-07-21-phase-1a-foundations-plan.md)，并确认其全量门禁通过。

```text
src/agent_foundations/tools/filesystem/path_policy.py
src/agent_foundations/tools/filesystem/list_directory.py
src/agent_foundations/tools/filesystem/read_file.py
src/agent_foundations/tools/filesystem/search_text.py
src/agent_foundations/runtime/agent.py
src/agent_foundations/runtime/session.py
src/agent_foundations/runtime/trace.py
src/agent_foundations/runtime/loop.py
src/agent_foundations/providers/openai_compatible.py
src/agent_foundations/cli/main.py
src/agent_foundations/cli/renderer.py
tests/fixtures/sample_project/README.md
tests/fixtures/sample_project/src/auth.py
tests/unit/tools/filesystem/*
tests/unit/runtime/*
tests/unit/providers/test_openai_compatible.py
tests/integration/test_agent_loop.py
tests/e2e/test_cli.py
docs/learning-notes/02-readonly-agent.md
```

## Task 1: 建立文件 fixture 与 PathPolicy

**Files:**
- Create: `tests/fixtures/sample_project/README.md`
- Create: `tests/fixtures/sample_project/src/auth.py`
- Create: `src/agent_foundations/tools/filesystem/__init__.py`
- Create: `src/agent_foundations/tools/filesystem/path_policy.py`
- Test: `tests/unit/tools/filesystem/test_path_policy.py`

- [ ] **Step 1: 写路径边界失败测试**

```python
# tests/unit/tools/filesystem/test_path_policy.py
from pathlib import Path

import pytest

from agent_foundations.domain.errors import PathPolicyViolationError
from agent_foundations.tools.filesystem.path_policy import PathPolicy


FIXTURE = Path("tests/fixtures/sample_project").resolve()


def test_authorizes_file_inside_root() -> None:
    policy = PathPolicy(FIXTURE)
    assert policy.authorize("src/auth.py") == FIXTURE / "src/auth.py"


@pytest.mark.parametrize("path", ["../outside.txt", ".env", "secrets.pem", ".git/config"])
def test_rejects_escape_and_sensitive_paths(path: str) -> None:
    policy = PathPolicy(FIXTURE)
    with pytest.raises(PathPolicyViolationError):
        policy.authorize(path, must_exist=False)


def test_rejects_absolute_path_even_when_inside_root() -> None:
    policy = PathPolicy(FIXTURE)
    with pytest.raises(PathPolicyViolationError, match="relative"):
        policy.authorize(str(FIXTURE / "README.md"))


def test_rejects_symlink_that_resolves_outside_root(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    link = root / "link.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("creating symlinks is not permitted on this Windows host")
    with pytest.raises(PathPolicyViolationError, match="escapes"):
        PathPolicy(root).authorize("link.txt")
```

- [ ] **Step 2: 验证 PathPolicy 尚不存在**

Run: `conda run -n agent-foundations python -m pytest tests/unit/tools/filesystem/test_path_policy.py -v`

Expected: FAIL，错误包含 `No module named 'agent_foundations.tools.filesystem'`。

- [ ] **Step 3: 创建 fixture 与安全策略**

```markdown
<!-- tests/fixtures/sample_project/README.md -->
# Sample Project

The sample project demonstrates token authentication.
```

```python
# tests/fixtures/sample_project/src/auth.py
def authenticate(token: str) -> bool:
    return token == "demo-token"
```

```python
# src/agent_foundations/tools/filesystem/__init__.py
"""Read-only filesystem tools guarded by one path policy."""
```

```python
# src/agent_foundations/tools/filesystem/path_policy.py
from pathlib import Path

from agent_foundations.domain.errors import PathPolicyViolationError


class PathPolicy:
    _blocked_parts = frozenset({".git", ".ssh", "credentials", "secrets"})
    _blocked_names = frozenset({".env", "id_rsa", "id_ed25519", "cookies.json"})
    _blocked_suffixes = frozenset({".key", ".pem", ".p12", ".pfx"})

    def __init__(self, root: Path) -> None:
        self.root = root.resolve(strict=True)
        if not self.root.is_dir():
            raise ValueError(f"project root is not a directory: {self.root}")

    def authorize(self, relative_path: str, *, must_exist: bool = True) -> Path:
        requested = Path(relative_path)
        if requested.is_absolute():
            raise PathPolicyViolationError("path must be relative to the project root")
        if self._is_sensitive(requested):
            raise PathPolicyViolationError(f"sensitive path is blocked: {relative_path}")

        try:
            candidate = (self.root / requested).resolve(strict=must_exist)
        except FileNotFoundError as exc:
            raise PathPolicyViolationError(f"path does not exist: {relative_path}") from exc
        if not candidate.is_relative_to(self.root):
            raise PathPolicyViolationError(f"path escapes project root: {relative_path}")
        relative_resolved = candidate.relative_to(self.root)
        if self._is_sensitive(relative_resolved):
            raise PathPolicyViolationError(f"resolved path is sensitive: {relative_path}")
        return candidate

    def display_path(self, path: Path) -> str:
        return path.resolve().relative_to(self.root).as_posix() or "."

    def _is_sensitive(self, path: Path) -> bool:
        lowered = tuple(part.lower() for part in path.parts)
        name = path.name.lower()
        return (
            any(part in self._blocked_parts for part in lowered)
            or name in self._blocked_names
            or name.startswith(".env.")
            or path.suffix.lower() in self._blocked_suffixes
        )
```

- [ ] **Step 4: 验证路径测试通过**

Run: `conda run -n agent-foundations python -m pytest tests/unit/tools/filesystem/test_path_policy.py -v`

Expected: `7 passed`；若 Windows 未允许创建符号链接，则为 `6 passed, 1 skipped`。

- [ ] **Step 5: 提交安全边界**

```powershell
git add tests/fixtures/sample_project/README.md tests/fixtures/sample_project/src/auth.py src/agent_foundations/tools/filesystem tests/unit/tools/filesystem/test_path_policy.py
git commit -m "feat: enforce project path policy"
```

## Task 2: 实现 list_directory

**Files:**
- Create: `src/agent_foundations/tools/filesystem/list_directory.py`
- Test: `tests/unit/tools/filesystem/test_list_directory.py`

- [ ] **Step 1: 写目录排序与数量限制测试**

```python
# tests/unit/tools/filesystem/test_list_directory.py
import json
from pathlib import Path

import pytest

from agent_foundations.tools.filesystem.list_directory import ListDirectoryTool
from agent_foundations.tools.filesystem.path_policy import PathPolicy


@pytest.mark.asyncio
async def test_lists_relative_entries_in_stable_order() -> None:
    root = Path("tests/fixtures/sample_project").resolve()
    tool = ListDirectoryTool(PathPolicy(root), max_entries=10)

    result = await tool.execute({"path": "."})
    payload = json.loads(result.content)

    assert result.success is True
    assert payload["path"] == "."
    assert payload["entries"] == [
        {"name": "src", "type": "directory"},
        {"name": "README.md", "type": "file"},
    ]
```

- [ ] **Step 2: 验证工具尚不存在**

Run: `conda run -n agent-foundations python -m pytest tests/unit/tools/filesystem/test_list_directory.py -v`

Expected: FAIL，错误包含 `No module named ...list_directory`。

- [ ] **Step 3: 实现目录工具**

```python
# src/agent_foundations/tools/filesystem/list_directory.py
import json
from pathlib import Path
from typing import Any

from agent_foundations.domain.errors import PathPolicyViolationError
from agent_foundations.domain.tool import ToolResult
from agent_foundations.tools.filesystem.path_policy import PathPolicy


class ListDirectoryTool:
    name = "list_directory"
    description = "List direct children of a project-relative directory in stable order."

    def __init__(self, policy: PathPolicy, max_entries: int = 200) -> None:
        self._policy = policy
        self._max_entries = max_entries

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"path": {"type": "string", "default": "."}},
            "additionalProperties": False,
        }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        path = self._policy.authorize(str(arguments.get("path", ".")))
        if not path.is_dir():
            return ToolResult(success=False, content="path is not a directory", error_code="not_directory")
        entries = [
            {"name": child.name, "type": "directory" if child.is_dir() else "file"}
            for child in sorted(path.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
            if self._is_visible(child)
        ]
        truncated = len(entries) > self._max_entries
        payload = {
            "path": self._policy.display_path(path),
            "entries": entries[: self._max_entries],
            "truncated": truncated,
        }
        return ToolResult(success=True, content=json.dumps(payload, ensure_ascii=False))

    def _is_visible(self, path: Path) -> bool:
        try:
            self._policy.authorize(self._policy.display_path(path))
        except (PathPolicyViolationError, ValueError):
            return False
        return True
```

- [ ] **Step 4: 验证目录工具测试通过**

Run: `conda run -n agent-foundations python -m pytest tests/unit/tools/filesystem/test_list_directory.py -v`

Expected: `1 passed`。

- [ ] **Step 5: 提交目录工具**

```powershell
git add src/agent_foundations/tools/filesystem/list_directory.py tests/unit/tools/filesystem/test_list_directory.py
git commit -m "feat: add read-only directory tool"
```

## Task 3: 实现 read_file 的文本、大小与行数边界

**Files:**
- Create: `src/agent_foundations/tools/filesystem/read_file.py`
- Test: `tests/unit/tools/filesystem/test_read_file.py`

- [ ] **Step 1: 写读取范围和二进制拒绝测试**

```python
# tests/unit/tools/filesystem/test_read_file.py
from pathlib import Path

import pytest

from agent_foundations.domain.errors import BinaryFileError, FileTooLargeError
from agent_foundations.tools.filesystem.path_policy import PathPolicy
from agent_foundations.tools.filesystem.read_file import ReadFileTool


@pytest.mark.asyncio
async def test_reads_numbered_line_range() -> None:
    root = Path("tests/fixtures/sample_project").resolve()
    tool = ReadFileTool(PathPolicy(root))
    result = await tool.execute({"path": "src/auth.py", "start_line": 1, "max_lines": 1})
    assert result.content == "1: def authenticate(token: str) -> bool:"
    assert result.metadata["truncated"] is True


@pytest.mark.asyncio
async def test_rejects_large_and_binary_files(tmp_path: Path) -> None:
    (tmp_path / "large.txt").write_text("12345", encoding="utf-8")
    (tmp_path / "binary.bin").write_bytes(b"a\x00b")
    tool = ReadFileTool(PathPolicy(tmp_path), max_bytes=4)
    with pytest.raises(FileTooLargeError):
        await tool.execute({"path": "large.txt"})
    tool = ReadFileTool(PathPolicy(tmp_path), max_bytes=100)
    with pytest.raises(BinaryFileError):
        await tool.execute({"path": "binary.bin"})
```

- [ ] **Step 2: 验证读取工具尚不存在**

Run: `conda run -n agent-foundations python -m pytest tests/unit/tools/filesystem/test_read_file.py -v`

Expected: FAIL，错误包含 `No module named ...read_file`。

- [ ] **Step 3: 实现只读文本读取**

```python
# src/agent_foundations/tools/filesystem/read_file.py
from typing import Any

from agent_foundations.domain.errors import BinaryFileError, FileTooLargeError
from agent_foundations.domain.tool import ToolResult
from agent_foundations.tools.filesystem.path_policy import PathPolicy


class ReadFileTool:
    name = "read_file"
    description = "Read a bounded UTF-8 line range from a project-relative text file."

    def __init__(self, policy: PathPolicy, max_bytes: int = 256_000) -> None:
        self._policy = policy
        self._max_bytes = max_bytes

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "start_line": {"type": "integer", "minimum": 1, "default": 1},
                "max_lines": {"type": "integer", "minimum": 1, "maximum": 500, "default": 200},
            },
            "required": ["path"],
            "additionalProperties": False,
        }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        path = self._policy.authorize(str(arguments["path"]))
        if not path.is_file():
            return ToolResult(success=False, content="path is not a file", error_code="not_file")
        size = path.stat().st_size
        if size > self._max_bytes:
            raise FileTooLargeError(f"file has {size} bytes; limit is {self._max_bytes}")
        raw = path.read_bytes()
        if b"\x00" in raw:
            raise BinaryFileError("file contains NUL bytes")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise BinaryFileError("file is not valid UTF-8 text") from exc

        lines = text.splitlines()
        start = int(arguments.get("start_line", 1)) - 1
        maximum = int(arguments.get("max_lines", 200))
        selected = lines[start : start + maximum]
        content = "\n".join(f"{number}: {line}" for number, line in enumerate(selected, start=start + 1))
        return ToolResult(
            success=True,
            content=content,
            metadata={
                "path": self._policy.display_path(path),
                "start_line": start + 1,
                "returned_lines": len(selected),
                "truncated": start + len(selected) < len(lines),
            },
        )
```

- [ ] **Step 4: 验证读取工具测试通过**

Run: `conda run -n agent-foundations python -m pytest tests/unit/tools/filesystem/test_read_file.py -v`

Expected: `2 passed`。

- [ ] **Step 5: 提交读取工具**

```powershell
git add src/agent_foundations/tools/filesystem/read_file.py tests/unit/tools/filesystem/test_read_file.py
git commit -m "feat: add bounded text file reader"
```

## Task 4: 实现 search_text

**Files:**
- Create: `src/agent_foundations/tools/filesystem/search_text.py`
- Test: `tests/unit/tools/filesystem/test_search_text.py`

- [ ] **Step 1: 写稳定搜索与敏感文件跳过测试**

```python
# tests/unit/tools/filesystem/test_search_text.py
import json
from pathlib import Path

import pytest

from agent_foundations.tools.filesystem.path_policy import PathPolicy
from agent_foundations.tools.filesystem.search_text import SearchTextTool


@pytest.mark.asyncio
async def test_searches_text_with_relative_locations() -> None:
    root = Path("tests/fixtures/sample_project").resolve()
    tool = SearchTextTool(PathPolicy(root), max_matches=10)
    result = await tool.execute({"query": "token", "path": ".", "glob": "*.py"})
    payload = json.loads(result.content)
    assert payload["matches"] == [
        {"path": "src/auth.py", "line": 1, "text": "def authenticate(token: str) -> bool:"},
        {"path": "src/auth.py", "line": 2, "text": "    return token == \"demo-token\""},
    ]
    assert "must-never-be-readable" not in result.content
```

- [ ] **Step 2: 验证搜索工具尚不存在**

Run: `conda run -n agent-foundations python -m pytest tests/unit/tools/filesystem/test_search_text.py -v`

Expected: FAIL，错误包含 `No module named ...search_text`。

- [ ] **Step 3: 实现有上限的纯 Python 搜索**

```python
# src/agent_foundations/tools/filesystem/search_text.py
import json
from fnmatch import fnmatch
from typing import Any

from agent_foundations.domain.errors import BinaryFileError, FileTooLargeError, PathPolicyViolationError
from agent_foundations.domain.tool import ToolResult
from agent_foundations.tools.filesystem.path_policy import PathPolicy
from agent_foundations.tools.filesystem.read_file import ReadFileTool


class SearchTextTool:
    name = "search_text"
    description = "Search for a literal string in bounded UTF-8 project files."

    def __init__(self, policy: PathPolicy, max_matches: int = 50, max_file_bytes: int = 256_000) -> None:
        self._policy = policy
        self._max_matches = max_matches
        self._reader = ReadFileTool(policy, max_bytes=max_file_bytes)

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1},
                "path": {"type": "string", "default": "."},
                "glob": {"type": "string", "default": "*"},
            },
            "required": ["query"],
            "additionalProperties": False,
        }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        base = self._policy.authorize(str(arguments.get("path", ".")))
        query = str(arguments["query"])
        pattern = str(arguments.get("glob", "*"))
        matches: list[dict[str, object]] = []
        candidates = [base] if base.is_file() else sorted(base.rglob("*"))
        for path in candidates:
            if not path.is_file() or not fnmatch(path.name, pattern):
                continue
            relative = self._policy.display_path(path)
            try:
                result = await self._reader.execute({"path": relative, "max_lines": 500})
            except (BinaryFileError, FileTooLargeError, PathPolicyViolationError):
                continue
            for numbered in result.content.splitlines():
                number, _, text = numbered.partition(": ")
                if query.lower() in text.lower():
                    matches.append({"path": relative, "line": int(number), "text": text})
                    if len(matches) == self._max_matches:
                        payload = {"query": query, "matches": matches, "truncated": True}
                        return ToolResult(success=True, content=json.dumps(payload, ensure_ascii=False))
        payload = {"query": query, "matches": matches, "truncated": False}
        return ToolResult(success=True, content=json.dumps(payload, ensure_ascii=False))
```

- [ ] **Step 4: 验证搜索工具测试通过**

Run: `conda run -n agent-foundations python -m pytest tests/unit/tools/filesystem/test_search_text.py -v`

Expected: `1 passed`。

- [ ] **Step 5: 提交搜索工具**

```powershell
git add src/agent_foundations/tools/filesystem/search_text.py tests/unit/tools/filesystem/test_search_text.py
git commit -m "feat: add bounded project text search"
```

## Task 5: 定义 Session、TraceEvent 与 EventSink

**Files:**
- Create: `src/agent_foundations/runtime/__init__.py`
- Create: `src/agent_foundations/runtime/session.py`
- Create: `src/agent_foundations/runtime/trace.py`
- Test: `tests/unit/runtime/test_session.py`

- [ ] **Step 1: 写 Session 状态与内存事件测试**

```python
# tests/unit/runtime/test_session.py
from pathlib import Path

import pytest

from agent_foundations.domain.messages import Message, Role
from agent_foundations.runtime.session import AgentSession, SessionStatus
from agent_foundations.runtime.trace import InMemoryEventSink, TraceEvent


@pytest.mark.asyncio
async def test_session_and_event_have_stable_identity() -> None:
    session = AgentSession(root=Path("."), messages=[Message(role=Role.USER, content="inspect")])
    sink = InMemoryEventSink()
    event = TraceEvent(
        session_id=session.session_id,
        step_id=0,
        event_type="session.started",
        status="started",
        summary="Session started",
    )
    await sink.emit(event)
    session.status = SessionStatus.COMPLETED
    assert sink.events == [event]
    assert session.status is SessionStatus.COMPLETED
```

- [ ] **Step 2: 验证 Runtime 类型尚不存在**

Run: `conda run -n agent-foundations python -m pytest tests/unit/runtime/test_session.py -v`

Expected: FAIL，错误包含 `No module named 'agent_foundations.runtime'`。

- [ ] **Step 3: 实现 Session 和最小事件协议**

```python
# src/agent_foundations/runtime/__init__.py
"""Agent loop, sessions, and event contracts."""
```

```python
# src/agent_foundations/runtime/session.py
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

from agent_foundations.domain.messages import Message


class SessionStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AgentSession:
    root: Path
    messages: list[Message] = field(default_factory=list)
    session_id: str = field(default_factory=lambda: str(uuid4()))
    status: SessionStatus = SessionStatus.CREATED
```

```python
# src/agent_foundations/runtime/trace.py
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class TraceEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str
    step_id: int = Field(ge=0)
    event_type: str
    status: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    duration_ms: float | None = Field(default=None, ge=0)
    summary: str
    payload: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class EventSink(Protocol):
    async def emit(self, event: TraceEvent) -> None: ...


class InMemoryEventSink:
    def __init__(self) -> None:
        self.events: list[TraceEvent] = []

    async def emit(self, event: TraceEvent) -> None:
        self.events.append(event)


class NoOpEventSink:
    async def emit(self, event: TraceEvent) -> None:
        return None
```

- [ ] **Step 4: 验证 Session 测试通过**

Run: `conda run -n agent-foundations python -m pytest tests/unit/runtime/test_session.py -v`

Expected: `1 passed`。

- [ ] **Step 5: 提交 Runtime 协议**

```powershell
git add src/agent_foundations/runtime tests/unit/runtime/test_session.py
git commit -m "feat: define sessions and trace events"
```

## Task 6: 实现可终止的 Agent Loop

**Files:**
- Create: `src/agent_foundations/runtime/agent.py`
- Create: `src/agent_foundations/runtime/loop.py`
- Test: `tests/integration/test_agent_loop.py`

- [ ] **Step 1: 写完整工具循环与最大步数测试**

```python
# tests/integration/test_agent_loop.py
from pathlib import Path

import pytest

from agent_foundations.context.budget import ContextBudget
from agent_foundations.context.builder import ContextBuilder
from agent_foundations.domain.errors import MaxStepsExceededError
from agent_foundations.domain.model import ModelResponse
from agent_foundations.domain.tool import ToolCall
from agent_foundations.providers.fake import FakeModelProvider
from agent_foundations.runtime.agent import AgentConfig
from agent_foundations.runtime.loop import AgentLoop
from agent_foundations.runtime.trace import InMemoryEventSink
from agent_foundations.tools.filesystem.list_directory import ListDirectoryTool
from agent_foundations.tools.filesystem.path_policy import PathPolicy
from agent_foundations.tools.registry import ToolRegistry


def build_loop(responses: list[ModelResponse], max_steps: int = 10) -> tuple[AgentLoop, InMemoryEventSink]:
    root = Path("tests/fixtures/sample_project").resolve()
    sink = InMemoryEventSink()
    loop = AgentLoop(
        provider=FakeModelProvider(responses),
        registry=ToolRegistry([ListDirectoryTool(PathPolicy(root))]),
        context_builder=ContextBuilder(ContextBudget()),
        event_sink=sink,
        config=AgentConfig(max_steps=max_steps),
    )
    return loop, sink


@pytest.mark.asyncio
async def test_agent_executes_tool_then_returns_final_answer() -> None:
    loop, sink = build_loop([
        ModelResponse(tool_calls=(ToolCall(id="c1", name="list_directory", arguments={"path": "."}),)),
        ModelResponse(content="The project contains source code and a README."),
    ])
    result = await loop.run(Path("tests/fixtures/sample_project"), "Summarize the project")
    assert result.answer.startswith("The project")
    assert [event.event_type for event in sink.events] == [
        "session.started", "user.message", "model.request.started", "model.response.received",
        "tool.call.requested", "tool.call.validated", "tool.call.completed",
        "model.request.started", "model.response.received", "agent.final_answer", "session.completed",
    ]


@pytest.mark.asyncio
async def test_agent_stops_after_max_steps() -> None:
    repeated = ModelResponse(tool_calls=(ToolCall(id="c1", name="list_directory", arguments={}),))
    loop, sink = build_loop([repeated, repeated], max_steps=2)
    with pytest.raises(MaxStepsExceededError):
        await loop.run(Path("tests/fixtures/sample_project"), "loop forever")
    assert sink.events[-2].event_type == "agent.loop.stopped"
    assert sink.events[-1].event_type == "session.failed"
```

- [ ] **Step 2: 验证 AgentLoop 尚不存在**

Run: `conda run -n agent-foundations python -m pytest tests/integration/test_agent_loop.py -v`

Expected: FAIL，错误包含 `No module named ...runtime.agent`。

- [ ] **Step 3: 实现 Agent 配置与循环**

```python
# src/agent_foundations/runtime/agent.py
from dataclasses import dataclass


@dataclass(frozen=True)
class AgentConfig:
    max_steps: int = 10
    system_prompt: str = (
        "You are a read-only coding agent. Use only the supplied tools. "
        "Never claim to modify files, run commands, or access paths outside the project."
    )

    def __post_init__(self) -> None:
        if self.max_steps < 1:
            raise ValueError("max_steps must be positive")


@dataclass(frozen=True)
class AgentResult:
    session_id: str
    answer: str
    steps: int
```

```python
# src/agent_foundations/runtime/loop.py
from pathlib import Path
from time import perf_counter

from agent_foundations.context.builder import ContextBuilder
from agent_foundations.domain.errors import MaxStepsExceededError, ProviderError, ToolError
from agent_foundations.domain.messages import Message, Role
from agent_foundations.domain.model import ModelProvider, ModelRequest
from agent_foundations.domain.tool import ToolResult
from agent_foundations.runtime.agent import AgentConfig, AgentResult
from agent_foundations.runtime.session import AgentSession, SessionStatus
from agent_foundations.runtime.trace import EventSink, TraceEvent
from agent_foundations.tools.registry import ToolRegistry


class AgentLoop:
    def __init__(
        self,
        provider: ModelProvider,
        registry: ToolRegistry,
        context_builder: ContextBuilder,
        event_sink: EventSink,
        config: AgentConfig,
    ) -> None:
        self._provider = provider
        self._registry = registry
        self._context_builder = context_builder
        self._event_sink = event_sink
        self._config = config

    async def run(self, root: Path, query: str) -> AgentResult:
        session = AgentSession(root=root.resolve())
        await self._emit(session, 0, "session.started", "started", "Session started")
        session.status = SessionStatus.RUNNING
        session.messages.extend([
            Message(role=Role.SYSTEM, content=self._config.system_prompt),
            Message(role=Role.USER, content=query),
        ])
        await self._emit(session, 0, "user.message", "completed", query)

        for step in range(1, self._config.max_steps + 1):
            request = ModelRequest(
                messages=self._context_builder.build(tuple(session.messages)),
                tools=self._registry.definitions(),
            )
            await self._emit(
                session, step, "model.request.started", "started", "Requesting model",
                payload={
                    "context": [message.model_dump(mode="json") for message in request.messages],
                    "tools": [tool.model_dump(mode="json") for tool in request.tools],
                },
            )
            started = perf_counter()
            try:
                response = await self._provider.complete(request)
            except ProviderError as exc:
                session.status = SessionStatus.FAILED
                await self._emit(
                    session, step, "session.failed", "failed", str(exc),
                    payload={
                        "error": type(exc).__name__,
                        "raw_response": getattr(exc, "raw_response", None),
                    },
                )
                raise
            await self._emit(
                session, step, "model.response.received", "completed", "Model responded",
                duration_ms=(perf_counter() - started) * 1000,
                payload={"content": response.content, "tool_calls": [call.model_dump() for call in response.tool_calls]},
            )
            session.messages.append(Message(
                role=Role.ASSISTANT,
                content=response.content,
                tool_calls=response.tool_calls,
            ))
            if not response.tool_calls:
                answer = response.content or ""
                await self._emit(session, step, "agent.final_answer", "completed", answer)
                session.status = SessionStatus.COMPLETED
                await self._emit(session, step, "session.completed", "completed", "Session completed")
                return AgentResult(session_id=session.session_id, answer=answer, steps=step)

            for call in response.tool_calls:
                await self._emit(
                    session, step, "tool.call.requested", "started", f"Calling {call.name}",
                    payload={"tool_call_id": call.id, "name": call.name, "arguments": call.arguments},
                )
                try:
                    self._registry.validate_call(call.name, call.arguments)
                    await self._emit(session, step, "tool.call.validated", "completed", f"Validated {call.name}")
                    result = await self._registry.execute(call.name, call.arguments)
                except ToolError as exc:
                    result = ToolResult(success=False, content=str(exc), error_code=type(exc).__name__)
                event_type = "tool.call.completed" if result.success else "tool.call.failed"
                await self._emit(
                    session, step, event_type, "completed" if result.success else "failed",
                    f"{call.name}: {result.error_code or 'ok'}",
                    payload={"tool_call_id": call.id, "name": call.name, "result": result.model_dump()},
                )
                session.messages.append(Message(
                    role=Role.TOOL,
                    name=call.name,
                    tool_call_id=call.id,
                    content=result.model_dump_json(),
                ))

        session.status = SessionStatus.FAILED
        await self._emit(session, self._config.max_steps, "agent.loop.stopped", "failed", "Maximum steps reached")
        await self._emit(session, self._config.max_steps, "session.failed", "failed", "Session failed")
        raise MaxStepsExceededError(f"agent exceeded {self._config.max_steps} steps")

    async def _emit(
        self,
        session: AgentSession,
        step_id: int,
        event_type: str,
        status: str,
        summary: str,
        *,
        duration_ms: float | None = None,
        payload: dict[str, object] | None = None,
    ) -> None:
        await self._event_sink.emit(TraceEvent(
            session_id=session.session_id,
            step_id=step_id,
            event_type=event_type,
            status=status,
            duration_ms=duration_ms,
            summary=summary,
            payload=payload or {},
        ))
```

- [ ] **Step 4: 验证完整循环与终止条件**

Run: `conda run -n agent-foundations python -m pytest tests/integration/test_agent_loop.py -v`

Expected: `2 passed`。

- [ ] **Step 5: 提交 Agent Loop**

```powershell
git add src/agent_foundations/runtime/agent.py src/agent_foundations/runtime/loop.py tests/integration/test_agent_loop.py
git commit -m "feat: implement bounded agent loop"
```

## Task 7: 实现 OpenAI-compatible Provider

**Files:**
- Modify: `pyproject.toml`
- Create: `src/agent_foundations/providers/openai_compatible.py`
- Test: `tests/unit/providers/test_openai_compatible.py`

- [ ] **Step 1: 写 SDK 转换与错误映射测试**

```python
# tests/unit/providers/test_openai_compatible.py
from types import SimpleNamespace
from typing import Any, cast

import httpx
import pytest
from openai import AsyncOpenAI, AuthenticationError

from agent_foundations.domain.errors import ProviderAuthenticationError
from agent_foundations.domain.messages import Message, Role
from agent_foundations.domain.model import ModelRequest
from agent_foundations.providers.openai_compatible import OpenAICompatibleProvider


class FakeCompletions:
    def __init__(self, response: object = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.kwargs: dict[str, Any] = {}

    async def create(self, **kwargs: Any) -> object:
        self.kwargs = kwargs
        if self.error:
            raise self.error
        return self.response


@pytest.mark.asyncio
async def test_converts_chat_completion_to_domain_response() -> None:
    message = SimpleNamespace(
        content=None,
        tool_calls=[SimpleNamespace(id="c1", function=SimpleNamespace(name="read_file", arguments='{"path":"README.md"}'))],
    )
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=message)],
        usage=SimpleNamespace(prompt_tokens=11, completion_tokens=4),
        model_dump=lambda mode: {"id": "response-1"},
    )
    completions = FakeCompletions(response=response)
    client = cast(AsyncOpenAI, SimpleNamespace(chat=SimpleNamespace(completions=completions)))
    provider = OpenAICompatibleProvider(client, model="demo-model")
    result = await provider.complete(ModelRequest(messages=(Message(role=Role.USER, content="inspect"),)))
    assert result.tool_calls[0].arguments == {"path": "README.md"}
    assert completions.kwargs["model"] == "demo-model"


@pytest.mark.asyncio
async def test_maps_authentication_error() -> None:
    request = httpx.Request("POST", "https://example.test/v1/chat/completions")
    response = httpx.Response(401, request=request)
    error = AuthenticationError("bad key", response=response, body=None)
    completions = FakeCompletions(error=error)
    client = cast(AsyncOpenAI, SimpleNamespace(chat=SimpleNamespace(completions=completions)))
    provider = OpenAICompatibleProvider(client, model="demo-model")
    with pytest.raises(ProviderAuthenticationError, match="authentication"):
        await provider.complete(ModelRequest(messages=(Message(role=Role.USER, content="inspect"),)))
```

- [ ] **Step 2: 增加 SDK 依赖并验证测试失败**

在 `pyproject.toml` 的 `dependencies` 增加：

```toml
  "openai>=1.59,<3",
```

Run: `conda run -n agent-foundations python -m pip install -e ".[dev]"`

Expected: 安装成功。

Run: `conda run -n agent-foundations python -m pytest tests/unit/providers/test_openai_compatible.py -v`

Expected: FAIL，错误包含 `No module named ...openai_compatible`。

- [ ] **Step 3: 实现请求、响应和已知错误映射**

```python
# src/agent_foundations/providers/openai_compatible.py
import json
from typing import Any

from openai import APITimeoutError, AsyncOpenAI, AuthenticationError, RateLimitError
from pydantic import ValidationError

from agent_foundations.domain.errors import (
    InvalidModelResponseError,
    ProviderAuthenticationError,
    ProviderRateLimitError,
    ProviderTimeoutError,
)
from agent_foundations.domain.messages import Message, Role
from agent_foundations.domain.model import ModelRequest, ModelResponse, TokenUsage
from agent_foundations.domain.tool import ToolCall


class OpenAICompatibleProvider:
    def __init__(self, client: AsyncOpenAI, model: str) -> None:
        self._client = client
        self._model = model

    async def complete(self, request: ModelRequest) -> ModelResponse:
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[self._message(message) for message in request.messages],
                tools=[
                    {"type": "function", "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    }}
                    for tool in request.tools
                ] or None,
                tool_choice="auto" if request.tools else None,
            )
        except AuthenticationError as exc:
            raise ProviderAuthenticationError("provider authentication failed") from exc
        except RateLimitError as exc:
            raise ProviderRateLimitError("provider rate limit exceeded") from exc
        except APITimeoutError as exc:
            raise ProviderTimeoutError("provider request timed out") from exc

        try:
            choice = response.choices[0].message
            calls = tuple(
                ToolCall(
                    id=call.id,
                    name=call.function.name,
                    arguments=json.loads(call.function.arguments),
                )
                for call in (choice.tool_calls or [])
            )
            usage = TokenUsage(
                input_tokens=response.usage.prompt_tokens if response.usage else 0,
                output_tokens=response.usage.completion_tokens if response.usage else 0,
            )
            return ModelResponse(
                content=choice.content,
                tool_calls=calls,
                usage=usage,
                raw_response=response.model_dump(mode="json"),
            )
        except (IndexError, AttributeError, json.JSONDecodeError, ValidationError) as exc:
            raw = response.model_dump(mode="json") if hasattr(response, "model_dump") else None
            raise InvalidModelResponseError("provider returned an invalid response", raw_response=raw) from exc

    @staticmethod
    def _message(message: Message) -> dict[str, Any]:
        converted: dict[str, Any] = {"role": message.role.value, "content": message.content}
        if message.role is Role.ASSISTANT and message.tool_calls:
            converted["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {"name": call.name, "arguments": json.dumps(call.arguments)},
                }
                for call in message.tool_calls
            ]
        if message.role is Role.TOOL:
            converted["tool_call_id"] = message.tool_call_id
            converted["name"] = message.name
        return converted
```

- [ ] **Step 4: 验证 Provider 测试通过**

Run: `conda run -n agent-foundations python -m pytest tests/unit/providers/test_openai_compatible.py -v`

Expected: `2 passed`。

- [ ] **Step 5: 提交 Provider 适配器**

```powershell
git add pyproject.toml src/agent_foundations/providers/openai_compatible.py tests/unit/providers/test_openai_compatible.py
git commit -m "feat: add OpenAI-compatible provider"
```

## Task 8: 组装 CLI、端到端测试与学习笔记

**Files:**
- Modify: `pyproject.toml`
- Create: `.env.example`
- Create: `src/agent_foundations/cli/__init__.py`
- Create: `src/agent_foundations/cli/renderer.py`
- Create: `src/agent_foundations/cli/main.py`
- Create: `tests/e2e/test_cli.py`
- Create: `docs/learning-notes/02-readonly-agent.md`

- [ ] **Step 1: 写 CLI 配置拒绝与 Fake Runtime 输出测试**

```python
# tests/e2e/test_cli.py
from pathlib import Path

from pytest import MonkeyPatch
from typer.testing import CliRunner

from agent_foundations.cli import main
from agent_foundations.runtime.agent import AgentResult


class FakeLoop:
    async def run(self, root: Path, query: str) -> AgentResult:
        return AgentResult(session_id="session-test", answer=f"Analyzed {root.name}: {query}", steps=1)


def test_cli_requires_api_configuration(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_API_KEY", raising=False)
    monkeypatch.delenv("AGENT_MODEL", raising=False)
    runner = CliRunner()
    result = runner.invoke(main.app, ["analyze", ".", "inspect"])
    assert result.exit_code == 2
    assert "AGENT_API_KEY" in result.output


def test_cli_renders_final_answer(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AGENT_API_KEY", "test-placeholder")
    monkeypatch.setenv("AGENT_MODEL", "test-model")
    monkeypatch.setattr(main, "build_runtime", lambda root: FakeLoop())
    result = CliRunner().invoke(main.app, ["analyze", str(tmp_path), "inspect"])
    assert result.exit_code == 0
    assert "Analyzed" in result.output
    assert "session-test" in result.output
```

- [ ] **Step 2: 增加 CLI 依赖与入口并验证测试失败**

在 `pyproject.toml` 的 `dependencies` 增加：

```toml
  "rich>=13.9,<15",
  "typer>=0.15,<1",
```

并增加：

```toml
[project.scripts]
agent-foundations = "agent_foundations.cli.main:app"
```

Run: `conda run -n agent-foundations python -m pip install -e ".[dev]"`

Expected: 安装成功。

Run: `conda run -n agent-foundations python -m pytest tests/e2e/test_cli.py -v`

Expected: FAIL，错误包含 `No module named 'agent_foundations.cli'`。

- [ ] **Step 3: 实现 CLI 依赖组装**

```dotenv
# .env.example
AGENT_API_KEY=replace-with-your-provider-key
AGENT_BASE_URL=https://api.openai.com/v1
AGENT_MODEL=replace-with-your-model-name
```

```python
# src/agent_foundations/cli/__init__.py
"""Command-line interface."""
```

```python
# src/agent_foundations/cli/renderer.py
from rich.console import Console
from rich.panel import Panel

from agent_foundations.runtime.agent import AgentResult


def render_result(console: Console, result: AgentResult) -> None:
    console.print(Panel(result.answer, title="Agent answer"))
    console.print(f"Session: {result.session_id} | Steps: {result.steps}")
```

```python
# src/agent_foundations/cli/main.py
import asyncio
import os
from pathlib import Path

import typer
from openai import AsyncOpenAI
from rich.console import Console

from agent_foundations.cli.renderer import render_result
from agent_foundations.context.budget import ContextBudget
from agent_foundations.context.builder import ContextBuilder
from agent_foundations.providers.openai_compatible import OpenAICompatibleProvider
from agent_foundations.runtime.agent import AgentConfig
from agent_foundations.runtime.loop import AgentLoop
from agent_foundations.runtime.trace import NoOpEventSink
from agent_foundations.tools.filesystem.list_directory import ListDirectoryTool
from agent_foundations.tools.filesystem.path_policy import PathPolicy
from agent_foundations.tools.filesystem.read_file import ReadFileTool
from agent_foundations.tools.filesystem.search_text import SearchTextTool
from agent_foundations.tools.registry import ToolRegistry


app = typer.Typer(no_args_is_help=True)
console = Console()


def build_runtime(root: Path) -> AgentLoop:
    api_key = os.environ["AGENT_API_KEY"]
    model = os.environ["AGENT_MODEL"]
    base_url = os.getenv("AGENT_BASE_URL", "https://api.openai.com/v1")
    policy = PathPolicy(root)
    registry = ToolRegistry([
        ListDirectoryTool(policy),
        ReadFileTool(policy),
        SearchTextTool(policy),
    ])
    client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=60.0, max_retries=2)
    return AgentLoop(
        provider=OpenAICompatibleProvider(client, model=model),
        registry=registry,
        context_builder=ContextBuilder(ContextBudget()),
        event_sink=NoOpEventSink(),
        config=AgentConfig(),
    )


@app.command()
def analyze(root: Path, query: str) -> None:
    """Analyze a local project without modifying it."""
    missing = [name for name in ("AGENT_API_KEY", "AGENT_MODEL") if not os.getenv(name)]
    if missing:
        console.print(f"Missing environment variables: {', '.join(missing)}", style="red")
        raise typer.Exit(code=2)
    try:
        result = asyncio.run(build_runtime(root.resolve()).run(root.resolve(), query))
    except Exception as exc:
        console.print(f"Agent failed: {exc}", style="red")
        raise typer.Exit(code=1) from exc
    render_result(console, result)


if __name__ == "__main__":
    app()
```

- [ ] **Step 4: 写学习笔记并运行 Milestone 2 门禁**

```markdown
# 02 Read-only Agent 学习笔记

## 安全模型

所有文件工具共享同一个 `PathPolicy`。工具只能接收项目相对路径；路径经过 `resolve()` 后必须仍位于根目录，并且不能命中敏感名称或后缀。读取和搜索还分别受字节、行数、文件数和匹配数限制。

## Agent Loop

循环每一步只做四件事：构建 Context、请求模型、校验并执行工具、判断最终回答。最大十步是硬终止条件。未知工具和参数错误作为 ToolResult 反馈给模型，路径越权则既反馈失败又进入 Trace。

## Provider 边界

OpenAI-compatible Adapter 负责 SDK 类型转换与错误映射。Agent Loop 只认识 `ModelRequest` 和 `ModelResponse`，因此未来可增加其他 Provider 而不修改循环。

## 下一轮源码对照

- Pydantic AI 如何组织 Agent Loop 和依赖注入？
- 它如何区分可重试的模型错误与不可重试错误？
- 当前实现的硬上限与成熟项目的预算策略有什么差异？
```

Run: `conda run -n agent-foundations python -m pytest -q`

Expected: 所有测试通过。

Run: `conda run -n agent-foundations python -m ruff check .`

Expected: `All checks passed!`。

Run: `conda run -n agent-foundations python -m mypy src tests`

Expected: `Success: no issues found`。

- [ ] **Step 5: 提交 CLI 和验收材料**

```powershell
git add pyproject.toml .env.example src/agent_foundations/cli tests/e2e/test_cli.py docs/learning-notes/02-readonly-agent.md
git commit -m "feat: expose read-only agent CLI"
```

## Milestone 2 人工 Smoke Test

真实调用可能产生 API 费用，只在用户主动确认后运行：

```powershell
conda activate agent-foundations
$env:AGENT_API_KEY = "在当前终端临时设置，不写入文件"
$env:AGENT_BASE_URL = "你的 OpenAI-compatible endpoint"
$env:AGENT_MODEL = "你的模型名"
agent-foundations analyze "tests/fixtures/sample_project" "解释这个项目如何认证，并给出代码证据"
```

预期：Agent 至少调用一次只读工具，最终答案引用 `src/auth.py`；工作区没有文件被修改。完成后关闭终端，使临时环境变量失效。

## Milestone 2 完成条件

- [ ] 三个工具均通过 Registry 暴露，不存在第四个隐式工具。
- [ ] 路径逃逸、敏感文件、二进制文件和大文件测试通过。
- [ ] Agent Loop 能处理工具成功、工具失败、最终回答和十步终止。
- [ ] 自动测试完全使用 FakeModel 或 Fake SDK，不产生网络请求和费用。
- [ ] CLI 仅从环境变量读取 Provider 配置，不加载或输出真实密钥。
- [ ] pytest、Ruff、mypy 全部通过。
