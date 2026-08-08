# Phase 1D Interactive Chat UI Design

**状态：** 已由用户确认（2026-08-02）

**目标：** 在进入可控 Coding Agent 之前，为现有只读 Agent Runtime 增加一个本机、多轮、可持久化、可观察并预留审批扩展能力的 Chat UI。

**技术栈：** React、TypeScript、Vite、FastAPI、SSE、Python 3.12、标准库 `sqlite3`、现有 JSONL Trace、Playwright、pytest。

---

## 1. 背景与设计原则

Phase 1A–1C 已建立领域模型、只读工具、Agent Loop、OpenAI-compatible Provider、JSONL Trace、SSE 和本地 Trace Viewer。当前 Viewer 能解释一次运行中模型和工具发生了什么，但不能创建对话、维持多轮上下文或处理权限请求。

Phase 1D 在第二阶段之前补齐“人如何使用 Agent”的交互层，同时保持学习优先和最小权限原则：

1. Chat 是控制面，负责对话、运行状态和权限决策；Trace 是观察面，负责完整技术细节。
2. 核心 Agent Runtime 不依赖 React、FastAPI 或 SQLite；Web 与持久化通过独立适配层调用 Runtime。
3. Phase 1D 仍然是只读 Agent，不新增写文件、Shell、Git、网络工具或无沙箱全盘访问。
4. 权限模型先实现两个用户可理解的模式，但内部使用可扩展的权限维度，避免第二阶段推倒重来。
5. JSONL 继续作为每次 Agent 运行的事实记录；SQLite 不复制完整 Trace。
6. 前端先实时显示 Agent 状态和完整工具步骤，模型最终回答一次性返回；逐 Token streaming（流式输出）以后增加。

## 2. 已确认的产品范围

### 2.1 本阶段包含

- React + TypeScript + Vite Chat UI。
- 一个对话绑定一个明确的本地项目根目录。
- 多个持久化对话，每个对话支持多轮用户/助手消息。
- 对话列表、创建对话、切换对话、发送消息和重新打开历史对话。
- Agent 运行时实时显示模型请求、工具调用、工具结果和最终状态的摘要卡片。
- 每次运行可跳转到独立 Trace 页面查看完整底层事件。
- `PROJECT_READ_ONLY` 与 `ASK_FOR_ACCESS` 两种权限模式。
- `ASK_FOR_ACCESS` 下，对项目根目录以外的只读访问创建一次性审批请求。
- SQLite 保存对话、可见消息、运行映射、审批记录和状态。
- FastAPI 同源 API 与 SSE；服务继续只绑定 `127.0.0.1`。
- FakeModel 驱动的单元、集成和浏览器端到端测试。

### 2.2 本阶段不包含

- 写文件、应用 Diff、删除文件、Shell、Git、测试执行或网络工具。
- 对写操作、命令或网络访问的审批。
- 永久目录授权、“本次会话全部允许”或真正的 unrestricted full access（无限制访问）。
- Provider Token 级流式输出。
- 多 Agent、Planning、Checkpoint、Memory、Skills、Hooks、MCP 或 Sandbox。
- 登录、远程访问、局域网或公网部署。
- 将现有 Trace Viewer 全面重写为 React。
- 服务器重启后恢复正在执行的 Python 协程；重启时未完成运行会被标记为 `interrupted`，用户可重新发送消息。

## 3. 方案选择

### 3.1 采用的方案：独立 React Chat + 保留原生 Trace Viewer

仓库增加独立 React Chat 应用，构建产物由现有 FastAPI 服务提供。Trace Viewer 保留现有原生 HTML/CSS/TypeScript 实现，入口从 `/` 调整为 `/trace`；Chat 成为 `/` 与 `/chat` 的主界面。

选择原因：

- Chat 后续会增加审批、流式消息、多会话和多 Agent 状态，React 组件与状态模型更适合持续扩展。
- Trace Viewer 已完成并通过验收，本阶段重写不会增加 Agent Engineering 学习价值。
- 两个页面共享同一 FastAPI 进程、SSE 基础设施和 Trace 数据，但职责保持分离。

### 3.2 未采用的方案

**继续使用原生 TypeScript：** 依赖最少，但审批和多会话状态增长后，手工 DOM 与状态同步的维护成本较高。

**立即统一重写全部前端：** 视觉和组件可以统一，但会扩大 Phase 1D 范围并使已经验收的 Trace Viewer 重新进入风险区。

## 4. 总体架构

```text
Browser
├─ React Chat UI (/chat)
│  ├─ Conversation list
│  ├─ Message timeline
│  ├─ Activity cards
│  └─ Approval card
└─ Existing Trace Viewer (/trace?session_id=...)
              │
              │ same-origin HTTP + SSE
              ▼
FastAPI Local App (127.0.0.1 only)
├─ Chat API
├─ ChatEventBroker
├─ RunSupervisor
├─ ConversationRunner
├─ ApprovalCoordinator
├─ ConversationRepository ── SQLite
└─ Existing Viewer API ────── JSONL Trace
              │
              ▼
AgentLoop + ToolRegistry + Path/Access Policy
```

边界如下：

- `ConversationRepository` 只负责结构化业务状态，不了解 React 或 Agent 工具实现。
- `RunSupervisor` 持有当前进程内的运行任务，执行每个对话只能有一个 active run 的约束，并在应用关闭时清理任务。
- `ConversationRunner` 负责一次用户消息的编排：加载历史、启动 Agent、保存结果、投影 UI 事件。
- `AgentLoop` 继续只依赖领域协议，不直接读写 SQLite，也不返回 FastAPI 类型。
- `ApprovalCoordinator` 是运行中工具调用与用户审批之间的异步桥梁。
- `ChatEventBroker` 传输适合 Chat 的安全事件，不直接把完整 Trace payload 暴露给 Chat 页面。
- JSONL Trace 仍由现有 `JsonlEventSink` 可靠写入；Chat 与 Trace 通过 `session_id` 关联。

## 5. 前端信息架构

### 5.1 Chat 页面

桌面布局分为三部分：

1. 左侧对话栏：新建对话、历史对话、最近状态。
2. 中间主区域：用户/助手消息、Agent activity（活动）卡片、审批卡片、输入框。
3. 顶部上下文栏：项目根目录、权限模式、运行状态和“查看 Trace”入口。

窄屏下左侧栏变为可展开抽屉，主区域保持单列，工具参数与长路径必须换行或横向滚动，不能遮挡输入框。

### 5.2 Activity 卡片

Chat 不显示完整模型上下文或原始 JSON，而显示可学习的摘要：

- `Thinking`：正在请求模型。
- `Tool requested`：工具名与安全化参数摘要。
- `Tool completed`：成功/失败与结果摘要。
- `Waiting for approval`：请求的规范化路径与只读操作。
- `Run completed` / `Run failed`：最终状态、耗时和 Trace 链接。

卡片可以展开查看本次事件的安全摘要，但完整参数、完整结果、Context Snapshot 和 Raw JSON 只在 Trace 页面查看。

### 5.3 审批交互

审批卡片必须明确显示：

- 发起访问的工具。
- 规范化后的绝对路径。
- 操作类型，本阶段固定为 `read`。
- 授权范围：仅当前 `session_id + tool_call_id + path + operation` 一次有效。
- `Approve once` 与 `Deny` 两个动作。

审批期间输入框禁用，状态显示 `Waiting for approval`。重复点击或已决策请求返回确定性冲突提示，不重复执行工具。

## 6. 对话、运行与消息模型

### 6.1 对话生命周期

创建对话时必须提供：

- `title`：可由第一条消息生成默认标题，用户可稍后修改。
- `project_root`：后端解析并验证为存在的本地目录。
- `permission_mode`：`PROJECT_READ_ONLY` 或 `ASK_FOR_ACCESS`。

`project_root` 创建后不可更改，避免历史消息、Trace 和权限边界失去语义。`permission_mode` 只能在对话空闲且没有待审批请求时修改。

同一对话同时只允许一个 active run（活动运行）；并发发送返回 HTTP `409`。不同对话可以并发运行。

### 6.2 多轮上下文

SQLite 保存 Chat 可见的 `user` 与最终 `assistant` 消息。新一轮运行加载该对话此前的可见消息，加上当前用户消息，再交给 Agent Runtime 构造上下文。

单轮内部的模型工具调用消息和工具结果继续只存在于该轮 Runtime 状态与 JSONL Trace，不复制为下一轮长期上下文。这样可以先学习清晰的多轮边界，避免 SQLite 与 Trace 出现两份不一致的内部历史。后续 Memory 阶段再引入摘要、选择性工具结果和 Context 来源管理。

### 6.3 运行关联

每条用户消息创建一个 `session_id`。SQLite 的 run 记录保存：

- `session_id`
- `conversation_id`
- 触发运行的 `user_message_id`
- 最终 `assistant_message_id`
- `status`
- `started_at`、`finished_at`
- `trace_path` 的相对标识

Trace Viewer 使用同一个 `session_id` 加载 JSONL。Chat 页面不通过文件路径猜测关联关系。

运行状态为：

```text
queued → running → waiting_approval → running → completed
                              └───────────────→ failed
queued/running/waiting_approval ── process restart ──→ interrupted
```

## 7. 权限模型

### 7.1 用户可选模式

#### `PROJECT_READ_ONLY`

- 允许读取对话绑定的项目根目录内部内容。
- 项目外路径直接拒绝，不创建审批。
- 保持当前 Phase 1B 的默认安全语义。

#### `ASK_FOR_ACCESS`

- 项目根目录内部仍按只读策略自动允许。
- 项目外只读访问先创建审批请求并暂停当前工具调用。
- 用户批准后，只执行这一次精确访问；下一个路径或下一次调用必须重新审批。
- 用户拒绝后，工具向模型返回结构化拒绝结果，Agent 可以据此继续回答。

### 7.2 内部权限维度

内部决策不使用单个“全权限”布尔值，而使用以下字段：

```text
resource: filesystem
operation: read
scope: project | external_exact_path
decision: allow | deny | ask
```

第二阶段可以在不改变 Chat API 基本形状的情况下扩展 `write`、`shell`、`git` 和 `network`，但这些操作在 Phase 1D 中必须被拒绝。

### 7.3 不可审批的硬拒绝

即使处于 `ASK_FOR_ACCESS`，以下内容也不能通过审批绕过：

- `.env`、凭据、私钥、Token、Cookie 和项目已有敏感文件规则。
- 不存在、解析失败或符号链接解析后不符合申请路径的目标。
- 写入、删除、执行、Shell、Git 或网络操作。
- 请求审批后参数发生变化的工具调用。

所有判断使用 `resolve()` 后的规范路径；UI 显示的路径与最终执行校验的路径必须一致，以防止 symlink（符号链接）或相对路径替换。

## 8. SQLite 持久化

Phase 1D 使用 Python 标准库 `sqlite3`，不新增 ORM。通过 Repository（仓储）接口隔离 SQL，事务边界保持明确。

数据库默认位于 `.agent-foundations/chat.sqlite3`，CLI 提供 `--state-db` 覆盖路径；该运行目录必须加入 `.gitignore`。

初始表：

| 表 | 责任 |
|---|---|
| `schema_version` | 保存本地 schema 版本，启动时执行受控迁移 |
| `conversations` | 标题、规范项目根目录、权限模式、创建/更新时间 |
| `messages` | 对话可见的 user/assistant 消息及顺序 |
| `runs` | `conversation_id` 与 Trace `session_id` 的映射及运行状态 |
| `approval_requests` | 精确资源、操作、状态、请求和决策时间 |

约束：

- 所有主键使用应用生成的 UUID 字符串。
- 时间统一保存为 UTC ISO 8601。
- 外键开启，删除对话不是 Phase 1D 功能。
- 用户消息与 run 创建在同一事务中。
- assistant 消息与 run 完成在同一事务中。
- 审批只能从 `pending` 原子迁移到 `approved` 或 `denied`。
- 启动时将遗留的 `queued`、`running`、`waiting_approval` 标记为 `interrupted`。

SQLite 不保存 API Key、完整 Provider 原始响应、完整工具结果或完整 Trace payload。

Repository 每次操作在工作线程中创建短生命周期连接并使用短事务，避免同步 `sqlite3` I/O 阻塞 FastAPI 事件循环；连接不跨线程共享。

## 9. HTTP 与 SSE 契约

所有接口保持同源，不启用宽泛 CORS。

### 9.1 HTTP API

```text
POST   /api/chat/conversations
GET    /api/chat/conversations
GET    /api/chat/conversations/{conversation_id}
PATCH  /api/chat/conversations/{conversation_id}
GET    /api/chat/conversations/{conversation_id}/messages
POST   /api/chat/conversations/{conversation_id}/messages
GET    /api/chat/runs/{session_id}
POST   /api/chat/approvals/{approval_id}/decision
```

发送消息接口在保存用户消息并创建 run 后返回 HTTP `202` 与 `session_id`。RunSupervisor 使用受控 `asyncio.Task` 运行 Agent、持有任务引用并处理完成回调；不使用无法跟踪长生命周期审批等待的普通 `BackgroundTasks`。状态和结果经 SSE 返回。

项目路径不存在、不是目录或无法解析返回 `422`；对话不存在返回 `404`；同一对话已有活动运行、重复审批或非法状态迁移返回 `409`。客户端错误不包含服务器堆栈或未经脱敏的 Provider 内容。

### 9.2 SSE API

```text
GET /api/chat/conversations/{conversation_id}/events
```

Chat SSE 事件使用稳定 envelope（信封）：

```json
{
  "event_id": "uuid",
  "conversation_id": "uuid",
  "session_id": "uuid",
  "type": "run.started",
  "occurred_at": "2026-08-02T00:00:00Z",
  "data": {}
}
```

Phase 1D 事件类型：

- `run.started`
- `model.requested`
- `tool.requested`
- `tool.completed`
- `tool.failed`
- `approval.requested`
- `approval.resolved`
- `assistant.message.completed`
- `run.completed`
- `run.failed`

ChatEventBroker 可以从 TraceEvent 投影模型和工具活动，但只输出经过脱敏和长度限制的摘要。`assistant.message.completed` 一次性携带最终回答，不承诺 Token 增量。

SSE 断线后客户端先重新读取 conversation、messages 和 run 状态，再重新连接；Phase 1D 不实现持久化 SSE event replay。JSONL Trace 保证完整运行事实不会因 Chat SSE 断线丢失。

## 10. 后端运行与审批数据流

### 10.1 正常运行

1. 浏览器创建或打开对话，并建立 conversation SSE。
2. 用户发送消息。
3. API 在一个事务中保存 user message 与 queued run，返回 `202 + session_id`。
4. RunSupervisor 注册受控任务；ConversationRunner 加载可见历史，设置 run 为 `running`。
5. AgentLoop 使用已有只读 ToolRegistry 执行该轮。
6. TraceEvent 同时进入可靠 JSONL sink 和 Chat 安全投影。
7. Agent 返回最终答案；Repository 在同一事务中保存 assistant message 并完成 run。
8. Chat 收到最终消息和完成事件，提供 Trace 链接。

### 10.2 项目外只读审批

1. Tool 请求规范化后发现目标超出项目根目录。
2. AccessController 根据模式返回 `deny` 或 `ask`。
3. `ask` 时 ApprovalCoordinator 保存 pending request，将 run 设为 `waiting_approval` 并发出 SSE。
4. 用户批准或拒绝；API 原子更新 request，并唤醒同一进程中的等待工具调用。
5. 批准时执行前再次校验 tool call、operation 和规范路径完全一致，然后只执行一次。
6. 拒绝时生成结构化 ToolResult，不抛出未处理异常。
7. run 恢复为 `running`，Agent 继续当前轮。

如果服务在等待审批时退出，数据库启动恢复会把 run 标记为 `interrupted`；旧 approval 不能在新进程中继续执行。

## 11. 错误处理与安全显示

- Provider、Tool 和 Runtime 错误先写入脱敏 Trace，再投影为短的用户可理解错误。
- Chat 不显示 API Key、完整环境变量、内部堆栈、未经脱敏的 raw response 或项目外未获批文件内容。
- React 将消息和工具结果作为纯文本渲染；Phase 1D 不解析或执行模型返回的 HTML。
- 所有 ID 和路径参数由后端验证，不直接拼接为数据库 SQL 或文件路径。
- Chat 服务与 Trace Viewer 均只绑定 `127.0.0.1`。
- Provider API Key 和模型配置继续由服务端环境变量提供，不在 Chat UI 中读取、编辑或返回。
- 前端刷新不影响已开始的同进程运行；重新打开对话可从 SQLite 恢复可见消息与状态。
- 浏览器关闭不会自动批准、拒绝或取消权限请求。

## 12. 测试策略

### 12.1 Python 单元测试

- SQLite schema、Repository CRUD、事务和非法状态迁移。
- 多轮可见消息组装，不把旧工具内部消息混入下一轮。
- 两种权限模式的 project/external/sensitive-path 决策矩阵。
- 一次性精确审批、重复决策、参数替换和 symlink 防护。
- TraceEvent 到 ChatEvent 的脱敏、摘要和长度限制。
- 启动时把未完成 run 转为 `interrupted`。

### 12.2 集成测试

- 创建对话、发送消息、读取历史和更新空闲权限模式。
- 同一对话并发发送返回 `409`，不同对话可以独立运行。
- FakeModel + 只读工具完成一轮，并能通过 `session_id` 加载 Trace。
- `ASK_FOR_ACCESS` 的批准、拒绝和服务重启中断语义。
- SSE 事件顺序、断线重连后的 HTTP 状态恢复。
- API 错误不泄露敏感路径内容、密钥或堆栈。

### 12.3 React 测试

- 对话列表、消息时间线和运行状态 reducer。
- Activity 卡片与 Trace 链接。
- 审批卡片只能决策一次。
- 长消息、长路径、窄屏和错误状态不溢出。

### 12.4 端到端测试

Playwright 使用 FakeModel 启动本机应用，验证：

1. 创建绑定 fixture 项目的 `PROJECT_READ_ONLY` 对话。
2. 发送两轮消息并在刷新后恢复历史。
3. 实时看到工具步骤，最终回答一次性出现。
4. 从 run 卡片跳转到对应 Trace session。
5. 在 `ASK_FOR_ACCESS` 中批准一次项目外 fixture 只读访问。
6. 第二次相同访问再次要求审批。
7. 拒绝访问后 Agent 收到结构化拒绝并正常结束或给出可理解失败。

所有自动测试使用 FakeModel 与临时目录，不调用真实模型、真实付费 API 或用户真实项目外文件。

## 13. 代码组织方向

具体文件名将在实施计划中依据当前代码再次核定，模块职责固定为：

```text
src/agent_foundations/chat/
├─ models.py          # Conversation、Run、Approval 与 ChatEvent 领域类型
├─ repository.py      # SQLite Repository 与 migration
├─ events.py          # ChatEventBroker 与 Trace-to-Chat projection
├─ approvals.py       # AccessController 与 ApprovalCoordinator
├─ supervisor.py      # 进程内 run task 生命周期与并发约束
├─ runner.py          # ConversationRunner 编排
└─ api.py             # FastAPI Chat routes

web/chat/
├─ components/        # Conversation、Message、Activity、Approval 组件
├─ state/             # API client、SSE client、reducer
├─ App.tsx
└─ main.tsx
```

现有 `runtime/`、`viewer/` 和 `tools/filesystem/` 只做使新边界成立的最小修改，不进行无关重构。

## 14. 依赖与构建策略

- Python 持久化使用标准库 `sqlite3`，不引入 SQLAlchemy。
- 前端新增 `react`、`react-dom`、`vite` 和必要的 TypeScript React 类型。
- 测试优先使用 Vitest + Testing Library；Playwright 继续沿用现有 Python 端到端环境，避免再增加第二套浏览器驱动。
- 根 `package.json` 保留现有 Trace Viewer 脚本，并新增 Chat 的 dev、typecheck、test 和 build 脚本。
- Vite 构建产物输出到 Python package 内的专用静态目录，由 FastAPI 提供；源码与生成物边界在实施 Task 中明确。
- 依赖安装属于后续实施动作，执行前必须按项目规则单独获得用户确认。

## 15. 分阶段交付边界

Phase 1D 应拆为可独立验收的顺序增量：

1. SQLite 对话与运行模型。
2. Chat API 与多轮 ConversationRunner。
3. Chat SSE 安全事件投影。
4. 两种只读权限模式与一次性审批。
5. React/Vite 基础框架与对话 UI。
6. Activity、审批与 Trace 跳转。
7. 浏览器端到端、文档和 Phase 1D 总验收。

详细实施计划必须继续遵守一次一个 Task、真实 Red → Green → Refactor、不得自动调用真实模型、不得自动 commit/push 的项目规则。

## 16. 完成标准

- 用户能在本机 Web UI 创建绑定项目根目录的对话并进行多轮交互。
- 刷新或重新启动应用后，已完成对话和消息仍可读取。
- 每个用户 turn 都有独立 `session_id`，可从 Chat 准确打开完整 JSONL Trace。
- 工具步骤实时出现，最终回答完整返回；不虚假宣称已实现 Token streaming。
- `PROJECT_READ_ONLY` 对项目外路径稳定拒绝。
- `ASK_FOR_ACCESS` 对项目外只读访问稳定创建一次性精确审批，批准和拒绝均可审计。
- 敏感文件、写操作、Shell、Git 和网络不能通过审批绕过。
- 服务仍只绑定 `127.0.0.1`，测试不访问真实模型或用户真实外部文件。
- pytest、Ruff、mypy、React typecheck、前端单元测试、Vite build、Playwright E2E、`pip check` 和 `git diff --check` 全部以新鲜输出通过。
