# 05 Offline Eval and Planning 学习笔记

## 本周实现

### Replay Eval 与固定任务集

Offline Eval 用 `FakeModelProvider` 重放固定 response fixture，不包装 `ResilientModelProvider`，不调用真实 Provider，也不启动 Docker。`evaluate` CLI 的 `fixture_root` 是 task set 的 `parent.parent`，因此 `project_fixture` 相对 `tests/fixtures/`。

Phase 1 任务集 `phase-1-readonly` 保持只读 + 既有 planning 语义，报告与 `docs/eval-baselines/phase-1-v1.json` 可比较。Phase 2 任务集 `phase-2-coding` 只**组合**已有 Tool：只读文件、Planning、`validate_patch`/`apply_patch`/`run_command` 注册项，以及 FakeBackend 上的 `git_status`/`git_diff`/`git_log`。副作用路径注入 FakeBackend；`DirectToolCallExecutor` 对 `apply_patch`/`run_command` 返回 `CONTROLLED_EXECUTION_REQUIRED`，因此 Offline Eval 失败关闭而不是去调 Docker。

### Planning 是 Runtime 控制面，不是新副作用 Tool

`set_plan` / `update_plan_step` / `replan` 走 `PlanController` + `ExecutionFactJournal`。`PlanningMode.REQUIRED` 在最终回答前要求计划存在且步骤完成。这是 Agent Loop 的控制能力，不产生项目写或进程副作用。

## 关键取舍

### 1. 为什么 Eval 不复用 Chat 的 Controlled Executor

Chat 的 `ControlledPatchExecutor` / `ControlledCommandExecutor` 依赖 Approval、Capability、Ledger 和 Docker Sandbox。把它们塞进 Offline Eval 会让基线依赖容器与审批时序，无法在无 Docker 的 CI 中比较 Prompt/Tool 选择。Eval 只证明「组合了哪些已有 Tool、策略拒绝是否仍发生」。

### 2. Fake Token 记 0 延迟、脚本用量

FakeModel 的 `usage.input_tokens` / `output_tokens` 来自 fixture，不是账单。`duration_ms` 在 Replay 中固定为 `0.0`。报告里的 Token 只用于脚本稳定性，不能当成真实模型成本。

## 各层职责

| 层 | 职责 |
|---|---|
| `evals/models` | 任务、断言种类（不含新断言） |
| `evals/replay` | FakeModel 重放、dataset/tag 分支、FakeBackend Git |
| `evals/runner` | 逐任务评分与报告 |
| `planning` | 计划 CAS/步骤证据 |
| Chat / Sandbox | 真实副作用；Eval 不进入 |

## 刻意未解决

- 不在 Eval 里跑真实 Docker `apply_patch` / `run_command`
- 不把 Chat 无 CheckpointSink 的 Provider attempt 跨崩溃持久化强行接到 Eval
- 不引入 MCP、Memory、Skills 作为 Eval 维度
