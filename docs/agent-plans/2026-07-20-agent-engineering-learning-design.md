# Agent Engineering 系统学习与产品演进设计

**状态：** 已确认

**日期：** 2026-07-20

**保守刷新：** 2026-08-07（依据 2026-08-04 开源 Agent 项目调研；不改变 Phase 1D 范围与 Task 9–12）

**主工作区：** `D:\codex-pj\search_agent`

**学习投入：** 每周 20 小时以上

## 1. 目标

从零实现一个可测试、可观察、安全受控的 Python Agent Runtime（智能体运行时），以编程智能体作为第一个完整应用，再逐步加入离线 Agent Eval（智能体评测）、可写工具、Shell、Git、Context Engineering、Durable Execution（持久化执行）、Memory、Skills、MCP、Sandbox 和 Sub-Agent，最终形成可扩展的通用多 Agent 平台。

本项目以系统学习 Agent Engineering 为第一目标，以可运行产品为每阶段的验证手段。学习过程必须亲自实现核心抽象，再与成熟开源项目进行源码对照，避免只会修改配置、提示词或界面。外部框架只作对照，不替代自研 Agent Loop、状态机、权限和执行核心；MCP、ACP、A2A 等外部协议通过 Adapter（适配器）接入，内部领域协议保持稳定且不绑定单一生态。

## 2. 已确认约束

- 前期使用 Anaconda，不使用全局 Python 环境。
- 第一阶段使用 Python 3.12。
- 第一阶段只接入一个 OpenAI-compatible API，通过统一 `ModelProvider` 预留其他模型适配能力。
- API Key 只从环境变量读取，不写入代码、Trace 或文档。
- 第一版产品入口是 CLI。
- 第一版 Agent 只能读取和分析代码，不允许修改文件。
- 第一版不提供 Shell 或 Git 工具。
- 第一版只提供 `list_directory`、`read_file`、`search_text` 三个文件工具。
- 第一版增加本地 Web Trace Viewer，专门用于学习和调试，不作为面向最终用户的 Web UI。
- 实现过程遵循 TDD、最小必要改动、阶段验收和频繁提交。

## 3. 仓库策略

```text
D:\codex-pj\
├── search_agent\               # 自研 Python Agent Runtime，所有原创代码在此实现
├── agent-reference-repos\      # 第三方参考仓库，只读
│   ├── smolagents\
│   ├── pydantic-ai\
│   ├── langgraph\
│   ├── openai-agents-python\
│   ├── microsoft-agent-framework\
│   ├── google-adk\
│   ├── deer-flow\
│   ├── openhands\
│   ├── goose\
│   ├── mini-swe-agent\
│   ├── browser-use\
│   ├── letta\
│   ├── letta-code\
│   ├── opencode\
│   ├── openai-codex\
│   └── grok-build\
└── qwen-code-custom\           # 中期正式 Fork Qwen Code 后的产品实验
```

规则：

1. `search_agent` 是长期主线，不复制第三方核心代码。
2. `agent-reference-repos` 中的仓库仅用于阅读、运行测试和架构对照，不在其中实现新功能。
3. 前十周不 Fork 大型 Coding Agent。
4. 自研 Runtime 完成可控 Coding Agent 阶段后，先通过 Coding Harness 基线比较门，再决定是否正式 Fork `QwenLM/qwen-code`。
5. Fork 前固定明确的 tag 或 commit，保存原项目测试与 Eval 基线，并记录 upstream remote、同步频率、冲突处理和停止同步条件；不得直接长期跟随快速变化的 `main`。
6. `OpenCode`、`Codex`、`Grok Build`、`OpenHands`、`goose` 和 `mini-SWE-agent` 先做主题式对照，不默认作为主项目 Fork。
7. `qwen-code-custom` 用于学习成熟 TypeScript 产品工程，不取代自研 Python Runtime。
8. 第三方许可证、NOTICE 和归属信息必须保留，不将参考代码伪装为原创实现。

## 4. 总体分层架构

```text
第五层：Multi-Agent Platform
主管 Agent、Sub-Agent、任务委派、共享状态、结果合并

第四层：Extensible Runtime
Eval、Durable Execution、Memory、Skills、Protocol Adapters、权限与 Sandbox

第三层：Coding Agent
代码库理解、任务规划、Diff、Shell、Git、测试反馈

第二层：Agent Runtime
Agent Loop、Tool Calling、Context、Session、Tracing

第一层：Foundations
Message、ModelProvider、结构化输出、配置与错误类型
```

实现严格由下向上。上层通过稳定接口调用下层；模型通信、工具执行、CLI、Trace 和可视化不能耦合在同一个模块中。

## 5. 第一阶段目录设计

```text
search_agent\
├── pyproject.toml
├── README.md
├── .env.example
├── src\
│   └── agent_foundations\
│       ├── cli\
│       │   ├── main.py
│       │   └── renderer.py
│       ├── domain\
│       │   ├── messages.py
│       │   ├── model.py
│       │   ├── tool.py
│       │   └── errors.py
│       ├── providers\
│       │   ├── base.py
│       │   └── openai_compatible.py
│       ├── tools\
│       │   ├── registry.py
│       │   └── filesystem\
│       │       ├── path_policy.py
│       │       ├── list_directory.py
│       │       ├── read_file.py
│       │       └── search_text.py
│       ├── context\
│       │   ├── builder.py
│       │   └── budget.py
│       ├── runtime\
│       │   ├── agent.py
│       │   ├── loop.py
│       │   ├── session.py
│       │   └── trace.py
│       └── viewer\
│           ├── app.py
│           ├── stream.py
│           └── static\
├── tests\
│   ├── unit\
│   ├── integration\
│   ├── e2e\
│   └── fixtures\
│       └── sample_project\
└── docs\
    ├── agent-plans\
    └── learning-notes\
```

## 6. 核心模块职责

| 模块 | 职责 |
|---|---|
| `domain` | 定义 Message、ToolCall、ModelRequest、ModelResponse、TraceEvent 和错误类型 |
| `providers` | 把统一模型请求转换为 OpenAI-compatible API 请求，屏蔽供应商差异 |
| `tools` | 注册、描述、校验和调用只读工具 |
| `path_policy` | 限制项目根目录、阻止路径穿越和敏感文件读取 |
| `context` | 选择消息、工具结果和代码内容，控制上下文预算 |
| `runtime` | 驱动 Agent Loop、Session、最大步数、终止条件和事件发布 |
| `trace` | 将结构化事件脱敏后写入 JSONL，并支持回放 |
| `viewer` | 在本机通过 FastAPI 和 SSE 展示实时或历史轨迹 |
| `cli` | 处理用户输入和结果渲染，不包含 Agent 核心逻辑 |

## 7. 核心接口

模型通信统一为异步接口：

```python
class ModelProvider(Protocol):
    async def complete(self, request: ModelRequest) -> ModelResponse:
        ...
```

工具统一为异步接口：

```python
class Tool(Protocol):
    name: str
    description: str

    def input_schema(self) -> dict[str, object]:
        ...

    async def execute(self, arguments: dict[str, object]) -> ToolResult:
        ...
```

事件输出统一为异步接口：

```python
class EventSink(Protocol):
    async def emit(self, event: TraceEvent) -> None:
        ...
```

Agent Loop 只依赖这些协议，不直接依赖 OpenAI SDK、FastAPI 或具体工具实现。

## 8. 第一版数据流

```text
用户在 CLI 输入分析任务
  → CLI 创建 Session 与 UserMessage
  → ContextBuilder 组合系统指令、历史消息和工具 Schema
  → ModelProvider 请求模型
  → 模型返回 ToolCall 或 FinalAnswer
  → ToolRegistry 校验工具名和参数
  → PathPolicy 校验文件路径和敏感规则
  → 工具执行并返回 ToolResult
  → Agent Loop 追加 ToolMessage
  → 模型继续决策
  → 达到 FinalAnswer 或终止条件
  → CLI 展示结果
  → EventSink 持久化并实时广播全部步骤
```

第一版默认最大执行十步。工具输出、单次文件读取和总上下文均有长度上限。Agent 不自动把整个仓库发送给模型，而是通过工具主动选择需要的文件。

## 9. Trace Viewer 设计

选择本地 Web Trace Viewer，而不是 TUI 或 PySide6 桌面窗口。

```text
Agent Runtime
     │
     │ TraceEvent
     ▼
CompositeEventSink
     ├── JsonlEventSink → traces/<session-id>.jsonl
     └── LiveEventSink  → SSE → Browser Trace Viewer
```

每个 `TraceEvent` 至少包含：

- `event_id`
- `session_id`
- `step_id`
- `event_type`
- `status`
- `timestamp`
- `duration_ms`
- `summary`
- `payload`

第一版事件类型：

- `session.started`
- `user.message`
- `model.request.started`
- `model.response.received`
- `tool.call.requested`
- `tool.call.validated`
- `tool.call.completed`
- `tool.call.failed`
- `agent.final_answer`
- `agent.loop.stopped`
- `session.completed`
- `session.failed`

Viewer 第一版使用 FastAPI、SSE、原生 HTML/CSS/TypeScript 和 JSONL，不引入 React。服务仅绑定 `127.0.0.1`。

第一版界面包括：

- Session 与运行状态栏
- 事件时间线
- 事件类型筛选
- 自动滚动暂停
- Overview、Model Input、Model Output、Tool Arguments、Tool Result、Context Snapshot、Raw JSON 和 Error 面板
- 历史 JSONL 回放
- 单事件 JSON 复制

Viewer 只能观察，不能修改 Agent 状态、批准工具或编辑 Prompt。多 Agent 关系图和 Token 可视化留到后期。

## 10. 错误处理

| 错误 | 处理方式 |
|---|---|
| `ProviderAuthenticationError` | 停止 Session，提示检查环境变量 |
| `ProviderRateLimitError` | 按受限次数退避重试 |
| `ProviderTimeoutError` | 重试后返回可读错误 |
| `InvalidModelResponseError` | 保存脱敏后的原始响应并停止当前步骤 |
| `UnknownToolError` | 把可用工具列表反馈给模型 |
| `InvalidToolArgumentsError` | 把参数错误反馈给模型，允许模型修正 |
| `PathPolicyViolationError` | 拒绝执行并记录安全事件 |
| `FileTooLargeError` | 提示模型缩小读取范围 |
| `BinaryFileError` | 拒绝按文本读取 |
| `ContextBudgetExceededError` | 截断低优先级内容并记录决策 |
| `MaxStepsExceededError` | 强制终止循环并解释原因 |

错误必须进入 Trace，记录发生步骤、重试次数和最终状态，但不得泄露密钥或完整环境变量。

## 11. 安全边界

- API Key 只通过环境变量读取，不进入日志或 Trace。
- 不提供批量读取环境变量的工具。
- Trace 保存前经过 `Redactor` 脱敏。
- 文件路径在界面中显示为项目相对路径。
- `PathPolicy` 使用解析后的绝对路径检查是否位于项目根目录。
- 默认拒绝 `.env`、私钥、凭据、Cookie 和常见敏感配置文件。
- 文件读取、工具结果和 Context 均设置硬上限。
- Viewer 只监听本机，不提供局域网或公网访问。
- Trace 可能包含源码，默认只保存在本地并被 Git 忽略。

## 12. 测试策略

### 单元测试

- Message、ToolCall、ModelRequest、ModelResponse 数据模型
- ToolRegistry 与 JSON Schema
- PathPolicy 与敏感文件规则
- Context Budget 与截断顺序
- Provider 错误映射
- Trace 脱敏

### 契约测试

- 所有 `ModelProvider` 返回统一结构。
- 所有 `Tool` 遵循统一输入输出协议。
- 所有 `EventSink` 接受相同 `TraceEvent`。

### 集成测试

- FakeModel 驱动完整多轮 Agent Loop。
- Mock HTTP 验证 OpenAI-compatible Provider。
- 工具参数错误后模型修正。
- JSONL 持久化、加载和回放。
- SSE 订阅和事件顺序。

### 端到端测试

- 启动 CLI 并分析 `sample_project`。
- 产生完整 Trace。
- Viewer 加载 Session 并显示事件详情。
- 核心自动测试不调用真实付费 API；真实模型仅用于用户主动执行的 Smoke Test。

### 离线 Agent Eval 基线

单元测试验证协议和确定性行为，Agent Eval 验证 Agent 是否更有效地完成任务。Phase 2 开头先固定 Phase 1 能力基线，再开放写入和 Shell 权限。

离线基线至少包含：

- 固定任务集：代码定位、错误解释、生成 Diff、测试失败修复和安全拒绝。
- 默认使用 FakeModel 或可回放响应，真实付费模型只作为用户明确授权的独立 profile。
- 指标：成功率、步骤数、无效工具调用、安全拒绝、审批次数、恢复次数、Token、成本和延迟；离线 profile 不强求真实 Token/成本。
- 每次结果记录任务集版本、Prompt 版本、模型/响应 fixture 版本、工具集合、Runtime commit 和环境信息。
- Phase 2–5 的能力增量必须与固定基线比较，不能只以“新增功能”代替行为改进证据。

### Durable Execution 边界

Checkpoint 不再只表示“保存一个状态对象”，而是 Durable Execution 的一个组成部分：

```text
Durable Execution
= 可持久化运行状态与 schema 版本
+ 明确的 resume / retry / cancel 入口
+ tool call 幂等键
+ 已执行副作用记录与提交结果
+ 崩溃点和重放测试
+ worker / run ownership 与 lease
```

恢复时必须区分“模型已经决定什么”和“现实世界已经执行什么”。写文件、Shell、Git 等副作用在记录提交状态前后都要有确定性恢复语义，避免崩溃后重复执行。多个 worker 不得同时拥有同一个 run；lease 过期、接管和取消必须可审计。

### Approval、Policy、Capability 与 Sandbox 分层

```text
Tool request
  → Policy：系统规则是否允许、拒绝或要求询问
  → Approval：用户是否同意这一次动作
  → Capability：把允许结果收敛为主体、run、tool call、资源、操作和有效期明确的最小授权
  → Sandbox：即使执行代码失控，仍限制进程、文件、网络和资源上限
  → Side-effect ledger + Trace：记录实际执行与结果
```

- Approval 表达人的决策，不负责强制隔离。
- Policy 是确定性系统规则，敏感资源与禁止操作可以硬拒绝且不可审批绕过。
- Capability 是可消费、可衰减、可审计的最小授权；未来 Sub-Agent 只能获得父 Agent 能力的子集。
- Sandbox 是最后的执行边界，不授予权限；用户批准也不能关闭 Sandbox。

### Phase 3–5 协议分工

内部领域模型是唯一核心协议，外部协议全部经 Adapter 转换：

| 协议/通道 | 负责 | 不负责 | 首次正式落点 |
|---|---|---|---|
| [MCP](https://modelcontextprotocol.io/docs/getting-started/intro) | Agent 与 Tool / Resource / Prompt Provider 的互操作 | UI 控制、Agent 委派、审批和 Sandbox | Phase 3 研究，Phase 5 实现 Client Adapter |
| [ACP](https://agentclientprotocol.com/get-started/introduction) | IDE、Chat/控制面与 Agent Backend 的会话、消息和运行交互 | Tool 协议和 Agent-to-Agent 委派 | Phase 3 对照，Phase 5 实现 Backend Adapter |
| [A2A](https://a2a-protocol.org/latest/) | 独立 Agent 之间的任务委派、状态和结构化结果交换 | 浏览器 UI 推送和底层工具调用 | Phase 5，在内部 `AgentTask` 稳定后接入 |
| SSE / UI Event | 本机 UI 的实时状态提示和交互更新 | 持久恢复、完整事实或跨 Agent 标准 | Phase 1D 已有最小版，Phase 5 扩展多 Agent 事件 |
| Trace / [OpenTelemetry](https://opentelemetry.io/docs/concepts/signals/traces/) | 运行观察、因果关联、指标、诊断和跨组件导出 | 控制命令、授权和恢复事实源 | JSONL Trace 贯穿；Phase 4 对照，Phase 5 增加 OTel Adapter |

HTTP、SQLite、Checkpoint 和 side-effect ledger 保存可恢复事实；SSE 断线后必须回读这些事实，不能把实时事件流当作 durable log。

## 13. 二十周学习与实现路线

本节是阶段级 Roadmap（路线图），用于分配学习目标和验收门。Phase 2–5 的每个实现增量在开始前仍须生成独立、经用户确认的设计与实施计划，写明文件、TDD Red/Green、evidence 路径和质量门禁；下面的周计划与复选框不构成 executor 授权。

### 阶段一：只读 Agent Runtime 与本机 Chat 控制面，第 1–6 周 + Phase 1D 验收增量

- [ ] 第 1 周：实现消息协议、模型请求响应和 FakeModel；周末只读对照 smolagents。
- [ ] 第 2 周：实现 Tool、ToolResult、JSON Schema 和 ToolRegistry；只读对照 OpenAI Agents SDK。
- [ ] 第 3 周：实现三个只读文件工具、PathPolicy、敏感文件和大小限制。
- [ ] 第 4 周：实现 Agent、AgentLoop、Session、ContextBuilder、OpenAI-compatible Provider 和 CLI；只读对照 Pydantic AI。
- [ ] 第 5 周：实现 TraceEvent、EventSink、JSONL、脱敏和回放。
- [ ] 第 6 周：实现 FastAPI、SSE 和本地 Web Trace Viewer，完成第一阶段验收。

Phase 1D 作为进入 Phase 2 前的独立验收增量，继续执行已确认的 12 个顺序 Task。Task 12 实现（恢复 API、E2E、文档）已完成 fresh 门禁，**awaiting independent review/user acceptance**；不提前加入 MCP、Memory、Sub-Agent、Shell、Sandbox 或 Token streaming。Phase 2 未开始。

第一阶段完成标准：

- CLI 可以指定并分析本地项目。
- Agent 能主动调用三个只读工具。
- Agent 无法读取项目根目录外或敏感文件。
- FakeModel 可以稳定复现完整 Agent Loop。
- 最大步骤限制能够终止异常循环。
- 所有步骤写入 JSONL 并实时显示在 Viewer。
- 历史 Trace 可以重新加载和回放。
- 测试、类型检查和代码风格检查通过。
- README 和学习笔记解释每个底层模块存在的原因。

### 阶段二：可控 Coding Agent，第 7–10 周

- [ ] 第 7 周：建立离线 Agent Eval 运行器和固定任务集，保存 Phase 1 基线；同时增加 Planning、Todo 和重规划限制。
- [ ] 第 8 周：把 Checkpoint 扩展为 Durable Execution，完成 schema/version、resume/retry/cancel、幂等键、副作用记录、崩溃点测试和单 run 所有权/lease；在该边界稳定后生成 Unified Diff。
- [ ] 第 9 周：实现 Approval、Policy、Capability 与 Sandbox 的分层；增加修改前审批、拒绝、回滚记录和最小 Docker Sandbox，再开放受控文件写入。
- [ ] 第 10 周：增加命令分类、只读 Shell 白名单、危险命令审批、Git 和测试反馈；合并 Repo Map、相关性评分、Context Budget、压缩、缓存、重试和限流，并跑离线 Eval 回归。

阶段完成标准：Agent 能分析、计划、生成 Diff、经批准修改文件并运行测试；离线 Eval 可比较能力变化；进程崩溃后可从版本化状态恢复且不会重复已提交副作用；单个 run 同时只有一个有效 owner；Approval、Policy、Capability 与 Sandbox 的职责和执行顺序有自动测试；所有危险动作可见、可拒绝、可追踪。

### 阶段三：基线比较与 Fork Qwen Code，第 11–14 周

- [ ] 第 11 周：先比较 Qwen Code、OpenCode、Codex、OpenHands、goose 与 mini-SWE-agent 的 Runtime、权限、协议、可维护性、许可证和同一离线任务基线；形成 Baseline Selection Gate，不预设 Qwen Code 必然胜出。
- [ ] 第 12 周：通过选择门后，固定候选仓库的明确 tag/commit，保存原测试与 Eval 结果，记录 upstream remote、同步频率、冲突处理、补丁重放和停止同步策略，再创建 `qwen-code-custom` Fork；若 Qwen Code 未通过门，先回到用户确认，不自动改选。
- [ ] 第 13 周：建立 Python 自研模块与 Fork 模块的架构映射，增加只读 Study Mode 和兼容 Trace 导出；逐项研究 Skills、Hooks、MCP、Sub-Agent、Memory、Plan Mode、Sandbox、Worktrees、Headless 和 ACP，并验证协议只通过 Adapter 接入。
- [ ] 第 14 周：只选择两项具有底层学习价值的个性化改造，优先统一 Trace Viewer、权限策略、中文学习模式或 Context 来源展示；完成一次上游差异检查和同步演练，不盲目合并 `main`。

Fork 后不优先修改主题、Logo 或其他表层内容。

### 阶段四：对照成熟 Runtime，第 15 周

- [ ] Runtime 组只读对照 OpenAI Agents SDK、Pydantic AI 和 LangGraph，重点研究 Agent Loop、HITL、Eval、Durable Execution 与类型/状态边界。
- [ ] 多 Agent 组只读对照 Google ADK 2.0、Microsoft Agent Framework 和 DeerFlow 2.0，重点研究 Workflow/Task、Checkpoint、Sub-Agent 隔离和 OpenTelemetry。
- [ ] Coding Harness 组只读对照 OpenHands、goose、mini-SWE-agent、OpenCode、OpenAI Codex 和 Grok Build；Browser Use 单独研究浏览器运行边界；Letta Agent/Letta Code 作为 Memory 与状态化 Coding Agent 对照。
- [ ] 输出按主题而非按项目堆叠的架构比较文档，明确哪些设计进入自研 Runtime、哪些通过 Adapter 接入、哪些只保留为参考。

### 阶段五：通用多 Agent 平台，第 16–20 周

- [ ] 第 16 周：实现内部 AgentDefinition、AgentTask、父子 Agent、任务委派、独立 Context、结构化结果回传和并发限制；子 Agent 的 Capability 必须从父 Agent 衰减，不能扩大权限。
- [ ] 第 17 周：实现 Working、Session、Project Memory 和记忆生命周期，对照 Letta Agent/Letta Code；Memory 不作为权限或恢复事实源。
- [ ] 第 18 周：实现 Skill Manifest、Skill Loader、Hooks、MCP Client Adapter、ACP Backend Adapter 和权限声明；在内部 AgentTask 稳定后增加最小 A2A Adapter。
- [ ] 第 19 周：强化 Docker Sandbox、资源限制、网络策略、挂载白名单和清理机制；验证多 Agent run ownership、租约接管和副作用幂等。
- [ ] 第 20 周：将 Trace Viewer 升级为 Multi-Agent Studio，扩展 SSE/UI Event 展示任务树、并行时间线、Context、Token、成本和人工干预点，并增加 Trace 到 OpenTelemetry 的导出 Adapter。

### 更新后的参考项目矩阵

| 参考项目 | 主要学习主题 | 使用方式 |
|---|---|---|
| [DeerFlow 2.0](https://github.com/bytedance/deer-flow) | Super Agent Harness、Skills、Memory、Sandbox、Context Compaction、隔离 Sub-Agent | Phase 4 多 Agent 对照，不引入其 Runtime |
| [OpenHands](https://github.com/OpenHands/OpenHands) | Agent 控制面、可替换 Backend、ACP、本地/远程 Runtime | Phase 3 Fork 比较 + Phase 4 Harness 对照 |
| [goose](https://github.com/aaif-goose/goose) | Desktop/CLI/API、MCP 扩展、ACP 互操作 | Phase 3 Fork 比较 + 协议对照 |
| [mini-SWE-agent](https://github.com/SWE-agent/mini-swe-agent) | 极简线性 Agent Loop、Coding Eval 基线 | Phase 2 Eval 外部基线 + Phase 3 复杂度校准 |
| [Google ADK 2.0](https://github.com/google/adk-python) | Workflow Runtime、Event/Session 版本、Task API | Phase 4 多 Agent 对照 |
| [Microsoft Agent Framework](https://github.com/microsoft/agent-framework) | Checkpoint、Time Travel、HITL、Skills、OpenTelemetry | Phase 4 多 Agent 与可观察性对照，替代 AutoGen 作为主要 Microsoft 新项目基线 |
| [Pydantic AI](https://github.com/pydantic/pydantic-ai) | 类型化 Agent、Eval、Capability、HITL、Durable Execution、MCP/UI | Phase 2–4 Runtime 对照，不替代自研核心 |
| [LangGraph](https://github.com/langchain-ai/langgraph) | 状态机、Durable Execution、HITL、Memory | Phase 2–4 恢复语义对照，不直接采用框架 |
| [Browser Use](https://github.com/browser-use/browser-use) | 浏览器 Harness、持久浏览器状态、恢复循环 | Phase 4 独立运行边界对照 |
| [Letta Agent](https://github.com/letta-ai/letta) / [Letta Code](https://github.com/letta-ai/letta-code) | 长期 Memory、身份、状态化 Coding Agent | Phase 5 Memory 生命周期对照 |

参考项目的 README、API 和主分支会变化。每次正式对照前都要记录访问日期和 tag/commit；表中结论是学习路由，不是永久 API 契约。

## 14. 每周学习节奏

建议每周 24 小时：

- 4 小时：概念、协议和论文学习。
- 10 小时：测试驱动实现。
- 4 小时：参考仓库主题式源码对照。
- 3 小时：测试、重构和评测。
- 3 小时：学习笔记与架构总结。

每周必须产生：

1. 一个可以运行的增量。
2. 一组自动测试。
3. 一篇学习笔记。
4. 至少一个范围清晰的 Git Commit。
5. 一份与参考实现的差异或取舍结论。

## 15. 最终成功标准

完成二十周后，项目应具备：

- 自研 Python Agent Runtime。
- 模型无关的 Provider 接口。
- 可校验、可授权的 Tool 系统。
- 可观察、可回放的 Trace Event 协议和 Web Studio。
- Context、Planning、Checkpoint、Memory、Skills、MCP 和 Hooks。
- 离线 Agent Eval 基线与可重复比较报告。
- 包含版本、恢复、幂等、副作用记录和运行所有权的 Durable Execution。
- 清晰分层的 Approval、Policy、Capability 与 Sandbox。
- 经审批的文件修改、Shell、Git 和测试能力。
- Docker Sandbox。
- Sub-Agent 与多 Agent 任务编排。
- Qwen Code 的实质性个性化 Fork。
- MCP、ACP、A2A、SSE/UI Event 和 Trace/OpenTelemetry 的 Adapter 与职责边界。
- 对更新后参考项目矩阵的主题式架构比较结论。
- 完整测试、学习笔记和阶段验收记录。
