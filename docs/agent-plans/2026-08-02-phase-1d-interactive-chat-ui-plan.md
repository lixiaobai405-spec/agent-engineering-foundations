# Phase 1D Interactive Chat UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `subagent-driven-development` (recommended) or `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有只读 Agent Runtime 上增加本机 React Chat UI、多轮 SQLite 对话、实时工具活动、完整 Trace 跳转，以及项目外只读访问的一次性审批。

**Architecture:** React Chat 是控制面，现有 Trace Viewer 是观察面；FastAPI 通过 HTTP 与 SSE 连接两者。SQLite 只保存对话业务状态，JSONL 继续保存完整运行事实；`ConversationRunner` 编排 Runtime，`RunSupervisor` 管理任务，`ApprovalCoordinator` 处理一次性精确授权。

**Tech Stack:** Python 3.12、Anaconda、FastAPI、Pydantic 2、标准库 `sqlite3`、SSE、React、TypeScript、Vite、Vitest、Testing Library、pytest、Playwright。

**Approved design:** `docs/agent-plans/2026-08-02-phase-1d-interactive-chat-ui-design.md`

---

## 0. 执行规则

- 一次只执行一个 Task；当前 Task 验收前不得开始下一 Task。
- 每个代码 Task 必须展示真实 Red，再写最小实现并展示 Green。
- Python 命令使用 `conda run -n agent-foundations ...`，不得使用全局 Python。
- 自动测试只用 FakeModel 和临时目录，不读取真实项目外文件，不调用真实或付费模型。
- Task 10 才允许安装 React/Vite 依赖，执行安装前必须单独征得用户确认。
- 计划中的 commit 是建议检查点，不构成授权。只有用户明确要求时才执行；不得 push 或创建 PR。
- 保护当前工作区已有 Phase 1B/1C 未提交改动，不回滚、不覆盖、不混入无关修改。
- 不添加 `# type: ignore`、`# noqa`，不弱化测试、脱敏、路径或审批断言。
- 每个 Task 结束至少执行目标 pytest、受影响 Ruff/mypy、`git diff --check` 和 `git status --short`。

## 1. 最终文件结构

```text
src/agent_foundations/chat/
├─ __init__.py
├─ api.py                 # Chat HTTP/SSE router 与 request/response schema
├─ approvals.py           # ApprovalCoordinator 与一次性决策
├─ events.py              # ChatEventBroker、Trace 投影和 SSE 编码
├─ models.py              # Conversation/Message/Run/Approval/ChatEvent
├─ repository.py          # sqlite3 schema、CRUD、事务与恢复
├─ runner.py              # 一轮对话编排
├─ supervisor.py          # asyncio.Task 生命周期与每对话单运行约束
└─ tool_execution.py      # 项目内直接执行与项目外审批执行

web/chat/
├─ components/
│  ├─ ActivityCard.tsx
│  ├─ ApprovalCard.tsx
│  ├─ ChatComposer.tsx
│  ├─ ConversationList.tsx
│  └─ MessageTimeline.tsx
├─ state/
│  ├─ api.ts
│  ├─ events.ts
│  ├─ reducer.ts
│  └─ types.ts
├─ App.tsx
├─ index.html
├─ main.tsx
└─ styles.css

tests/unit/chat/
├─ test_approvals.py
├─ test_events.py
├─ test_models.py
├─ test_repository.py
├─ test_runner.py
├─ test_supervisor.py
└─ test_tool_execution.py

tests/integration/
├─ test_chat_api.py
└─ test_chat_approval_flow.py

tests/chat/
├─ activity.test.tsx
├─ app.test.tsx
├─ reducer.test.ts
└─ setup.ts

tests/e2e/test_chat_ui.py
```

现有文件只做最小修改：

- `src/agent_foundations/runtime/loop.py`：支持可见历史、指定 `session_id` 和可注入 `ToolCallExecutor`。
- `src/agent_foundations/runtime/session.py`：验证外部注入的 UUID session id。
- `src/agent_foundations/tools/filesystem/path_policy.py`：增加“不代表授权”的绝对路径规范化/敏感校验 helper。
- `src/agent_foundations/viewer/app.py`：保留 Trace-only 模式，并允许挂载 Chat router 与 `/trace`。
- `src/agent_foundations/viewer/static/app.ts`：支持 URL 中的 `session_id` 自动选择历史 Trace。
- `src/agent_foundations/cli/main.py`：增加 `chat` 命令，现有 `analyze`/`viewer` 保持兼容。
- `package.json`、`package-lock.json`、`tsconfig.chat.json`、`vite.config.ts`、`vitest.config.ts`：Chat 构建与测试。
- `.gitignore`：忽略 `.agent-foundations/` 与 Vite 临时输出。
- `AGENTS.md`、`README.md`、学习笔记和 Phase 计划：阶段边界与运行说明。

---

## Task 1: 建立 Chat 领域模型并切换阶段边界

**Files:**

- Create: `src/agent_foundations/chat/__init__.py`
- Create: `src/agent_foundations/chat/models.py`
- Create: `src/agent_foundations/chat/errors.py`
- Create: `tests/unit/chat/__init__.py`
- Create: `tests/unit/chat/test_models.py`
- Modify: `AGENTS.md`

- [x] **Step 1: 检查已有改动并记录 Phase 1D 授权来源**

Run:

```powershell
git status --short
git diff -- AGENTS.md
```

Expected: 看见并保留用户已有 Phase 1B/1C 改动；不得清理工作区。用户已于 2026-08-02 确认 Phase 1D 设计。

- [x] **Step 2: 写领域模型失败测试**

`tests/unit/chat/test_models.py` 至少包含：

```python
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from pydantic import ValidationError

from agent_foundations.chat.models import (
    ApprovalRequest,
    ApprovalStatus,
    AccessOperation,
    AccessScope,
    ChatEvent,
    ChatEventType,
    ChatMessage,
    Conversation,
    MessageRole,
    PermissionMode,
    PolicyDecision,
    ResourceKind,
    RunRecord,
    RunStatus,
)


NOW = datetime(2026, 8, 2, tzinfo=UTC)


def test_conversation_normalizes_existing_project_root(tmp_path: Path) -> None:
    conversation = Conversation(
        conversation_id="11111111-1111-4111-8111-111111111111",
        title="Learn Agent Runtime",
        project_root=str(tmp_path),
        permission_mode=PermissionMode.PROJECT_READ_ONLY,
        created_at=NOW,
        updated_at=NOW,
    )
    assert conversation.project_root == str(tmp_path.resolve())
    assert conversation.permission_mode.value == "PROJECT_READ_ONLY"


def test_conversation_rejects_missing_root(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="existing directory"):
        Conversation(
            conversation_id="11111111-1111-4111-8111-111111111111",
            title="Invalid",
            project_root=str(tmp_path / "missing"),
            permission_mode=PermissionMode.ASK_FOR_ACCESS,
            created_at=NOW,
            updated_at=NOW,
        )


def test_run_and_approval_identifiers_are_validated(tmp_path: Path) -> None:
    run = RunRecord(
        session_id="22222222-2222-4222-8222-222222222222",
        conversation_id="11111111-1111-4111-8111-111111111111",
        user_message_id="33333333-3333-4333-8333-333333333333",
        trace_path="traces/22222222-2222-4222-8222-222222222222.jsonl",
        status=RunStatus.QUEUED,
        created_at=NOW,
    )
    UUID(run.session_id)
    approval = ApprovalRequest(
        approval_id="44444444-4444-4444-8444-444444444444",
        conversation_id=run.conversation_id,
        session_id=run.session_id,
        tool_call_id="call-1",
        tool_name="read_file",
        canonical_path=str(tmp_path.resolve()),
        operation="read",
        status=ApprovalStatus.PENDING,
        requested_at=NOW,
    )
    assert approval.operation == "read"
    with pytest.raises(ValidationError):
        approval.model_copy(update={"operation": "write"})


def test_chat_event_is_utc_frozen_and_json_safe() -> None:
    event = ChatEvent(
        event_id="55555555-5555-4555-8555-555555555555",
        conversation_id="11111111-1111-4111-8111-111111111111",
        session_id="22222222-2222-4222-8222-222222222222",
        type=ChatEventType.RUN_STARTED,
        occurred_at=NOW,
        data={"status": "running"},
    )
    assert event.model_dump(mode="json")["data"] == {"status": "running"}
    mutable_view: Any = event.data
    with pytest.raises(TypeError):
        mutable_view["status"] = "changed"


def test_visible_message_roles_exclude_system_and_tool() -> None:
    assert {role.value for role in MessageRole} == {"user", "assistant"}
    assert RunStatus.active() == {
        RunStatus.QUEUED,
        RunStatus.RUNNING,
        RunStatus.WAITING_APPROVAL,
    }


def test_access_dimensions_are_explicit() -> None:
    assert ResourceKind.FILESYSTEM.value == "filesystem"
    assert AccessOperation.READ.value == "read"
    assert {scope.value for scope in AccessScope} == {"project", "external_exact_path"}
    assert {decision.value for decision in PolicyDecision} == {"allow", "deny", "ask"}
```

- [x] **Step 3: 运行测试确认 Red**

Run:

```powershell
conda run -n agent-foundations python -m pytest tests/unit/chat/test_models.py -q
```

Expected: collection FAIL because `agent_foundations.chat` does not exist.

- [x] **Step 4: 实现冻结且可验证的领域模型**

`src/agent_foundations/chat/models.py` 必须定义这些稳定名称和字段：

```python
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID, uuid4

from pydantic import AfterValidator, ConfigDict, Field, PlainSerializer, PlainValidator, WithJsonSchema, field_validator

from agent_foundations.domain._freeze import FrozenJSON, to_json_value
from agent_foundations.domain._model import ValidatedCopyModel


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid4())


def _valid_uuid(value: str) -> str:
    UUID(value)
    return value


def _utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


def _relative_trace_path(value: str) -> str:
    path = Path(value)
    if not path.parts or path.drive or path.is_absolute() or ".." in path.parts:
        raise ValueError("trace_path must be a relative trace path")
    return path.as_posix()


UUIDString = Annotated[str, AfterValidator(_valid_uuid)]
UTCDateTime = Annotated[datetime, AfterValidator(_utc_datetime)]
RelativeTracePath = Annotated[str, AfterValidator(_relative_trace_path)]


def _freeze_data(value: Any) -> FrozenJSON:
    if isinstance(value, FrozenJSON):
        return value
    if not isinstance(value, dict):
        raise ValueError("chat event data must be an object")
    return FrozenJSON(value)


class PermissionMode(StrEnum):
    PROJECT_READ_ONLY = "PROJECT_READ_ONLY"
    ASK_FOR_ACCESS = "ASK_FOR_ACCESS"


class ResourceKind(StrEnum):
    FILESYSTEM = "filesystem"


class AccessOperation(StrEnum):
    READ = "read"


class AccessScope(StrEnum):
    PROJECT = "project"
    EXTERNAL_EXACT_PATH = "external_exact_path"


class PolicyDecision(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"

    @classmethod
    def active(cls) -> set["RunStatus"]:
        return {cls.QUEUED, cls.RUNNING, cls.WAITING_APPROVAL}


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    INVALIDATED = "invalidated"


class ChatEventType(StrEnum):
    RUN_STARTED = "run.started"
    MODEL_REQUESTED = "model.requested"
    TOOL_REQUESTED = "tool.requested"
    TOOL_COMPLETED = "tool.completed"
    TOOL_FAILED = "tool.failed"
    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_RESOLVED = "approval.resolved"
    ASSISTANT_MESSAGE_COMPLETED = "assistant.message.completed"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"


class ChatModel(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True)


class AccessDecision(ChatModel):
    resource: ResourceKind = ResourceKind.FILESYSTEM
    operation: AccessOperation = AccessOperation.READ
    scope: AccessScope
    decision: PolicyDecision
    canonical_path: str


class Conversation(ChatModel):
    conversation_id: UUIDString = Field(default_factory=new_id)
    title: str = Field(min_length=1, max_length=120)
    project_root: str
    permission_mode: PermissionMode
    created_at: UTCDateTime = Field(default_factory=utc_now)
    updated_at: UTCDateTime = Field(default_factory=utc_now)

    @field_validator("project_root")
    @classmethod
    def existing_root(cls, value: str) -> str:
        try:
            path = Path(value).resolve(strict=True)
        except (OSError, ValueError) as exc:
            raise ValueError("project_root must be an existing directory") from exc
        if not path.is_dir():
            raise ValueError("project_root must be an existing directory")
        return str(path)


class ChatMessage(ChatModel):
    message_id: UUIDString = Field(default_factory=new_id)
    conversation_id: UUIDString
    role: MessageRole
    content: str = Field(min_length=1)
    sequence: int = Field(ge=1)
    created_at: UTCDateTime = Field(default_factory=utc_now)


class RunRecord(ChatModel):
    session_id: UUIDString = Field(default_factory=new_id)
    conversation_id: UUIDString
    user_message_id: UUIDString
    trace_path: RelativeTracePath
    assistant_message_id: UUIDString | None = None
    status: RunStatus = RunStatus.QUEUED
    error_code: str | None = None
    created_at: UTCDateTime = Field(default_factory=utc_now)
    started_at: UTCDateTime | None = None
    finished_at: UTCDateTime | None = None


class ApprovalRequest(ChatModel):
    approval_id: UUIDString = Field(default_factory=new_id)
    conversation_id: UUIDString
    session_id: UUIDString
    tool_call_id: str = Field(min_length=1)
    tool_name: str = Field(min_length=1)
    canonical_path: str
    operation: AccessOperation = AccessOperation.READ
    status: ApprovalStatus = ApprovalStatus.PENDING
    requested_at: UTCDateTime = Field(default_factory=utc_now)
    decided_at: UTCDateTime | None = None


class ChatEvent(ChatModel):
    event_id: UUIDString = Field(default_factory=new_id)
    conversation_id: UUIDString
    session_id: UUIDString
    type: ChatEventType
    occurred_at: UTCDateTime = Field(default_factory=utc_now)
    data: Annotated[
        FrozenJSON,
        PlainValidator(_freeze_data),
        PlainSerializer(to_json_value, return_type=dict[str, Any]),
        WithJsonSchema({"type": "object"}),
    ] = Field(default_factory=lambda: FrozenJSON({}))
```

The tests must include invalid IDs and naive datetimes for each record type, proving the
reusable annotated validators apply everywhere. `RunRecord.trace_path` is required, remains
relative to the configured Trace directory, and rejects absolute paths, drive-qualified paths,
and `..` traversal.

`src/agent_foundations/chat/errors.py`:

```python
class ChatError(Exception):
    """Base error for deterministic Chat control-plane failures."""


class ChatNotFoundError(ChatError):
    pass


class ChatConflictError(ChatError):
    pass


class ApprovalUnavailableError(ChatConflictError):
    pass
```

- [x] **Step 5: 更新 `AGENTS.md` 当前阶段边界**

Replace the Phase 1C-only statement with: Phase 1A–1C are user-accepted; Phase 1D is current; the approved design and this plan are authoritative. Add allowed Phase 1D capabilities and retain explicit prohibitions on write/Shell/Git/network/real paid tests. Do not rewrite unrelated global rules.

- [x] **Step 6: 运行 Green 与质量检查**

Run:

```powershell
conda run -n agent-foundations python -m pytest tests/unit/chat/test_models.py -q
conda run -n agent-foundations python -m ruff check src/agent_foundations/chat tests/unit/chat
conda run -n agent-foundations python -m mypy src tests
git diff --check
```

Expected: all commands exit `0`; no ignore comments or unrelated modifications.

- [x] **Step 7: 检查提交范围**

Run:

```powershell
git diff -- AGENTS.md src/agent_foundations/chat tests/unit/chat
git status --short
```

Suggested commit, only after explicit authorization:

```powershell
git add AGENTS.md src/agent_foundations/chat tests/unit/chat
git commit -m "feat: add phase 1d chat domain models"
```

---

## Task 2: 实现 SQLite schema 与 Conversation Repository

**Files:**

- Create: `src/agent_foundations/chat/repository.py`
- Create: `tests/unit/chat/test_repository.py`
- Modify: `.gitignore`

- [x] **Step 1: 写 schema、创建、查询和更新失败测试**

Tests must cover:

```python
@pytest.mark.asyncio
async def test_initialize_and_conversation_crud(tmp_path: Path) -> None:
    repository = ConversationRepository(tmp_path / "state" / "chat.sqlite3")
    await repository.initialize()
    created = await repository.create_conversation(
        title="Runtime study",
        project_root=tmp_path,
        permission_mode=PermissionMode.PROJECT_READ_ONLY,
    )
    assert await repository.get_conversation(created.conversation_id) == created
    assert await repository.list_conversations() == [created]
    updated = await repository.update_conversation(
        created.conversation_id,
        title="Updated title",
        permission_mode=PermissionMode.ASK_FOR_ACCESS,
    )
    assert updated.title == "Updated title"


@pytest.mark.asyncio
async def test_schema_enables_foreign_keys_and_version(tmp_path: Path) -> None:
    path = tmp_path / "chat.sqlite3"
    repository = ConversationRepository(path)
    await repository.initialize()
    with repository._connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (1,)
        assert connection.execute("PRAGMA foreign_keys").fetchone() == (1,)


@pytest.mark.asyncio
async def test_missing_conversation_raises_not_found(tmp_path: Path) -> None:
    repository = ConversationRepository(tmp_path / "chat.sqlite3")
    await repository.initialize()
    with pytest.raises(ChatNotFoundError):
        await repository.get_conversation("11111111-1111-4111-8111-111111111111")
```

Also assert list ordering is `updated_at DESC, conversation_id ASC`, root is canonical, title is stripped, empty title is rejected, and `.agent-foundations/` is ignored.

- [x] **Step 2: 运行 Red**

```powershell
conda run -n agent-foundations python -m pytest tests/unit/chat/test_repository.py -q
```

Expected: FAIL because `ConversationRepository` is missing.

- [x] **Step 3: 实现 schema v1 和连接边界**

`repository.py` must use one connection per worker-thread operation:

```python
class ConversationRepository:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path.resolve()

    async def initialize(self) -> None:
        await asyncio.to_thread(self._initialize_sync)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection
```

`_initialize_sync` creates the parent directory, rejects `PRAGMA user_version > 1`, applies the complete schema in one transaction, and sets version `1`. Required constraints:

```sql
CREATE TABLE conversations (
  conversation_id TEXT PRIMARY KEY,
  title TEXT NOT NULL CHECK(length(trim(title)) BETWEEN 1 AND 120),
  project_root TEXT NOT NULL,
  permission_mode TEXT NOT NULL CHECK(permission_mode IN ('PROJECT_READ_ONLY','ASK_FOR_ACCESS')),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE messages (
  message_id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id),
  role TEXT NOT NULL CHECK(role IN ('user','assistant')),
  content TEXT NOT NULL CHECK(length(content) > 0),
  sequence INTEGER NOT NULL CHECK(sequence >= 1),
  created_at TEXT NOT NULL,
  UNIQUE(conversation_id, sequence)
);
CREATE TABLE runs (
  session_id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id),
  user_message_id TEXT NOT NULL REFERENCES messages(message_id),
  assistant_message_id TEXT REFERENCES messages(message_id),
  trace_path TEXT NOT NULL CHECK(length(trim(trace_path)) > 0),
  status TEXT NOT NULL CHECK(status IN ('queued','running','waiting_approval','completed','failed','interrupted')),
  error_code TEXT,
  created_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT
);
CREATE UNIQUE INDEX one_active_run_per_conversation
ON runs(conversation_id)
WHERE status IN ('queued','running','waiting_approval');
CREATE TABLE approval_requests (
  approval_id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id),
  session_id TEXT NOT NULL REFERENCES runs(session_id),
  tool_call_id TEXT NOT NULL,
  tool_name TEXT NOT NULL,
  canonical_path TEXT NOT NULL,
  operation TEXT NOT NULL CHECK(operation = 'read'),
  status TEXT NOT NULL CHECK(status IN ('pending','approved','denied','invalidated')),
  requested_at TEXT NOT NULL,
  decided_at TEXT,
  UNIQUE(session_id, tool_call_id)
);
```

Implement row-to-model functions that call Pydantic validation. Do not return raw `sqlite3.Row` outside the repository.

- [x] **Step 4: 实现 Conversation CRUD**

Implement exact async signatures:

```python
async def create_conversation(
    self, *, title: str, project_root: Path, permission_mode: PermissionMode
) -> Conversation: ...
async def get_conversation(self, conversation_id: str) -> Conversation: ...
async def list_conversations(self) -> list[Conversation]: ...
async def update_conversation(
    self,
    conversation_id: str,
    *,
    title: str | None = None,
    permission_mode: PermissionMode | None = None,
) -> Conversation: ...
```

Each async method delegates the complete transaction to one `asyncio.to_thread` call. `update_conversation` must reject permission changes when an active run or pending approval exists by raising `ChatConflictError`.

- [x] **Step 5: 运行 Green 和并发回归**

```powershell
conda run -n agent-foundations python -m pytest tests/unit/chat/test_repository.py -q
conda run -n agent-foundations python -m ruff check src/agent_foundations/chat/repository.py tests/unit/chat/test_repository.py
conda run -n agent-foundations python -m mypy src tests
git diff --check
```

Expected: PASS; no connection is reused across threads.

- [x] **Step 6: 检查范围并等待授权**

Suggested commit:

```powershell
git add .gitignore src/agent_foundations/chat/repository.py tests/unit/chat/test_repository.py
git commit -m "feat: persist chat conversations in sqlite"
```

---

## Task 3: 实现消息、Run 和审批的原子持久化

**Files:**

- Modify: `src/agent_foundations/chat/repository.py`
- Modify: `tests/unit/chat/test_repository.py`

- [x] **Step 1: 写原子状态转换失败测试**

Add tests for these exact behaviors:

```python
user_message, run = await repository.begin_run(
    conversation_id,
    content="first question",
    session_id="22222222-2222-4222-8222-222222222222",
)
assert user_message.sequence == 1
assert run.status is RunStatus.QUEUED
await repository.transition_run(run.session_id, RunStatus.QUEUED, RunStatus.RUNNING)
assistant = await repository.complete_run(run.session_id, "final answer")
assert assistant.role is MessageRole.ASSISTANT
assert assistant.sequence == 2
assert (await repository.get_run(run.session_id)).assistant_message_id == assistant.message_id
```

Also test:

- second active run for the same conversation raises `ChatConflictError` and does not insert a user message;
- invalid `queued → completed` and terminal-state transitions raise `ChatConflictError`;
- `list_context_before(conversation_id, user_message_id)` returns only earlier visible messages in sequence;
- `fail_run` stores only stable `error_code`, not exception text;
- `create_approval` requires a `waiting_approval` run and is unique per tool call;
- `resolve_approval` performs only `pending → approved|denied` once;
- `interrupt_unfinished` maps queued/running/waiting runs to interrupted and pending approvals to invalidated in one transaction.

- [x] **Step 2: 运行 Red**

```powershell
conda run -n agent-foundations python -m pytest tests/unit/chat/test_repository.py -q
```

Expected: new tests FAIL because run/message methods do not exist.

- [x] **Step 3: 实现明确状态机**

Add this transition table and reject all other edges:

```python
_RUN_TRANSITIONS = {
    RunStatus.QUEUED: {RunStatus.RUNNING, RunStatus.FAILED, RunStatus.INTERRUPTED},
    RunStatus.RUNNING: {
        RunStatus.WAITING_APPROVAL,
        RunStatus.COMPLETED,
        RunStatus.FAILED,
        RunStatus.INTERRUPTED,
    },
    RunStatus.WAITING_APPROVAL: {
        RunStatus.RUNNING,
        RunStatus.FAILED,
        RunStatus.INTERRUPTED,
    },
    RunStatus.COMPLETED: set(),
    RunStatus.FAILED: set(),
    RunStatus.INTERRUPTED: set(),
}
```

Implement exact public methods:

```python
async def begin_run(...) -> tuple[ChatMessage, RunRecord]: ...
async def get_run(session_id: str) -> RunRecord: ...
async def list_messages(conversation_id: str) -> list[ChatMessage]: ...
async def list_context_before(...) -> list[ChatMessage]: ...
async def transition_run(session_id: str, expected: RunStatus, target: RunStatus) -> RunRecord: ...
async def complete_run(session_id: str, answer: str) -> ChatMessage: ...
async def fail_run(session_id: str, error_code: str) -> RunRecord: ...
async def interrupt_run(session_id: str) -> RunRecord: ...
async def create_approval(...) -> ApprovalRequest: ...
async def get_approval(approval_id: str) -> ApprovalRequest: ...
async def resolve_approval(approval_id: str, decision: ApprovalStatus) -> ApprovalRequest: ...
async def interrupt_unfinished(self) -> tuple[int, int]: ...
```

Use `BEGIN IMMEDIATE` for `begin_run`, `complete_run`, approval resolution and startup recovery. Catch `sqlite3.IntegrityError` only at the repository boundary and translate known uniqueness conflicts to `ChatConflictError`; re-raise unknown database failures.

- [x] **Step 4: Green 与完整 repository 检查**

```powershell
conda run -n agent-foundations python -m pytest tests/unit/chat/test_repository.py -q
conda run -n agent-foundations python -m ruff check src/agent_foundations/chat tests/unit/chat
conda run -n agent-foundations python -m mypy src tests
git diff --check
```

Expected: all repository tests PASS, including atomic rollback assertions.

- [ ] **Step 5: 检查范围并等待授权**

Suggested commit:

```powershell
git add src/agent_foundations/chat/repository.py tests/unit/chat/test_repository.py
git commit -m "feat: persist chat runs and approvals"
```

---

## Task 4: 扩展 AgentLoop 的多轮输入、固定 Session 和工具执行边界

**Files:**

- Create: `src/agent_foundations/runtime/tool_execution.py`
- Create: `tests/unit/runtime/test_tool_execution.py`
- Modify: `src/agent_foundations/runtime/loop.py`
- Modify: `src/agent_foundations/runtime/session.py`
- Modify: `tests/unit/runtime/test_session.py`
- Modify: `tests/integration/test_agent_loop.py`

- [x] **Step 1: 写兼容性与新行为失败测试**

Required tests:

```python
@pytest.mark.asyncio
async def test_run_includes_visible_history_and_fixed_session_id() -> None:
    session_id = "22222222-2222-4222-8222-222222222222"
    loop, sink, provider = build_loop([ModelResponse(content="continued")])
    result = await loop.run(
        FIXTURE_ROOT,
        "new question",
        history=(
            Message(role=Role.USER, content="old question"),
            Message(role=Role.ASSISTANT, content="old answer"),
        ),
        session_id=session_id,
    )
    assert result.session_id == session_id
    assert [message.content for message in provider.requests[0].messages] == [
        AgentConfig().system_prompt,
        "old question",
        "old answer",
        "new question",
    ]
    assert {event.session_id for event in sink.events} == {session_id}
```

Add rejection tests for history containing `SYSTEM`, `TOOL`, tool calls or empty assistant content. Add a spy `ToolCallExecutor` assertion that receives `ToolExecutionContext(session_id, root, tool_call_id, tool_name)` and that existing callers without an executor still use direct execution.

- [x] **Step 2: 运行 Red**

```powershell
conda run -n agent-foundations python -m pytest tests/integration/test_agent_loop.py tests/unit/runtime/test_session.py tests/unit/runtime/test_tool_execution.py -q
```

Expected: FAIL because `history`, `session_id` and `ToolCallExecutor` are missing.

- [x] **Step 3: 新增工具执行协议，不修改 Tool 协议**

`runtime/tool_execution.py`:

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from agent_foundations.domain.tool import Tool, ToolResult


@dataclass(frozen=True)
class ToolExecutionContext:
    session_id: str
    root: Path
    tool_call_id: str
    tool_name: str


@runtime_checkable
class ToolCallExecutor(Protocol):
    async def execute(
        self,
        tool: Tool,
        arguments: dict[str, Any],
        context: ToolExecutionContext,
    ) -> ToolResult: ...


class DirectToolCallExecutor:
    async def execute(
        self,
        tool: Tool,
        arguments: dict[str, Any],
        context: ToolExecutionContext,
    ) -> ToolResult:
        return await tool.execute(arguments)
```

- [x] **Step 4: 扩展 Session 与 Loop**

Use this compatible signature:

```python
async def run(
    self,
    root: Path,
    query: str,
    *,
    history: tuple[Message, ...] = (),
    session_id: str | None = None,
) -> AgentResult:
```

`AgentLoop.__init__` adds optional `tool_executor: ToolCallExecutor | None = None` and defaults to `DirectToolCallExecutor`. Create `AgentSession(root=root, session_id=session_id or str(uuid4()))`, seed `SYSTEM + history + current USER`, but emit `user.message` only for the current turn. Execute validated tools through the injected executor with explicit context.

`AgentSession.__post_init__` validates its `session_id` as a UUID without changing TraceEvent's broader compatibility. Preserve all existing exception-to-Trace behavior.

- [x] **Step 5: Green 与全量 Runtime 回归**

```powershell
conda run -n agent-foundations python -m pytest tests/unit/runtime tests/integration/test_agent_loop.py tests/e2e/test_cli.py -q
conda run -n agent-foundations python -m ruff check src/agent_foundations/runtime tests/unit/runtime tests/integration/test_agent_loop.py
conda run -n agent-foundations python -m mypy src tests
git diff --check
```

Expected: new tests and all previous loop/CLI tests PASS; existing `run(root, query)` remains source-compatible.

- [ ] **Step 6: 检查范围并等待授权**

Suggested commit:

```powershell
git add src/agent_foundations/runtime tests/unit/runtime tests/integration/test_agent_loop.py
git commit -m "feat: support multi-turn agent runs"
```

---

## Task 5: 实现安全 Chat 事件投影、Broker 与 SSE 编码

**Files:**

- Create: `src/agent_foundations/chat/events.py`
- Create: `tests/unit/chat/test_events.py`

- [x] **Step 1: 写投影、脱敏、队列和编码失败测试**

Use a `Redactor(tmp_path, secrets=("secret-token",))` and assert:

```python
projector = TraceToChatProjector(
    conversation_id="11111111-1111-4111-8111-111111111111",
    redactor=redactor,
    max_summary_chars=240,
)
chat_event = projector.project(
    TraceEvent(
        session_id="22222222-2222-4222-8222-222222222222",
        step_id=1,
        event_type="tool.call.requested",
        status="started",
        summary="Calling read_file",
        payload={
            "name": "read_file",
            "arguments": {"path": str(tmp_path / "README.md"), "token": "secret-token"},
        },
    )
)
assert chat_event is not None
assert chat_event.type is ChatEventType.TOOL_REQUESTED
serialized = chat_event.model_dump_json()
assert "secret-token" not in serialized
assert str(tmp_path) not in serialized
```

Also test:

- only `model.request.started`, `tool.call.requested`, `tool.call.completed`, and `tool.call.failed` are projected;
- Trace payloads are reduced to `name`, bounded `arguments_summary`, `result_summary`, `status`, not copied wholesale;
- summaries over the limit end with one ellipsis and stay within the configured bound;
- one slow subscriber filling a queue does not block `publish`; oldest queued event is dropped and newest retained;
- `subscribe(conversation_id)` removes its queue on close;
- `encode_chat_sse` emits `event: <event_type>` and exactly one JSON `data:` line.

- [x] **Step 2: 运行 Red**

```powershell
conda run -n agent-foundations python -m pytest tests/unit/chat/test_events.py -q
```

Expected: FAIL because Chat event infrastructure is missing.

- [x] **Step 3: 实现投影和 Broker**

Required interfaces:

```python
class TraceToChatProjector:
    def __init__(self, conversation_id: str, redactor: Redactor, max_summary_chars: int = 240) -> None: ...
    def project(self, event: TraceEvent) -> ChatEvent | None: ...


class ChatProjectionSink:
    def __init__(self, projector: TraceToChatProjector, broker: "ChatEventBroker") -> None: ...
    async def emit(self, event: TraceEvent) -> None: ...


class ChatEventBroker:
    def __init__(self, queue_size: int = 256) -> None: ...
    async def publish(self, event: ChatEvent) -> None: ...
    async def subscribe(self, conversation_id: str) -> AsyncGenerator[ChatEvent, None]: ...


def encode_chat_sse(event: ChatEvent) -> str:
    return f"event: {event.type.value}\ndata: {event.model_dump_json()}\n\n"
```

Apply `Redactor.redact` before selecting any payload field. For a full queue, call `get_nowait()` once then `put_nowait(event)`; do not await a slow browser. Do not project `agent.final_answer` because `ConversationRunner` publishes the committed assistant message.

- [x] **Step 4: Green 与质量检查**

验收补充（2026-08-03）：`_truncate_summary` 在截断点落在已有 `…` 时先 `rstrip("…")` 再追加单个省略号，避免 `……`；新增 `test_truncate_summary_avoids_consecutive_ellipsis` 与 `test_trace_to_chat_summary_avoids_double_ellipsis_in_projection`；回归 `63 passed`。

```powershell
conda run -n agent-foundations python -m pytest tests/unit/chat/test_events.py tests/unit/runtime/test_redaction.py -q
conda run -n agent-foundations python -m ruff check src/agent_foundations/chat/events.py tests/unit/chat/test_events.py
conda run -n agent-foundations python -m mypy src tests
git diff --check
```

Suggested commit after authorization:

```powershell
git add src/agent_foundations/chat/events.py tests/unit/chat/test_events.py
git commit -m "feat: stream safe chat activity events"
```

---

## Task 6: 实现 ConversationRunner 与 RunSupervisor 正常路径

**Files:**

- Create: `src/agent_foundations/chat/runner.py`
- Create: `src/agent_foundations/chat/supervisor.py`
- Create: `tests/unit/chat/test_runner.py`
- Create: `tests/unit/chat/test_supervisor.py`

- [x] **Step 1: 写 Runner 正常、失败和取消测试**

Define a test `RuntimeFactory` that returns an `AgentLoop` backed by `FakeModelProvider`. Required assertions:

- runner changes `queued → running → completed`;
- prior visible user/assistant messages appear in the provider request before the new question;
- final assistant message is committed before `assistant.message.completed` and `run.completed` are published;
- `session_id` is identical in SQLite, AgentResult, ChatEvent and JSONL filename;
- provider failure stores only `FakeModelExhaustedError`, emits `run.failed`, and re-raises only inside the supervised task;
- cancellation marks the run `interrupted` and re-raises `CancelledError`.

Use this factory protocol:

```python
class RuntimeFactory(Protocol):
    def __call__(
        self,
        conversation: Conversation,
        event_sink: EventSink,
        tool_executor: ToolCallExecutor,
    ) -> AgentLoop: ...
```

- [x] **Step 2: 写 Supervisor 并发失败测试**

Assert one active task per conversation, different conversations may run together, finished tasks are removed, exceptions are consumed by the done callback (not logged as “Task exception was never retrieved”), and `shutdown()` cancels/gathers every task.

- [x] **Step 3: 运行 Red**

```powershell
conda run -n agent-foundations python -m pytest tests/unit/chat/test_runner.py tests/unit/chat/test_supervisor.py -q
```

Expected: FAIL because runner and supervisor do not exist.

- [x] **Step 4: 实现 `ConversationRunner`**

Required constructor and method:

```python
class ConversationRunner:
    def __init__(
        self,
        repository: ConversationRepository,
        broker: ChatEventBroker,
        runtime_factory: RuntimeFactory,
        trace_dir: Path,
        redactor_factory: Callable[[Conversation], Redactor],
        tool_executor_factory: Callable[[Conversation, str], ToolCallExecutor] = direct_executor_factory,
    ) -> None: ...

    async def run_turn(
        self,
        conversation_id: str,
        session_id: str,
        user_message_id: str,
        query: str,
    ) -> None: ...
```

Algorithm order is fixed:

1. Load conversation and prior visible messages with `list_context_before`.
2. Transition queued to running.
3. Publish `run.started`.
4. Build `CompositeEventSink([JsonlEventSink, ChatProjectionSink])`.
5. Map stored visible roles to domain `Message` and call `AgentLoop.run(..., history=..., session_id=...)`.
6. Commit assistant message and completed run atomically.
7. Publish `assistant.message.completed`, then `run.completed`.
8. On ordinary exception, `fail_run(type(exc).__name__)`, publish safe `run.failed`, and return without exposing exception text to Chat.
9. On cancellation, `interrupt_run`, then re-raise cancellation.

- [x] **Step 5: 实现 `RunSupervisor`**

Required API:

```python
class RunSupervisor:
    async def start(
        self,
        conversation_id: str,
        run_factory: Callable[[], Coroutine[Any, Any, None]],
    ) -> None: ...
    def is_active(self, conversation_id: str) -> bool: ...
    async def shutdown(self) -> None: ...
```

Guard the task map with `asyncio.Lock`. Check and register under the same lock. The done callback removes only the identical task and calls `task.exception()` unless cancelled.

- [x] **Step 6: Green 与回归**

```powershell
conda run -n agent-foundations python -m pytest tests/unit/chat/test_runner.py tests/unit/chat/test_supervisor.py tests/integration/test_agent_loop.py -q
conda run -n agent-foundations python -m ruff check src/agent_foundations/chat tests/unit/chat
conda run -n agent-foundations python -m mypy src tests
git diff --check
```

Suggested commit after authorization:

```powershell
git add src/agent_foundations/chat/runner.py src/agent_foundations/chat/supervisor.py tests/unit/chat
git commit -m "feat: orchestrate persistent chat runs"
```

---

## Task 7: 接入基础 Chat HTTP/SSE API、Trace 路由和 CLI

**Files:**

- Create: `src/agent_foundations/chat/api.py`
- Create: `tests/integration/test_chat_api.py`
- Modify: `src/agent_foundations/viewer/app.py`
- Modify: `src/agent_foundations/viewer/static/app.ts`
- Modify: `src/agent_foundations/cli/main.py`
- Modify: `tests/integration/test_viewer_api.py`
- Modify: `tests/e2e/test_trace_viewer.py`
- Modify: `tests/e2e/test_cli.py`

- [x] **Step 1: 写 Conversation API 失败测试**

Create a `ChatServices` dataclass containing repository, broker, runner and supervisor. With `TestClient`, test:

```text
POST /api/chat/conversations                 -> 201
GET  /api/chat/conversations                 -> 200 ordered list
GET  /api/chat/conversations/{id}            -> 200 or 404
PATCH /api/chat/conversations/{id}           -> 200, root cannot change
GET  /api/chat/conversations/{id}/messages   -> 200
POST /api/chat/conversations/{id}/messages   -> 202 + session_id
GET  /api/chat/runs/{session_id}              -> 200
GET  /api/chat/conversations/{id}/events      -> text/event-stream
```

Assert blank title/query and missing/non-directory project root return `422`; active run and permission update during a run return `409`; error bodies contain stable `detail` only.

- [x] **Step 2: 写路由兼容和 CLI 失败测试**

Tests must assert:

- `create_app(trace_dir)` remains Trace-only at `/` for existing callers;
- `create_app(trace_dir, chat_services=...)` serves Chat build at `/` and `/chat`, Trace at `/trace`;
- `/trace?session_id=browser-session` auto-selects that session without changing the existing Trace API;
- new `agent-foundations chat --help` shows `--state-db`, `--trace-dir`, `--port`;
- chat command validates `AGENT_API_KEY`/`AGENT_MODEL` before startup and binds only `127.0.0.1`.

- [x] **Step 3: 运行 Red**

```powershell
conda run -n agent-foundations python -m pytest tests/integration/test_chat_api.py tests/integration/test_viewer_api.py tests/e2e/test_cli.py -q
npm run test:viewer
```

Expected: new API/CLI tests FAIL for missing routes; existing Viewer tests remain Green before implementation.

- [x] **Step 4: 实现 router 与错误映射**

Use Pydantic request types with `extra="forbid"`. The message endpoint must call `repository.begin_run` before `supervisor.start`; if supervisor registration unexpectedly conflicts, mark that new run failed with stable `RunSupervisorConflict`.

SSE generator sends `: connected\n\n`, a keepalive at a bounded interval, then encoded events. On disconnect, close the subscription. Map only these domain errors:

```python
ChatNotFoundError -> 404
ChatConflictError -> 409
Pydantic/path validation -> 422
```

Unexpected exceptions use FastAPI's generic 500 response; do not return `str(exc)`.

- [x] **Step 5: 组合应用与 CLI**

Keep `create_app(trace_dir, broker=None, chat_services=None)`. When Chat services are present, add a lifespan that calls `repository.initialize()`, `interrupt_unfinished()` before serving, then `supervisor.shutdown()` on exit. Mount Vite output only if present; return an explicit `503` “Chat UI build is missing” before Task 10.

Add `chat` CLI without changing `viewer` behavior. Extract shared provider/tool construction rather than duplicating API key access. Do not start Uvicorn in tests; patch `uvicorn.run` and assert `host="127.0.0.1"`.

- [x] **Step 6: Green 与兼容回归**

```powershell
conda run -n agent-foundations python -m pytest tests/integration/test_chat_api.py tests/integration/test_viewer_api.py tests/e2e/test_cli.py -q
conda run -n agent-foundations python -m ruff check src tests/integration tests/e2e/test_cli.py
conda run -n agent-foundations python -m mypy src tests
npm run test:viewer
git diff --check
```

Suggested commit after authorization:

```powershell
git add src/agent_foundations/chat/api.py src/agent_foundations/viewer src/agent_foundations/cli tests/integration tests/e2e/test_cli.py tests/e2e/test_trace_viewer.py
git commit -m "feat: expose local chat api"
```

---

## Task 8: 实现一次性 ApprovalCoordinator

**Files:**

- Create: `src/agent_foundations/chat/approvals.py`
- Create: `tests/unit/chat/test_approvals.py`
- Modify: `src/agent_foundations/chat/models.py`

- [x] **Step 1: 写请求、决策、重复和关闭失败测试**

Required flow:

```python
waiter = asyncio.create_task(coordinator.request(request))
created = await wait_for_pending(repository, request.approval_id)
assert created.status is ApprovalStatus.PENDING
await coordinator.resolve(request.approval_id, ApprovalDecision.APPROVE)
assert await waiter is ApprovalStatus.APPROVED
```

Also test denied, duplicate resolve, unknown/invalidated approval, two approvals with different IDs, task cancellation removes the in-memory future, and `shutdown()` invalidates/unblocks all waiters without approving anything.

- [x] **Step 2: 运行 Red**

```powershell
conda run -n agent-foundations python -m pytest tests/unit/chat/test_approvals.py -q
```

Expected: FAIL because coordinator is missing.

- [x] **Step 3: 实现显式决策类型与 Coordinator**

Add `ApprovalDecision(StrEnum)` with only `APPROVE="approve"` and `DENY="deny"` for API input; repository status remains `approved|denied`.

Required interface:

```python
class ApprovalCoordinator:
    def __init__(self, repository: ConversationRepository, broker: ChatEventBroker) -> None: ...
    async def request(self, request: ApprovalRequest) -> ApprovalStatus: ...
    async def resolve(self, approval_id: str, decision: ApprovalDecision) -> ApprovalRequest: ...
    async def shutdown(self) -> None: ...
```

`request` must transition run `running → waiting_approval`, persist request, register a future, publish `approval.requested`, await the future, transition run back to running for both approve and deny, then publish `approval.resolved`. Register/persist order must not lose a very fast decision: protect future registration and resolution with one lock, and rollback/invalidate on publish failure.

`shutdown()` never resolves as approved. It cancels futures and relies on repository startup recovery to mark records interrupted/invalidated.

- [x] **Step 4: Green 与质量检查**

```powershell
conda run -n agent-foundations python -m pytest tests/unit/chat/test_approvals.py tests/unit/chat/test_repository.py -q
conda run -n agent-foundations python -m ruff check src/agent_foundations/chat tests/unit/chat
conda run -n agent-foundations python -m mypy src tests
git diff --check
```

Suggested commit after authorization:

```powershell
git add src/agent_foundations/chat/approvals.py src/agent_foundations/chat/models.py tests/unit/chat/test_approvals.py
git commit -m "feat: coordinate one-time access approvals"
```

---

## Task 9: 实现项目外只读执行并接入审批 API

**Files:**

- Create: `src/agent_foundations/chat/tool_execution.py`
- Create: `tests/unit/chat/test_tool_execution.py`
- Create: `tests/integration/test_chat_approval_flow.py`
- Modify: `src/agent_foundations/tools/filesystem/path_policy.py`
- Modify: `tests/unit/tools/filesystem/test_path_policy.py`
- Modify: `src/agent_foundations/chat/api.py`
- Modify: `src/agent_foundations/chat/runner.py`
- Modify: `src/agent_foundations/cli/main.py`

- [x] **Step 1: 写路径决策矩阵失败测试**

Test the complete matrix using only `tmp_path`:

| Mode | Requested path | Result |
|---|---|---|
| PROJECT_READ_ONLY | relative inside root | direct allow |
| PROJECT_READ_ONLY | absolute inside root | normalize to project-relative, allow |
| PROJECT_READ_ONLY | external | raise policy violation, no approval |
| ASK_FOR_ACCESS | relative/absolute inside root | direct allow |
| ASK_FOR_ACCESS | external normal target | create exact approval |
| ASK_FOR_ACCESS | external sensitive target | hard deny, no approval |
| either | write/shell/git/network | unavailable in registry |

For an approved external target, test `read_file`, `list_directory`, and `search_text`; a second identical call creates a new approval. Denial returns `ToolResult(success=False, error_code="access_denied")`. Re-resolve the path after approval and reject a changed symlink target when the host permits symlink creation.

- [x] **Step 2: 写审批 API 集成失败测试**

Start a FakeModel script that requests an external file then returns a final answer after receiving the tool result. Assert:

1. POST message returns `202`.
2. run becomes `waiting_approval`.
3. `POST /api/chat/approvals/{id}/decision` with `{"decision":"approve"}` returns `200`.
4. run completes and JSONL contains the requested/completed tool events.
5. repeating the message creates a different approval id.
6. deny lets the model receive `access_denied` and continue.
7. duplicate decision is `409`; unknown id is `404`.

- [x] **Step 3: 运行 Red**

```powershell
conda run -n agent-foundations python -m pytest tests/unit/chat/test_tool_execution.py tests/unit/tools/filesystem/test_path_policy.py tests/integration/test_chat_approval_flow.py -q
```

Expected: FAIL because external read execution and decision endpoint are missing.

- [x] **Step 4: 增加仅规范化、不授权的绝对路径 helper**

In `PathPolicy`, add:

```python
@classmethod
def resolve_external_read_target(cls, value: str) -> Path:
    """Resolve and validate an absolute existing target; this does not grant access."""
```

It must require an absolute path, reuse component/device/sensitive checks, call `resolve(strict=True)`, reject sensitive components both before and after resolution, and return only a canonical file or directory. The docstring and tests must make clear that permission is decided elsewhere.

- [x] **Step 5: 实现 `ApprovalAwareToolExecutor`**

Constructor dependencies:

```python
class ApprovalAwareToolExecutor:
    def __init__(
        self,
        conversation: Conversation,
        coordinator: ApprovalCoordinator,
    ) -> None: ...
```

Before the executor, implement a pure `FilesystemAccessController.decide(conversation, raw_path) -> AccessDecision`. It canonicalizes the target, classifies project vs exact external scope, and returns only `allow`, `deny`, or `ask`; it never waits for UI input or executes a tool. Unit tests must assert all four decision fields, not only the final boolean behavior.

Execution rules:

- no `path` argument or relative path: call original tool unchanged;
- absolute path resolving inside project: convert to project-relative POSIX string and call original tool;
- external + PROJECT_READ_ONLY: raise `PathPolicyViolationError`;
- external + ASK_FOR_ACCESS: build `ApprovalRequest` from exact context/tool/path, await coordinator;
- denied: return stable `access_denied` result;
- approved: re-resolve and compare canonical path, then create a fresh scoped `PathPolicy` and standard tool instance:
  - `read_file`: root `target.parent`, path `target.name`;
  - `list_directory`: target must be directory, root `target`, path `.`;
  - `search_text`: root `target` for directory or `target.parent` for file; rewrite path accordingly;
- any other tool name with an external path is hard denied.

Do not cache approvals or external tool instances. Reuse existing bounded defaults and sensitive-child filtering.

- [x] **Step 6: 接入 Runner、CLI 与 API**

Production Chat runtime uses `ApprovalAwareToolExecutor`; CLI `analyze` continues to use direct execution. Add:

```text
POST /api/chat/approvals/{approval_id}/decision
```

Request body accepts only `approve|deny`. Add coordinator shutdown before supervisor shutdown so waiting tasks unblock/cancel deterministically.

- [x] **Step 7: Green 与安全回归**

```powershell
conda run -n agent-foundations python -m pytest tests/unit/chat tests/unit/tools/filesystem tests/integration/test_chat_approval_flow.py -q
conda run -n agent-foundations python -m ruff check src tests/unit/chat tests/unit/tools/filesystem tests/integration/test_chat_approval_flow.py
conda run -n agent-foundations python -m mypy src tests
git diff --check
```

Expected: all matrix and integration cases PASS; no test reads outside its temporary directory.

Suggested commit after authorization:

```powershell
git add src/agent_foundations/chat src/agent_foundations/tools/filesystem/path_policy.py tests/unit/chat tests/unit/tools/filesystem/test_path_policy.py tests/integration/test_chat_approval_flow.py src/agent_foundations/cli/main.py
git commit -m "feat: approve exact external read access"
```

---

## Task 10: 引入 React/Vite/Vitest 并建立 typed Chat state

**Authorization gate:** 本 Task 会联网修改 `node_modules`、`package.json` 和 `package-lock.json`。执行者必须先报告拟安装包和回退方式（恢复两个 manifest 并删除本 Task 新增前端文件），获得用户明确确认后才运行安装命令。

**Files:**

- Create: `tsconfig.chat.json`
- Create: `vite.config.ts`
- Create: `vitest.config.ts`
- Create: `web/chat/index.html`
- Create: `web/chat/main.tsx`
- Create: `web/chat/App.tsx`
- Create: `web/chat/state/types.ts`
- Create: `web/chat/state/api.ts`
- Create: `web/chat/state/events.ts`
- Create: `web/chat/state/reducer.ts`
- Create: `tests/chat/reducer.test.ts`
- Create: `tests/chat/setup.ts`
- Modify: `package.json`
- Modify: `package-lock.json`

- [x] **Step 1: 获得依赖安装确认**

Planned commands after approval:

```powershell
npm install react react-dom
npm install --save-dev @types/node @types/react @types/react-dom @vitejs/plugin-react vite vitest jsdom @testing-library/react @testing-library/dom @testing-library/user-event @testing-library/jest-dom
```

Expected: `package-lock.json` pins the resolved versions; do not use global npm packages and do not delete the existing lockfile.

Before installation, run `node --version`, `npm --version`, `npm view vite engines --json`, and `npm view vitest engines --json`. If the installed Node version does not satisfy the resolved packages, stop and report the mismatch; do not silently downgrade packages or change the system Node installation.

- [x] **Step 2: 先写 reducer 失败测试**

`tests/chat/reducer.test.ts` must construct exact backend-shaped values and assert:

```typescript
import { describe, expect, it } from "vitest";
import { initialState, reduceChatState } from "../../web/chat/state/reducer";
import type { ChatEvent, Conversation } from "../../web/chat/state/types";

it("keeps conversations, messages, activities, and run state separate", () => {
  const conversation: Conversation = {
    conversation_id: "c1",
    title: "Runtime study",
    project_root: "D:\\project",
    permission_mode: "PROJECT_READ_ONLY",
    created_at: "2026-08-02T00:00:00Z",
    updated_at: "2026-08-02T00:00:00Z",
  };
  const selected = reduceChatState(initialState, { type: "conversations.loaded", conversations: [conversation] });
  const running: ChatEvent = {
    event_id: "e1",
    conversation_id: "c1",
    session_id: "s1",
    type: "run.started",
    occurred_at: "2026-08-02T00:00:01Z",
    data: {},
  };
  const next = reduceChatState(selected, { type: "event.received", event: running });
  expect(next.activeConversationId).toBe("c1");
  expect(next.runStatusByConversation.c1).toBe("running");
  expect(next.activitiesByConversation.c1).toEqual([running]);
});
```

Additional cases: `assistant.message.completed` does not duplicate a later HTTP message reload; `approval.requested` sets waiting state; resolved/completed/failed events clear it; switching conversations never shares activities; unknown event data remains inert.

- [x] **Step 3: 配置构建并确认 Red**

Use separate configs so the existing Trace Viewer `tsconfig.json` remains unchanged:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "jsx": "react-jsx",
    "strict": true,
    "noEmit": true,
    "skipLibCheck": true,
    "types": ["node", "vitest/globals", "vitest/jsdom"]
  },
  "include": ["web/chat/**/*.ts", "web/chat/**/*.tsx", "tests/chat/**/*.ts", "tests/chat/**/*.tsx", "vite.config.ts", "vitest.config.ts"]
}
```

`vite.config.ts` uses `root: "web/chat"`, `base: "/chat-static/"`, React plugin, and an absolute `outDir` resolved from `import.meta.url` to `src/agent_foundations/viewer/static/chat`, with `emptyOutDir: true`. `vitest.config.ts` uses React plugin, `environment: "jsdom"`, includes `tests/chat/**/*.test.{ts,tsx}`, and loads `tests/chat/setup.ts`; that setup imports `@testing-library/jest-dom/vitest`.

Add scripts without removing existing ones:

```json
"dev:chat": "vite --config vite.config.ts",
"build:chat": "vite build --config vite.config.ts",
"typecheck:chat": "tsc --project tsconfig.chat.json --noEmit",
"test:chat": "vitest run --config vitest.config.ts"
```

Run:

```powershell
npm run test:chat
```

Expected: FAIL because typed state implementation is missing or incomplete.

- [x] **Step 4: 实现与后端严格一致的前端类型**

`types.ts` must define unions, not broad strings:

```typescript
export type PermissionMode = "PROJECT_READ_ONLY" | "ASK_FOR_ACCESS";
export type MessageRole = "user" | "assistant";
export type RunStatus = "queued" | "running" | "waiting_approval" | "completed" | "failed" | "interrupted";
export type ApprovalDecision = "approve" | "deny";
export type ChatEventType =
  | "run.started" | "model.requested" | "tool.requested" | "tool.completed"
  | "tool.failed" | "approval.requested" | "approval.resolved"
  | "assistant.message.completed" | "run.completed" | "run.failed";
```

Define `Conversation`, `ChatMessage`, `RunRecord`, `ApprovalRequest`, `ChatEvent` with fields exactly matching FastAPI JSON. `ChatEvent` uses `type: ChatEventType`; TraceEvent alone retains `event_type`. Use `Record<string, unknown>` only for `ChatEvent.data`.

- [x] **Step 5: 实现 API client、SSE client 和 reducer**

`api.ts` provides typed functions for every endpoint and a single helper:

```typescript
async function requestJson<T>(input: RequestInfo | URL, init?: RequestInit): Promise<T>
```

On non-2xx, parse `{detail}` when safe and throw `ChatApiError(status, detail)`; never render raw HTML. `events.ts` creates one `EventSource` per active conversation, registers every stable event name, validates required envelope string fields before dispatch, and closes the old source when switching.

The reducer is pure and owns no network objects. Store messages and activities by conversation id, plus active run/approval state. Do not store complete Trace payloads.

- [x] **Step 6: 建立最小 React root**

`main.tsx` follows the current React client API:

```typescript
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";

const container = document.getElementById("root");
if (!container) throw new Error("Missing #root container");
createRoot(container).render(<StrictMode><App /></StrictMode>);
```

At this Task, `App` may show a semantic heading and loading/error status, but it must load conversations through the typed client; it is not a static landing page.

- [x] **Step 7: Green、旧 Viewer 兼容和构建**

```powershell
npm run test:chat
npm run typecheck:chat
npm run build:chat
npm run test:viewer
conda run -n agent-foundations python -m pytest tests/integration/test_chat_api.py -q
git diff --check
```

Expected: all commands exit `0`; Vite output is served at `/chat-static/`; Trace Viewer scripts still pass.

Suggested commit after authorization:

```powershell
git add package.json package-lock.json tsconfig.chat.json vite.config.ts vitest.config.ts web/chat tests/chat src/agent_foundations/viewer/static/chat
git commit -m "feat: scaffold react chat client"
```

---

## Task 11: 构建对话、Activity、审批和 Trace 跳转 UI

**Files:**

- Create: `web/chat/components/ConversationList.tsx`
- Create: `web/chat/components/MessageTimeline.tsx`
- Create: `web/chat/components/ChatComposer.tsx`
- Create: `web/chat/components/ActivityCard.tsx`
- Create: `web/chat/components/ApprovalCard.tsx`
- Create: `web/chat/styles.css`
- Create: `tests/chat/app.test.tsx`
- Create: `tests/chat/activity.test.tsx`
- Modify: `web/chat/App.tsx`
- Modify: `web/chat/main.tsx`

**Planner clarification (2026-08-07):** Task 11 的运行状态恢复边界只覆盖当前浏览器生命周期。初始加载读取 conversation 列表；选择对话后读取 conversation 与 messages；只有当前浏览器已经通过消息 POST、SSE 或内存状态知道 `session_id` 时，才在连接 SSE 前调用现有 `GET /api/chat/runs/{session_id}` 恢复 run。Task 11 不负责 fresh load/reload 后发现未知 `session_id` 或重建 pending approval；该完整刷新恢复及其最小 API/Repository 支持明确属于 Task 12。按此澄清，`docs/task-evidence/phase-1d-task-11.md` 所描述的当前实现满足 Task 11 的功能范围；这不替代 reviewer 对当前实现的最终验收，也不改变原始 Red 缺失所导致的 TDD 过程证据结论。

- [x] **Step 1: 写用户行为失败测试**

With Testing Library and `userEvent.setup()`, mock only the typed API module. Cover:

- empty state has “New conversation” and no fake messages;
- creation form requires title, existing project path text, and permission mode;
- selecting a conversation loads messages and establishes its SSE connection;
- sending a nonblank message disables composer while active and adds no optimistic assistant text;
- user/assistant contents render as text even when content contains `<script>`;
- activity cards show safe summary, status and an expand button;
- `approval.requested` renders canonical path, operation, tool, one-time scope, Approve once and Deny;
- one decision disables both buttons immediately; API conflict renders an accessible error;
- completed run renders `/trace?session_id=<encoded-id>` link;
- narrow viewport does not create body-level horizontal overflow (component class contract plus E2E visual geometry in Task 12).

- [x] **Step 2: 运行 Red**

```powershell
npm run test:chat
```

Expected: component tests FAIL because the interactive components are missing.

- [x] **Step 3: 实现组件边界**

Component contracts:

```typescript
ConversationList({ conversations, activeId, onSelect, onCreate })
MessageTimeline({ messages, activities, activeSessionId })
ChatComposer({ disabled, onSubmit })
ActivityCard({ event })
ApprovalCard({ event, disabled, onDecision })
```

Use semantic `nav`, `main`, `ol`, `article`, `form`, `label`, `button`, `role="status"` and `aria-live="polite"`. Do not use `dangerouslySetInnerHTML`. Long paths use `overflow-wrap:anywhere`; code/result summaries use `white-space:pre-wrap` and bounded height.

- [x] **Step 4: 实现 App 数据流**

On initial load fetch conversations. On selection, fetch conversation and messages first; if the current browser lifecycle already knows the conversation's `session_id`, also fetch that run before opening SSE. On SSE reconnect within the same browser lifecycle, re-fetch conversation/messages and the known run, then continue live events; do not promise SSE replay. A fresh load/reload cannot discover an unknown run or pending approval through the Task 11 API and is explicitly deferred to Task 12. Creation uses backend canonical root response. Message POST uses returned `session_id` and waits for SSE/HTTP reload for final answer.

Approval decision is keyed by `approval_id` from event data. Prevent double submit locally, but treat server `409` as authoritative. Permission mode may be edited only when no active run or pending approval.

- [x] **Step 5: 实现克制且响应式样式**

Required layout behavior:

- desktop: 280px conversation sidebar + flexible main column;
- below 800px: sidebar becomes top drawer/stack, no fixed overlay over composer;
- composer remains visible after long timelines without covering content;
- focus ring is visible; status is not color-only;
- respect `prefers-reduced-motion`;
- dark neutral palette, limited accent colors, no decorative gradients or excessive animation.

- [x] **Step 6: Green 与构建**

```powershell
npm run test:chat
npm run typecheck:chat
npm run build:chat
npm run test:viewer
git diff --check
```

Expected: component behavior tests, typecheck and both frontend builds pass.

Suggested commit after authorization:

```powershell
git add web/chat tests/chat src/agent_foundations/viewer/static/chat
git commit -m "feat: build interactive agent chat ui"
```

---

## Task 12: 端到端验收、文档与 Phase 1D 总门禁

**Files:**

- Create: `tests/e2e/test_chat_ui.py`
- Create: `docs/learning-notes/04-chat-control-plane.md`
- Modify: `src/agent_foundations/chat/repository.py`
- Modify: `src/agent_foundations/chat/api.py`
- Modify: `tests/unit/chat/test_repository.py`
- Modify: `tests/integration/test_chat_api.py`
- Modify: `web/chat/state/types.ts`
- Modify: `web/chat/state/api.ts`
- Modify: `web/chat/state/reducer.ts`
- Modify: `web/chat/App.tsx`
- Modify: `tests/chat/reducer.test.ts`
- Modify: `tests/chat/app.test.tsx`
- Modify: `README.md`
- Modify: `docs/agent-plans/2026-07-20-agent-engineering-learning-design.md`
- Modify: `docs/agent-plans/2026-07-21-phase-1-implementation-plan.md`
- Modify: `docs/agent-plans/2026-08-02-phase-1d-interactive-chat-ui-plan.md`

**Refresh-recovery contract:** Task 12 owns fresh load/reload recovery. Add one same-origin endpoint:

```text
GET /api/chat/conversations/{conversation_id}/state
```

The exact response is:

```json
{
  "latest_run": null,
  "pending_approval": null
}
```

`latest_run` is either `null` or the existing complete `RunRecord` JSON. `pending_approval` is either `null` or an exact recovery projection containing:

```text
approval_id
conversation_id
session_id
tool_call_id
tool_name
canonical_path
operation: "read"
scope: "external_exact_path"
status: "pending"
requested_at
```

The endpoint returns `404` for a missing conversation and the existing `422` validation response for a malformed UUID. Repository adds one read-only recovery query that, in one short-lived connection/read transaction, verifies the conversation, selects the latest run deterministically by its user message sequence, and returns only that run's pending approval. A completed, failed or interrupted run never returns a pending approval; approved, denied and invalidated approvals are not recoverable as pending. This is an API projection only: no schema migration, new permission, persistent SSE replay or coroutine restart is introduced.

- [x] **Step 1: 写恢复契约与浏览器 E2E 失败测试**

Before production changes, first add recovery-contract tests:

- `tests/unit/chat/test_repository.py`: no run returns `(None, None)`; multiple runs select the latest by user message sequence; a `waiting_approval` run returns only its own pending approval; terminal runs and resolved/invalidated approvals return no pending approval; another conversation's run/approval never leaks.
- `tests/integration/test_chat_api.py`: exact `/state` response shape for no run, running, waiting approval and terminal run; waiting approval includes the exact fields above; missing conversation is `404`; malformed ID is `422`; no stack, secret or unrelated path appears.
- `tests/chat/reducer.test.ts`: a typed HTTP recovery action restores `latest_run`, active `session_id` and pending approval without manufacturing an SSE event; terminal/no-run state clears active approval correctly.
- `tests/chat/app.test.tsx`: fresh load waits for conversation, messages and `/state` before constructing `EventSource`; recovered `running` and `waiting_approval` disable composer and permission mode; waiting approval recreates the approval card; terminal/no-run state enables idle controls; reconnect repeats HTTP recovery before opening the no-replay SSE stream.

Start Uvicorn on a free `127.0.0.1` port with temporary SQLite/Trace directories and a scripted FakeModel factory. The test must perform real browser actions:

1. Open `/chat`, create `PROJECT_READ_ONLY` conversation bound to `tests/fixtures/sample_project`.
2. Send turn one; observe `Thinking`, tool requested/completed, final assistant answer.
3. Send turn two; assert FakeModel's request includes prior visible user/assistant messages.
4. Reload page; assert both turns remain.
5. Open Trace link; assert `/trace` selects the exact session and displays tool detail.
6. Create `ASK_FOR_ACCESS` conversation bound to an isolated temporary project.
7. Request another temporary external file, approve once, and complete.
8. Request the same path again; assert a new approval id/card appears.
9. Deny it; assert tool result is `access_denied` and the scripted model can finish.
10. Set viewport to 390x844; assert `document.documentElement.scrollWidth <= innerWidth` and composer/buttons remain visible.
11. Hold a run in `running`, reload the page, and assert HTTP recovery completes before SSE connects while composer and permission mode remain disabled; release the scripted run and confirm normal completion.
12. Hold an `ASK_FOR_ACCESS` run in `waiting_approval`, reload the page, and assert the approval card is reconstructed with the same approval id, tool, canonical path, `read` operation and `external_exact_path` scope; composer and permission mode remain disabled until the decision resolves.

The E2E fixture must never use the user's home directory or a real API client.

- [x] **Step 2: 运行 Red**

```powershell
conda run -n agent-foundations python -m pytest tests/unit/chat/test_repository.py tests/integration/test_chat_api.py -q
npm run test:chat
conda run -n agent-foundations python -m pytest tests/e2e/test_chat_ui.py -q
```

Expected: FAIL because the conversation state query, typed frontend recovery and/or fresh reload behavior is missing, not due to a real credential, network request or unrelated environment error. Record the valid Red before modifying Repository, API or frontend production files.

- [x] **Step 3: 修正最小集成缺口并完成 E2E Green**

Implement only the recovery contract above:

1. Repository returns the latest run and its pending approval atomically for one conversation, without schema changes.
2. FastAPI exposes `GET /api/chat/conversations/{conversation_id}/state` with the exact response shape and stable `404`/`422` behavior.
3. The typed client and reducer represent the response without broad `any`, synthetic SSE events or complete Trace payloads.
4. App fresh load, selection and reconnect finish conversation/messages/state HTTP recovery before opening SSE.
5. Recovered `running` or `waiting_approval` disables composer and permission editing; recovered pending approval restores the exact one-time approval card.
6. Terminal or no-run recovery leaves idle controls enabled, while service restart semantics remain `interrupted` with no resumable old approval.

Only fix defects exposed by this recovery and E2E contract. Do not add token streaming, write tools, shell, Git, network, conversation deletion, permanent approval, persistent SSE replay or restartable Python coroutines.

Run:

```powershell
conda run -n agent-foundations python -m pytest tests/unit/chat/test_repository.py tests/integration/test_chat_api.py -q
npm run test:chat
conda run -n agent-foundations python -m pytest tests/e2e/test_chat_ui.py -q
```

Expected: repository/API recovery, React recovery, desktop, fresh reload and narrow viewport flows pass.

- [x] **Step 4: 更新 README 和学习笔记**

README must clearly separate:

- `agent-foundations analyze`: one-shot CLI;
- `agent-foundations viewer`: Trace-only viewer;
- `agent-foundations chat`: multi-turn local Chat + Trace;
- startup commands using the `agent-foundations` Conda environment;
- `.agent-foundations/chat.sqlite3` and `traces/` data locations;
- both permission modes and the fact that Phase 1D approves only one exact external read;
- current prohibitions and no token streaming claim.

`04-chat-control-plane.md` explains:

- control plane vs observation plane;
- SQLite vs JSONL ownership;
- why `RunSupervisor` and `ApprovalCoordinator` are separate;
- exact one-time capability vs broad full access;
- why SSE is live hinting while HTTP/SQLite/JSONL are recovery facts;
- current restart/interrupted limitation and future Phase 2 extension points.

- [x] **Step 5: 更新计划状态但不得提前勾选**

Evidence: [`docs/task-evidence/phase-1d-task-12.md`](../../task-evidence/phase-1d-task-12.md). Phase 1D implementation completed, awaiting independent review/user acceptance. Phase 2 not started.

- [x] **Step 6: 运行完整新鲜质量门禁**

```powershell
conda run -n agent-foundations python -m pytest -q
conda run -n agent-foundations python -m ruff check .
conda run -n agent-foundations python -m mypy src tests
conda run -n agent-foundations python -m pip check
npm run test:viewer
npm run typecheck:viewer
npm run test:chat
npm run typecheck:chat
npm run build:chat
git diff --check
git status --short
```

Expected: every command exits `0`; report exact pass counts from this run. `git status` may still include preserved Phase 1B/1C user changes, which must be identified rather than removed.

- [ ] **Step 7: 人工安全验收**

Automated E2E does not substitute independent manual smoke. Awaiting reviewer/user completion (see `docs/task-evidence/phase-1d-task-12.md` remediation checklist).

- [ ] **Step 8: 检查最终范围并等待 commit/push 授权**

Suggested commit only after explicit authorization and careful staging:

```powershell
git add README.md AGENTS.md .gitignore package.json package-lock.json tsconfig.chat.json vite.config.ts vitest.config.ts web/chat src/agent_foundations/chat src/agent_foundations/runtime src/agent_foundations/tools/filesystem/path_policy.py src/agent_foundations/viewer src/agent_foundations/cli tests docs/agent-plans docs/learning-notes/04-chat-control-plane.md
git diff --cached --check
git status --short
git commit -m "feat: complete phase 1d interactive chat ui"
```

Do not push or create a PR without a new explicit confirmation.

---

## 规格覆盖映射

| 已确认规格能力 | 实施 Task | 主要验收证据 |
|---|---:|---|
| SQLite 对话、消息、run、审批与中断恢复 | 1–3 | Repository 原子性与恢复单测 |
| 多轮可见历史、固定 session、Runtime 解耦 | 4、6 | AgentLoop 与 Runner 测试 |
| Chat 安全事件、SSE、完整 Trace 关联 | 5、7 | 投影/Broker/API/Trace 路由测试 |
| 两种权限模式和一次性精确外部只读审批 | 8–9 | 决策矩阵、批准/拒绝集成测试 |
| React/Vite typed client 与当前浏览器生命周期内的多会话 UI | 10–11 | Vitest、Testing Library、typecheck/build |
| fresh load/reload 的 latest run 与 pending approval 恢复、窄屏、审批和 Trace 真实交互 | 12 | Repository/API recovery tests、Vitest、Playwright E2E 与人工安全验收 |
| 不实现写/Shell/Git/network/token streaming | 0、9、12 | Registry、安全回归与文档边界 |

---

## Phase 1D 完成定义

- [x] 多对话、多轮消息在 SQLite 中持久化并可重启读取。
- [x] 每个 turn 使用同一个 `session_id` 关联 SQLite run、Chat events 和 JSONL Trace。
- [x] Chat 实时显示安全活动摘要，完整底层内容只在 Trace Viewer 显示。
- [x] `PROJECT_READ_ONLY` 和 `ASK_FOR_ACCESS` 行为符合完整决策矩阵。
- [x] 项目外批准是 `session_id + tool_call_id + canonical_path + read` 一次性能力。
- [x] 敏感路径、写、Shell、Git、network 无法通过审批绕过。
- [x] React UI 在桌面和 390px 窄屏真实可交互，无文字遮挡或横向溢出。
- [x] Provider 配置和密钥只在服务端，不进入 SQLite、Chat JSON 或前端。
- [x] 自动测试完全离线，不访问真实模型或用户真实外部文件。
- [x] Python、Viewer、Chat、E2E 和依赖门禁均有最新通过证据（见 `docs/task-evidence/phase-1d-task-12.md`）。
- [x] README、学习笔记、阶段文档与实现边界一致。

**Note:** Checkboxes reflect executor fresh gate evidence only. Phase 1D **not** user-accepted; Phase 2 **not** started.

## 实施时参考的官方资料

- React `createRoot`: https://react.dev/reference/react-dom/client/createRoot
- Vite build 与 `base`/`outDir`: https://vite.dev/guide/build
- Vite alternative root: https://vite.dev/guide/
- Vitest jsdom environment: https://vitest.dev/guide/environment.html
- React Testing Library: https://testing-library.com/docs/react-testing-library/intro/
