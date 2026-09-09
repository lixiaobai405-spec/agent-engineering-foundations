# 06 Durable Execution 学习笔记

## 本周实现

Durable Execution 把一次 Agent run 变成可恢复的事实源：版本化 schema、`DurableRun` 状态机、lease 所有权、checkpoint、副作用账本。Chat 的 SQLite run 与 durable run 共用 `session_id`/`run_id`，但 JSONL Trace 仍然只是观察面，不是恢复或授权事实源。

崩溃恢复读取已提交的 checkpoint 与 side-effect 记录。`UNKNOWN` effect 必须 reconcile，不能假装成功。committed 的 Patch/command 不因重放再执行一次。lease takeover 保证同一 run 同时只有一个有效 owner。

Provider 重试次数记在 `AgentRunState.provider_attempts`；`DurableRun.attempt` 仍是 run 级 `begin_retry`。崩溃恢复保留 attempts；controller `begin_retry` 才清零。FakeModel/Eval 不包真实 token bucket。

## 关键取舍

### 1. 为什么副作用账本独立于 Trace

Trace 可以丢、可以脱敏、可以晚写。恢复如果读 JSONL，会把观察面变成控制面。账本与 checkpoint 必须在 SQLite 事务里提交，才能在进程崩溃后回答「这件事有没有做过」。

### 2. 为什么 Chat 可以没有 CheckpointSink

Chat 热路径可以只在进程内累计 Provider attempts。跨崩溃的 Provider budget 是受保护缺口：本阶段不把 `chat/runner.py` 或 `durable/controller.py` 强行接线，以免总验收 Task 扩大架构。

## 各层职责

| 层 | 职责 |
|---|---|
| `durable/repository` | schema v1–v10、run、checkpoint、lease、effects |
| `durable/effects` | 账本 CAS 与 UNKNOWN |
| `runtime/state_machine` | Agent 阶段与 provider_attempts |
| Chat runner | 把 Chat run 映射到 durable 状态；不把 SSE 当 log |

## 刻意未解决

- 无 v11 migration
- 不把 SSE/Trace 当 durable log
- 不实现跨 conversation 的长期 Memory
