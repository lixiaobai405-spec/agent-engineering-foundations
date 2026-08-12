# 04 Chat Control Plane 学习笔记

## Control plane 与 Observation plane

Phase 1D 把 Agent 交互拆成两个平面：

| 平面 | 职责 | 持久化 | 实时通道 |
|------|------|--------|----------|
| **Control plane（Chat）** | 多轮对话、权限模式、审批决策、活动摘要 | SQLite（`.agent-foundations/chat.sqlite3`） | SSE（活动提示，非 durable log） |
| **Observation plane（Trace）** | 完整但已脱敏的 step 时间线、工具参数与结果 | JSONL（`traces/`） | Viewer SSE（历史 + 实时追加） |

Chat UI 只展示持久化且脱敏的工具摘要、审批卡片和最终回答。每个 run 的 tool activity 折叠成一组；完整 Provider 内容、原始 ToolResult 和完整 Trace payload 只在 Trace Viewer 的 `/trace?conversation_id=...&session_id=...` 中查看。

## SQLite 与 JSONL 的事实所有权

- **SQLite** 拥有 conversation、message、run、approval，以及可替换的脱敏 tool activity UI 投影。浏览器刷新、HTTP 恢复和 Repository 查询都以 SQLite 为准。
- **JSONL** 拥有 Agent Runtime 的逐步 TraceEvent。一个 turn 的 `session_id` 同时关联 SQLite run 与 JSONL 文件。
- **SSE** 只是当前浏览器生命周期的实时提示：连接断开或页面刷新后，不能依赖 SSE 回放历史；必须先通过 HTTP 读取 SQLite 事实，再建立新的 SSE 连接接收后续 live events，并立即通过 activity HTTP catch-up 关闭 snapshot 与订阅之间的窗口。

JSONL 写入先于 Chat 投影。tool activity 投影失败只会被记录，不会反向使 Agent run 失败；因此 JSONL 仍是完整 observability record，SQLite activity 只是安全、可重建但不从 JSONL 临时合成的 UI read model。

`(session_id, tool_call_id)` 是 activity 的幂等键：同一次工具调用的 requested/completed/failed 更新同一行，terminal 状态不会被迟到的 running 事件降级。服务重启时未完成 run 与 activity 一起变为 `interrupted`。

## ConversationRunner 与 RunSupervisor

- **ConversationRunner** 负责把一次 user message 转成 Agent Loop 执行：创建 run、绑定固定 `session_id`、写入 Trace、投影 Chat events。
- **RunSupervisor** 跟踪同一 conversation 内 run 的生命周期：queued → running → waiting_approval / completed / failed / interrupted。它确保同一 conversation 不会并发多个 active run，并在服务启动时对未完成 run 调用 `interrupt_unfinished()`。

Runner 关心“如何跑一轮”；Supervisor 关心“这轮处于什么状态、能否开始下一轮”。

## ApprovalCoordinator 为什么独立

审批不是 Tool Registry 的一部分，也不应耦合在 Agent Loop 内部：

1. **权限决策与控制面 UI 同源**：pending approval 必须写入 SQLite，并通过 Chat API 投影给前端；Tool 层只接收“已批准的一次性 capability”或拒绝结果。
2. **一次性 exact capability**：Phase 1D 只允许 `session_id + tool_call_id + canonical_path + read` 的精确外部只读，不提供目录级或会话级 allow-all。
3. **可测试的决策矩阵**：`PROJECT_READ_ONLY` 与 `ASK_FOR_ACCESS` 的行为、批准/拒绝/过期/服务重启语义，需要独立于 Provider 与 Loop 进行单元和集成测试。

## One-time exact capability 与 broad full access

| 概念 | Phase 1D | Phase 2+（未实现） |
|------|----------|-------------------|
| 项目内只读 | `PROJECT_READ_ONLY` 默认允许 | — |
| 项目外只读 | `ASK_FOR_ACCESS` + 用户批准一次 exact path | 可能扩展为 broader capability |
| 永久目录授权 | **不支持** | 未来可能讨论 |
| 写 / Shell / Git / network | **硬拒绝**，审批无法绕过 | Phase 2 起逐步引入 |

批准后只对该次 tool call 生效；下一次访问同一路径必须产生新的 `approval_id` 和新卡片。敏感文件名（如 `.env`）在两种模式下均硬拒绝，不能通过审批绕过。

## HTTP/SQLite/JSONL 是恢复事实，SSE 不 replay

Task 12 引入：

```text
GET /api/chat/conversations/{conversation_id}/state
```

响应精确为 `{ latest_run, pending_approval }`：

- `latest_run`：按触发它的 user message `sequence DESC` 确定的最新 `RunRecord`。
- `pending_approval`：仅当 latest run 为 `waiting_approval` 且 approval 仍为 `pending` 时返回安全投影字段（含 `operation: read`、`scope: external_exact_path`）。

前端 **fresh load / reload / SSE reconnect** 的顺序：

1. list conversations
2. get conversation + list messages + list runs + list activities + get `/state`
3. 核心 HTTP 恢复完成后才构造 `EventSource`；activity 失败不阻塞消息阅读，并提供 conversation-scoped retry
4. SSE 连接后立即再取一次 activities，合并期间坚持 terminal-over-running
5. SSE 只接收 live events，不伪造历史 `ChatEvent`

Reducer 使用独立的 `conversation.state.loaded` action，不把 HTTP 恢复伪装成 SSE `event.received`。

## 为什么 Markdown 不直接渲染 HTML

Chat message 先解析为 Markdown AST/token，再映射到受控 React 元素；GFM table、task list、blockquote、inline code 等保留语义，但 raw HTML、图片、媒体和危险 URL 被阻断。代码高亮使用 Shiki token API 返回文本 token，再渲染为 React `<span>`，不使用 `dangerouslySetInnerHTML` 或 `rehype-raw`。

这个边界同时解决两件事：模型输出更易读，但模型返回的字符串仍只是数据，不能变成可执行 DOM。解析或高亮失败时分别回退到 plain text 和原始 `<code>`，不会让消息消失。

## `/state` 为什么只恢复 latest run / pending approval

Phase 1D Chat UI 只需要知道“当前 conversation 最新一轮处于什么状态”：

- **running**：禁用 composer 与 permission mode，等待 SSE 继续。
- **waiting_approval**：重建同一 approval card，禁用 composer，等待用户决策。
- **completed / failed / interrupted**：清除 active session/approval，但保留 `latestSessionId` 供 Trace 链接。
- **no run**：不虚构 completed，idle controls 可用。

历史 run 列表、完整审批审计和逐步 Trace 仍由 Trace Viewer 与 JSONL 提供；控制面 API 保持最小投影，避免把 Trace payload 或 Provider 内容泄漏到 Chat JSON。

## Browser reload 与 server restart 的区别

| 场景 | SQLite run 状态 | pending approval | Python 协程 |
|------|-----------------|------------------|-------------|
| **浏览器 reload** | 保持 running / waiting_approval / terminal | pending 仍可恢复（同 `approval_id`） | 服务端协程继续运行 |
| **服务 restart** | 未完成 run → `interrupted` | 旧 approval **不可**继续 | 协程不恢复 |

服务启动时 `RunSupervisor.interrupt_unfinished()` 把 queued/running/waiting_approval 的 run 标记为 interrupted，并 invalidate 相关 pending approval。UI 刷新后若 run 已是 interrupted，不会静默恢复旧审批或假装协程仍在运行。

Phase 1D **刻意不实现**：持久 SSE replay、跨重启可恢复的 Python 协程、conversation 删除、Token streaming。

## Phase 2 扩展点（尚未实现）

以下能力在设计文档中预留，但 Phase 1D 代码与文档边界均视为**未实现**：

- 写文件、Shell、Git、network 工具及对应审批
- 永久目录授权或 session 级 allow-all
- Memory、Planning、Checkpoint、MCP、Skills、Sandbox、Sub-Agent
- 远程绑定、多租户、登录
- Token streaming 与成本实时展示

进入 Phase 2 前，Phase 1D 须完成全部 Task 12 门禁并经独立 reviewer / 用户验收；本笔记描述的是当前已交付的控制面语义，而非未来权限模型。
