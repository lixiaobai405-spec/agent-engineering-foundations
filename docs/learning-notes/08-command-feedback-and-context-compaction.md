# 08 Command Feedback and Context Compaction 学习笔记

## 本周实现

### Artifact metadata vs raw bytes vs CommandFeedback

`run_command` 的原始 stdout/stderr 写入 Command Artifact（metadata 在 SQLite，bytes 在 store）。Agent 默认拿到的是 Parser 产出的 `CommandFeedback`：exit code、失败 test id、推荐范围、parser status。原始路径和 raw ticket 不进入模型输入。Chat UI 默认显示 feedback；分页 sanitizer 与显式本机 raw download 不改变 Agent 的 context 或 permission。

### Compaction 是当前对话的模型输入派生视图

loss-aware compaction 从**当前 conversation** 的模型输入消息提取 critical facts（目标、决策、plan/todo、路径、行号、test id 等），用 fingerprint/range 支持 rehydration。它不是跨 conversation Memory，也不把 raw Artifact 字节送进压缩请求。critical fact recall 必须以 100% 为门禁；压缩率只报告，不能用低 recall 换高压缩。

自动测试使用 `FakeCompactor`。真实模型压缩器未经本 Task 授权，标记 not-run。

## 关键取舍

### 1. 为什么 Agent 不能读 raw log 拼 context

原始输出含密钥、绝对路径和超长噪声。结构化 Feedback 把「失败了什么」从「原始字节在哪」分开，才能在不泄漏 Artifact 的前提下做定向复现。

### 2. 为什么 compaction 不是 Memory

Memory 会跨会话积累并成为新的信任边界。当前 compact 只解决单次对话的字符预算。source fingerprint 让摘要可以指回原消息，而不是发明新事实。

## 各层职责

| 层 | 职责 |
|---|---|
| Parser | 把受信任格式变成 Feedback；partial/failed 保留 unparsed bytes |
| Artifact store | 配额、reservation、eviction、pending_delete |
| Command output tools | 同 run Capability + 预算读取 |
| context/critical_facts | 抽取可 rehydrate 的短事实 |
| FakeCompactor | 可重复的压缩质量门 |

## 刻意未解决

- 真实模型 3×3 人工场景
- 真实模型 compactor
- MCP / Skills / 跨会话 Memory
