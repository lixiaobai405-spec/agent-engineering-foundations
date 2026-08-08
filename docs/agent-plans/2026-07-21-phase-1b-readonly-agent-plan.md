# Milestone 2 Read-only Coding Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Foundations 之上实现具备严格项目根目录边界、三个只读工具、最大步数保护、OpenAI-compatible Provider 和 CLI 的可运行 Agent。

**Architecture:** `PathPolicy` 是所有文件工具必须经过的安全门；`AgentLoop` 只依赖 ModelProvider、ToolRegistry、ContextBuilder 和 EventSink。CLI 负责读取非敏感配置并组装依赖，核心循环不导入 Typer、Rich、OpenAI SDK 或具体文件工具。Phase 1A 已把 JSON 字段实现为深层不可变 `FrozenJSON`，因此本里程碑先在 Registry 边界恢复普通 JSON 容器，再进入文件工具和 Agent Loop。

**Tech Stack:** Python 3.12、Pydantic 2、OpenAI Python SDK 2.x、Typer、Rich、pytest、pytest-asyncio、Anaconda

---

> **2026-07-25 阶段复核：** Phase 1A 已通过 `101 passed`、Ruff、mypy、`pip check`
> 和 `git diff --check`，提交 `1d32991` 已推送至 `origin/main`。本计划已根据实际
> `FrozenJSON`、`ContextBudgetExceededError` 和 Windows 文件搜索边界修订。

## 前置条件与文件结构

先完成 [Milestone 1](2026-07-21-phase-1a-foundations-plan.md)，并确认其全量门禁通过。

```text
README.md
src/agent_foundations/domain/_freeze.py
src/agent_foundations/tools/registry.py
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

## Task 0: 对齐不可变 JSON 与 ToolRegistry 边界

**Why first:** `ToolCall.arguments` 的公开类型是 `Mapping[str, Any]`，运行时实际为
`FrozenJSON`；`jsonschema` 默认不会把自定义 `Mapping` 识别为 JSON Schema 的
`object`。如果跳过本 Task，Agent Loop 把真实 ToolCall 交给 Registry 时会在合法参数上
失败。

**Files:**
- Modify: `src/agent_foundations/domain/_freeze.py`
- Modify: `src/agent_foundations/tools/registry.py`
- Test: `tests/unit/tools/test_registry.py`

- [x] **Step 1: 写真实 ToolCall 参数经过 Registry 的失败测试**

在 `tests/unit/tools/test_registry.py` 增加：

```python
from agent_foundations.domain.tool import ToolCall


class CaptureTool(EchoTool):
    def __init__(self) -> None:
        self.received: dict[str, Any] | None = None

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "options": {
                    "type": "object",
                    "properties": {
                        "tags": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["tags"],
                    "additionalProperties": False,
                },
            },
            "required": ["text", "options"],
            "additionalProperties": False,
        }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        self.received = arguments
        return ToolResult(success=True, content=str(arguments["text"]))


@pytest.mark.asyncio
async def test_registry_thaws_tool_call_arguments_before_validation_and_execution() -> None:
    tool = CaptureTool()
    registry = ToolRegistry([tool])
    call = ToolCall(
        id="c1",
        name="echo",
        arguments={"text": "hello", "options": {"tags": ["a", "b"]}},
    )

    result = await registry.execute(call.name, call.arguments)

    assert result.success is True
    assert tool.received == {
        "text": "hello",
        "options": {"tags": ["a", "b"]},
    }
    assert isinstance(tool.received, dict)
    assert isinstance(tool.received["options"], dict)
    assert isinstance(tool.received["options"]["tags"], list)
```

- [x] **Step 2: 运行测试并确认失败原因是 FrozenJSON 不被识别为 object**

Run:

```powershell
conda run -n agent-foundations python -m pytest tests/unit/tools/test_registry.py::test_registry_thaws_tool_call_arguments_before_validation_and_execution -v
```

Expected: FAIL，`jsonschema.exceptions.ValidationError` 包含
`FrozenJSON(...) is not of type 'object'`。

- [x] **Step 3: 增加公共 JSON 解冻函数并修改 Registry**

在 `src/agent_foundations/domain/_freeze.py` 增加公共转换函数；它只转换容器，不改变
叶子值：

```python
def to_json_value(value: Any) -> Any:
    """Return plain dict/list containers suitable for SDKs and JSON Schema."""
    if isinstance(value, Mapping):
        return {key: to_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_json_value(item) for item in value]
    return value
```

把 `src/agent_foundations/tools/registry.py` 的参数边界改为：

```python
from collections.abc import Iterable, Mapping
from typing import Any, cast

from jsonschema import ValidationError, validate

from agent_foundations.domain._freeze import to_json_value
from agent_foundations.domain.errors import InvalidToolArgumentsError, UnknownToolError
from agent_foundations.domain.tool import Tool, ToolDefinition, ToolResult


class ToolRegistry:
    def __init__(self, tools: Iterable[Tool]) -> None:
        self._tools: dict[str, Tool] = {}
        for tool in tools:
            if tool.name in self._tools:
                raise ValueError(f"duplicate tool name: {tool.name}")
            self._tools[tool.name] = tool

    def definitions(self) -> tuple[ToolDefinition, ...]:
        return tuple(
            ToolDefinition(
                name=tool.name,
                description=tool.description,
                parameters=tool.input_schema(),
            )
            for tool in self._tools.values()
        )

    def validate_call(
        self,
        name: str,
        arguments: Mapping[str, Any],
    ) -> tuple[Tool, dict[str, Any]]:
        tool = self._tools.get(name)
        if tool is None:
            available = ", ".join(sorted(self._tools))
            raise UnknownToolError(f"unknown tool '{name}'; available tools: {available}")
        normalized = cast(dict[str, Any], to_json_value(arguments))
        try:
            validate(instance=normalized, schema=tool.input_schema())
        except ValidationError as exc:
            raise InvalidToolArgumentsError(exc.message) from exc
        return tool, normalized

    async def execute(
        self,
        name: str,
        arguments: Mapping[str, Any],
    ) -> ToolResult:
        tool, normalized = self.validate_call(name, arguments)
        return await tool.execute(normalized)
```

`Tool.execute()` 继续接收普通 `dict`。不可变领域对象在 Registry 之前保持不可变，工具实现
不需要了解 `FrozenJSON`。

- [x] **Step 4: 运行目标测试与 Phase 1A 回归门禁**

Run:

```powershell
conda run -n agent-foundations python -m pytest tests/unit/tools/test_registry.py -v
conda run -n agent-foundations python -m pytest tests/unit tests/contract -q
conda run -n agent-foundations python -m ruff check src tests
conda run -n agent-foundations python -m mypy src tests
git diff --check
```

Expected: 所有命令退出码为 `0`；Phase 1A 的 `101` 个测试不得减少或被跳过。

- [x] **Step 5: 等待用户验收，不自动提交**

建议检查点 Commit：

```powershell
git add src/agent_foundations/domain/_freeze.py src/agent_foundations/tools/registry.py tests/unit/tools/test_registry.py
git commit -m "fix: bridge immutable tool arguments"
```

该命令只是建议检查点；只有用户明确授权后才执行。

## Task 1: 建立文件 fixture 与 PathPolicy

**Files:**
- Create: `tests/fixtures/sample_project/README.md`
- Create: `tests/fixtures/sample_project/src/auth.py`
- Create: `src/agent_foundations/tools/filesystem/__init__.py`
- Create: `src/agent_foundations/tools/filesystem/path_policy.py`
- Test: `tests/unit/tools/filesystem/test_path_policy.py`

- [x] **Step 1: 写路径边界失败测试**

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


@pytest.mark.parametrize(
    "path",
    [
        "../outside.txt",
        ".env",
        ".env.local",
        "credentials.json",
        "secrets.pem",
        ".git/config",
        "C:drive-relative.txt",
        "README.md:alternate-stream",
    ],
)
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


@pytest.mark.parametrize(
    "path",
    [
        ".env/child.txt",
        ".ENV.local/child.txt",
        "credentials.json/child.txt",
        "secrets.pem/child.txt",
        "private.key/child.txt",
        "cookies.json/child.txt",
        "id_rsa/child.txt",
    ],
)
def test_rejects_sensitive_name_in_any_path_component(
    tmp_path: Path,
    path: str,
) -> None:
    root = tmp_path / "root"
    target = root / path
    target.parent.mkdir(parents=True)
    target.write_text("sensitive", encoding="utf-8")
    with pytest.raises(PathPolicyViolationError, match="sensitive"):
        PathPolicy(root).authorize(path)


@pytest.mark.parametrize(
    "name",
    [".npmrc", ".pypirc", ".netrc", ".git-credentials"],
)
def test_rejects_common_credential_files(tmp_path: Path, name: str) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / name).write_text("token=secret", encoding="utf-8")
    with pytest.raises(PathPolicyViolationError, match="sensitive"):
        PathPolicy(root).authorize(name)


@pytest.mark.parametrize(
    "name",
    [
        "NUL",
        "CON.txt",
        "AUX.json",
        "PRN",
        "COM1.log",
        "LPT9.txt",
        "CLOCK$",
        "CONIN$",
        "CONOUT$",
    ],
)
def test_rejects_windows_reserved_device_names(name: str) -> None:
    with pytest.raises(PathPolicyViolationError, match="reserved"):
        PathPolicy(FIXTURE).authorize(name, must_exist=False)


@pytest.mark.parametrize(
    "path",
    ["bad\x00name", "bad?name", "bad*name", "bad|name"],
)
def test_maps_invalid_windows_path_syntax_to_policy_error(path: str) -> None:
    with pytest.raises(PathPolicyViolationError, match="invalid"):
        PathPolicy(FIXTURE).authorize(path, must_exist=False)


def test_display_path_rejects_sensitive_path(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    sensitive = root / ".npmrc"
    sensitive.write_text("token=secret", encoding="utf-8")
    with pytest.raises(PathPolicyViolationError, match="sensitive"):
        PathPolicy(root).display_path(sensitive)
```

- [x] **Step 2: 验证 PathPolicy 尚不存在**

Run: `conda run -n agent-foundations python -m pytest tests/unit/tools/filesystem/test_path_policy.py -v`

Expected: FAIL，错误包含 `No module named 'agent_foundations.tools.filesystem'`。

- [x] **Step 3: 创建 fixture 与安全策略**

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
    """Authorize project-relative paths in a stable, locally trusted workspace.

    The returned path should be used immediately. This policy does not claim to
    prevent an external process from replacing filesystem entries after
    authorization.
    """

    _blocked_parts = frozenset({".git", ".ssh", "credentials", "secrets"})
    _blocked_names = frozenset(
        {
            ".env",
            ".envrc",
            ".git-credentials",
            ".netrc",
            ".npmrc",
            ".pypirc",
            "cookies.json",
            "id_ed25519",
            "id_rsa",
        }
    )
    _blocked_suffixes = frozenset({".key", ".pem", ".p12", ".pfx"})
    _blocked_prefixes = ("credentials.", "secrets.")
    _windows_forbidden_chars = frozenset('<>"|?*')
    _windows_reserved_stems = frozenset(
        {
            "aux",
            "clock$",
            "con",
            "conin$",
            "conout$",
            "nul",
            "prn",
            *(f"com{number}" for number in range(1, 10)),
            *(f"lpt{number}" for number in range(1, 10)),
        }
    )

    def __init__(self, root: Path) -> None:
        self.root = root.resolve(strict=True)
        if not self.root.is_dir():
            raise ValueError(f"project root is not a directory: {self.root}")

    def authorize(self, relative_path: str, *, must_exist: bool = True) -> Path:
        try:
            requested = Path(relative_path)
        except (TypeError, ValueError) as exc:
            raise PathPolicyViolationError(
                f"invalid path syntax is blocked: {relative_path}"
            ) from exc
        if requested.is_absolute() or requested.drive:
            raise PathPolicyViolationError("path must be relative to the project root")
        self._validate_components(requested, relative_path)
        if self._is_sensitive(requested):
            raise PathPolicyViolationError(f"sensitive path is blocked: {relative_path}")

        try:
            candidate = (self.root / requested).resolve(strict=must_exist)
        except (OSError, ValueError) as exc:
            raise PathPolicyViolationError(
                f"path cannot be resolved: {relative_path}"
            ) from exc
        if not candidate.is_relative_to(self.root):
            raise PathPolicyViolationError(f"path escapes project root: {relative_path}")
        relative_resolved = candidate.relative_to(self.root)
        if self._is_sensitive(relative_resolved):
            raise PathPolicyViolationError(f"resolved path is sensitive: {relative_path}")
        return candidate

    def display_path(self, path: Path) -> str:
        try:
            resolved = path.resolve(strict=True)
        except (OSError, ValueError) as exc:
            raise PathPolicyViolationError("path cannot be resolved") from exc
        try:
            relative = resolved.relative_to(self.root)
        except ValueError as exc:
            raise PathPolicyViolationError("path escapes project root") from exc
        if self._is_sensitive(relative):
            raise PathPolicyViolationError("resolved path is sensitive")
        return relative.as_posix() or "."

    @classmethod
    def _validate_components(cls, path: Path, original: str) -> None:
        for part in path.parts:
            if ":" in part:
                raise PathPolicyViolationError(
                    f"alternate path syntax is blocked: {original}"
                )
            if any(
                ord(character) < 32 or character in cls._windows_forbidden_chars
                for character in part
            ):
                raise PathPolicyViolationError(
                    f"invalid path syntax is blocked: {original}"
                )

            normalized = cls._normalize_component(part)
            stem = normalized.partition(".")[0]
            if stem in cls._windows_reserved_stems:
                raise PathPolicyViolationError(
                    f"reserved device path is blocked: {original}"
                )

    @staticmethod
    def _normalize_component(part: str) -> str:
        return part.rstrip(" .").casefold()

    @classmethod
    def _is_sensitive(cls, path: Path) -> bool:
        return any(cls._is_sensitive_component(part) for part in path.parts)

    @classmethod
    def _is_sensitive_component(cls, part: str) -> bool:
        normalized = cls._normalize_component(part)
        suffix = Path(normalized).suffix.casefold()
        return (
            normalized in cls._blocked_parts
            or normalized in cls._blocked_names
            or normalized.startswith(".env.")
            or normalized.startswith(cls._blocked_prefixes)
            or suffix in cls._blocked_suffixes
        )
```

- [x] **Step 4: 验证路径测试通过**

Run: `conda run -n agent-foundations python -m pytest tests/unit/tools/filesystem/test_path_policy.py -v`

Expected: `36 passed`；若 Windows 未允许创建符号链接，则为 `35 passed, 1 skipped`。

- [ ] **Step 5: 提交安全边界**

```powershell
git add tests/fixtures/sample_project/README.md tests/fixtures/sample_project/src/auth.py src/agent_foundations/tools/filesystem tests/unit/tools/filesystem/test_path_policy.py
git commit -m "feat: enforce project path policy"
```

## Task 2: 实现 list_directory

**Files:**
- Create: `src/agent_foundations/tools/filesystem/list_directory.py`
- Test: `tests/unit/tools/filesystem/test_list_directory.py`

- [x] **Step 1: 写目录排序与数量限制测试**

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
    assert payload["truncated"] is False


@pytest.mark.asyncio
async def test_limits_entries_and_hides_sensitive_children(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    for name in ("a.txt", "b.txt", "c.txt"):
        (tmp_path / name).write_text(name, encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET=blocked", encoding="utf-8")
    tool = ListDirectoryTool(PathPolicy(tmp_path), max_entries=2)

    result = await tool.execute({"path": "."})
    payload = json.loads(result.content)

    assert payload["entries"] == [
        {"name": "src", "type": "directory"},
        {"name": "a.txt", "type": "file"},
    ]
    assert payload["truncated"] is True
    assert ".env" not in result.content


@pytest.mark.asyncio
async def test_returns_failure_for_file_path() -> None:
    root = Path("tests/fixtures/sample_project").resolve()
    tool = ListDirectoryTool(PathPolicy(root))

    result = await tool.execute({"path": "README.md"})

    assert result.success is False
    assert result.error_code == "not_directory"


def test_rejects_non_positive_entry_limit() -> None:
    root = Path("tests/fixtures/sample_project").resolve()

    with pytest.raises(ValueError, match="positive"):
        ListDirectoryTool(PathPolicy(root), max_entries=0)
```

- [x] **Step 2: 验证工具尚不存在**

Run: `conda run -n agent-foundations python -m pytest tests/unit/tools/filesystem/test_list_directory.py -v`

Expected: FAIL，错误包含 `No module named ...list_directory`。

- [x] **Step 3: 实现目录工具**

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
        if max_entries < 1:
            raise ValueError("max_entries must be positive")
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

- [x] **Step 4: 验证目录工具测试通过**

Run: `conda run -n agent-foundations python -m pytest tests/unit/tools/filesystem/test_list_directory.py -v`

Expected: `4 passed`。

- [ ] **Step 5: 提交目录工具**

```powershell
git add src/agent_foundations/tools/filesystem/list_directory.py tests/unit/tools/filesystem/test_list_directory.py
git commit -m "feat: add read-only directory tool"
```

## Task 3: 实现 read_file 的文本、大小与行数边界

**Files:**
- Create: `src/agent_foundations/tools/filesystem/read_file.py`
- Test: `tests/unit/tools/filesystem/test_read_file.py`

- [x] **Step 1: 写读取范围和二进制拒绝测试**

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
    assert result.metadata["path"] == "src/auth.py"
    assert result.metadata["start_line"] == 1
    assert result.metadata["returned_lines"] == 1
    assert result.metadata["truncated"] is True


def test_read_lines_returns_complete_bounded_file(tmp_path: Path) -> None:
    lines = [f"line-{number}" for number in range(1, 551)]
    (tmp_path / "long.txt").write_text("\n".join(lines), encoding="utf-8")
    tool = ReadFileTool(PathPolicy(tmp_path), max_bytes=20_000)

    result = tool.read_lines("long.txt")

    assert len(result) == 550
    assert result[-1] == "line-550"


def test_accepts_exact_byte_limit_and_rejects_larger_file(
    tmp_path: Path,
) -> None:
    (tmp_path / "exact.txt").write_bytes(b"1234")
    (tmp_path / "large.txt").write_bytes(b"12345")
    tool = ReadFileTool(PathPolicy(tmp_path), max_bytes=4)

    assert tool.read_lines("exact.txt") == ("1234",)
    with pytest.raises(FileTooLargeError):
        tool.read_lines("large.txt")


@pytest.mark.parametrize(
    "raw",
    [b"a\x00b", b"\xff"],
    ids=["nul-byte", "invalid-utf8"],
)
def test_rejects_binary_or_invalid_utf8(
    tmp_path: Path,
    raw: bytes,
) -> None:
    (tmp_path / "binary.bin").write_bytes(raw)
    tool = ReadFileTool(PathPolicy(tmp_path), max_bytes=100)

    with pytest.raises(BinaryFileError):
        tool.read_lines("binary.bin")


@pytest.mark.asyncio
async def test_returns_failure_for_directory(tmp_path: Path) -> None:
    tool = ReadFileTool(PathPolicy(tmp_path))

    result = await tool.execute({"path": "."})

    assert result.success is False
    assert result.error_code == "not_file"


def test_rejects_non_positive_byte_limit(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="positive"):
        ReadFileTool(PathPolicy(tmp_path), max_bytes=0)
```

- [x] **Step 2: 验证读取工具尚不存在**

Run: `conda run -n agent-foundations python -m pytest tests/unit/tools/filesystem/test_read_file.py -v`

Expected: FAIL，错误包含 `No module named ...read_file`。

- [x] **Step 3: 实现只读文本读取**

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
        if max_bytes < 1:
            raise ValueError("max_bytes must be positive")
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
        relative_path = str(arguments["path"])
        path = self._policy.authorize(relative_path)
        if not path.is_file():
            return ToolResult(
                success=False,
                content="path is not a file",
                error_code="not_file",
            )
        lines = self.read_lines(relative_path)
        start = int(arguments.get("start_line", 1)) - 1
        maximum = int(arguments.get("max_lines", 200))
        selected = lines[start : start + maximum]
        content = "\n".join(
            f"{number}: {line}"
            for number, line in enumerate(selected, start=start + 1)
        )
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

    def read_lines(self, relative_path: str) -> tuple[str, ...]:
        """Load one complete UTF-8 file under the configured byte limit."""
        path = self._policy.authorize(relative_path)
        if not path.is_file():
            raise BinaryFileError("path is not a regular text file")
        with path.open("rb") as stream:
            raw = stream.read(self._max_bytes + 1)
        if len(raw) > self._max_bytes:
            raise FileTooLargeError(
                f"file exceeds {self._max_bytes} byte limit"
            )
        if b"\x00" in raw:
            raise BinaryFileError("file contains NUL bytes")
        try:
            return tuple(raw.decode("utf-8").splitlines())
        except UnicodeDecodeError as exc:
            raise BinaryFileError("file is not valid UTF-8 text") from exc
```

`read_lines()` 是 `read_file` 与 `search_text` 共用的有界文本读取边界；它返回整个文件，
但整个文件仍受 `max_bytes` 硬限制。`execute()` 继续负责面向模型的行号、起始行和最多
500 行输出限制。

- [x] **Step 4: 验证读取工具测试通过**

Run: `conda run -n agent-foundations python -m pytest tests/unit/tools/filesystem/test_read_file.py -v`

Expected: `7 passed`。

- [ ] **Step 5: 提交读取工具**

```powershell
git add src/agent_foundations/tools/filesystem/read_file.py tests/unit/tools/filesystem/test_read_file.py
git commit -m "feat: add bounded text file reader"
```

## Task 4: 实现 search_text

**Files:**
- Create: `src/agent_foundations/tools/filesystem/search_text.py`
- Test: `tests/unit/tools/filesystem/test_search_text.py`

- [x] **Step 1: 写稳定搜索与敏感文件跳过测试**

```python
# tests/unit/tools/filesystem/test_search_text.py
import json
from pathlib import Path

import pytest

from agent_foundations.domain.errors import InvalidToolArgumentsError
from agent_foundations.tools.filesystem.path_policy import PathPolicy
from agent_foundations.tools.filesystem.search_text import SearchTextTool
from agent_foundations.tools.registry import ToolRegistry


@pytest.mark.asyncio
async def test_searches_text_with_relative_locations() -> None:
    root = Path("tests/fixtures/sample_project").resolve()
    tool = SearchTextTool(PathPolicy(root), max_matches=10)
    result = await tool.execute(
        {"query": "token", "path": ".", "glob": "src/*.py"}
    )
    payload = json.loads(result.content)
    assert payload["matches"] == [
        {"path": "src/auth.py", "line": 1, "text": "def authenticate(token: str) -> bool:"},
        {"path": "src/auth.py", "line": 2, "text": "    return token == \"demo-token\""},
    ]
    assert payload["scanned_files"] == 1
    assert payload["truncated"] is False


@pytest.mark.asyncio
async def test_searches_unicode_text_with_casefolding(tmp_path: Path) -> None:
    (tmp_path / "unicode.txt").write_text("Straße", encoding="utf-8")
    tool = SearchTextTool(PathPolicy(tmp_path), max_matches=10)

    result = await tool.execute(
        {"query": "STRASSE", "path": ".", "glob": "unicode.txt"}
    )
    payload = json.loads(result.content)

    assert payload["matches"] == [
        {"path": "unicode.txt", "line": 1, "text": "Straße"}
    ]


@pytest.mark.asyncio
async def test_registry_rejects_empty_glob(tmp_path: Path) -> None:
    registry = ToolRegistry([SearchTextTool(PathPolicy(tmp_path))])

    with pytest.raises(InvalidToolArgumentsError):
        await registry.execute("search_text", {"query": "needle", "glob": ""})


@pytest.mark.asyncio
async def test_searches_after_line_500_and_skips_sensitive_files(
    tmp_path: Path,
) -> None:
    source = tmp_path / "src"
    source.mkdir()
    lines = ["ordinary"] * 520 + ["late needle"]
    (source / "long.py").write_text("\n".join(lines), encoding="utf-8")
    (tmp_path / ".env").write_text(
        "SECRET=must-never-be-readable",
        encoding="utf-8",
    )
    tool = SearchTextTool(
        PathPolicy(tmp_path),
        max_matches=10,
        max_files=10,
    )

    result = await tool.execute(
        {"query": "needle", "path": ".", "glob": "src/*.py"}
    )
    payload = json.loads(result.content)

    assert payload["matches"] == [
        {"path": "src/long.py", "line": 521, "text": "late needle"}
    ]
    assert "must-never-be-readable" not in result.content
    assert payload["skipped_files"] == 1


@pytest.mark.asyncio
async def test_stops_after_file_budget(tmp_path: Path) -> None:
    for name in ("a.py", "b.py", "c.py"):
        (tmp_path / name).write_text("needle", encoding="utf-8")
    tool = SearchTextTool(
        PathPolicy(tmp_path),
        max_matches=10,
        max_files=2,
    )

    result = await tool.execute({"query": "needle", "path": "."})
    payload = json.loads(result.content)

    assert payload["scanned_files"] == 2
    assert [match["path"] for match in payload["matches"]] == [
        "a.py",
        "b.py",
    ]
    assert payload["truncated"] is True


@pytest.mark.asyncio
async def test_stops_after_match_budget(tmp_path: Path) -> None:
    (tmp_path / "source.py").write_text(
        "needle one\nneedle two\nneedle three",
        encoding="utf-8",
    )
    tool = SearchTextTool(
        PathPolicy(tmp_path),
        max_matches=2,
        max_files=10,
    )

    result = await tool.execute({"query": "needle", "path": "."})
    payload = json.loads(result.content)

    assert [match["line"] for match in payload["matches"]] == [1, 2]
    assert payload["truncated"] is True


@pytest.mark.asyncio
async def test_exact_match_budget_is_not_marked_truncated(tmp_path: Path) -> None:
    (tmp_path / "source.py").write_text("needle\nneedle", encoding="utf-8")
    tool = SearchTextTool(PathPolicy(tmp_path), max_matches=2)

    result = await tool.execute({"query": "needle", "path": "."})
    payload = json.loads(result.content)

    assert len(payload["matches"]) == 2
    assert payload["truncated"] is False


@pytest.mark.asyncio
async def test_skips_binary_and_oversized_files(tmp_path: Path) -> None:
    (tmp_path / "a-binary.bin").write_bytes(b"a\x00b")
    (tmp_path / "b-large.txt").write_text("1234567", encoding="utf-8")
    (tmp_path / "c-readable.txt").write_text("needle", encoding="utf-8")
    tool = SearchTextTool(
        PathPolicy(tmp_path),
        max_matches=10,
        max_files=10,
        max_file_bytes=6,
    )

    result = await tool.execute({"query": "needle", "path": "."})
    payload = json.loads(result.content)

    assert payload["matches"] == [
        {"path": "c-readable.txt", "line": 1, "text": "needle"}
    ]
    assert payload["scanned_files"] == 3
    assert payload["skipped_files"] == 2


@pytest.mark.parametrize(
    ("keyword", "value"),
    [
        ("max_matches", 0),
        ("max_files", 0),
        ("max_file_bytes", 0),
    ],
)
def test_rejects_non_positive_limits(
    tmp_path: Path,
    keyword: str,
    value: int,
) -> None:
    arguments = {
        "max_matches": 10,
        "max_files": 10,
        "max_file_bytes": 100,
        keyword: value,
    }

    with pytest.raises(ValueError, match="positive"):
        SearchTextTool(PathPolicy(tmp_path), **arguments)
```

- [x] **Step 2: 验证搜索工具尚不存在**

Run: `conda run -n agent-foundations python -m pytest tests/unit/tools/filesystem/test_search_text.py -v`

Expected: FAIL，错误包含 `No module named ...search_text`。

- [x] **Step 3: 实现有上限的纯 Python 搜索**

```python
# src/agent_foundations/tools/filesystem/search_text.py
import json
from collections.abc import Iterator
from pathlib import Path, PurePosixPath
from typing import Any

from agent_foundations.domain.errors import BinaryFileError, FileTooLargeError, PathPolicyViolationError
from agent_foundations.domain.tool import ToolResult
from agent_foundations.tools.filesystem.path_policy import PathPolicy
from agent_foundations.tools.filesystem.read_file import ReadFileTool


class SearchTextTool:
    name = "search_text"
    description = "Search for a literal string in bounded UTF-8 project files."

    def __init__(
        self,
        policy: PathPolicy,
        max_matches: int = 50,
        max_files: int = 1_000,
        max_file_bytes: int = 256_000,
    ) -> None:
        if max_matches < 1 or max_files < 1 or max_file_bytes < 1:
            raise ValueError("search limits must be positive")
        self._policy = policy
        self._max_matches = max_matches
        self._max_files = max_files
        self._reader = ReadFileTool(policy, max_bytes=max_file_bytes)

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1},
                "path": {"type": "string", "default": "."},
                "glob": {"type": "string", "minLength": 1, "default": "*"},
            },
            "required": ["query"],
            "additionalProperties": False,
        }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        base = self._policy.authorize(str(arguments.get("path", ".")))
        query = str(arguments["query"])
        folded_query = query.casefold()
        pattern = str(arguments.get("glob", "*"))
        matches: list[dict[str, object]] = []
        scanned_files = 0
        skipped_files = 0
        truncated = False

        for path in self._candidate_files(base):
            try:
                relative = self._policy.display_path(path)
                self._policy.authorize(relative)
            except (PathPolicyViolationError, ValueError):
                skipped_files += 1
                continue
            if not PurePosixPath(relative).match(pattern):
                continue
            if scanned_files == self._max_files:
                truncated = True
                break
            scanned_files += 1
            try:
                lines = self._reader.read_lines(relative)
            except (BinaryFileError, FileTooLargeError, PathPolicyViolationError):
                skipped_files += 1
                continue
            for number, text in enumerate(lines, start=1):
                if folded_query in text.casefold():
                    if len(matches) == self._max_matches:
                        return self._result(
                            query,
                            matches,
                            scanned_files,
                            skipped_files,
                            truncated=True,
                        )
                    matches.append(
                        {"path": relative, "line": number, "text": text}
                    )
        return self._result(
            query,
            matches,
            scanned_files,
            skipped_files,
            truncated,
        )

    def _candidate_files(self, base: Path) -> Iterator[Path]:
        if base.is_file():
            yield base
            return
        for directory, directory_names, file_names in base.walk():
            directory_names.sort(key=str.casefold)
            file_names.sort(key=str.casefold)
            visible_directories: list[str] = []
            for directory_name in directory_names:
                candidate = directory / directory_name
                try:
                    relative = self._policy.display_path(candidate)
                    self._policy.authorize(relative)
                except (PathPolicyViolationError, ValueError):
                    continue
                visible_directories.append(directory_name)
            directory_names[:] = visible_directories
            for file_name in file_names:
                yield directory / file_name

    @staticmethod
    def _result(
        query: str,
        matches: list[dict[str, object]],
        scanned_files: int,
        skipped_files: int,
        truncated: bool,
    ) -> ToolResult:
        payload = {
            "query": query,
            "matches": matches,
            "scanned_files": scanned_files,
            "skipped_files": skipped_files,
            "truncated": truncated,
        }
        return ToolResult(
            success=True,
            content=json.dumps(payload, ensure_ascii=False),
        )
```

- [x] **Step 4: 验证搜索工具测试通过**

Run: `conda run -n agent-foundations python -m pytest tests/unit/tools/filesystem/test_search_text.py -v`

Expected: `11 passed`。

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

- [x] **Step 1: 写 Session 状态与内存事件测试**

```python
# tests/unit/runtime/test_session.py
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from pydantic import ValidationError

from agent_foundations.domain.messages import Message, Role
from agent_foundations.runtime.session import AgentSession, SessionStatus
from agent_foundations.runtime.trace import (
    EventSink,
    InMemoryEventSink,
    NoOpEventSink,
    TraceEvent,
)


@pytest.mark.asyncio
async def test_session_and_event_have_stable_identity() -> None:
    session = AgentSession(root=Path("."), messages=[Message(role=Role.USER, content="inspect")])
    event = TraceEvent(
        session_id=session.session_id,
        step_id=0,
        event_type="session.started",
        status="started",
        summary="Session started",
    )

    UUID(session.session_id)
    UUID(event.event_id)
    assert session.root == Path(".").resolve()
    assert event.timestamp.tzinfo is not None
    assert event.timestamp.utcoffset() is not None
    session.status = SessionStatus.COMPLETED
    assert session.status is SessionStatus.COMPLETED


def test_session_and_events_get_unique_ids() -> None:
    first_session = AgentSession(root=Path("."))
    second_session = AgentSession(root=Path("."))
    first_event = TraceEvent(
        session_id=first_session.session_id,
        step_id=0,
        event_type="session.started",
        status="started",
        summary="first",
    )
    second_event = TraceEvent(
        session_id=second_session.session_id,
        step_id=0,
        event_type="session.started",
        status="started",
        summary="second",
    )

    assert first_session.session_id != second_session.session_id
    assert first_event.event_id != second_event.event_id


def test_trace_payload_is_deeply_immutable_and_json_safe() -> None:
    event = TraceEvent(
        session_id="session-test",
        step_id=1,
        event_type="tool.call.requested",
        status="started",
        summary="Calling tool",
        payload={"arguments": {"tags": ["safe"]}},
    )

    assert isinstance(event.payload, Mapping)
    assert not isinstance(event.payload, dict)
    payload: Any = event.payload
    with pytest.raises(TypeError):
        payload["arguments"]["tags"][0] = "mutated"
    assert event.model_dump(mode="json")["payload"] == {
        "arguments": {"tags": ["safe"]}
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"bad": b"bytes"},
        {"bad": {"set-value"}},
        {"bad": float("nan")},
    ],
)
def test_trace_rejects_non_json_payload(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        TraceEvent(
            session_id="session-test",
            step_id=0,
            event_type="invalid",
            status="failed",
            summary="invalid payload",
            payload=payload,
        )


@pytest.mark.asyncio
async def test_event_sinks_satisfy_protocol() -> None:
    event = TraceEvent(
        session_id="session-test",
        step_id=0,
        event_type="session.started",
        status="started",
        summary="Session started",
    )
    memory_sink = InMemoryEventSink()
    no_op_sink = NoOpEventSink()

    assert isinstance(memory_sink, EventSink)
    assert isinstance(no_op_sink, EventSink)
    await memory_sink.emit(event)
    await no_op_sink.emit(event)
    assert memory_sink.events == [event]


def test_trace_accepts_any_mapping_payload() -> None:
    """TraceEvent must accept any collections.abc.Mapping, e.g. MappingProxyType."""
    from types import MappingProxyType

    event = TraceEvent(
        session_id="s1", step_id=0, event_type="t", status="ok",
        summary="x", payload=MappingProxyType({"key": "value"}),
    )
    assert isinstance(event.payload, Mapping)
    assert not isinstance(event.payload, dict)
    assert event.payload["key"] == "value"


def test_model_copy_revalidates() -> None:
    """model_copy(update=...) must re-enter validation through ValidatedCopyModel."""
    event = TraceEvent(
        session_id="s1", step_id=0, event_type="t", status="ok",
        summary="x", payload={"items": ["a", "b"]},
    )

    # Legal update
    updated = event.model_copy(update={"summary": "updated"})
    assert updated.summary == "updated"
    assert isinstance(updated.payload, Mapping)
    with pytest.raises(TypeError):
        updated.payload["items"][0] = "mutated"

    # step_id=-1 rejected
    with pytest.raises(ValidationError):
        event.model_copy(update={"step_id": -1})

    # Non-JSON payload through model_copy rejected
    with pytest.raises(ValidationError):
        event.model_copy(update={"payload": {"bad": b"bytes"}})
    with pytest.raises(ValidationError):
        event.model_copy(update={"payload": {"bad": {1, 2}}})
    with pytest.raises(ValidationError):
        event.model_copy(update={"payload": {"bad": float("nan")}})


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_duration_ms_rejects_non_finite_values(bad: float) -> None:
    with pytest.raises(ValidationError):
        TraceEvent(
            session_id="s1", step_id=0, event_type="t", status="ok",
            summary="x", duration_ms=bad,
        )


def test_timestamp_rejects_naive_and_normalizes_to_utc() -> None:
    from datetime import datetime, timedelta, timezone

    # Naive datetime is rejected
    with pytest.raises(ValidationError):
        TraceEvent(
            session_id="s1", step_id=0, event_type="t", status="ok",
            summary="x", timestamp=datetime(2025, 1, 1, 12, 0, 0),
        )

    # Non-UTC timezone-aware datetime is unified to UTC
    jst = timezone(timedelta(hours=9))
    event = TraceEvent(
        session_id="s1", step_id=0, event_type="t", status="ok",
        summary="x", timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=jst),
    )
    assert event.timestamp.utcoffset() == timedelta(0)
    assert event.timestamp.hour == 3


@pytest.mark.parametrize("serialized_form", ["json", "mapping"])
def test_trace_event_round_trips_serialized_timestamp(
    serialized_form: str,
) -> None:
    event = TraceEvent(
        session_id="s1",
        step_id=1,
        event_type="tool.call.completed",
        status="completed",
        summary="Tool completed",
        duration_ms=1.25,
        payload={"result": {"tags": ["safe"]}},
    )

    if serialized_form == "json":
        restored = TraceEvent.model_validate_json(event.model_dump_json())
    else:
        restored = TraceEvent.model_validate(event.model_dump(mode="json"))

    assert restored == event
    assert restored.timestamp.utcoffset() is not None
```

- [x] **Step 2: 验证 Runtime 类型尚不存在**

Run: `conda run -n agent-foundations python -m pytest tests/unit/runtime/test_session.py -v`

Expected: FAIL，错误包含 `No module named 'agent_foundations.runtime'`。

- [x] **Step 3: 实现 Session 和最小事件协议**

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

    def __post_init__(self) -> None:
        self.root = self.root.resolve(strict=True)
        if not self.root.is_dir():
            raise ValueError(f"session root is not a directory: {self.root}")
```

```python
# src/agent_foundations/runtime/trace.py
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Annotated, Any, Protocol, runtime_checkable
from uuid import uuid4

from pydantic import (
    ConfigDict,
    Field,
    PlainSerializer,
    PlainValidator,
    WithJsonSchema,
    field_validator,
)

from agent_foundations.domain._freeze import FrozenJSON, to_json_value
from agent_foundations.domain._model import ValidatedCopyModel


def _freeze_payload(value: Any) -> FrozenJSON:
    """Validate and freeze a JSON-compatible mapping into FrozenJSON."""
    if isinstance(value, FrozenJSON):
        return value
    if isinstance(value, Mapping):
        return FrozenJSON(dict(value))
    raise ValueError(f"expected a mapping, got {type(value).__name__}")


class TraceEvent(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True, allow_inf_nan=False)

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str
    step_id: int = Field(ge=0)
    event_type: str
    status: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    duration_ms: float | None = Field(default=None, ge=0)
    summary: str
    payload: Annotated[
        Mapping[str, Any],
        PlainValidator(_freeze_payload),
        PlainSerializer(to_json_value, return_type=dict[str, Any]),
        WithJsonSchema({"type": "object"}),
    ] = Field(default_factory=lambda: FrozenJSON({}))

    @field_validator("timestamp")
    @classmethod
    def _ensure_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        return value.astimezone(UTC)


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

- [x] **Step 4: 验证 Session 测试通过**

Run: `conda run -n agent-foundations python -m pytest tests/unit/runtime/test_session.py -v`

Expected: `15 passed`（含 MappingProxyType、model_copy 重校验、
`allow_inf_nan=False`、timestamp UTC 归一化与 JSON 回放回归测试）。

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

- [x] **Step 1: 写完整工具循环与最大步数测试**

```python
# tests/integration/test_agent_loop.py
import json
from pathlib import Path
from typing import Any

import pytest

from agent_foundations.context.budget import ContextBudget
from agent_foundations.context.builder import ContextBuilder
from agent_foundations.domain.errors import (
    ContextBudgetExceededError,
    FakeModelExhaustedError,
    MaxStepsExceededError,
)
from agent_foundations.domain.messages import Role
from agent_foundations.domain.model import ModelResponse
from agent_foundations.domain.tool import ToolCall, ToolResult
from agent_foundations.providers.fake import FakeModelProvider
from agent_foundations.runtime.agent import AgentConfig
from agent_foundations.runtime.loop import AgentLoop
from agent_foundations.runtime.trace import InMemoryEventSink
from agent_foundations.tools.filesystem.list_directory import ListDirectoryTool
from agent_foundations.tools.filesystem.path_policy import PathPolicy
from agent_foundations.tools.registry import ToolRegistry


def build_loop(
    responses: list[ModelResponse],
    max_steps: int = 10,
    budget: ContextBudget | None = None,
    registry: ToolRegistry | None = None,
) -> tuple[AgentLoop, InMemoryEventSink, FakeModelProvider]:
    root = Path("tests/fixtures/sample_project").resolve()
    sink = InMemoryEventSink()
    provider = FakeModelProvider(responses)
    loop = AgentLoop(
        provider=provider,
        registry=registry or ToolRegistry([ListDirectoryTool(PathPolicy(root))]),
        context_builder=ContextBuilder(budget or ContextBudget()),
        event_sink=sink,
        config=AgentConfig(max_steps=max_steps),
    )
    return loop, sink, provider


@pytest.mark.asyncio
async def test_agent_executes_tool_then_returns_final_answer() -> None:
    loop, sink, provider = build_loop([
        ModelResponse(tool_calls=(ToolCall(id="c1", name="list_directory", arguments={"path": "."}),)),
        ModelResponse(content="The project contains source code and a README."),
    ])
    result = await loop.run(Path("tests/fixtures/sample_project"), "Summarize the project")
    assert result.answer.startswith("The project")
    assert result.steps == 2
    assert len(provider.requests) == 2
    assert [event.event_type for event in sink.events] == [
        "session.started", "user.message", "model.request.started", "model.response.received",
        "tool.call.requested", "tool.call.validated", "tool.call.completed",
        "model.request.started", "model.response.received", "agent.final_answer", "session.completed",
    ]


@pytest.mark.asyncio
async def test_agent_stops_after_max_steps() -> None:
    repeated = ModelResponse(tool_calls=(ToolCall(id="c1", name="list_directory", arguments={}),))
    loop, sink, _ = build_loop([repeated, repeated], max_steps=2)
    with pytest.raises(MaxStepsExceededError):
        await loop.run(Path("tests/fixtures/sample_project"), "loop forever")
    assert sink.events[-2].event_type == "agent.loop.stopped"
    assert sink.events[-1].event_type == "session.failed"


@pytest.mark.asyncio
async def test_context_budget_failure_is_traced() -> None:
    loop, sink, _ = build_loop(
        [ModelResponse(content="unreachable")],
        budget=ContextBudget(max_chars=1, max_tool_result_chars=1),
    )

    with pytest.raises(ContextBudgetExceededError):
        await loop.run(
            Path("tests/fixtures/sample_project"),
            "query that cannot fit",
        )

    assert sink.events[-1].event_type == "session.failed"
    assert sink.events[-1].payload["error"] == "ContextBudgetExceededError"


@pytest.mark.parametrize(
    ("tool_call", "expected_error"),
    [
        (
            ToolCall(id="unknown", name="missing_tool", arguments={}),
            "UnknownToolError",
        ),
        (
            ToolCall(
                id="invalid",
                name="list_directory",
                arguments={"unexpected": True},
            ),
            "InvalidToolArgumentsError",
        ),
    ],
)
@pytest.mark.asyncio
async def test_tool_validation_failure_is_returned_to_model_and_recovers(
    tool_call: ToolCall,
    expected_error: str,
) -> None:
    loop, sink, provider = build_loop(
        [
            ModelResponse(tool_calls=(tool_call,)),
            ModelResponse(content="Recovered after tool error."),
        ]
    )

    result = await loop.run(
        Path("tests/fixtures/sample_project"),
        "inspect",
    )

    assert result.answer == "Recovered after tool error."
    assert any(event.event_type == "tool.call.failed" for event in sink.events)
    tool_message = provider.requests[1].messages[-1]
    assert tool_message.role is Role.TOOL
    payload = json.loads(tool_message.content or "")
    assert payload["error_code"] == expected_error


@pytest.mark.asyncio
async def test_provider_failure_marks_session_failed() -> None:
    loop, sink, _ = build_loop([])

    with pytest.raises(FakeModelExhaustedError):
        await loop.run(Path("tests/fixtures/sample_project"), "inspect")

    assert sink.events[-1].event_type == "session.failed"
    assert sink.events[-1].payload["error"] == "FakeModelExhaustedError"


class ExplodingTool:
    name = "explode"
    description = "Raise an unexpected implementation error."

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        raise RuntimeError("unexpected tool bug")


@pytest.mark.asyncio
async def test_unexpected_tool_error_marks_session_failed() -> None:
    response = ModelResponse(
        tool_calls=(ToolCall(id="boom", name="explode", arguments={}),)
    )
    loop, sink, _ = build_loop(
        [response],
        registry=ToolRegistry([ExplodingTool()]),
    )

    with pytest.raises(RuntimeError, match="unexpected tool bug"):
        await loop.run(Path("tests/fixtures/sample_project"), "explode")

    assert sink.events[-1].event_type == "session.failed"
    assert sink.events[-1].payload["error"] == "RuntimeError"


def test_agent_config_rejects_non_positive_max_steps() -> None:
    with pytest.raises(ValueError, match="positive"):
        AgentConfig(max_steps=0)
```

- [x] **Step 2: 验证 AgentLoop 尚不存在**

Run: `conda run -n agent-foundations python -m pytest tests/integration/test_agent_loop.py -v`

Expected: FAIL，错误包含 `No module named ...runtime.agent`。

- [x] **Step 3: 实现 Agent 配置与循环**

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
from agent_foundations.domain._freeze import to_json_value
from agent_foundations.domain.errors import (
    ContextBudgetExceededError,
    MaxStepsExceededError,
    ProviderError,
    ToolError,
)
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
            try:
                context = self._context_builder.build(tuple(session.messages))
            except ContextBudgetExceededError as exc:
                session.status = SessionStatus.FAILED
                await self._emit(
                    session,
                    step,
                    "session.failed",
                    "failed",
                    "Context budget exceeded",
                    payload={"error": type(exc).__name__},
                )
                raise
            request = ModelRequest(
                messages=context,
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
                        "raw_response": to_json_value(
                            getattr(exc, "raw_response", None)
                        ),
                    },
                )
                raise
            await self._emit(
                session, step, "model.response.received", "completed", "Model responded",
                duration_ms=(perf_counter() - started) * 1000,
                payload={
                    "content": response.content,
                    "tool_calls": [
                        call.model_dump(mode="json")
                        for call in response.tool_calls
                    ],
                },
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
                call_payload = call.model_dump(mode="json")
                await self._emit(
                    session, step, "tool.call.requested", "started", f"Calling {call.name}",
                    payload={
                        "tool_call_id": call.id,
                        "name": call.name,
                        "arguments": call_payload["arguments"],
                    },
                )
                try:
                    tool, normalized = self._registry.validate_call(
                        call.name,
                        call.arguments,
                    )
                    await self._emit(session, step, "tool.call.validated", "completed", f"Validated {call.name}")
                    result = await tool.execute(normalized)
                except ToolError as exc:
                    result = ToolResult(success=False, content=str(exc), error_code=type(exc).__name__)
                except Exception as exc:
                    session.status = SessionStatus.FAILED
                    await self._emit(
                        session,
                        step,
                        "session.failed",
                        "failed",
                        "Unexpected tool failure",
                        payload={"error": type(exc).__name__},
                    )
                    raise
                event_type = "tool.call.completed" if result.success else "tool.call.failed"
                await self._emit(
                    session, step, event_type, "completed" if result.success else "failed",
                    f"{call.name}: {result.error_code or 'ok'}",
                    payload={
                        "tool_call_id": call.id,
                        "name": call.name,
                        "result": result.model_dump(mode="json"),
                    },
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

- [x] **Step 4: 验证完整循环与终止条件**

Run: `conda run -n agent-foundations python -m pytest tests/integration/test_agent_loop.py -v`

Expected: `8 passed`。

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

**执行补充（2026-07-31）：**

- 当前环境尚未安装 `openai`。先运行 `pip show openai`；若仍未安装，必须在当前
  Task 中取得用户对联网安装的明确确认，然后才可修改环境。
- 安装依赖只是 TDD 前置条件。可以先写测试文件但不得执行；安装完成后运行测试，
  并以 `No module named ...openai_compatible` 作为目标 Red 证据。
- 将下方测试扩展为 10 个 case：2 个请求/响应转换、5 个异常映射和 3 个畸形响应。
  转换测试还必须覆盖：完整四角色消息转换、`name`、
  assistant `tool_calls`、tool `tool_call_id`、工具定义从不可变容器转为普通
  `dict`/`list`、无工具时省略 `tools`/`tool_choice`、有工具时
  `tool_choice="auto"`、缺失 usage 时回落到零。
- 使用参数化测试覆盖 `AuthenticationError`、`RateLimitError`、
  `APITimeoutError`、`APIConnectionError`、`APIStatusError` 五类映射，并验证
  exception chaining（异常链）仍保留原 SDK 异常。
- 使用参数化测试覆盖空 `choices`、非法 JSON arguments、非 object arguments
  三类畸形响应，统一映射为 `InvalidModelResponseError` 并保留可用的
  `raw_response`。
- 全部测试只允许使用 fake client，不配置 API Key，不读取 `.env`，不调用真实
  模型、付费 API 或外部 endpoint。

- [x] **Step 1: 写 SDK 转换与错误映射测试**

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
    assert "tools" not in completions.kwargs
    assert "tool_choice" not in completions.kwargs


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

- [x] **Step 2: 增加 SDK 依赖并验证测试失败**

在 `pyproject.toml` 的 `dependencies` 增加：

```toml
  "openai>=2.46,<3",
```

安装会联网修改 `agent-foundations` 环境，执行前必须先取得用户在当前 Task 中的明确确认。
若用户尚未明确确认，只完成只读预检并停止，不得先写入依赖或安装。

经确认后 Run:

`conda run -n agent-foundations python -m pip install -e ".[dev]"`

Expected: 安装成功。

Run: `conda run -n agent-foundations python -m pytest tests/unit/providers/test_openai_compatible.py -v`

Expected: FAIL，错误包含 `No module named ...openai_compatible`。

- [x] **Step 3: 实现请求、响应和已知错误映射**

```python
# src/agent_foundations/providers/openai_compatible.py
import json
from typing import Any

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    RateLimitError,
)
from pydantic import ValidationError

from agent_foundations.domain._freeze import to_json_value
from agent_foundations.domain.errors import (
    InvalidModelResponseError,
    ProviderError,
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
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": [
                self._message(message)
                for message in request.messages
            ],
        }
        if request.tools:
            kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": to_json_value(tool.parameters),
                    },
                }
                for tool in request.tools
            ]
            kwargs["tool_choice"] = "auto"
        try:
            response = await self._client.chat.completions.create(**kwargs)
        except AuthenticationError as exc:
            raise ProviderAuthenticationError("provider authentication failed") from exc
        except RateLimitError as exc:
            raise ProviderRateLimitError("provider rate limit exceeded") from exc
        except APITimeoutError as exc:
            raise ProviderTimeoutError("provider request timed out") from exc
        except APIConnectionError as exc:
            raise ProviderError("provider connection failed") from exc
        except APIStatusError as exc:
            raise ProviderError(
                f"provider returned HTTP {exc.status_code}"
            ) from exc

        raw = self._raw_response(response)
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
                raw_response=raw,
            )
        except (
            IndexError,
            AttributeError,
            TypeError,
            json.JSONDecodeError,
            ValidationError,
        ) as exc:
            raise InvalidModelResponseError("provider returned an invalid response", raw_response=raw) from exc

    @staticmethod
    def _message(message: Message) -> dict[str, Any]:
        converted: dict[str, Any] = {"role": message.role.value, "content": message.content}
        if message.name is not None and message.role is not Role.TOOL:
            converted["name"] = message.name
        if message.role is Role.ASSISTANT and message.tool_calls:
            converted["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": json.dumps(
                            to_json_value(call.arguments),
                            ensure_ascii=False,
                        ),
                    },
                }
                for call in message.tool_calls
            ]
        if message.role is Role.TOOL:
            converted["tool_call_id"] = message.tool_call_id
        return converted

    @staticmethod
    def _raw_response(response: object) -> dict[str, object] | None:
        model_dump = getattr(response, "model_dump", None)
        if not callable(model_dump):
            return None
        try:
            raw = model_dump(mode="json")
        except Exception:
            return None
        return raw if isinstance(raw, dict) else None
```

这里有意识地继续使用 Chat Completions：第一版 Provider 的目标是兼容常见
OpenAI-compatible endpoint。[官方 Chat Completions API](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)
仍支持 `tools` 与
`tool_choice`；有工具时使用 `auto`，无工具时省略这两个字段。SDK 自带有限重试，
CLI 固定 `max_retries=2`；本 Task 不在 Agent Loop 内叠加第二套重试，避免一次请求
产生不可见的重复调用。

- [x] **Step 4: 验证 Provider 测试通过**

Run: `conda run -n agent-foundations python -m pytest tests/unit/providers/test_openai_compatible.py -v`

Expected: `10 passed`（2 个基础测试、5 个异常映射 case、3 个畸形响应 case）。

随后运行：

```powershell
conda run -n agent-foundations python -m pytest -q
conda run -n agent-foundations python -m ruff check src tests
conda run -n agent-foundations python -m mypy src tests
conda run -n agent-foundations python -m pip check
git diff --check
```

Expected: 全量测试与全部质量门禁通过，没有真实网络请求。

- [x] **Step 5: 检查差异并等待用户验收**

```powershell
git status --short
git diff -- pyproject.toml src/agent_foundations/providers/openai_compatible.py tests/unit/providers/test_openai_compatible.py docs/agent-plans/2026-07-21-phase-1b-readonly-agent-plan.md
```

只勾选具有真实验证证据的步骤。未经用户明确授权，不执行 `git commit`、
`git push`，不进入 Task 8。

## Task 8: 组装 CLI、端到端测试与学习笔记

**Files:**
- Modify: `pyproject.toml`
- Modify: `README.md`
- Create: `.env.example`
- Create: `src/agent_foundations/cli/__init__.py`
- Create: `src/agent_foundations/cli/renderer.py`
- Create: `src/agent_foundations/cli/main.py`
- Create: `tests/e2e/test_cli.py`
- Create: `docs/learning-notes/02-readonly-agent.md`

**执行补充（2026-07-31）：**

- 当前 `typer` 与 `rich` 尚未安装。先运行只读 `pip show`；若仍未安装，必须在
  当前 Task 中取得用户对联网安装的明确确认，才可修改环境。
- Task 8 自动测试不得使用真实 API Key。只使用明显的测试占位符和 fake runtime，
  不读取 `.env`，不调用真实模型或外部 endpoint。
- Typer 在只有一个命令且没有 callback 时会把该命令提升为根命令。由于本项目
  明确要求 `agent-foundations analyze ...`，必须增加无副作用的 `@app.callback()`
  以强制保留 `analyze` 子命令。
- 将下方 E2E 扩展为至少 6 个独立行为：帮助中显示 `analyze`；缺少配置返回 2；
  空白配置也返回 2；fake runtime 成功输出 answer/session/steps；runtime 失败返回 1；
  `build_runtime` 只装配 `list_directory`、`read_file`、`search_text` 三个工具，并
  将 `base_url`、60 秒 timeout、2 次 retry 传给 SDK client。
- 配置和装配测试通过 monkeypatch/fake 对象完成，不得通过真实网络探测配置。
- README 必须明确区分：自动测试已验证、CLI 可用、真实 Provider 调用未验证、
  Phase 1C Trace Viewer 尚未实现。

- [x] **Step 1: 写 CLI 配置拒绝与 Fake Runtime 输出测试**

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

- [x] **Step 2: 增加 CLI 依赖与入口并验证测试失败**

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

安装会联网修改 `agent-foundations` 环境，执行前必须先取得用户在当前 Task 中的明确确认。

经确认后 Run:

`conda run -n agent-foundations python -m pip install -e ".[dev]"`

Expected: 安装成功。

Run: `conda run -n agent-foundations python -m pytest tests/e2e/test_cli.py -v`

Expected: FAIL，错误包含 `No module named 'agent_foundations.cli'`。

- [x] **Step 3: 实现 CLI 依赖组装**

```dotenv
# .env.example
AGENT_API_KEY=replace-with-your-provider-key
AGENT_BASE_URL=https://api.openai.com/v1
AGENT_MODEL=replace-with-your-model-name
```

````markdown
<!-- README.md -->
# Agent Engineering Foundations

Learning-first implementation of a small, testable Agent Runtime.

## Current capability

Phase 1B provides a read-only coding Agent with exactly three tools:

- `list_directory`
- `read_file`
- `search_text`

It cannot write or delete files, execute Shell commands, or operate Git.

## Environment

```powershell
conda create -n agent-foundations python=3.12 -y
conda run -n agent-foundations python -m pip install -e ".[dev]"
```

Do not install the project into the global Python environment.

## Automated verification

```powershell
conda run -n agent-foundations python -m pytest -q
conda run -n agent-foundations python -m ruff check src tests
conda run -n agent-foundations python -m mypy src tests
```

Automated tests use FakeModel or a fake SDK client and do not make paid API
requests.

## CLI configuration

Set configuration only in the current terminal or another local secret manager:

```powershell
$env:AGENT_API_KEY = "your-provider-key"
$env:AGENT_BASE_URL = "https://your-provider.example/v1"
$env:AGENT_MODEL = "your-model"
agent-foundations analyze "D:\path\to\project" "Explain the authentication flow"
```

Never commit a real API key or place it in Trace data. A real model invocation
may incur fees and is only an optional, manually approved Smoke Test.

## Safety boundary

All paths must be relative to the selected project root. The runtime rejects
path escape, sensitive files, binary files, and oversized files. Search and
Agent execution also have hard file, match, context, and step limits.
````

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


@app.callback()
def cli() -> None:
    """Run the read-only Agent CLI."""


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
    missing = [
        name
        for name in ("AGENT_API_KEY", "AGENT_MODEL")
        if not (os.getenv(name) or "").strip()
    ]
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

- [x] **Step 4: 写学习笔记并运行 Milestone 2 门禁**

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

Run: `conda run -n agent-foundations python -m ruff check src tests`

Expected: `All checks passed!`。

Run: `conda run -n agent-foundations python -m mypy src tests`

Expected: `Success: no issues found`。

Run:

```powershell
conda run -n agent-foundations python -m pip check
conda run -n agent-foundations agent-foundations --help
git diff --check
```

Expected: 依赖完整；帮助输出包含 `analyze`；`git diff --check` exit code 为 0。

- [x] **Step 5: 检查差异并等待用户验收**

```powershell
git status --short
git diff -- pyproject.toml README.md .env.example src/agent_foundations/cli tests/e2e/test_cli.py docs/learning-notes/02-readonly-agent.md docs/agent-plans/2026-07-21-phase-1b-readonly-agent-plan.md
```

只勾选具有真实验证证据的步骤。未经用户明确授权，不执行 `git commit`、
`git push`，不运行 Milestone 2 真实 Smoke Test，不进入 Phase 1C。

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

- [x] `ToolRegistry` 能接收真实 `ToolCall.arguments`，并在校验前递归转换为普通 JSON 容器。
- [x] 三个工具均通过 Registry 暴露，不存在第四个隐式工具。
- [x] 路径逃逸、敏感文件、二进制文件和大文件测试通过。
- [x] `search_text` 能搜索第 500 行之后的内容，并受文件数、文件大小和匹配数上限保护。
- [x] Agent Loop 能处理工具成功、工具失败、Context 失败、最终回答和十步终止。
- [x] 自动测试完全使用 FakeModel 或 Fake SDK，不产生网络请求和费用。
- [x] CLI 仅从环境变量读取 Provider 配置，不加载或输出真实密钥。
- [x] `README.md` 说明环境、运行方法、安全边界和真实 API 费用边界。
- [x] pytest、Ruff、mypy 全部通过。
