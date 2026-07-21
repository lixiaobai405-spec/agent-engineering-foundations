# Milestone 1 Agent Foundations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立与具体模型 SDK、文件系统和界面解耦的 Agent 领域模型、Provider、Tool、Registry、Context 和 FakeModel 基础层。

**Architecture:** `domain` 只保存稳定数据结构与错误类型；`providers`、`tools` 和 `context` 依赖这些类型但互不依赖。所有外部行为使用异步协议，单元测试通过 FakeModel 和内存工具确定性验证，不访问网络或真实项目文件。

**Tech Stack:** Python 3.12、Pydantic 2、jsonschema、pytest、pytest-asyncio、Ruff、mypy、Anaconda

---

## 文件结构

```text
pyproject.toml                         # 包元数据、依赖、pytest/Ruff/mypy 配置
README.md                              # 项目入口与当前阶段边界
src/agent_foundations/__init__.py      # 包版本
src/agent_foundations/domain/errors.py # 稳定错误层级
src/agent_foundations/domain/messages.py
src/agent_foundations/domain/tool.py
src/agent_foundations/domain/model.py
src/agent_foundations/providers/base.py
src/agent_foundations/providers/fake.py
src/agent_foundations/tools/registry.py
src/agent_foundations/context/budget.py
src/agent_foundations/context/builder.py
tests/unit/domain/test_models.py
tests/unit/providers/test_fake.py
tests/unit/tools/test_registry.py
tests/unit/context/test_builder.py
tests/contract/test_protocols.py
docs/learning-notes/01-foundations.md
```

## Task 1: 建立可安装、可检查的 Python 项目

**Files:**
- Create: `pyproject.toml`
- Create: `README.md`
- Create: `src/agent_foundations/__init__.py`
- Create: `tests/unit/test_package.py`

- [ ] **Step 1: 写导入失败测试**

```python
# tests/unit/test_package.py
from agent_foundations import __version__


def test_package_exposes_version() -> None:
    assert __version__ == "0.1.0"
```

- [ ] **Step 2: 验证测试先失败**

Run: `conda run -n agent-foundations python -m pytest tests/unit/test_package.py -v`

Expected: FAIL，错误包含 `ModuleNotFoundError: No module named 'agent_foundations'`。

- [ ] **Step 3: 创建项目配置与最小包**

```toml
# pyproject.toml
[build-system]
requires = ["hatchling>=1.27,<2"]
build-backend = "hatchling.build"

[project]
name = "agent-engineering-foundations"
version = "0.1.0"
description = "A learning-first, read-only Python agent runtime"
readme = "README.md"
requires-python = ">=3.12,<3.13"
dependencies = [
  "jsonschema>=4.23,<5",
  "pydantic>=2.10,<3",
]

[project.optional-dependencies]
dev = [
  "mypy>=1.14,<2",
  "pytest>=8.3,<9",
  "pytest-asyncio>=0.25,<1",
  "pytest-cov>=6,<7",
  "ruff>=0.9,<1",
]

[tool.hatch.build.targets.wheel]
packages = ["src/agent_foundations"]

[tool.pytest.ini_options]
addopts = "--strict-markers --strict-config"
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "ASYNC"]

[tool.mypy]
python_version = "3.12"
strict = true
packages = ["agent_foundations"]
```

```python
# src/agent_foundations/__init__.py
__version__ = "0.1.0"
```

```markdown
<!-- README.md -->
# Agent Engineering Foundations

Learning-first implementation of a read-only Python Agent Runtime. The project is built from the protocol layer upward; no file writes, Shell, or Git tools are available in Phase 1.
```

Run: `conda run -n agent-foundations python -m pip install -e ".[dev]"`

Expected: 安装成功，退出码为 `0`。

- [ ] **Step 4: 验证测试通过**

Run: `conda run -n agent-foundations python -m pytest tests/unit/test_package.py -v`

Expected: `1 passed`。

- [ ] **Step 5: 提交项目骨架**

```powershell
git add pyproject.toml README.md src/agent_foundations/__init__.py tests/unit/test_package.py
git commit -m "build: initialize Python agent package"
```

## Task 2: 定义消息、工具和模型领域类型

**Files:**
- Create: `src/agent_foundations/domain/__init__.py`
- Create: `src/agent_foundations/domain/messages.py`
- Create: `src/agent_foundations/domain/tool.py`
- Create: `src/agent_foundations/domain/model.py`
- Test: `tests/unit/domain/test_models.py`

- [ ] **Step 1: 写领域模型失败测试**

```python
# tests/unit/domain/test_models.py
import pytest
from pydantic import ValidationError

from agent_foundations.domain.messages import Message, Role
from agent_foundations.domain.model import ModelRequest, ModelResponse, TokenUsage
from agent_foundations.domain.tool import ToolCall, ToolDefinition


def test_message_preserves_tool_call_relationship() -> None:
    message = Message(
        role=Role.TOOL,
        content='{"entries": ["src"]}',
        name="list_directory",
        tool_call_id="call-1",
    )
    assert message.tool_call_id == "call-1"


def test_model_response_requires_content_or_tool_call() -> None:
    with pytest.raises(ValidationError):
        ModelResponse()


def test_request_contains_model_independent_tool_schema() -> None:
    tool = ToolDefinition(
        name="read_file",
        description="Read a UTF-8 text file",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
    )
    request = ModelRequest(
        messages=(Message(role=Role.USER, content="Inspect the project"),),
        tools=(tool,),
    )
    response = ModelResponse(
        tool_calls=(ToolCall(id="call-1", name="read_file", arguments={"path": "README.md"}),),
        usage=TokenUsage(input_tokens=10, output_tokens=5),
    )
    assert request.tools[0].name == response.tool_calls[0].name
```

- [ ] **Step 2: 验证领域模型尚不存在**

Run: `conda run -n agent-foundations python -m pytest tests/unit/domain/test_models.py -v`

Expected: FAIL，错误包含 `No module named 'agent_foundations.domain'`。

- [ ] **Step 3: 实现不可变领域模型**

```python
# src/agent_foundations/domain/__init__.py
"""Stable domain types shared by the runtime boundaries."""
```

```python
# src/agent_foundations/domain/messages.py
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from agent_foundations.domain.tool import ToolCall


class Role(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class Message(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: Role
    content: str | None = None
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()
```

```python
# src/agent_foundations/domain/tool.py
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field


class ToolCall(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    arguments: dict[str, Any]


class ToolDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    parameters: dict[str, Any]


class ToolResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    success: bool
    content: str
    error_code: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class Tool(Protocol):
    name: str
    description: str

    def input_schema(self) -> dict[str, Any]: ...

    async def execute(self, arguments: dict[str, Any]) -> ToolResult: ...
```

```python
# src/agent_foundations/domain/model.py
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agent_foundations.domain.messages import Message
from agent_foundations.domain.tool import ToolCall, ToolDefinition


class TokenUsage(BaseModel):
    model_config = ConfigDict(frozen=True)

    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)


class ModelRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    messages: tuple[Message, ...]
    tools: tuple[ToolDefinition, ...] = ()


class ModelResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    content: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()
    usage: TokenUsage = TokenUsage()
    raw_response: dict[str, object] | None = None

    @model_validator(mode="after")
    def require_content_or_tool_call(self) -> "ModelResponse":
        if not self.content and not self.tool_calls:
            raise ValueError("model response requires content or at least one tool call")
        return self


@runtime_checkable
class ModelProvider(Protocol):
    async def complete(self, request: ModelRequest) -> ModelResponse: ...
```

- [ ] **Step 4: 验证领域测试通过**

Run: `conda run -n agent-foundations python -m pytest tests/unit/domain/test_models.py -v`

Expected: `3 passed`。

- [ ] **Step 5: 提交领域模型**

```powershell
git add src/agent_foundations/domain tests/unit/domain/test_models.py
git commit -m "feat: define agent domain models"
```

## Task 3: 建立稳定错误层与 FakeModel

**Files:**
- Create: `src/agent_foundations/domain/errors.py`
- Create: `src/agent_foundations/providers/__init__.py`
- Create: `src/agent_foundations/providers/base.py`
- Create: `src/agent_foundations/providers/fake.py`
- Test: `tests/unit/providers/test_fake.py`

- [ ] **Step 1: 写 FakeModel 队列与耗尽测试**

```python
# tests/unit/providers/test_fake.py
import pytest

from agent_foundations.domain.errors import FakeModelExhaustedError
from agent_foundations.domain.messages import Message, Role
from agent_foundations.domain.model import ModelRequest, ModelResponse
from agent_foundations.providers.fake import FakeModelProvider


@pytest.mark.asyncio
async def test_fake_model_returns_scripted_responses_and_records_requests() -> None:
    provider = FakeModelProvider([ModelResponse(content="done")])
    request = ModelRequest(messages=(Message(role=Role.USER, content="inspect"),))

    assert await provider.complete(request) == ModelResponse(content="done")
    assert provider.requests == [request]


@pytest.mark.asyncio
async def test_fake_model_fails_when_script_is_exhausted() -> None:
    provider = FakeModelProvider([])
    request = ModelRequest(messages=(Message(role=Role.USER, content="inspect"),))

    with pytest.raises(FakeModelExhaustedError):
        await provider.complete(request)
```

- [ ] **Step 2: 验证 FakeModel 尚不存在**

Run: `conda run -n agent-foundations python -m pytest tests/unit/providers/test_fake.py -v`

Expected: FAIL，错误包含 `No module named 'agent_foundations.providers'`。

- [ ] **Step 3: 实现错误层与 FakeModel**

```python
# src/agent_foundations/domain/errors.py
class AgentFoundationsError(Exception):
    """Base class for expected runtime failures."""


class ProviderError(AgentFoundationsError):
    pass


class ProviderAuthenticationError(ProviderError):
    pass


class ProviderRateLimitError(ProviderError):
    pass


class ProviderTimeoutError(ProviderError):
    pass


class InvalidModelResponseError(ProviderError):
    def __init__(self, message: str, raw_response: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.raw_response = raw_response


class FakeModelExhaustedError(ProviderError):
    pass


class ToolError(AgentFoundationsError):
    pass


class UnknownToolError(ToolError):
    pass


class InvalidToolArgumentsError(ToolError):
    pass


class PathPolicyViolationError(ToolError):
    pass


class FileTooLargeError(ToolError):
    pass


class BinaryFileError(ToolError):
    pass


class ContextBudgetExceededError(AgentFoundationsError):
    pass


class MaxStepsExceededError(AgentFoundationsError):
    pass
```

```python
# src/agent_foundations/providers/__init__.py
"""Model provider adapters."""
```

```python
# src/agent_foundations/providers/base.py
from agent_foundations.domain.model import ModelProvider

__all__ = ["ModelProvider"]
```

```python
# src/agent_foundations/providers/fake.py
from collections import deque

from agent_foundations.domain.errors import FakeModelExhaustedError
from agent_foundations.domain.model import ModelRequest, ModelResponse


class FakeModelProvider:
    def __init__(self, responses: list[ModelResponse]) -> None:
        self._responses = deque(responses)
        self.requests: list[ModelRequest] = []

    async def complete(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        if not self._responses:
            raise FakeModelExhaustedError("fake model response script is exhausted")
        return self._responses.popleft()
```

- [ ] **Step 4: 验证 FakeModel 测试通过**

Run: `conda run -n agent-foundations python -m pytest tests/unit/providers/test_fake.py -v`

Expected: `2 passed`。

- [ ] **Step 5: 提交 Provider 边界**

```powershell
git add src/agent_foundations/domain/errors.py src/agent_foundations/providers tests/unit/providers/test_fake.py
git commit -m "feat: add provider protocol and fake model"
```

## Task 4: 实现 ToolRegistry 与 JSON Schema 校验

**Files:**
- Create: `src/agent_foundations/tools/__init__.py`
- Create: `src/agent_foundations/tools/registry.py`
- Test: `tests/unit/tools/test_registry.py`

- [ ] **Step 1: 写注册、未知工具与参数校验测试**

```python
# tests/unit/tools/test_registry.py
from typing import Any

import pytest

from agent_foundations.domain.errors import InvalidToolArgumentsError, UnknownToolError
from agent_foundations.domain.tool import ToolResult
from agent_foundations.tools.registry import ToolRegistry


class EchoTool:
    name = "echo"
    description = "Echo a string"

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
            "additionalProperties": False,
        }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, content=str(arguments["text"]))


def test_registry_exports_model_independent_definitions() -> None:
    registry = ToolRegistry([EchoTool()])
    assert registry.definitions()[0].name == "echo"


@pytest.mark.asyncio
async def test_registry_validates_before_execution() -> None:
    registry = ToolRegistry([EchoTool()])
    with pytest.raises(InvalidToolArgumentsError, match="'text' is a required property"):
        await registry.execute("echo", {})


@pytest.mark.asyncio
async def test_registry_rejects_unknown_tool() -> None:
    registry = ToolRegistry([EchoTool()])
    with pytest.raises(UnknownToolError, match="available tools: echo"):
        await registry.execute("missing", {})
```

- [ ] **Step 2: 验证 Registry 测试先失败**

Run: `conda run -n agent-foundations python -m pytest tests/unit/tools/test_registry.py -v`

Expected: FAIL，错误包含 `No module named 'agent_foundations.tools.registry'`。

- [ ] **Step 3: 实现注册和执行边界**

```python
# src/agent_foundations/tools/__init__.py
"""Tool registration and execution boundaries."""
```

```python
# src/agent_foundations/tools/registry.py
from collections.abc import Iterable
from typing import Any

from jsonschema import ValidationError, validate

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

    def validate_call(self, name: str, arguments: dict[str, Any]) -> Tool:
        tool = self._tools.get(name)
        if tool is None:
            available = ", ".join(sorted(self._tools))
            raise UnknownToolError(f"unknown tool '{name}'; available tools: {available}")
        try:
            validate(instance=arguments, schema=tool.input_schema())
        except ValidationError as exc:
            raise InvalidToolArgumentsError(exc.message) from exc
        return tool

    async def execute(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        tool = self.validate_call(name, arguments)
        return await tool.execute(arguments)
```

- [ ] **Step 4: 验证 Registry 测试通过**

Run: `conda run -n agent-foundations python -m pytest tests/unit/tools/test_registry.py -v`

Expected: `3 passed`。

- [ ] **Step 5: 提交 ToolRegistry**

```powershell
git add src/agent_foundations/tools tests/unit/tools/test_registry.py
git commit -m "feat: add validated tool registry"
```

## Task 5: 实现 Context Budget 与消息构建器

**Files:**
- Create: `src/agent_foundations/context/__init__.py`
- Create: `src/agent_foundations/context/budget.py`
- Create: `src/agent_foundations/context/builder.py`
- Test: `tests/unit/context/test_builder.py`

- [ ] **Step 1: 写优先级与截断测试**

```python
# tests/unit/context/test_builder.py
from agent_foundations.context.budget import ContextBudget
from agent_foundations.context.builder import ContextBuilder
from agent_foundations.domain.messages import Message, Role


def test_builder_keeps_system_and_latest_user_message() -> None:
    builder = ContextBuilder(ContextBudget(max_chars=45, max_tool_result_chars=12))
    messages = (
        Message(role=Role.SYSTEM, content="You are read-only."),
        Message(role=Role.USER, content="old request"),
        Message(role=Role.TOOL, content="abcdefghijklmnopqrstuvwxyz", tool_call_id="c1"),
        Message(role=Role.USER, content="latest request"),
    )

    result = builder.build(messages)

    assert result[0].role is Role.SYSTEM
    assert result[-1].content == "latest request"
    assert all(message.content != "old request" for message in result)
    assert any(message.content == "abcdefghi..." for message in result)


def test_builder_does_not_mutate_source_messages() -> None:
    source = Message(role=Role.TOOL, content="123456", tool_call_id="c1")
    ContextBuilder(ContextBudget(max_chars=100, max_tool_result_chars=4)).build((source,))
    assert source.content == "123456"
```

- [ ] **Step 2: 验证 Context 模块尚不存在**

Run: `conda run -n agent-foundations python -m pytest tests/unit/context/test_builder.py -v`

Expected: FAIL，错误包含 `No module named 'agent_foundations.context'`。

- [ ] **Step 3: 实现确定性预算算法**

```python
# src/agent_foundations/context/__init__.py
"""Context selection and character budgeting."""
```

```python
# src/agent_foundations/context/budget.py
from dataclasses import dataclass


@dataclass(frozen=True)
class ContextBudget:
    max_chars: int = 32_000
    max_tool_result_chars: int = 8_000

    def __post_init__(self) -> None:
        if self.max_chars < 1 or self.max_tool_result_chars < 1:
            raise ValueError("context limits must be positive")
```

```python
# src/agent_foundations/context/builder.py
from agent_foundations.context.budget import ContextBudget
from agent_foundations.domain.messages import Message, Role


class ContextBuilder:
    def __init__(self, budget: ContextBudget) -> None:
        self._budget = budget

    def build(self, messages: tuple[Message, ...]) -> tuple[Message, ...]:
        normalized = tuple(self._truncate_tool_message(message) for message in messages)
        system = tuple(message for message in normalized if message.role is Role.SYSTEM)
        non_system = tuple(message for message in normalized if message.role is not Role.SYSTEM)
        selected: list[Message] = list(system)
        used = sum(self._size(message) for message in selected)

        recent: list[Message] = []
        for message in reversed(non_system):
            size = self._size(message)
            if used + size <= self._budget.max_chars or not recent:
                recent.append(message)
                used += size
        selected.extend(reversed(recent))
        return tuple(selected)

    def _truncate_tool_message(self, message: Message) -> Message:
        if message.role is not Role.TOOL or message.content is None:
            return message
        limit = self._budget.max_tool_result_chars
        if len(message.content) <= limit:
            return message
        suffix = "..."
        return message.model_copy(update={"content": message.content[: limit - len(suffix)] + suffix})

    @staticmethod
    def _size(message: Message) -> int:
        return len(message.content or "")
```

- [ ] **Step 4: 验证 Context 测试通过**

Run: `conda run -n agent-foundations python -m pytest tests/unit/context/test_builder.py -v`

Expected: `2 passed`。

- [ ] **Step 5: 提交 ContextBuilder**

```powershell
git add src/agent_foundations/context tests/unit/context/test_builder.py
git commit -m "feat: add deterministic context budgeting"
```

## Task 6: 增加协议契约、质量门禁和学习笔记

**Files:**
- Create: `tests/contract/test_protocols.py`
- Create: `docs/learning-notes/01-foundations.md`

- [ ] **Step 1: 写运行时协议契约测试**

```python
# tests/contract/test_protocols.py
from typing import Any

from agent_foundations.domain.model import ModelProvider, ModelRequest, ModelResponse
from agent_foundations.domain.tool import Tool, ToolResult
from agent_foundations.providers.fake import FakeModelProvider


class ContractTool:
    name = "contract"
    description = "Contract test tool"

    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "additionalProperties": False}

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, content="ok")


def test_fake_model_satisfies_provider_protocol() -> None:
    assert isinstance(FakeModelProvider([ModelResponse(content="ok")]), ModelProvider)


def test_tool_implementation_satisfies_tool_protocol() -> None:
    assert isinstance(ContractTool(), Tool)


async def _type_check_provider(provider: ModelProvider, request: ModelRequest) -> ModelResponse:
    return await provider.complete(request)
```

- [ ] **Step 2: 运行契约测试**

Run: `conda run -n agent-foundations python -m pytest tests/contract/test_protocols.py -v`

Expected: `2 passed`。

- [ ] **Step 3: 写基础层学习笔记**

```markdown
# 01 Foundations 学习笔记

## 本周实现

- `Message` 统一保存角色、内容和工具调用关系。
- `ModelProvider` 隔离 Agent Runtime 与具体 SDK。
- `Tool` 通过 JSON Schema 公开参数契约。
- `ContextBuilder` 用确定性字符预算控制第一版上下文。
- `FakeModelProvider` 让 Agent 行为可重复测试。

## 关键取舍

1. 领域模型不直接使用 OpenAI SDK 类型，否则更换 Provider 会影响 Runtime。
2. Registry 在执行前校验参数，具体 Tool 不重复承担通用校验。
3. 第一版使用字符预算，不假装不同模型具有相同 tokenizer；Token 预算在 Context Engineering 阶段实现。
4. FakeModel 是测试基础设施，不是线上降级模型。

## 与参考项目对照问题

- smolagents 如何表示消息与工具调用？
- OpenAI Agents SDK 在哪里执行工具参数校验？
- 哪些成熟抽象适合当前阶段，哪些属于过早设计？
```

- [ ] **Step 4: 运行 Milestone 1 全量门禁**

Run: `conda run -n agent-foundations python -m pytest tests/unit tests/contract -q`

Expected: 所有测试通过。

Run: `conda run -n agent-foundations python -m ruff check src tests`

Expected: `All checks passed!`。

Run: `conda run -n agent-foundations python -m mypy src tests`

Expected: `Success: no issues found`。

- [ ] **Step 5: 提交 Milestone 1 验收材料**

```powershell
git add tests/contract/test_protocols.py docs/learning-notes/01-foundations.md
git commit -m "test: verify foundation protocols"
```

## Milestone 1 完成条件

- [ ] 所有领域模型不可变且通过 Pydantic 校验。
- [ ] FakeModel 能记录请求并按脚本返回结果。
- [ ] ToolRegistry 能导出 Schema、拒绝未知工具并在执行前验证参数。
- [ ] ContextBuilder 的选择与截断结果可重复。
- [ ] 单元、契约、Ruff、mypy 全部通过。
- [ ] 学习笔记完成，并记录与 smolagents、OpenAI Agents SDK 的只读对照结论。
