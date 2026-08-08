# 03 Observability 学习笔记

## Event 为什么是一等公民

日志主要供人阅读，`TraceEvent` 同时服务于测试、回放、Viewer 和未来评测。稳定字段（`event_id`、`session_id`、`step_id`、`event_type`、`status`、`timestamp`、`summary`）描述事件身份和顺序，`payload` 保存事件特有数据。

**一等公民意味着什么：** Agent Loop 的每一步——模型请求、工具校验、工具执行、最终回答——都通过 `EventSink` 发出结构化事件，而不是事后从日志字符串反推。测试可以断言事件序列；JSONL 可以严格回放；Viewer 可以按 step 展示时间线。这种设计把“可观察性”从附加功能变成 Runtime 契约的一部分。

## 双 Sink 设计

JSONL 是本地事实记录；Live Sink 是最佳努力传输。Viewer 未启动或短暂断开时，Agent 仍继续运行，历史事件仍能从 JSONL 加载。

**为什么分开：**

| Sink | 可靠性 | 用途 |
|------|--------|------|
| `JsonlEventSink` | 高（本地追加写入） | 持久化、回放、审计 |
| `LiveEventSink` | 最佳努力（HTTP POST） | 实时 Viewer 更新 |

CLI 的 `build_runtime` 始终创建 `JsonlEventSink`；仅当 `analyze --viewer-url` 指向 `127.0.0.1` 时才追加 `LiveEventSink`。`CompositeEventSink` 顺序调用两者；它不会统一吞掉异常，而是传播失败并停止调用后续 Sink。`LiveEventSink` 仅在自身内部吞掉 `httpx.HTTPError`，所以 Viewer 离线不会阻断 Agent；`JsonlEventSink` 等其他 Sink 失败仍会向上抛出。

## 安全顺序

事件先在 Runtime 中形成，再由 `Redactor` 生成持久化和传输副本。Redactor 不修改 Runtime 原对象，并递归处理嵌套字典、列表、Header、已知密钥和项目绝对路径。

**顺序为什么重要：**

1. Runtime 持有完整 `TraceEvent`（含工具参数、模型输入等）用于当前 step 决策。
2. 写入 JSONL 或 POST 到 Viewer 前，`redact(event.model_dump(mode="json"))` 生成脱敏副本。
3. 原始对象不被污染，避免后续 Context 构建意外丢失信息。

Provider API Key 通过 `Redactor(root, secrets=(api_key,))` 注入；Bearer Token、`Authorization` 头和项目绝对路径有独立规则。

## Viewer 边界

Viewer 只接收事件和读取 Trace，不提供暂停 Agent、修改 Prompt、批准工具或执行命令的 API。控制面留到需要权限模型的第二阶段。

**网络边界：**

- `agent-foundations viewer` 固定 `host="127.0.0.1"`，CLI 不暴露 `--host`。
- `LiveEventSink` 拒绝 `localhost`、IPv6 和非 loopback 主机名，防止 Trace 数据意外发往远程。
- FastAPI 提供只读 Session 列表、历史加载、SSE 流和静态前端；无写文件或执行工具接口。

**前端职责：** 历史 Session 从 `/api/sessions/{id}` 加载；实时事件通过 SSE 追加；筛选、标签页详情、复制 JSON 均为纯客户端展示，不反馈到 Agent。

## CLI 接线

Task 7 把 Trace 与 Viewer 接入 CLI：

- `analyze` 默认 `--trace-dir traces`，可选 `--viewer-url`。
- `viewer` 独立启动，不依赖 `AGENT_API_KEY` / `AGENT_MODEL`。

CLI 是 composition root：在这里组装 `Redactor`、`JsonlEventSink`、`LiveEventSink`、`CompositeEventSink` 与 Provider，Runtime 本身不关心 JSONL 路径或 Viewer URL。

## 后续改进依据

- 事件量超过内存队列上限时，需要明确背压或丢弃策略。
- 多进程并发写同一 Session 前，需要文件锁或单写者。
- Token 与成本展示必须来自 Provider 统一 Usage，而不是前端估算。
- 浏览器 E2E 验证历史加载与详情展示；真实 API 人工验收仍须用户确认费用后单独执行。

## 当前实现刻意没有解决的能力

- **远程 Viewer：** 不支持 `0.0.0.0` 绑定或跨机器访问。
- **Agent 控制：** Viewer 不能暂停、重试或修改运行中的 Agent。
- **Token 成本图：** 无 Usage 聚合与可视化。
- **多 Agent 关系图：** 单 Session 时间线，无 Sub-Agent 拓扑。
- **写操作 Trace：** Phase 1 仍为只读 Agent；写工具与审批流属第二阶段。
