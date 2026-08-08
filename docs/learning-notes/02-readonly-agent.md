# 02 Read-only Agent 学习笔记

## 安全模型

所有文件工具共享同一个 `PathPolicy`。工具只能接收项目相对路径；路径经过 `resolve()` 后必须仍位于根目录，并且不能命中敏感名称或后缀。读取和搜索还分别受字节、行数、文件数和匹配数限制。

**PathPolicy 为什么是所有文件工具的共同安全门：** 如果每个工具独立实现路径校验，不同工具可能对"安全路径"有不同理解，产生不一致的安全边界。集中到 `PathPolicy` 保证无论未来增加多少新工具，它们都经过同一个严格的安全检查。`PathPolicy` 在构造时接收并 resolve 项目根目录，所有后续授权都以此为参照，避免了路径穿越和符号链接攻击。

## Agent Loop

循环每一步只做四件事：构建 Context、请求模型、校验并执行工具、判断最终回答。最大十步是硬终止条件。未知工具和参数错误作为 ToolResult 反馈给模型，路径越权则既反馈失败又进入 Trace。

**每一步的状态变化：**
1. `ContextBuilder.build()` 从所有历史消息中构建新上下文（截断旧的工具结果以适应预算）
2. 创建 `ModelRequest` 并发布 `model.request.started`
3. 调用 `provider.complete()` 并计时 → 发布 `model.response.received`（含 `duration_ms`）
4. 模型无 `tool_calls` 时 → 最终回答，发布 `agent.final_answer` + `session.completed`
5. 有 `tool_calls` 时 → 逐个校验并执行，结果作为 TOOL 消息追加到对话历史
6. 耗尽 `max_steps` → `agent.loop.stopped` + `session.failed` + 抛出 `MaxStepsExceededError`

## ToolRegistry 的定位

**ToolRegistry 为什么位于 AgentLoop 与具体工具之间：** 它实现了单一职责的解耦——AgentLoop 只知道"有一个工具名和一些参数"，不需要知道哪个具体类处理、参数长什么样。Registry 负责：按名称查找工具、用 JSON Schema 校验参数、在进入工具前将 `FrozenJSON` 解冻为普通 `dict`。这种设计让 AgentLoop 保持对工具实现的零依赖。

## Provider 边界

**Provider Adapter 为什么隔离 SDK 类型：** OpenAI-compatible Adapter 负责 SDK 类型转换与错误映射。Agent Loop 只认识 `ModelRequest` 和 `ModelResponse`，因此未来可增加其他 Provider 而不修改循环。`AuthenticationError` → `ProviderAuthenticationError` 等映射确保循环收到的总是项目自己的错误类型，不依赖特定 SDK 的异常层次。

**SDK retry 与 AgentLoop retry 的区别：** `AsyncOpenAI(max_retries=2)` 是 SDK 内置的透明重试，发生在单次 Provider 请求内部。除连接错误和超时外，SDK 还会重试 HTTP 408、409、429 和 5xx；`max_retries=2` 表示首次请求失败后最多再尝试 2 次，因此单次 `provider.complete()` 最多产生 3 次 HTTP 尝试。AgentLoop 不叠加第二套重试——如果 `provider.complete()` 最终失败，它直接终止 Session。这样可以避免 HTTP 尝试次数在多个重试层之间成倍放大，并让一个 Agent step 始终对应一次完整的 Provider 调用。

## CLI 组合根

**CLI 为什么属于 composition root（组合根）：** CLI 是唯一知道所有具体实现的地方——它导入 Typer、Rich、OpenAI SDK、PathPolicy、三个具体工具、ContextBuilder、AgentLoop 等所有组件，并将它们组装在一起。AgentLoop 依赖的是 `ModelProvider`、`ToolRegistry`、`ContextBuilder`、`EventSink` 协议——它从不导入 SDK 或具体工具。这种分层让测试可以用 FakeModel 和 InMemoryEventSink 完整驱动循环，也让未来增加其他入口（如 Web API）不需要修改循环。

**为什么 Typer callback 用于保留 analyze 子命令：** Typer 只有一个命令且没有 callback 时，默认把该命令提升为根命令（直接 `agent-foundations ROOT QUERY` 而非 `agent-foundations analyze ROOT QUERY`）。增加零操作的 `@app.callback()` 强制保留子命令结构，使 CLI 用法明确且可扩展（未来可增加 `agent-foundations serve` 或 `agent-foundations replay` 等子命令）。

## 当前实现刻意没有解决的能力

- **写操作：** Phase 1B Agent 无法创建、修改或删除文件。这是有意识的安全边界——在没有审批流、Sandbox 和回滚机制之前，不应暴露写能力。
- **Shell/Git：** 不能运行系统命令或操作 Git。调用外部命令的安全上下文远复杂于只读文件访问，需要独立的审批和沙箱策略。
- **持久化 Trace：** 当前 TraceEvent 只发送给 `EventSink` Protocol，但尚未实现 JSONL 写入或数据库持久化。Phase 1C 将加入本地文件持久化。
- **Web Viewer：** 当前没有 Web 界面。Phase 1C 计划实现基于 FastAPI + SSE 的 Trace Viewer，但尚未实施。
- **Memory：** 没有跨 Session 的记忆。每个 Session 独立运行。
- **Planning：** 没有任务规划能力。Agent 按模型返回按步执行工具调用。
- **MCP：** 没有 Model Context Protocol 集成。当前工具全部是本项目自实现的。
- **Sub-Agent：** 没有多 Agent 协作或任务委派。只有一个 Agent Loop 处理所有推理。
