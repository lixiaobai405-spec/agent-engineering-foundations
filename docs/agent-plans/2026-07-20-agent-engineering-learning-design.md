# Agent Engineering 系统学习与产品演进设计

**状态：** 已确认

**日期：** 2026-07-20

**主工作区：** `D:\codex-pj\search_agent`

**学习投入：** 每周 20 小时以上

## 1. 目标

从零实现一个可测试、可观察、安全受控的 Python Agent Runtime（智能体运行时），以编程智能体作为第一个完整应用，再逐步加入可写工具、Shell、Git、Context Engineering、Memory、Skills、MCP、Sandbox 和 Sub-Agent，最终形成可扩展的通用多 Agent 平台。

本项目以系统学习 Agent Engineering 为第一目标，以可运行产品为每阶段的验证手段。学习过程必须亲自实现核心抽象，再与成熟开源项目进行源码对照，避免只会修改配置、提示词或界面。

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
│   ├── openai-agents-python\
│   ├── opencode\
│   ├── openai-codex\
│   └── grok-build\
└── qwen-code-custom\           # 中期正式 Fork Qwen Code 后的产品实验
```

规则：

1. `search_agent` 是长期主线，不复制第三方核心代码。
2. `agent-reference-repos` 中的仓库仅用于阅读、运行测试和架构对照，不在其中实现新功能。
3. 前十周不 Fork 大型 Coding Agent。
4. 自研 Runtime 完成可控 Coding Agent 阶段后，正式 Fork `QwenLM/qwen-code`。
5. `OpenCode`、`Codex`、`Grok Build` 只做主题式对照阅读，不作为主项目 Fork。
6. `qwen-code-custom` 用于学习成熟 TypeScript 产品工程，不取代自研 Python Runtime。
7. 第三方许可证、NOTICE 和归属信息必须保留，不将参考代码伪装为原创实现。

## 4. 总体分层架构

```text
第五层：Multi-Agent Platform
主管 Agent、Sub-Agent、任务委派、共享状态、结果合并

第四层：Extensible Runtime
Memory、Skills、MCP、Hooks、Checkpoint、权限与 Sandbox

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

## 13. 二十周学习与实现路线

### 阶段一：只读 Agent Runtime，第 1–6 周

- [ ] 第 1 周：实现消息协议、模型请求响应和 FakeModel；周末只读对照 smolagents。
- [ ] 第 2 周：实现 Tool、ToolResult、JSON Schema 和 ToolRegistry；只读对照 OpenAI Agents SDK。
- [ ] 第 3 周：实现三个只读文件工具、PathPolicy、敏感文件和大小限制。
- [ ] 第 4 周：实现 Agent、AgentLoop、Session、ContextBuilder、OpenAI-compatible Provider 和 CLI；只读对照 Pydantic AI。
- [ ] 第 5 周：实现 TraceEvent、EventSink、JSONL、脱敏和回放。
- [ ] 第 6 周：实现 FastAPI、SSE 和本地 Web Trace Viewer，完成第一阶段验收。

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

- [ ] 第 7 周：增加 Planning、Todo、重规划限制和 Checkpoint 基础结构。
- [ ] 第 8 周：增加 Unified Diff、修改前审批、拒绝修改和回滚记录。
- [ ] 第 9 周：增加命令分类、只读 Shell 白名单、危险命令审批、Git 和测试反馈；开始引入 Docker Sandbox。
- [ ] 第 10 周：增加 Repo Map、相关性评分、Context Budget、压缩、缓存、重试和限流。

阶段完成标准：Agent 能分析、计划、生成 Diff、经批准修改文件并运行测试；所有危险动作可见、可拒绝、可追踪。

### 阶段三：Fork Qwen Code，第 11–14 周

- [ ] 第 11 周：在 GitHub Fork `QwenLM/qwen-code`，克隆到 `D:\codex-pj\qwen-code-custom`，固定基线并通过原项目测试。
- [ ] 第 12 周：建立 Python 自研模块与 Qwen Code 模块的架构映射，增加只读 Study Mode 和兼容的 Trace 导出。
- [ ] 第 13 周：逐项研究 Skills、Hooks、MCP、Sub-Agents、Memory、Plan Mode、Sandbox、Worktrees、Headless 和 ACP。
- [ ] 第 14 周：只选择两项具有底层学习价值的个性化改造，优先统一 Trace Viewer、权限策略、中文学习模式或 Context 来源展示。

Fork 后不优先修改主题、Logo 或其他表层内容。

### 阶段四：对照成熟 Runtime，第 15 周

- [ ] 只读克隆 OpenCode、OpenAI Codex 和 Grok Build。
- [ ] 只研究 Agent Loop、Permission、Sandbox、Context、Workspace 和 Extension 六个主题。
- [ ] 输出架构比较文档，明确哪些设计进入自研 Runtime，哪些只保留为参考。

### 阶段五：通用多 Agent 平台，第 16–20 周

- [ ] 第 16 周：实现 AgentDefinition、AgentTask、父子 Agent、任务委派、独立 Context 和并发限制。
- [ ] 第 17 周：实现 Working、Session、Project Memory 和记忆生命周期，再对照 Letta 与 Mem0。
- [ ] 第 18 周：实现 Skill Manifest、Skill Loader、MCP Client、Hooks 和权限声明。
- [ ] 第 19 周：实现 Docker Sandbox、资源限制、网络策略、挂载白名单和清理机制。
- [ ] 第 20 周：将 Trace Viewer 升级为 Multi-Agent Studio，展示任务树、并行时间线、Context、Token、成本和人工干预点。

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
- 经审批的文件修改、Shell、Git 和测试能力。
- Docker Sandbox。
- Sub-Agent 与多 Agent 任务编排。
- Qwen Code 的实质性个性化 Fork。
- 对 OpenCode、Codex 和 Grok Build 的架构比较结论。
- 完整测试、学习笔记和阶段验收记录。
