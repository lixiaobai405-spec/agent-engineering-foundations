# Phase 2 Controllable Coding Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在保持自研 Runtime 核心和 Phase 1 回归基线的前提下，按权限递增门禁实现离线 Eval、Planning、Durable Execution、项目内受控 Patch、Sandbox 命令和只读 Git 反馈闭环。

**Architecture:** Phase 2 分成 2A–2D 四个顺序子里程碑。内部领域协议先稳定，再通过 `ToolCallExecutor`、Policy、Capability、`ExecutionBackend` 和 side-effect ledger 组合副作用；SQLite 中的 Durable、授权和副作用表保存控制面恢复事实，现有 `chat_tool_activities` 只保存脱敏、可替换的 UI read model，不得充当 Checkpoint、授权或副作用事实源。JSONL Trace 只负责观察，SSE/UI Event 只负责实时提示。外部框架只作对照，MCP、ACP、A2A 及主机完全访问不进入本计划。

**Tech Stack:** Python 3.12、Pydantic 2、SQLite、FastAPI、React 19、TypeScript、Vite、Vitest、Playwright、Docker CLI、pytest、Ruff、mypy；不新增 Agent 框架依赖。

---

## 0. 计划状态与执行规则

- 状态：Task 1–24 的真实完成状态以各自 evidence、独立 reviewer 和用户确认共同为准。Task 17（`phase-2d-task-1`）已于 2026-08-26 由用户确认验收通过；evidence 见 `docs/task-evidence/phase-2d-task-1.md`。Task 18（`phase-2d-task-2`）已于 2026-08-26 由用户确认验收通过；evidence 见 `docs/task-evidence/phase-2d-task-2.md`。Task 19（`phase-2d-task-3`）已于 2026-08-26 由用户确认验收通过；evidence 见 `docs/task-evidence/phase-2d-task-3.md`。Task 20（`phase-2d-task-4`）已于 2026-08-26 由用户确认验收通过；evidence 见 `docs/task-evidence/phase-2d-task-4.md`。Task 21（`phase-2d-task-5`）已于 2026-08-26 由用户确认验收通过；evidence 见 `docs/task-evidence/phase-2d-task-5.md`。Task 22（`phase-2d-task-6`）已于 2026-08-26 由用户确认验收通过；evidence 见 `docs/task-evidence/phase-2d-task-6.md`。Task 23（`phase-2d-task-7`）已于 2026-08-27 由用户确认验收通过；evidence 见 `docs/task-evidence/phase-2d-task-7.md`。Task 24（`phase-2d-task-8`）已于 2026-08-27 由用户确认验收通过；evidence 见 `docs/task-evidence/phase-2d-task-8.md`。2026-08-13 已批准 Task 18–25 修订设计。Task 25（`phase-2d-task-9`）的 P1 FakeModel E2E `_DIFF` 对齐已于 2026-08-27 由用户确认验收通过；evidence 见 `docs/task-evidence/phase-2d-task-9.md` §9。Task 25 计划正文 Step 10 已于 2026-09-09 用户验收通过（Round 3 付费 Chat UI 3×3 连续 9/9；2026-09-08 Round 2 记分不得改写成通过）；Step 11 已于 2026-09-09 用户验收通过（见 `docs/task-evidence/phase-2d-task-9-step-11.md` §12）。用户 Phase 2 已于 2026-09-09 确认完成（见同文件 §13）。附录 Task 26 / `phase-2d-task-10`（Chat sandbox pin）已于 2026-08-27 由用户确认验收通过；evidence 见 `docs/task-evidence/phase-2d-task-10.md` §9。该确认不是计划正文 Task 10（Side-effect Ledger）。附录 Task 27 / `phase-2d-task-11`（Chat CheckpointSink）已于 2026-08-27 由用户确认验收通过；evidence 见 `docs/task-evidence/phase-2d-task-11.md` §9。该确认不是计划正文 Task 11（Patch 解析）。附录 Task 28 / `phase-2d-task-12`（FakeModel 纠错流 Docker 兄弟 E2E）已于 2026-08-27 由用户确认验收通过；evidence 见 `docs/task-evidence/phase-2d-task-12.md` §9。该确认不是计划正文 Task 12（Approval/Policy）。建议顺序中的 P1 与三条 P3 follow-up 均已用户验收。附录 Task 29 / `phase-2d-task-13`（Chat 人工验收缺陷修复）已于 2026-08-28 由用户确认验收通过；evidence 见 `docs/task-evidence/phase-2d-task-13.md` §9。该确认不是计划正文 Task 13（Approval/Policy）。可靠性 follow-on Task 30 / `phase-2d-task-14`（Patch 合同升级）已于 2026-08-29 由用户确认验收通过；evidence 见 `docs/task-evidence/phase-2d-task-14.md` §9。该确认不是计划正文 Task 14（ExecutionBackend）。可靠性 follow-on Task 31 / `phase-2d-task-15`（错误类型驱动恢复）已于 2026-08-29 由用户确认验收通过；evidence 见 `docs/task-evidence/phase-2d-task-15.md` §9。该确认不是计划正文 Task 15。可靠性 follow-on Task 32 / `phase-2d-task-16`（Chat Planning 持久化与 UI）已于 2026-08-29 由用户确认验收通过；evidence 见 `docs/task-evidence/phase-2d-task-16.md` §9。该确认不是计划正文 Task 16。可靠性 follow-on Task 33 / `phase-2d-task-17`（Prompt / Schema / Tool 描述）已于 2026-08-29 由用户确认验收通过；evidence 见 `docs/task-evidence/phase-2d-task-17.md` §9。该确认不是计划正文 Task 17。可靠性 follow-on Task 34 / `phase-2d-task-18`（分层预算 + Offline Eval）已于 2026-09-04 由用户确认验收通过；evidence 见 `docs/task-evidence/phase-2d-task-18.md` §10。该确认不是计划正文 Task 18。产品 hardening Task 35 / `phase-2d-task-19`（`run_command` 的 `gate_id` 合同）已于 2026-09-04 由用户确认验收通过；evidence 见 `docs/task-evidence/phase-2d-task-19.md` §9。该确认不是计划正文 Task 19。产品 hardening Task 36 / `phase-2d-task-20`（Git 探测与预定义 fallback）已于 2026-09-04 由用户确认验收通过；evidence 见 `docs/task-evidence/phase-2d-task-20.md` §9。该确认不是计划正文 Task 20。产品 hardening Task 37 / `phase-2d-task-21`（审批 PolicyRequest 渲染）已于 2026-09-04 由用户确认验收通过；evidence 见 `docs/task-evidence/phase-2d-task-21.md` §9。该确认不是计划正文 Task 21。产品 hardening Task 38 / `phase-2d-task-22`（stdout/stderr 标签）已于 2026-09-05 由用户确认验收通过；evidence 见 `docs/task-evidence/phase-2d-task-22.md` §9。该确认不是计划正文 Task 22。产品 hardening Task 39 / `phase-2d-task-23`（独立数据根）已于 2026-09-05 由用户确认验收通过；evidence 见 `docs/task-evidence/phase-2d-task-23.md` §9。该确认不是计划正文 Task 23。产品 hardening Task 40 / `phase-2d-task-24`（sweep 接入 Chat）已于 2026-09-05 由用户确认验收通过；evidence 见 `docs/task-evidence/phase-2d-task-24.md` §9。该确认不是计划正文 Task 24。产品 hardening Task 41 / `phase-2d-task-25`（关闭语义）已于 2026-09-05 由用户确认验收通过；evidence 见 `docs/task-evidence/phase-2d-task-25.md` §9。该确认不是计划正文 Task 25。硬化计划 Task 35–41 均已用户验收；该计划无 Task 42。付费 3×3 前缺口见 `docs/agent-plans/2026-09-08-phase-2-pre-3x3-gap-remediation-plan.md`。附录 Task 42 / `phase-2d-task-26`（把已验收 Chat UI 打进被服务的静态包）已于 2026-09-08 由用户确认验收通过；evidence 见 `docs/task-evidence/phase-2d-task-26.md` §9。附录 Task 43 / `phase-2d-task-27`（`read_file` 与 structured patch 同一套 UTF-8 行文本）已于 2026-09-08 由用户确认验收通过；evidence 见 `docs/task-evidence/phase-2d-task-27.md` §9。上述确认不是计划正文 Task 25，也不是硬化计划项。pre-3×3 缺口计划无 Task 44。附录 Task 44 / `phase-2d-task-28`（Node sandbox 可写 `node_modules` 父目录）已于 2026-09-08 由用户确认验收通过；evidence 见 `docs/task-evidence/phase-2d-task-28.md` §9。该确认不是计划正文 Task 25，也不是 Step 10。附录 Task 45 / `phase-2d-task-29`（畸形 tool JSON 降成可恢复工具失败）已于 2026-09-08 由用户确认验收通过；evidence 见 `docs/task-evidence/phase-2d-task-29.md` §9。该确认不是计划正文 Task 25，也不是 Step 10。附录 Task 46 / `phase-2d-task-30`（`read_command_output` 选择器仍安全地可被模型写对）已于 2026-09-08 由用户确认验收通过；evidence 见 `docs/task-evidence/phase-2d-task-30.md` §9。该确认不是计划正文 Task 25，也不是 Step 10。附录 Task 47 / `phase-2d-task-31`（Chat 中断同时收口 Durable）已于 2026-09-08 由用户确认验收通过；evidence 见 `docs/task-evidence/phase-2d-task-31.md` §9。该确认不是计划正文 Task 25，也不是 Step 10。附录 Task 48 / `phase-2d-task-32`（真 Stop）已于 2026-09-09 由用户确认验收通过；evidence 见 `docs/task-evidence/phase-2d-task-32.md` §9。该确认不是计划正文 Task 25，也不是 Step 10。post-3×3 计划本身无 Task 49。附录 Task 49 / `phase-2d-task-33`（修绿 Step 6 完整基线）已于 2026-09-09 由用户确认验收通过；evidence 见 `docs/task-evidence/phase-2d-task-33.md` §9。该确认接受完整 Step 6 变绿，当时不是计划正文 Task 25 完成，也不是 Step 11。Step 6 基线修绿的权威合同是 `docs/agent-plans/2026-09-09-phase-2-step-6-baseline-unblock-plan.md`。计划正文 Task 25 **Step 10** 已于 2026-09-09 由用户确认验收通过（Round 3 付费 Chat UI 3×3 连续 9/9）；evidence 见 `docs/task-evidence/phase-2d-task-9-step-10.md` §11。计划正文 Task 25 **Step 11** 已于 2026-09-09 由用户确认验收通过；evidence 见 `docs/task-evidence/phase-2d-task-9-step-11.md` §12。2026-09-08 Round 2 记分不得改写成通过。用户 Phase 2 已于 2026-09-09 确认完成（见 `docs/task-evidence/phase-2d-task-9-step-11.md` §13）。未授权 commit、push、付费 3×3 重跑或 Phase 3。
- 2026-08-09 migration 基线已同步到当前 Chat schema v2；Phase 2 已顺序占用 v3–v8，Task 18 和 Task 20 分别预留 v9–v10。
- 权威设计：[`2026-08-08-phase-2-controllable-coding-agent-design.md`](2026-08-08-phase-2-controllable-coding-agent-design.md)。
- 用户将另行让 planner 为单个 Task 生成执行 prompt；本计划本身不构成实现授权。
- 一次只能执行用户明确指定的一个 Task。完成 evidence 后停止，等待 reviewer 与用户决定。
- Phase 2A、2B、2C、2D 必须顺序执行；每个子里程碑的最后一个 Task 通过用户验收后，才能扩大下一层权限。
- 每个实现 Task 的 evidence 路径固定为 `docs/task-evidence/<task-id>.md`，由 executor 按 `docs/task-evidence/_template.md` 在运行命令时维护。
- TDD 为默认要求。Red 必须在生产代码修改前保存，并因目标行为缺失而失败；语法、导入、环境或无关错误不算有效 Red。
- 新模块尚不存在时，测试必须在测试函数内使用 `importlib.util.find_spec()` 并先做行为断言，确保 pytest 正常收集且 Red 是 assertion failure；不得让 `ModuleNotFoundError` 成为 Red。
- 不安装依赖、不拉取或构建 Docker image、不调用真实模型或付费 API，除非用户在当前 Task 明确确认。
- 不自动 commit、push、创建 PR、部署或进入下一 Task。每个 Task 只提供建议 commit，执行仍需用户明确授权。
- 保留所有已有未提交修改；每个 Task 开始和结束都运行 `git status --short` 与范围审计。
- 计划中的接口是该 Task 的最小稳定合同。若现实代码与合同冲突，executor 停止并交回 planner，不得自行改写架构。
- 本文代码块用于锁定公开类型、Schema、测试断言和调用顺序，不是 planner 对生产实现的代写；单 Task prompt 必须在不改变这些合同的前提下补齐该 Task 的最小实现细节。

## 1. 文件结构与职责锁定

```text
src/agent_foundations/
├─ evals/                 # 离线任务集、Runner、评分、报告和回放 Adapter
├─ planning/              # Plan/Todo 领域模型、受限重规划与内部控制 Tool
├─ storage/               # 共享 SQLite 连接和顺序 migration
├─ durable/               # Run、Checkpoint、lease、恢复命令和副作用账本
├─ security/              # Tool metadata、Policy、Permission Profile、Approval、Capability
├─ execution/             # ExecutionBackend、FakeBackend 与 DockerBackend
├─ tools/patch/           # Unified Diff 解析、校验、预览与 apply_patch
├─ tools/command/         # 结构化 argv、命令分类、run_command 与受限日志读取
├─ command_output/        # 原始命令产物、保留策略、Parser 与结构化反馈
├─ tools/git/             # 只读 git_status、git_diff、git_log
├─ context/               # 现有预算 + Repo Map、来源、相关性、loss-aware compaction 与缓存
├─ providers/             # 现有 Provider + bounded retry/rate-limit wrapper
├─ runtime/               # AgentLoop、ToolCallExecutor、Trace 和可恢复状态机
└─ chat/                  # Chat 业务状态、API、审批协调和 UI 投影

docker/
├─ agent-sandbox-python.Dockerfile
├─ agent-sandbox-node.Dockerfile
└─ README.md

tests/
├─ fixtures/evals/        # 固定任务集、回放响应和预期基线
├─ unit/<new-module>/     # 纯领域和确定性边界测试
├─ integration/          # Runtime/SQLite/Policy/Tool 组合测试
└─ e2e/                  # FakeModel + 本机 Chat UI 验收
```

边界约束：

- 不继续把 Durable Execution、安全策略或副作用账本塞进已很大的 `chat/repository.py`。
- `storage/` 只负责 SQLite 机制；各领域 Repository 负责自己的表和不变量。
- `security/` 决定是否允许；`execution/` 只执行已授权请求，不重新解释用户意图。
- `ToolRegistry` 向模型暴露 Schema；Tool metadata 供 Policy 使用，两者不能混为一个自由文本 Prompt。
- `apply_patch`、`run_command` 和 Git Tool 必须经过同一执行链，不在 CLI 或 API 中建立绕过路径。
- Phase 2 的 durable `run_id` 与现有 AgentLoop/Trace/Chat `session_id` 是同一个 UUID；领域模型可使用各自术语，但不得再生成或映射第二个运行标识。
- 当前 Chat SQLite 已使用全局 `PRAGMA user_version` v1–v2：v1 是 Phase 1 Chat 核心表，v2 是 `chat_tool_activities` 脱敏 UI 投影。Phase 2 不得复用这两个版本号，也不得把 v2 activity 投影升级为 Durable、授权或副作用事实源。

全局 migration 编号锁定如下；所有领域 schema 通过 Task 6 的共享 runner 进入同一条严格连续、不可复用的版本流：

| `user_version` | 所属 Task / 领域 | 主要表或变更 |
|---:|---|---|
| 1 | Phase 1D Chat 基线 | conversations、messages、runs、approval_requests |
| 2 | Structured Chat rendering 基线 | chat_tool_activities（仅 UI read model） |
| 3 | Task 7 / Durable Run | durable_runs、run_checkpoints |
| 4 | Task 8 / Run ownership | run_leases |
| 5 | Task 10 / Idempotency | side_effects |
| 6 | Task 11 / Patch preview | patch_proposals |
| 7 | Task 13 / Authorization | authorization_requests、capabilities |
| 8 | Task 16 / Permission Profile | conversations permission_profile/profile_version migration |
| 9 | Task 18 / Command Artifact | command_output_artifacts（仅 metadata，不含 stdout/stderr 内容） |
| 10 | Task 20 / Artifact access audit | command_output_reads（仅读取区段、原因和计数，不含日志内容） |

## 2. Task 总览与门禁

| Task | Task ID | 子里程碑 | 产物 | 权限变化 |
|---:|---|---|---|---|
| 1 | `phase-2a-task-1` | 2A | Eval 领域模型与版本化任务集 | 无 |
| 2 | `phase-2a-task-2` | 2A | Offline Eval Runner、评分与报告 | 无 |
| 3 | `phase-2a-task-3` | 2A | 离线 CLI 与 Phase 1 固定基线 | 无 |
| 4 | `phase-2a-task-4` | 2A | Plan/Todo 与受限重规划领域层 | 无 |
| 5 | `phase-2a-task-5` | 2A Gate | Planning Runtime 接线与 Eval 回归 | 无；通过后才能进入 2B |
| 6 | `phase-2b-task-1` | 2B | 共享 SQLite migration 机制 | 无 |
| 7 | `phase-2b-task-2` | 2B | Durable Run 与版本化 Checkpoint | 无 |
| 8 | `phase-2b-task-3` | 2B | 单 run owner 与 lease | 无 |
| 9 | `phase-2b-task-4` | 2B | resume/retry/cancel 控制器 | 无 |
| 10 | `phase-2b-task-5` | 2B | side-effect ledger、幂等与崩溃点 | 无副作用 Tool |
| 11 | `phase-2b-task-6` | 2B Gate | Unified Diff 解析、校验与预览 | 只表达修改；不得落盘 |
| 12 | `phase-2c-task-1` | 2C | Tool metadata、Policy 与 Permission Profile | 无 |
| 13 | `phase-2c-task-2` | 2C | 通用 Approval 与一次性 Capability | 无 |
| 14 | `phase-2c-task-3` | 2C | ExecutionBackend 与最小 Docker Sandbox | 仅隔离基础设施 |
| 15 | `phase-2c-task-4` | 2C | 受控 `apply_patch` 与回滚 | 经门禁的项目内写入 |
| 16 | `phase-2c-task-5` | 2C Gate | Chat/API/UI 安全闭环与 Eval 回归 | 项目级 Profile 生效 |
| 17 | `phase-2d-task-1` | 2D | 命令安全合同、项目 manifest 与可复现 Sandbox | 无执行 Tool |
| 18 | `phase-2d-task-2` | 2D | `run_command`、durable 生命周期与 Command Output Artifact | 受限项目命令 |
| 19 | `phase-2d-task-3` | 2D | Tool-specific Parser 与 `CommandFeedback` | 无新权限 |
| 20 | `phase-2d-task-4` | 2D | 受限 Artifact 读取、Chat/API/UI 生产闭环 | 同 run 脱敏日志片段读取 |
| 21 | `phase-2d-task-5` | 2D | 结构化只读 Git Tool | 只读 Git |
| 22 | `phase-2d-task-6` | 2D | Repo Map、相关性与确定性 Context selection | 只读 |
| 23 | `phase-2d-task-7` | 2D | Loss-aware context compaction 与 rehydration | 无新权限 |
| 24 | `phase-2d-task-8` | 2D | Provider retry、rate limit 与 durable attempt budget | 无新权限 |
| 25 | `phase-2d-task-9` | 2D Gate | 全量 Eval、E2E、文档与人工验收 | Phase 2 总验收 |

---

## Phase 2A：Offline Eval 与 Planning

### Task 1：Eval 领域模型与版本化任务集

**Task ID:** `phase-2a-task-1`
**Evidence:** `docs/task-evidence/phase-2a-task-1.md`
**Depends on:** Phase 1 用户验收
**TDD:** required

**Files:**

- Create: `src/agent_foundations/evals/__init__.py`
- Create: `src/agent_foundations/evals/models.py`
- Create: `src/agent_foundations/evals/task_sets.py`
- Create: `tests/unit/evals/__init__.py`
- Create: `tests/unit/evals/test_models.py`
- Create: `tests/unit/evals/test_task_sets.py`
- Create: `tests/fixtures/evals/phase-1-tasks-v1.json`

**Stable contract:**

```python
class EvalAssertionKind(StrEnum):
    ANSWER_CONTAINS = "answer_contains"
    ANSWER_EXCLUDES = "answer_excludes"
    TOOL_CALLED = "tool_called"
    TOOL_NOT_CALLED = "tool_not_called"
    ERROR_CODE = "error_code"

class EvalAssertion(ValidatedCopyModel):
    kind: EvalAssertionKind
    value: str

class EvalTask(ValidatedCopyModel):
    task_id: str
    project_fixture: str
    prompt: str
    assertions: tuple[EvalAssertion, ...]
    max_steps: int
    tags: tuple[str, ...] = ()

class EvalTaskSet(ValidatedCopyModel):
    schema_version: Literal[1]
    dataset_id: str
    dataset_version: str
    tasks: tuple[EvalTask, ...]

def load_task_set(path: Path, *, fixture_root: Path) -> EvalTaskSet: ...
```

- [x] **Step 1: 创建 evidence 并保存 pre-change Git 快照**
- [x] **Step 2: 写模型冻结、重复 Task ID、绝对/`..` fixture 路径、空断言和未知 schema 的失败测试**

```python
def test_load_task_set_rejects_duplicate_task_ids(tmp_path: Path) -> None:
    path = write_task_set(tmp_path, task_ids=("duplicate", "duplicate"))
    with pytest.raises(ValueError, match="duplicate task_id"):
        load_task_set(path, fixture_root=tmp_path)
```

- [x] **Step 3: 运行 Red**

Run: `conda run -n agent-foundations python -m pytest tests/unit/evals -q`
Expected: pytest 正常收集，因 Eval 模型/校验行为缺失而出现 assertion failure；不得是导入或环境错误。

- [x] **Step 4: 实现最小冻结模型、相对路径校验、唯一性校验和 JSON loader**
- [x] **Step 5: 添加至少 5 个 Phase 1 固定任务：代码定位、错误解释、只读工具选择、敏感文件拒绝、项目外路径拒绝**
- [x] **Step 6: 运行 Green 与质量门禁**

Run:

```powershell
conda run -n agent-foundations python -m pytest tests/unit/evals -q
conda run -n agent-foundations python -m ruff check src/agent_foundations/evals tests/unit/evals
conda run -n agent-foundations python -m mypy src tests
git diff --check
```

Expected: 全部退出 `0`；fixture 不包含真实路径、凭据或模型响应。

- [x] **Step 7: 完成 evidence 范围审计并停止**

**Acceptance:** 同一任务集可确定性加载；未知版本、重复 ID、越界 fixture 和无断言任务稳定拒绝。
**Suggested commit after explicit authorization:** `feat: add versioned offline eval task sets`

---

### Task 2：Offline Eval Runner、评分与原子报告

**Task ID:** `phase-2a-task-2`
**Evidence:** `docs/task-evidence/phase-2a-task-2.md`
**Depends on:** Task 1 accepted
**TDD:** required

**Files:**

- Create: `src/agent_foundations/evals/runner.py`
- Create: `src/agent_foundations/evals/scoring.py`
- Create: `src/agent_foundations/evals/reporting.py`
- Create: `tests/unit/evals/test_scoring.py`
- Create: `tests/unit/evals/test_reporting.py`
- Create: `tests/integration/test_offline_eval.py`

**Stable contract:**

```python
class EvalObservation(ValidatedCopyModel):
    answer: str
    steps: int
    tool_names: tuple[str, ...]
    policy_decisions: tuple[str, ...] = ()
    error_code: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    duration_ms: float = 0.0

class EvalAgent(Protocol):
    async def run(self, task: EvalTask, project_root: Path) -> EvalObservation: ...

class OfflineEvalRunner:
    async def run(self, task_set: EvalTaskSet, agent: EvalAgent) -> EvalReport: ...

def write_report_atomic(report: EvalReport, path: Path) -> None: ...
```

- [x] **Step 1: 创建 evidence，记录 Task 1 已验收状态**
- [x] **Step 2: 写逐断言评分、单任务异常隔离、稳定排序、汇总指标和原子替换失败回滚测试**

```python
@pytest.mark.asyncio
async def test_runner_records_one_failure_without_skipping_later_tasks() -> None:
    report = await OfflineEvalRunner().run(task_set, ScriptedEvalAgent(outcomes))
    assert [result.task_id for result in report.results] == ["first", "second"]
    assert report.results[0].passed is False
    assert report.results[1].passed is True
```

- [x] **Step 3: 运行 Red**

Run: `conda run -n agent-foundations python -m pytest tests/unit/evals tests/integration/test_offline_eval.py -q`
Expected: 因 runner/评分/原子报告行为缺失而失败，已有 Task 1 测试保持通过。

- [x] **Step 4: 实现顺序 Runner、纯函数评分、版本/环境元数据和临时文件 + `os.replace` 报告写入**
- [x] **Step 5: 确保报告包含 dataset、Prompt、response fixture、Tool 集合和 Runtime revision 的显式输入字段，不在 Runner 内调用 Git**
- [x] **Step 6: 运行 Green、Phase 1 Eval 回归和 Ruff/mypy/diff 门禁**

Run:

```powershell
conda run -n agent-foundations python -m pytest tests/unit/evals tests/integration/test_offline_eval.py -q
conda run -n agent-foundations python -m pytest tests/unit/providers tests/integration/test_agent_loop.py -q
conda run -n agent-foundations python -m ruff check src/agent_foundations/evals tests/unit/evals tests/integration/test_offline_eval.py
conda run -n agent-foundations python -m mypy src tests
git diff --check
```

- [x] **Step 7: 记录精确结果并停止**

**Acceptance:** 报告可重复、失败隔离、统计可核对；相同输入生成除显式时间字段外语义相同的 JSON。
**Suggested commit after explicit authorization:** `feat: add deterministic offline eval runner`

---

### Task 3：离线 Eval CLI 与 Phase 1 基线

**Task ID:** `phase-2a-task-3`
**Evidence:** `docs/task-evidence/phase-2a-task-3.md`
**Depends on:** Task 2 accepted
**TDD:** required

**Files:**

- Create: `src/agent_foundations/evals/replay.py`
- Create: `tests/unit/evals/test_replay.py`
- Create: `tests/fixtures/evals/phase-1-responses-v1.json`
- Create: `docs/eval-baselines/phase-1-v1.json`
- Modify: `src/agent_foundations/cli/main.py`
- Modify: `tests/e2e/test_cli.py`
- Modify: `.gitignore`

**CLI contract:**

```text
agent-foundations evaluate \
  --task-set tests/fixtures/evals/phase-1-tasks-v1.json \
  --responses tests/fixtures/evals/phase-1-responses-v1.json \
  --output .agent-foundations/evals/latest.json \
  --runtime-revision working-tree
```

- `evaluate` 只接受回放响应，不读取 `AGENT_API_KEY`，不构造真实 Provider。
- response fixture 按 `task_id` 保存完整 `ModelResponse` 序列；缺失、重复、耗尽和剩余响应均失败。
- canonical baseline 固定任务集/响应集 hash、Tool 清单和指标；运行产物目录进入 `.gitignore`。

- [x] **Step 1: 创建 evidence 并确认不会调用真实模型**
- [x] **Step 2: 写 response script 校验、CLI 无凭据运行、缺失 Task 响应失败和输出 shape 的 Red**

```python
def test_evaluate_command_does_not_require_model_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AGENT_API_KEY", raising=False)
    result = runner.invoke(app, ["evaluate", *offline_args])
    assert result.exit_code == 0
```

- [x] **Step 3: 运行 Red**

Run: `conda run -n agent-foundations python -m pytest tests/unit/evals/test_replay.py tests/e2e/test_cli.py -q`
Expected: `evaluate` 或 replay 行为缺失导致测试断言失败；不得发起网络连接。

- [x] **Step 4: 实现 ReplayEvalAgent、CLI 参数校验和确定性退出码：全通过 `0`、能力失败 `1`、输入无效 `2`**
- [x] **Step 5: 运行 CLI 生成报告，人工核对后保存 `docs/eval-baselines/phase-1-v1.json`；记录实际 revision 输入，不伪称 clean commit**
- [x] **Step 6: 运行 Green 和 CLI/Provider 回归**

Run:

```powershell
conda run -n agent-foundations python -m pytest tests/unit/evals tests/integration/test_offline_eval.py tests/e2e/test_cli.py -q
conda run -n agent-foundations agent-foundations evaluate --task-set tests/fixtures/evals/phase-1-tasks-v1.json --responses tests/fixtures/evals/phase-1-responses-v1.json --output .agent-foundations/evals/latest.json --runtime-revision working-tree
conda run -n agent-foundations python -m ruff check src/agent_foundations/evals src/agent_foundations/cli tests/unit/evals tests/e2e/test_cli.py
conda run -n agent-foundations python -m mypy src tests
git diff --check
```

- [x] **Step 7: 记录基线 hash、指标和未验证项并停止**

**Acceptance:** 没有 API Key 也能完整运行固定基线；报告失败能使 CLI 非零退出；无网络、付费调用和真实用户项目读取。
**Suggested commit after explicit authorization:** `feat: establish phase one offline eval baseline`

---

### Task 4：Plan/Todo 领域模型与受限重规划

**Task ID:** `phase-2a-task-4`
**Evidence:** `docs/task-evidence/phase-2a-task-4.md`
**Depends on:** Task 3 accepted
**TDD:** required

**Files:**

- Create: `src/agent_foundations/planning/__init__.py`
- Create: `src/agent_foundations/planning/models.py`
- Create: `src/agent_foundations/planning/controller.py`
- Create: `tests/unit/planning/__init__.py`
- Create: `tests/unit/planning/test_models.py`
- Create: `tests/unit/planning/test_controller.py`

**Stable contract:**

```python
class PlanStepStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"

class PlanStep(ValidatedCopyModel):
    step_id: str
    description: str
    status: PlanStepStatus = PlanStepStatus.PENDING
    depends_on: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()

class ExecutionPlan(ValidatedCopyModel):
    plan_id: str
    version: int
    goal: str
    steps: tuple[PlanStep, ...]
    replan_count: int = 0
    max_replans: int = 2

class PlanController:
    def create(self, goal: str, steps: tuple[PlanStep, ...]) -> ExecutionPlan: ...
    def transition(self, expected_version: int, step_id: str,
                   target: PlanStepStatus, evidence_refs: tuple[str, ...]) -> ExecutionPlan: ...
    def replan(self, expected_version: int, reason: str,
               replacement_pending_steps: tuple[PlanStep, ...]) -> ExecutionPlan: ...
```

- [x] **Step 1: 创建 evidence**
- [x] **Step 2: 写重复/悬空依赖、依赖环、同时多个 in-progress、无 evidence 完成、版本冲突和重规划次数上限测试**

```python
def test_completed_step_requires_recorded_execution_fact() -> None:
    controller = PlanController()
    plan = controller.create("inspect", (PlanStep(step_id="read", description="read"),))
    with pytest.raises(PlanTransitionError, match="evidence"):
        controller.transition(plan.version, "read", PlanStepStatus.COMPLETED, ())
```

- [x] **Step 3: 运行 Red**

Run: `conda run -n agent-foundations python -m pytest tests/unit/planning -q`
Expected: 因 Plan 不变量和 CAS version 行为缺失而失败。

- [x] **Step 4: 实现冻结模型、DAG 校验、单 in-progress、不变量、版本 CAS 和 `max_replans`**
- [x] **Step 5: `replan` 只能替换未完成步骤，保留 completed 步骤和 evidence；reason 必须非空并进入新版本**
- [x] **Step 6: 运行 Green、Ruff、mypy、diff**

Run:

```powershell
conda run -n agent-foundations python -m pytest tests/unit/planning -q
conda run -n agent-foundations python -m ruff check src/agent_foundations/planning tests/unit/planning
conda run -n agent-foundations python -m mypy src tests
git diff --check
```

- [x] **Step 7: evidence 范围审计并停止**

**Acceptance:** Plan 更新是版本化、确定性且有界的；模型不能无执行事实把 Todo 标记完成。
**Suggested commit after explicit authorization:** `feat: add bounded planning state machine`

---

### Task 5：Planning Tool、Runtime 接线与 Phase 2A Gate

**Task ID:** `phase-2a-task-5`
**Evidence:** `docs/task-evidence/phase-2a-task-5.md`
**Depends on:** Task 4 accepted
**TDD:** required

**Files:**

- Create: `src/agent_foundations/planning/tools.py`
- Create: `src/agent_foundations/planning/execution.py`
- Create: `tests/unit/planning/test_tools.py`
- Create: `tests/unit/planning/test_execution.py`
- Modify: `src/agent_foundations/runtime/agent.py`
- Modify: `src/agent_foundations/runtime/loop.py`
- Modify: `src/agent_foundations/cli/main.py`
- Modify: `tests/integration/test_agent_loop.py`
- Modify: `tests/fixtures/evals/phase-1-tasks-v1.json`
- Modify: `tests/fixtures/evals/phase-1-responses-v1.json`

**Tool contract:**

```text
set_plan(goal, steps[])
update_plan_step(plan_version, step_id, status, evidence_tool_call_ids[])
replan(plan_version, reason, replacement_pending_steps[])
```

`PlanningToolExecutor` 包装下游 executor：记录成功/失败 Tool Call fact；Planning Tool 只能引用已记录的成功 call ID。`ToolResult.metadata["plan_event"]` 触发 `plan.created`、`plan.step.updated` 或 `plan.replanned` Trace。

- [x] **Step 1: 创建 evidence 并记录 Phase 2A 前四个 Task 状态**
- [x] **Step 2: 写 Planning Tool Schema、伪造 evidence ID 拒绝、Trace 顺序、重规划限制和 `PlanningMode.DISABLED/REQUIRED` 兼容测试**

```python
@pytest.mark.asyncio
async def test_required_planning_rejects_final_answer_before_plan() -> None:
    loop, sink, _ = build_loop([ModelResponse(content="done")], planning_required=True)
    with pytest.raises(PlanningRequiredError):
        await loop.run(FIXTURE_ROOT, "inspect")
    assert sink.events[-1].event_type == "session.failed"
```

- [x] **Step 3: 运行 Red**

Run: `conda run -n agent-foundations python -m pytest tests/unit/planning tests/integration/test_agent_loop.py -q`
Expected: 因 Planning Tool/executor/required mode 缺失而失败；Phase 1 默认模式测试仍被收集。

- [x] **Step 4: 实现三个内部控制 Tool、execution fact journal、Trace 投影和可选 `PlanningMode`；默认保持 Phase 1 行为兼容**
- [x] **Step 5: 更新离线 fixture 增加有计划/无计划/超限重规划任务；不增加文件写、Shell 或 Sandbox**
- [x] **Step 6: 运行 Phase 2A 完整门禁**

Run:

```powershell
conda run -n agent-foundations python -m pytest tests/unit/evals tests/unit/planning tests/integration/test_offline_eval.py tests/integration/test_agent_loop.py tests/e2e/test_cli.py -q
conda run -n agent-foundations agent-foundations evaluate --task-set tests/fixtures/evals/phase-1-tasks-v1.json --responses tests/fixtures/evals/phase-1-responses-v1.json --output .agent-foundations/evals/phase-2a.json --runtime-revision working-tree
conda run -n agent-foundations python -m ruff check src tests
conda run -n agent-foundations python -m mypy src tests
conda run -n agent-foundations python -m pip check
git diff --check
```

- [ ] **Step 7: 由 reviewer 独立复验；等待用户确认 Phase 2A，未确认不得开始 Task 6**

**Acceptance:** Agent 可创建、更新和有界重规划；完成状态引用真实 Tool fact；Eval 能比较 Planning 增量；权限仍为只读。
**Suggested commit after explicit authorization:** `feat: integrate bounded planning into runtime`

---

## Phase 2B：Durable Execution 与 Unified Diff

### Task 6：共享 SQLite migration 基础设施

**Task ID:** `phase-2b-task-1`
**Evidence:** `docs/task-evidence/phase-2b-task-1.md`
**Depends on:** Phase 2A user-accepted
**TDD:** required

**Files:**

- Create: `src/agent_foundations/storage/__init__.py`
- Create: `src/agent_foundations/storage/database.py`
- Create: `src/agent_foundations/storage/migrations.py`
- Create: `src/agent_foundations/chat/schema.py`
- Create: `tests/unit/storage/__init__.py`
- Create: `tests/unit/storage/test_database.py`
- Modify: `src/agent_foundations/chat/repository.py`
- Modify: `tests/unit/chat/test_repository.py`

**Stable contract:**

```python
@dataclass(frozen=True)
class Migration:
    version: int
    statements: tuple[str, ...]

class SqliteDatabase:
    def __init__(self, path: Path, migrations: tuple[Migration, ...]) -> None: ...
    async def initialize(self) -> None: ...
    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]: ...
```

- [x] **Step 1: 创建 evidence，确认当前 `_SCHEMA_VERSION == 2`；在 `tests/unit/storage/test_database.py` 的 test helper 中用已锁定 SQL 构造真实 v1 与 v2 数据库，不提交二进制 SQLite fixture；v2 fixture 必须包含 conversation、message、run、approval 和至少一行 `chat_tool_activities`**
- [x] **Step 2: 写空库迁移、已有 v1→v2 无损升级、已有 v2 原样接管、v2 activity 行/索引保持、缺号/重复 migration、事务回滚和未来版本拒绝测试**
- [x] **Step 3: 运行 Red**

Run: `conda run -n agent-foundations python -m pytest tests/unit/storage tests/unit/chat/test_repository.py -q`
Expected: 新 migration 行为断言失败；已有 Repository 测试保持当前基线。

- [x] **Step 4: 把 `_SCHEMA_V1_SQL` 与 `_MIGRATION_V1_TO_V2_STATEMENTS` 移到 `chat/schema.py`，分别注册为 version 1、2；实施顺序 migration 和共享连接设置，Phase 2 的下一可用版本固定为 3**
- [x] **Step 5: `ConversationRepository(Path)` 保持源兼容并委托 `SqliteDatabase`；不得重写 conversation/message/run/approval/activity 业务 SQL，不得改变 Phase 1 行为或把 `chat_tool_activities` 当作控制事实**
- [x] **Step 6: 运行 Repository 全量回归、Ruff、mypy、diff**
- [x] **Step 7: evidence 分别记录真实 v1 升级和真实 v2 接管后的表、索引、行数与关键字段保持结果并停止**

**Acceptance:** v1 数据无损升级到 v2；现有 v2 数据库被共享 runner 无损接管且 `chat_tool_activities` 行与索引保持；migration 严格连续、原子、可审计；未来版本稳定拒绝；Phase 2 后续 migration 从 v3 开始。
**Suggested commit after explicit authorization:** `refactor: add shared sqlite migration runner`

---

### Task 7：Durable Run 与版本化 Checkpoint Repository

**Task ID:** `phase-2b-task-2`
**Evidence:** `docs/task-evidence/phase-2b-task-2.md`
**Depends on:** Task 6 accepted
**TDD:** required

**Files:**

- Create: `src/agent_foundations/durable/__init__.py`
- Create: `src/agent_foundations/durable/models.py`
- Create: `src/agent_foundations/durable/repository.py`
- Create: `src/agent_foundations/durable/schema.py`
- Create: `tests/unit/durable/__init__.py`
- Create: `tests/unit/durable/test_models.py`
- Create: `tests/unit/durable/test_repository.py`
- Modify: `src/agent_foundations/storage/migrations.py`

**Schema and contract:**

```text
durable_runs(run_id PK, project_root, status,
             schema_version, state_version, attempt, created_at, updated_at)
run_checkpoints(checkpoint_id PK, run_id FK, sequence, schema_version,
                state_json, created_at, UNIQUE(run_id, sequence))
```

```python
class DurableRunStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class DurableRunRepository:
    async def create_run(self, run: DurableRun) -> DurableRun: ...
    async def save_checkpoint(self, run_id: str, expected_state_version: int,
                              state: RunState) -> RunCheckpoint: ...
    async def load_latest_checkpoint(self, run_id: str) -> RunCheckpoint: ...
```

创建 Durable Run 时直接使用 `AgentLoop.run(..., session_id=...)` 的 UUID 作为 `run_id`；Chat/API 继续对外叫 `session_id`，Repository 和 Adapter 不生成第二个标识。

- [x] **Step 1: 创建 evidence**
- [x] **Step 2: 写 schema/version、JSON 冻结、CAS 冲突、checkpoint 单调序列、未知 run 和事务回滚测试**
- [x] **Step 3: 运行 Red**

Run: `conda run -n agent-foundations python -m pytest tests/unit/durable/test_models.py tests/unit/durable/test_repository.py -q`
Expected: Durable 模型/表/CAS 行为缺失导致 assertion failure。

- [x] **Step 4: 添加 version 3 migration、冻结 `RunState`、Repository 和 `BEGIN IMMEDIATE` CAS 保存；不得改写或依赖 v2 `chat_tool_activities`**
- [x] **Step 5: checkpoint 必须包含消息、next step、plan snapshot、attempt 和最近已提交 Tool fact；不得包含凭据或开放文件句柄**
- [x] **Step 6: 运行 Green、migration/Chat 回归、Ruff/mypy/diff**
- [x] **Step 7: evidence 审计并停止**

**Acceptance:** Checkpoint 可版本化读取，旧 state version 不能覆盖新状态，未知 schema 稳定拒绝。
**Suggested commit after explicit authorization:** `feat: persist versioned durable checkpoints`

---

### Task 8：单 Run Owner 与 Lease

**Task ID:** `phase-2b-task-3`
**Evidence:** `docs/task-evidence/phase-2b-task-3.md`
**Depends on:** Task 7 accepted
**TDD:** required

**Files:**

- Create: `src/agent_foundations/durable/lease.py`
- Create: `tests/unit/durable/test_lease.py`
- Modify: `src/agent_foundations/durable/models.py`
- Modify: `src/agent_foundations/durable/repository.py`
- Modify: `src/agent_foundations/durable/schema.py`
- Modify: `src/agent_foundations/storage/migrations.py`

**Stable contract:**

```python
class RunLease(ValidatedCopyModel):
    run_id: str
    owner_id: str
    lease_token: str
    acquired_at: datetime
    expires_at: datetime

class LeaseManager:
    async def acquire(self, run_id: str, owner_id: str, ttl: timedelta) -> RunLease: ...
    async def renew(self, lease: RunLease, ttl: timedelta) -> RunLease: ...
    async def release(self, lease: RunLease) -> None: ...
    async def takeover_expired(self, run_id: str, owner_id: str,
                               ttl: timedelta) -> RunLease: ...
```

- [x] **Step 1: 创建 evidence**
- [x] **Step 2: 使用注入 UTC clock 写双 owner 冲突、错误 token、过期续租、到期接管、并发 acquire 仅一胜和审计字段测试**
- [x] **Step 3: 运行 Red**

Run: `conda run -n agent-foundations python -m pytest tests/unit/durable/test_lease.py -q`
Expected: lease 原子所有权行为缺失导致失败。

- [x] **Step 4: 添加 version 4 `run_leases` migration 和基于 `BEGIN IMMEDIATE` 的 LeaseManager**
- [x] **Step 5: 所有比较使用注入的 timezone-aware UTC；不得依赖 sleep 或本机时钟竞态**
- [x] **Step 6: 运行 Green、Durable/Chat migration 回归和质量门禁**
- [x] **Step 7: evidence 记录并停止**

**Acceptance:** 任意时刻只有一个有效 owner；过期、接管、续租和释放均需匹配 token 且可审计。
**Suggested commit after explicit authorization:** `feat: enforce durable run ownership leases`

---

### Task 9：resume、retry、cancel 与可恢复 Agent 状态机

**Task ID:** `phase-2b-task-4`
**Evidence:** `docs/task-evidence/phase-2b-task-4.md`
**Depends on:** Task 8 accepted
**TDD:** required

**Files:**

- Create: `src/agent_foundations/durable/controller.py`
- Create: `src/agent_foundations/runtime/state_machine.py`
- Create: `tests/unit/durable/test_controller.py`
- Create: `tests/unit/runtime/test_state_machine.py`
- Modify: `src/agent_foundations/runtime/session.py`
- Modify: `src/agent_foundations/runtime/loop.py`
- Modify: `tests/integration/test_agent_loop.py`

**Stable contract:**

```python
class RunCommand(StrEnum):
    RESUME = "resume"
    RETRY = "retry"
    CANCEL = "cancel"

class DurableRunController:
    async def resume(self, run_id: str, owner_id: str) -> AgentResult: ...
    async def retry(self, run_id: str, owner_id: str) -> AgentResult: ...
    async def cancel(self, run_id: str, requested_by: str) -> DurableRun: ...
```

Checkpoint 时机固定为：model response 持久化后、每个 Tool result 持久化后、Plan 更新后和终态提交前。cancel 在下一次 Provider/Tool 边界前生效。

- [x] **Step 1: 创建 evidence**
- [x] **Step 2: 写从 model 后、tool 后 checkpoint 恢复，retry attempt 递增，cancel 不再调用 Provider/Tool，过期 lease 接管和双 owner 拒绝测试**
- [x] **Step 3: 运行 Red**

Run: `conda run -n agent-foundations python -m pytest tests/unit/durable/test_controller.py tests/unit/runtime/test_state_machine.py tests/integration/test_agent_loop.py -q`
Expected: 恢复状态机和命令行为缺失导致断言失败；Phase 1 run 路径保持可运行。

- [x] **Step 4: 提取可序列化 `AgentRunState`，让 `AgentLoop` 接受可选 checkpoint sink/cancel token；默认 Direct 模式不创建数据库**
- [x] **Step 5: 实现 Controller 获取 lease、读取最新 checkpoint、CAS 保存、终态释放；retry 从最后安全 checkpoint 开始而非清空历史**
- [x] **Step 6: 运行 Green、AgentLoop/Chat Runner 回归和质量门禁**
- [x] **Step 7: 记录恢复点矩阵并停止**

**Acceptance:** resume/retry/cancel 有明确状态转换；恢复不会重放已经持久化的模型决定或 Tool result；单 owner 约束贯穿执行。
**Suggested commit after explicit authorization:** `feat: add durable run resume retry and cancel`

---

### Task 10：Side-effect Ledger、幂等执行与崩溃点

**Task ID:** `phase-2b-task-5`
**Evidence:** `docs/task-evidence/phase-2b-task-5.md`
**Depends on:** Task 9 accepted
**TDD:** required

**Files:**

- Create: `src/agent_foundations/durable/effects.py`
- Create: `src/agent_foundations/durable/faults.py`
- Create: `tests/unit/durable/test_effects.py`
- Create: `tests/integration/test_idempotent_tool_execution.py`
- Modify: `src/agent_foundations/durable/models.py`
- Modify: `src/agent_foundations/durable/repository.py`
- Modify: `src/agent_foundations/durable/schema.py`
- Modify: `src/agent_foundations/storage/migrations.py`
- Modify: `src/agent_foundations/runtime/tool_execution.py`

**Stable states:**

```python
class EffectStatus(StrEnum):
    INTENT_RECORDED = "intent_recorded"
    EXECUTING = "executing"
    COMMITTED = "committed"
    FAILED = "failed"
    UNKNOWN = "unknown"
    ROLLED_BACK = "rolled_back"

class SideEffectClassifier(Protocol):
    def describe(self, tool: Tool, arguments: Mapping[str, Any],
                 context: ToolExecutionContext) -> SideEffectIntent | None: ...
```

唯一键为 `(run_id, tool_call_id, tool_name)`；`idempotency_key` 从稳定字段派生并持久化。Task 10 使用注入式 `SideEffectClassifier` 测试机制，Task 12 再用正式 Tool metadata 接线，避免提前引用尚未定义的类型。已 `COMMITTED` 返回保存结果；`UNKNOWN` 必须停止并要求 reconcile，绝不盲目重跑。

- [x] **Step 1: 创建 evidence**
- [x] **Step 2: 写重复执行只产生一次副作用、intent 前失败、execute 前崩溃、execute 后 commit 前崩溃、commit 后恢复和 UNKNOWN 拒绝重跑测试**

```python
@pytest.mark.asyncio
async def test_crash_after_effect_before_commit_never_reexecutes() -> None:
    with pytest.raises(InjectedCrash):
        await executor.execute_once(call, crash_at=CrashPoint.AFTER_EXECUTE)
    with pytest.raises(EffectResolutionRequiredError):
        await executor.execute_once(call)
    assert fake_effect.count == 1
```

- [x] **Step 3: 运行 Red**

Run: `conda run -n agent-foundations python -m pytest tests/unit/durable/test_effects.py tests/integration/test_idempotent_tool_execution.py -q`
Expected: ledger/idempotency/crash semantics 缺失导致失败。

- [x] **Step 4: 添加 version 5 `side_effects` migration、Ledger Repository、`IdempotentToolCallExecutor` 和仅测试可注入 CrashPoint**
- [x] **Step 5: Trace 只记录 effect ID、状态和脱敏摘要；不得把完整 Patch、命令输出或凭据复制进 ledger 事件**
- [x] **Step 6: 运行 Green、Durable/AgentLoop 回归、Ruff/mypy/diff**
- [x] **Step 7: 记录每个崩溃点结果并停止**

**Acceptance:** 已提交副作用不会重复；不确定状态不会自动重试；所有状态转换 CAS 化并可恢复。
**Suggested commit after explicit authorization:** `feat: add idempotent side effect ledger`

---

### Task 11：Unified Diff 解析、校验、预览与 Phase 2B Gate

**Task ID:** `phase-2b-task-6`
**Evidence:** `docs/task-evidence/phase-2b-task-6.md`
**Depends on:** Task 10 accepted
**TDD:** required

**Files:**

- Create: `src/agent_foundations/tools/patch/__init__.py`
- Create: `src/agent_foundations/tools/patch/models.py`
- Create: `src/agent_foundations/tools/patch/parser.py`
- Create: `src/agent_foundations/tools/patch/validator.py`
- Create: `src/agent_foundations/tools/patch/repository.py`
- Create: `src/agent_foundations/tools/patch/execution.py`
- Create: `src/agent_foundations/tools/patch/validate_patch.py`
- Create: `tests/unit/tools/patch/__init__.py`
- Create: `tests/unit/tools/patch/test_parser.py`
- Create: `tests/unit/tools/patch/test_validator.py`
- Create: `tests/unit/tools/patch/test_repository.py`
- Create: `tests/unit/tools/patch/test_execution.py`
- Create: `tests/unit/tools/patch/test_validate_patch.py`
- Create: `tests/integration/test_patch_preview_flow.py`
- Modify: `src/agent_foundations/storage/migrations.py`

**Supported subset:** UTF-8 text；Git-style unified diff；修改现有文件或创建新文件。明确拒绝 delete、rename、binary patch、绝对路径、`..`、ADS/控制字符、symlink/reparse target、超限文件和基线 hash 不匹配。

```python
class PatchOperation(StrEnum):
    MODIFY = "modify"
    CREATE = "create"

class ValidatedPatch(ValidatedCopyModel):
    patch_id: str
    project_root_fingerprint: str
    files: tuple[PatchFile, ...]

class ValidatePatchTool:
    name = "validate_patch"

class PatchProposalRepository:
    async def save(self, run_id: str, patch: ValidatedPatch) -> ValidatedPatch: ...
    async def get(self, run_id: str, patch_id: str) -> ValidatedPatch: ...

class PatchProposalExecutor:
    async def execute(self, tool: Tool, arguments: dict[str, Any],
                      context: ToolExecutionContext) -> ToolResult: ...
```

`PatchProposalExecutor` 包装下游 executor，并只在识别到 `ValidatePatchTool` 时使用 `context.session_id` 和 `context.root` 校验、持久化、返回脱敏摘要；该 Tool 不得通过 `DirectToolCallExecutor` 绕过 run 绑定。

- [x] **Step 1: 创建 evidence**
- [x] **Step 2: 写多 hunk、无换行标记、create/modify、路径穿越、Windows ADS、控制字符、rename/delete/binary、symlink、内容漂移、大小限制、跨 run 读取拒绝和持久化回滚测试**
- [x] **Step 3: 运行 Red**

Run: `conda run -n agent-foundations python -m pytest tests/unit/tools/patch tests/integration/test_patch_preview_flow.py -q`
Expected: parser/validator/Tool 行为缺失导致断言失败；测试不得修改 fixture 项目。

- [x] **Step 4: 手写受限 parser、基于 SHA-256 的基线校验和 context-aware `PatchProposalExecutor`；添加 version 6 `patch_proposals` migration，按 `(run_id, patch_id)` 保存完整校验结果；不引入第三方 Patch 库**
- [x] **Step 5: `validate_patch` 只向模型返回 patch ID、文件摘要、hunk 计数和错误，不写文件；完整提案只进入 SQLite 恢复事实，Trace 默认不保存源码 Diff**
- [x] **Step 6: 运行 Phase 2B 完整门禁**

Run:

```powershell
conda run -n agent-foundations python -m pytest tests/unit/durable tests/unit/storage tests/unit/tools/patch tests/integration/test_agent_loop.py tests/integration/test_idempotent_tool_execution.py tests/integration/test_patch_preview_flow.py tests/unit/chat/test_repository.py -q
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
```

- [x] **Step 7: reviewer 独立复验并等待用户确认 Phase 2B；未确认不得开始 Task 12**

**Acceptance:** Agent 可表达并校验 Patch，但 Registry 中不存在任何写 Tool；恢复、lease、ledger 和 crash tests 全部通过。
**Suggested commit after explicit authorization:** `feat: validate unified diff proposals`

---

## Phase 2C：Policy、Capability、Sandbox 与受控写入

### Task 12：Tool Metadata、Policy 与版本化 Permission Profile

**Task ID:** `phase-2c-task-1`
**Evidence:** `docs/task-evidence/phase-2c-task-1.md`
**Depends on:** Phase 2B user-accepted
**TDD:** required

**Files:**

- Create: `src/agent_foundations/security/__init__.py`
- Create: `src/agent_foundations/security/models.py`
- Create: `src/agent_foundations/security/policy.py`
- Create: `src/agent_foundations/security/resources.py`
- Create: `tests/unit/security/__init__.py`
- Create: `tests/unit/security/test_models.py`
- Create: `tests/unit/security/test_policy.py`
- Modify: `src/agent_foundations/domain/tool.py`
- Modify: `src/agent_foundations/tools/registry.py`
- Modify: `src/agent_foundations/tools/filesystem/list_directory.py`
- Modify: `src/agent_foundations/tools/filesystem/read_file.py`
- Modify: `src/agent_foundations/tools/filesystem/search_text.py`
- Modify: `src/agent_foundations/planning/tools.py`
- Modify: `src/agent_foundations/tools/patch/validate_patch.py`
- Modify: `src/agent_foundations/cli/main.py`
- Modify: `tests/contract/test_protocols.py`
- Modify: `tests/unit/tools/test_registry.py`

**Stable contract:**

```python
class PermissionProfileName(StrEnum):
    PROJECT_READ_ONLY = "PROJECT_READ_ONLY"
    ASK_ALWAYS = "ASK_ALWAYS"
    RISK_BASED = "RISK_BASED"
    PROJECT_FULL_ACCESS = "PROJECT_FULL_ACCESS"
    CUSTOM = "CUSTOM"

class SideEffectKind(StrEnum):
    NONE = "none"
    PROJECT_WRITE = "project_write"
    PROCESS = "process"
    NETWORK = "network"

class ToolManifest(ValidatedCopyModel):
    name: str
    resource_kind: str
    operations: tuple[str, ...]
    side_effect: SideEffectKind
    sandbox_required: bool

class RegisteredTool(NamedTuple):
    tool: Tool
    manifest: ToolManifest
    resource_resolver: ToolResourceResolver

class PolicyEngine:
    def decide(self, profile: PermissionProfile, request: PolicyRequest) -> PolicyOutcome: ...
```

保留 `PROJECT_READ_ONLY` 作为最安全基线；Phase 1 的 `ASK_FOR_ACCESS` 只作为读取旧 SQLite/API 值的 migration alias，规范化后写入 `ASK_ALWAYS`，不得继续生成新 legacy 值。

确定性矩阵固定为：项目内 read、Planning 和 `validate_patch` 对五个 Profile 均 allow；项目 write 对 `PROJECT_READ_ONLY` deny、`ASK_ALWAYS`/`RISK_BASED` ask、`PROJECT_FULL_ACCESS` allow、`CUSTOM` 按规则且默认 deny；ephemeral Sandbox allowlist command 对 `PROJECT_READ_ONLY` deny、`ASK_ALWAYS` ask、`RISK_BASED`/`PROJECT_FULL_ACCESS` allow；Phase 1 external exact read 在 `ASK_ALWAYS` 下 ask；network、系统修改、项目外 write 和未知 Tool 在 Phase 2 对全部 Profile hard deny。

- [x] **Step 1: 创建 evidence 并记录 Phase 2B 用户验收**
- [x] **Step 2: 写所有 Tool 必须显式 metadata、名称不一致拒绝、五个 Profile 决策矩阵、CUSTOM 默认拒绝、硬 deny 不可审批绕过和 legacy alias 测试**

```python
@pytest.mark.parametrize(
    ("profile", "effect", "expected"),
    [
        ("PROJECT_READ_ONLY", "project_write", "deny"),
        ("ASK_ALWAYS", "project_write", "ask"),
        ("RISK_BASED", "project_write", "ask"),
        ("PROJECT_FULL_ACCESS", "project_write", "allow"),
    ],
)
def test_project_write_policy_matrix(profile: str, effect: str, expected: str) -> None:
    assert decide(profile, effect).decision == expected
```

- [x] **Step 3: 运行 Red**

Run: `conda run -n agent-foundations python -m pytest tests/unit/security tests/unit/tools/test_registry.py tests/contract/test_protocols.py -q`
Expected: metadata/Profile/Policy 行为缺失导致断言失败；测试正常收集。

- [x] **Step 4: 实现显式 `RegisteredTool`、资源解析器和纯函数 Policy；更新所有现有 Tool 注册点，不提供宽松默认 metadata**
- [x] **Step 5: Policy 输入固定 profile version、run、tool call、资源、操作和 Tool manifest；输出只含 allow/ask/deny、rule ID 和原因代码**
- [x] **Step 6: 运行 Green、全部 Tool/AgentLoop 回归和质量门禁**
- [x] **Step 7: evidence 附决策矩阵并停止**

**Acceptance:** Tool 能力和风险可机器判定；五个有效 Profile 与 legacy migration 行为明确；Policy 不执行 Tool、不签发 Capability。
**Suggested commit after explicit authorization:** `feat: add versioned tool policy profiles`

---

### Task 13：通用 Approval 与一次性 Capability

**Task ID:** `phase-2c-task-2`
**Evidence:** `docs/task-evidence/phase-2c-task-2.md`
**Depends on:** Task 12 accepted
**TDD:** required

**Files:**

- Create: `src/agent_foundations/security/approvals.py`
- Create: `src/agent_foundations/security/capabilities.py`
- Create: `src/agent_foundations/security/repository.py`
- Create: `src/agent_foundations/security/schema.py`
- Create: `tests/unit/security/test_approvals.py`
- Create: `tests/unit/security/test_capabilities.py`
- Create: `tests/unit/security/test_repository.py`
- Create: `tests/integration/test_authorization_flow.py`
- Modify: `src/agent_foundations/storage/migrations.py`
- Modify: `src/agent_foundations/chat/approvals.py`
- Modify: `src/agent_foundations/chat/tool_execution.py`
- Modify: `tests/integration/test_chat_approval_flow.py`

**Stable contract and schema:**

```text
authorization_requests(authorization_id PK, run_id, tool_call_id, tool_name,
  resource_json, operation, profile_name, profile_version, status,
  requested_at, decided_at, UNIQUE(run_id, tool_call_id))
capabilities(capability_id PK, authorization_id, run_id, tool_call_id,
  tool_name, resource_json, operation, profile_version, issued_at,
  expires_at, consumed_at)
```

```python
class CapabilityIssuer:
    async def issue(self, request: PolicyRequest, outcome: PolicyOutcome,
                    approval: AuthorizationDecision | None) -> Capability: ...

class CapabilityConsumer:
    async def consume(self, capability_id: str, execution: PolicyRequest) -> Capability: ...
```

- [x] **Step 1: 创建 evidence**
- [x] **Step 2: 写 allow 直接签发、ask 未批准拒绝、deny 永不签发、exact resource、过期、重复消费、profile/version/tool-call 不匹配和原子审批 + 签发回滚测试**
- [x] **Step 3: 运行 Red**

Run: `conda run -n agent-foundations python -m pytest tests/unit/security tests/integration/test_authorization_flow.py tests/integration/test_chat_approval_flow.py -q`
Expected: 通用 authorization/capability 行为缺失导致失败；Phase 1 外部只读审批回归仍被执行。

- [x] **Step 4: 添加 version 7 migration、通用 Repository、Issuer/Consumer；Capability 一次性消费并绑定 exact request**
- [x] **Step 5: 用 Adapter 让现有外部只读审批经过新链，保持旧 API response shape；不得删除历史 approval 数据或扩大外部访问**
- [x] **Step 6: 运行 Green、Chat/API/Repository 回归和质量门禁**
- [x] **Step 7: 记录 allow/ask/deny → capability 顺序证据并停止**

**Acceptance:** Approval 只表达人决定，Capability 才授权具体执行；旧外部读取流程行为不变；重复、过期或错配 Capability 稳定拒绝。
**Suggested commit after explicit authorization:** `feat: issue scoped one-time capabilities`

---

### Task 14：ExecutionBackend 与最小 Docker Sandbox

**Task ID:** `phase-2c-task-3`
**Evidence:** `docs/task-evidence/phase-2c-task-3.md`
**Depends on:** Task 13 accepted
**TDD:** required；Docker smoke 另需用户当前 Task 明确授权

**Files:**

- Create: `src/agent_foundations/execution/__init__.py`
- Create: `src/agent_foundations/execution/models.py`
- Create: `src/agent_foundations/execution/backend.py`
- Create: `src/agent_foundations/execution/fake.py`
- Create: `src/agent_foundations/execution/docker.py`
- Create: `src/agent_foundations/execution/container_runner.py`
- Create: `docker/agent-sandbox.Dockerfile`
- Create: `docker/README.md`
- Create: `tests/unit/execution/__init__.py`
- Create: `tests/unit/execution/test_models.py`
- Create: `tests/unit/execution/test_fake.py`
- Create: `tests/unit/execution/test_docker.py`
- Create: `tests/integration/test_execution_backend.py`

**Stable contract:**

```python
class ExecutionBackend(Protocol):
    async def execute(self, request: ExecutionRequest) -> ExecutionResult: ...
    async def cancel(self, execution_id: str) -> None: ...

class ExecutionRequest(ValidatedCopyModel):
    execution_id: str
    run_id: str
    capability_id: str
    argv: tuple[str, ...]
    cwd: str
    mount_mode: Literal["read_only", "project_write"]
    stdin: bytes = b""
    timeout_seconds: int
    max_output_bytes: int
```

Docker CLI 必须固定生成：`--network none`、`--read-only`、`--cap-drop ALL`、`--security-opt no-new-privileges`、非 root user、pids/memory/cpu 限制和单一 `/workspace` bind mount。禁止挂载 Docker socket、主目录、凭据目录或未解析路径。

- [x] **Step 1: 创建 evidence，运行只读 `docker version` 和 `docker image inspect python:3.12-slim-bookworm`；只记录可用性和 image ID，不自动 pull/build**
- [x] **Step 2: 写 argv 构造、Windows 路径、只读/读写 mount、network none、资源上限、超时、输出截断、取消和 Capability 错配测试**
- [x] **Step 3: 运行 Red（不需要 Docker daemon）**

Run: `conda run -n agent-foundations python -m pytest tests/unit/execution tests/integration/test_execution_backend.py -q`
Expected: Backend/command-builder 行为缺失导致断言失败；FakeBackend 完成确定性测试。

- [x] **Step 4: 实现模型、FakeBackend、Docker argv builder 和异步 DockerBackend；始终 `shell=False`，stderr/stdout 有界收集**
- [x] **Step 5: 若用户明确批准且 base image 已存在或批准拉取，再构建 sandbox image 并运行只读 mount/无网络/非 root smoke；否则 evidence 标记未验证并停止，不得开始 Task 15**

Authorized smoke commands:

```powershell
docker build -f docker/agent-sandbox.Dockerfile -t agent-foundations-sandbox:phase2 .
conda run -n agent-foundations python -m pytest tests/integration/test_execution_backend.py -m docker -q
```

- [x] **Step 6: 运行 Green、Ruff、mypy、`pip check`、diff**
- [ ] **Step 7: reviewer 确认 Sandbox 边界和 Docker smoke 后停止**

**Acceptance:** ExecutionBackend 可替换且不授予权限；Docker 默认无网络、非 root、资源受限、只挂载明确项目；Docker 不可用时 Phase 2C 阻塞而非退回不受限 host execution。
**Suggested commit after explicit authorization:** `feat: add minimal docker execution sandbox`

---

### Task 15：受控 `apply_patch`、回滚与恢复

**Task ID:** `phase-2c-task-4`
**Evidence:** `docs/task-evidence/phase-2c-task-4.md`
**Depends on:** Task 14 accepted with Docker smoke
**TDD:** required

**Files:**

- Create: `src/agent_foundations/tools/patch/apply_patch.py`
- Create: `src/agent_foundations/tools/patch/applier.py`
- Create: `tests/unit/tools/patch/test_applier.py`
- Create: `tests/unit/tools/patch/test_apply_patch.py`
- Create: `tests/integration/test_controlled_patch_flow.py`
- Create: `tests/integration/test_patch_crash_recovery.py`
- Modify: `src/agent_foundations/execution/container_runner.py`
- Modify: `src/agent_foundations/runtime/tool_execution.py`
- Modify: `src/agent_foundations/cli/main.py`

**Tool contract:**

```text
apply_patch(patch_id)
```

`patch_id` 必须属于同一 run 的 `PatchProposalRepository`；调用时重新 strict-resolve 路径并比较当前 SHA-256。执行顺序固定为 Policy → Approval（如需）→ Capability consume → ledger intent → Docker project-write backend → verify → ledger commit。

- [x] **Step 1: 创建 evidence，复制 fixture 到临时目录；不得使用仓库真实文件作为写目标**
- [x] **Step 2: 写 modify/create、多文件 staging、基线漂移、symlink swap、ADS/控制字符、跨 run patch、拒绝/delete、用户 deny、Capability 重放、第二文件失败全量回滚和四个 crash point 测试**

```python
@pytest.mark.asyncio
async def test_apply_patch_rolls_back_all_files_when_second_replace_fails() -> None:
    before = snapshot(project)
    result = await apply_with_injected_failure(project, fail_on_replace=2)
    assert result.success is False
    assert snapshot(project) == before
    assert (await ledger.latest()).status is EffectStatus.ROLLED_BACK
```

- [x] **Step 3: 运行 Red**

Run: `conda run -n agent-foundations python -m pytest tests/unit/tools/patch tests/integration/test_controlled_patch_flow.py tests/integration/test_patch_crash_recovery.py -q`
Expected: apply/rollback/authorization/recovery 行为缺失导致断言失败。

- [x] **Step 4: 实现临时 staging、备份、逐文件 replace、失败逆序回滚和执行后 hash 验证；不支持 delete/rename**
- [x] **Step 5: 将 `apply_patch` 以 `PROJECT_WRITE` metadata 注册，只允许 Sandbox backend；`DirectToolCallExecutor` 不得执行它**
- [x] **Step 6: 运行 Green、Docker integration（已授权环境）、安全回归、Ruff/mypy/diff**
- [x] **Step 7: evidence 记录副作用/回滚/崩溃矩阵并停止**

**Acceptance:** 只有已校验、同 run、同基线 Patch 能写项目；拒绝或失败不留部分修改；已提交/未知副作用遵守 ledger 恢复语义。
**Suggested commit after explicit authorization:** `feat: apply approved patches inside sandbox`

---

### Task 16：Chat/API/UI 权限闭环与 Phase 2C Gate

**Task ID:** `phase-2c-task-5`
**Evidence:** `docs/task-evidence/phase-2c-task-5.md`
**Depends on:** Task 15 accepted
**TDD:** required

**Files:**

- Create: `web/chat/components/PermissionProfileSelect.tsx`
- Create: `web/chat/components/PatchPreviewCard.tsx`
- Create: `tests/chat/permission-profile.test.tsx`
- Create: `tests/chat/patch-preview.test.tsx`
- Modify: `src/agent_foundations/chat/models.py`
- Modify: `src/agent_foundations/chat/schema.py`
- Modify: `src/agent_foundations/chat/repository.py`
- Modify: `src/agent_foundations/chat/api.py`
- Modify: `src/agent_foundations/chat/runner.py`
- Modify: `src/agent_foundations/chat/events.py`
- Modify: `src/agent_foundations/chat/tool_execution.py`
- Modify: `src/agent_foundations/storage/migrations.py`
- Modify: `web/chat/App.tsx`
- Modify: `web/chat/components/ApprovalCard.tsx`
- Modify: `web/chat/state/api.ts`
- Modify: `web/chat/state/events.ts`
- Modify: `web/chat/state/reducer.ts`
- Modify: `web/chat/state/types.ts`
- Modify: `tests/integration/test_chat_api.py`
- Modify: `tests/integration/test_chat_approval_flow.py`
- Modify: `tests/e2e/test_chat_ui.py`

**API/UI contract:**

- Conversation 使用 `permission_profile` + `profile_version`；version 8 migration 把 `PROJECT_READ_ONLY` 保留，把 legacy `ASK_FOR_ACCESS` 转成 `ASK_ALWAYS`。
- Profile 只能在没有 active run/pending authorization 时修改。
- UI 同时展示 Policy decision、资源、操作、Tool、一次性范围和 Sandbox backend；approve/deny 只能一次。
- Patch 卡只展示文件、operation、hunk 数、基线状态和截断摘要，不把完整源码 Diff 写入 SSE。
- `PROJECT_FULL_ACCESS` 必须显示“仅项目能力，不是电脑完全访问”；UI 不出现 `HOST_FULL_ACCESS`。

```python
class Conversation(ChatModel):
    permission_profile: PermissionProfileName
    profile_version: int

class PatchPreviewState(_StrictModel):
    patch_id: str
    files: tuple[PatchFileSummary, ...]
    authorization: AuthorizationRequest | None
```

```typescript
export type PermissionProfile =
  | "PROJECT_READ_ONLY"
  | "ASK_ALWAYS"
  | "RISK_BASED"
  | "PROJECT_FULL_ACCESS"
  | "CUSTOM";
```

- [x] **Step 1: 创建 evidence**
- [x] **Step 2: 写 migration、API shape、profile change conflict、write approval、deny、reload recovery、权限版本变化重新确认和前端可访问性 Red**
- [x] **Step 3: 运行 Red**

Run:

```powershell
conda run -n agent-foundations python -m pytest tests/unit/chat tests/integration/test_chat_api.py tests/integration/test_chat_approval_flow.py tests/e2e/test_chat_ui.py -q
npm run test:chat
```

Expected: 新 profile/Patch authorization/UI 行为缺失导致断言失败；Phase 1 只读流程继续运行。

- [x] **Step 4: 实现 schema/API/Runner 投影和 React 状态；HTTP/SQLite 是恢复事实，SSE 只触发刷新**
- [x] **Step 5: 添加 Eval 任务覆盖四种新 Profile、保留 `PROJECT_READ_ONLY`、权限升级和 write deny/approve；不得开放 Shell/Git**
- [x] **Step 6: 运行 Phase 2C 全量门禁**

Run:

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
```

- [x] **Step 7: reviewer 独立验证 profile/approval/sandbox/rollback；等待用户确认 Phase 2C，未确认不得开始 Task 17**

**Acceptance:** 五个有效 Profile、通用 Approval、Capability、Sandbox 和 Patch 写入形成闭环；刷新恢复不重复副作用；电脑完全访问仍不可选。
**Suggested commit after explicit authorization:** `feat: expose controlled patch authorization in chat`

---

## Phase 2D：受限命令、只读 Git 与反馈闭环

Phase 2D 中任何标记 `Full suite: required` 的 Task，除该 Task 的 Target、Affected regression 和 Additional gates 外，还必须运行以下完整自动化基线，并在 evidence 记录每条命令的本次精确结果：

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

`git status --short` 是范围审计，不要求工作区为空；必须区分当前 Task 修改、用户已有修改和生成物。Docker/image build、真实模型和付费 API 永远不是上述自动化基线的隐式授权，仍按各 Task 单独确认。

### Task 17：命令安全合同、项目 Manifest 与可复现 Sandbox

**Task ID:** `phase-2d-task-1`
**Evidence:** `docs/task-evidence/phase-2d-task-1.md`
**Depends on:** Phase 2C user-accepted
**TDD:** required；构建/运行 image 需用户在当前 Task 另行授权

**Validation contract:**

- Target tests: `conda run -n agent-foundations python -m pytest tests/unit/tools/command tests/unit/execution/test_workspace.py tests/unit/execution/test_sandbox_manifest.py -q`
- Affected regression tests: `conda run -n agent-foundations python -m pytest tests/unit/security tests/unit/execution tests/integration/test_execution_backend.py -q`
- Full suite: `not-required`
- Full suite reason: 本 Task 只建立数据合同、filtered snapshot 和固定 image，不向 Agent 注册命令 Tool；权限尚未扩大。
- Additional gates: 经单独授权的 Python/Node image build 与无网络、非 root、只读输入、资源限制 smoke；未授权时必须报告 `not-run`，不得回退 host execution。

**Files:**

- Create: `src/agent_foundations/tools/command/__init__.py`
- Create: `src/agent_foundations/tools/command/models.py`
- Create: `src/agent_foundations/tools/command/classifier.py`
- Create: `src/agent_foundations/tools/command/config.py`
- Create: `src/agent_foundations/execution/workspace.py`
- Create: `src/agent_foundations/execution/sandbox_manifest.py`
- Rename: `docker/agent-sandbox.Dockerfile` to `docker/agent-sandbox-python.Dockerfile`
- Create: `docker/agent-sandbox-node.Dockerfile`
- Create: `tests/unit/tools/command/__init__.py`
- Create: `tests/unit/tools/command/test_models.py`
- Create: `tests/unit/tools/command/test_classifier.py`
- Create: `tests/unit/execution/test_workspace.py`
- Create: `tests/unit/execution/test_sandbox_manifest.py`
- Modify: `src/agent_foundations/execution/models.py`
- Modify: `src/agent_foundations/execution/docker.py`
- Modify: `docker/README.md`
- Modify: `pyproject.toml`

**Stable contract:**

```python
class CommandCategory(StrEnum):
    TEST = "test"
    LINT = "lint"
    TYPECHECK = "typecheck"
    BUILD = "build"
    PACKAGE_CHECK = "package_check"
    DENIED = "denied"
    UNKNOWN = "unknown"

class CommandSpec(ValidatedCopyModel):
    argv: tuple[str, ...]
    cwd: str = "."
    timeout_seconds: int = Field(ge=1, le=300)

class CommandClassifier:
    def classify(self, spec: CommandSpec, manifest: ProjectCommandManifest) -> CommandClassification: ...

class ProjectCommandManifest(ValidatedCopyModel):
    schema_version: Literal[1]
    project_fingerprint: str
    gates: tuple[CommandGate, ...]
    sandbox: SandboxManifest

class CommandClassification(ValidatedCopyModel):
    category: CommandCategory
    rule_id: str
    normalized_argv: tuple[str, ...]
    sandbox_profile: Literal["python", "node"]
    hard_denied: bool
```

Phase 2 只承诺本仓库 manifest 中固定、参数化收窄后的 gates：

- `python -m pytest <project-relative targets>`
- `python -m ruff check <project-relative targets>`
- `python -m mypy <project-relative targets>`
- `python -m pip check`
- `npm run test:viewer|typecheck:viewer|test:chat|typecheck:chat|build:chat`

拒绝 shell 字符串、`shell=True`、pipeline/redirection、PowerShell/Bash/cmd、`python -c`、包安装、下载器、解释器脚本路径、Git、网络工具和项目外 cwd。Classifier 只做 category、normalization 和 hard-deny，不替代 Policy；未 hard-deny 的命令仍必须由 Policy 根据 Permission Profile 决定 allow/ask/deny。

Sandbox 使用两个固定、可复现 image。Python image 只包含锁定的 Python 3.12 与本仓库 gates 所需依赖；Node image 只包含锁定的 Node/npm 与本仓库固定 scripts。构建时记录 base image digest、lockfile fingerprint 和最终 image ID；运行时 `--network=none`、非 root、drop capabilities、no-new-privileges、只读 rootfs、CPU/内存/PID/时间限制。不得把 host conda、venv、`node_modules` 或凭据挂进容器。

Filtered workspace snapshot 必须在 host controller 侧按 PathPolicy 创建，只复制 regular file；默认排除 `.git`、`.env*`、凭据/私钥、symlink/reparse point、依赖目录、cache、build output、日志、数据库和 Artifact。输入 snapshot 只读挂载为 `/project-ro`，容器内 `/workspace` 是短生命周期可写副本，退出后丢弃。

- [x] **Step 1: 创建 evidence，记录 Phase 2C 用户验收、pre-change Git 状态和本机 Docker/image 可用性；不得自动 pull/build**
- [x] **Step 2: 写 Manifest/model/classifier Red，覆盖 allowlist 正例、参数收窄、空 argv、绝对 cwd、`..`、ADS/控制字符、shell metacharacter、package install、网络、Git、未知命令和 project fingerprint 漂移**

```python
@pytest.mark.parametrize("argv", [
    ("pwsh", "-Command", "Get-ChildItem"),
    ("python", "-m", "pip", "install", "x"),
    ("curl", "https://example.invalid"),
    ("git", "status"),
])
def test_classifier_hard_denies_commands_outside_coding_allowlist(argv: tuple[str, ...]) -> None:
    assert classifier.classify(CommandSpec(argv=argv), manifest).hard_denied is True
```

- [x] **Step 3: 运行 classifier Red**

Run: `conda run -n agent-foundations python -m pytest tests/unit/tools/command -q`
Expected: CommandSpec/classifier 行为缺失导致 assertion failure。

- [x] **Step 4: 实现纯模型、manifest fingerprint、路径参数校验和 exact-prefix 分类；输出 rule ID、category、normalized argv、Sandbox profile 和 hard-deny，UNKNOWN 默认 hard-deny**
- [x] **Step 5: 写 workspace/Sandbox Red，覆盖 `.env`、私钥、`.git`、cache/build、数据库、symlink/reparse point、snapshot race、只读输入、ephemeral 写层和 image digest 不匹配**

Run: `conda run -n agent-foundations python -m pytest tests/unit/execution/test_workspace.py tests/unit/execution/test_sandbox_manifest.py -q`
Expected: filtered snapshot、manifest/image pinning 或 mount 合同缺失导致 assertion failure。

- [x] **Step 6: 实现 filtered snapshot、SandboxManifest 和 Python/Node Dockerfile；不实现 `run_command`，不向 ToolRegistry 注册命令能力**
- [x] **Step 7: 运行 Target、Affected regression、Ruff、mypy、`git diff --check`；若已获授权，再运行 image build/smoke 并记录 digest，不得通过 host subprocess 替代**
- [x] **Step 8: evidence 附命令矩阵、排除矩阵、image provenance 和未运行项并停止**

**Acceptance:** 模型只能表达 manifest 中结构化 argv；Classifier 默认 hard-deny 且与 Policy 分离；snapshot 不携带敏感/宿主状态；Sandbox 可复现、无网络、非 root、资源受限；尚不存在命令执行 Tool。
**User acceptance:** 2026-08-26 用户确认 `Task 17 验收通过`；planner 记录于本计划与 `docs/task-evidence/phase-2d-task-1.md` §15。满足 Task 18 前置依赖 `Task 17 accepted`。
**Suggested commit after explicit authorization:** `feat: define reproducible command sandboxes`

---

### Task 18：`run_command`、Durable 生命周期与 Command Output Artifact

**Task ID:** `phase-2d-task-2`
**Evidence:** `docs/task-evidence/phase-2d-task-2.md`
**Depends on:** Task 17 accepted
**TDD:** required；运行 image 需用户当前 Task 明确授权

**Validation contract:**

- Target tests: `conda run -n agent-foundations python -m pytest tests/unit/tools/command/test_run_command.py tests/unit/command_output tests/integration/test_run_command_flow.py tests/integration/test_run_command_cancellation.py tests/integration/test_command_artifact_lifecycle.py -q`
- Affected regression tests: `conda run -n agent-foundations python -m pytest tests/unit/security tests/unit/durable tests/unit/execution tests/unit/runtime/test_tool_execution.py tests/integration/test_idempotent_tool_execution.py -q`
- Full suite: `required`
- Full suite reason: 本 Task 首次扩大到命令副作用，并修改 shared migration、durable ledger、ExecutionBackend 和 Tool executor。
- Additional gates: 经授权 Docker command lifecycle；Artifact ACL/permission probe；容量、淘汰和 crash-point matrix；禁止真实模型、网络、包安装和 host fallback。

**Files:**

- Create: `src/agent_foundations/tools/command/run_command.py`
- Create: `src/agent_foundations/command_output/__init__.py`
- Create: `src/agent_foundations/command_output/models.py`
- Create: `src/agent_foundations/command_output/store.py`
- Create: `src/agent_foundations/command_output/repository.py`
- Create: `src/agent_foundations/command_output/retention.py`
- Create: `src/agent_foundations/command_output/permissions.py`
- Create: `tests/unit/tools/command/test_run_command.py`
- Create: `tests/unit/command_output/__init__.py`
- Create: `tests/unit/command_output/test_models.py`
- Create: `tests/unit/command_output/test_store.py`
- Create: `tests/unit/command_output/test_repository.py`
- Create: `tests/unit/command_output/test_retention.py`
- Create: `tests/integration/test_run_command_flow.py`
- Create: `tests/integration/test_run_command_cancellation.py`
- Create: `tests/integration/test_command_artifact_lifecycle.py`
- Modify: `src/agent_foundations/execution/models.py`
- Modify: `src/agent_foundations/execution/docker.py`
- Modify: `src/agent_foundations/execution/container_runner.py`
- Modify: `src/agent_foundations/durable/effects.py`
- Modify: `src/agent_foundations/runtime/tool_execution.py`
- Modify: `src/agent_foundations/cli/main.py`
- Modify: `src/agent_foundations/storage/migrations.py`
- Modify: `tests/unit/storage/test_database.py`

**Tool contract:**

```python
class CommandArtifactMetadata(ValidatedCopyModel):
    artifact_id: str
    run_id: UUID
    effect_id: UUID
    execution_id: UUID
    stdout_bytes: int
    stderr_bytes: int
    sha256: str
    created_at: datetime
    retention_status: RetentionStatus
    parser_status: ParserStatus

class RetentionStatus(StrEnum):
    ACTIVE = "active"
    RETAINED = "retained"
    PENDING_DELETE = "pending_delete"
    DELETED = "deleted"
    DELETE_FAILED = "delete_failed"
    EVICTED = "evicted"

class ParserStatus(StrEnum):
    PENDING = "pending"
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"

class RunCommandRequest(ValidatedCopyModel):
    argv: tuple[str, ...]
    cwd: str = "."
    timeout_seconds: int = Field(default=120, ge=1, le=300)
```

Artifact root 默认固定为 `%LOCALAPPDATA%\AgentFoundations\command-output`，配置必须拒绝项目目录、Git worktree、相对路径和 symlink/reparse-point root。`artifact_id` 固定为 `coa_` 加 128-bit CSPRNG 的 base64url 无 padding 编码，并按完整正则校验；它只映射到 store 内部 exact directory，Agent、API 和前端不得提交任意本地路径。stdout/stderr 保持两个 stream，分别原子写入临时文件并 `flush`/`fsync` 后 rename；metadata 只在文件 durable 后写入 SQLite v9。`sha256` 对 `stream-name + 8-byte length + raw bytes` 的 stdout/stderr canonical framing 计算。文件权限限制为当前本机用户：Windows 使用 stdlib `ctypes` 调用系统安全 API设置/验证 owner-only DACL，不调用 shell；POSIX 使用 `0700` directory 与 `0600` file，并在写入后复验。

固定默认值：单 execution 的 stdout+stderr 原始输出上限 `64 MiB`；全局容量 `1 GiB`；保留 `7 days`。启动前按单文件上限预留容量；容量不足时先按创建时间淘汰最旧的 completed Artifact，不删除 active Artifact；仍无法预留则在命令启动前返回 `ARTIFACT_CAPACITY_EXCEEDED`。达到单 execution 上限必须终止容器、保留已产生内容并返回 `OUTPUT_LIMIT_EXCEEDED`/`output_truncated=true`，不得静默截断后继续执行。

删除 run/conversation 时先在 transaction 中把精确 Artifact 标记 `pending_delete`，sweeper 只按数据库返回的 `artifact_id` 删除；成功改为 `deleted`，失败改为 `delete_failed`，不得影响其他 run。Artifact directory 不得进入 Git；原始内容不得复制进 SQLite JSON、JSONL Trace、Chat JSON、SSE 或默认模型上下文。

执行顺序固定为：Classifier → Policy → Approval（如需）→ one-use Capability → side-effect ledger intent → Artifact quota reservation → ephemeral Sandbox → streaming stdout/stderr → atomic Artifact finalize → execution outcome/metadata transaction → ledger terminal state。命令实际结束但 Artifact finalize 失败时，ledger 必须记录真实 command outcome，Tool 返回 `OUTPUT_ARTIFACT_WRITE_FAILED`，不得自动重跑命令；重启恢复也不得重复已启动或 outcome 未知的 effect。

- [x] **Step 1: 创建 evidence，记录 Task 17 验收、pre-change Git 状态、Artifact root 和 Docker/image 可用性；不读取 `.env`，不自动运行 image**
- [x] **Step 2: 写 Artifact/SQLite v9 Red，覆盖 opaque ID、路径穿越/绝对路径/ADS/控制字符、原子写、两个 stream、hash/byte count、current-user permission、root 边界、64 MiB/1 GiB/7 days、quota reservation、淘汰、pending delete、跨 run 不误删和数据库不含 raw bytes**

```python
def test_artifact_repository_persists_metadata_not_output(
    artifact_store: CommandArtifactStore,
    database: Database,
) -> None:
    artifact = artifact_store.write(stdout=b"fixture-secret", stderr=b"failure")
    row = database.fetch_artifact(artifact.artifact_id)
    assert row.stdout_bytes == len(b"fixture-secret")
    assert b"fixture-secret" not in database.path.read_bytes()
```

- [x] **Step 3: 运行 Artifact Red**

Run: `conda run -n agent-foundations python -m pytest tests/unit/command_output tests/unit/storage/test_database.py tests/integration/test_command_artifact_lifecycle.py -q`
Expected: Artifact store、v9 metadata、quota/retention 行为缺失导致 assertion failure。

- [x] **Step 4: 实现 Artifact store、permission checks、v9 repository 和 retention sweeper；`parser_status` 初始为 `pending`，不得实现 Parser 或 Agent 读取**
- [x] **Step 5: 写 `run_command` Red，覆盖 Policy ask/allow/deny、Capability 绑定、ephemeral copy、非零退出码、超时、取消进程树、64 MiB 终止、stdout/stderr 并发、Artifact finalize failure、ledger crash points 和重启不重复执行**

```python
@pytest.mark.asyncio
async def test_run_command_discards_workspace_writes() -> None:
    result = await run_allowed_test_that_creates_cache(project)
    assert result.exit_code == 0
    assert not (project / ".pytest_cache").exists()
```

- [x] **Step 6: 运行 `run_command` Red（FakeBackend）**

Run: `conda run -n agent-foundations python -m pytest tests/unit/tools/command/test_run_command.py tests/integration/test_run_command_flow.py tests/integration/test_run_command_cancellation.py -q`
Expected: run_command、streaming Artifact 和 durable lifecycle 行为缺失导致 assertion failure。

- [x] **Step 7: 把 `ContainerRunner` 从 bounded in-memory capture 改为 controller 侧 streaming Artifact sink，并实现上述固定执行顺序；不得把 raw output 放进 Tool result**
- [x] **Step 8: 运行 Target、Affected regression、完整 Phase 1 基线、Ruff、mypy、pip check、前端 gates 和 `git diff --check`；若获授权再运行 Docker lifecycle，失败不得回退 host subprocess**
- [x] **Step 9: evidence 记录每种 command/effect/artifact 终止状态、migration、容量和泄漏扫描并停止**

**Acceptance:** 受限命令只在固定 Sandbox 运行；完整原始输出只存在受控本地产物；metadata、hash、quota、retention 和 durable effect 一致；输出或 Artifact 失败不会伪造成功或触发重复执行；默认模型上下文仍得不到原始日志。
**User acceptance:** 2026-08-26 用户确认 `确认验收通过`；记录于本计划与 `docs/task-evidence/phase-2d-task-2.md` §9。满足 Task 19 前置依赖 `Task 18 accepted`。Task 19 仍需单独 executor 授权，未授权不得开始。
**Suggested commit after explicit authorization:** `feat: persist sandbox command artifacts safely`

---

### Task 19：Tool-specific Parser 与统一 `CommandFeedback`

**Task ID:** `phase-2d-task-3`
**Evidence:** `docs/task-evidence/phase-2d-task-3.md`
**Depends on:** Task 18 accepted
**TDD:** required

**Validation contract:**

- Target tests: `conda run -n agent-foundations python -m pytest tests/unit/command_output/test_sanitize.py tests/unit/command_output/test_feedback.py tests/unit/command_output/parsers -q`
- Affected regression tests: `conda run -n agent-foundations python -m pytest tests/unit/tools/command tests/integration/test_run_command_flow.py tests/integration/test_command_artifact_lifecycle.py -q`
- Full suite: `not-required`
- Full suite reason: 本 Task 只把既有 Artifact 投影为确定性、脱敏反馈，不注册新 Tool、不扩大权限、不修改全局控制协议。
- Additional gates: fixture corpus completeness、known-secret leakage scan、parser mutation/fuzz cases；不得调用真实模型总结日志。

**Files:**

- Create: `src/agent_foundations/command_output/sanitize.py`
- Create: `src/agent_foundations/command_output/feedback.py`
- Create: `src/agent_foundations/command_output/parsers/__init__.py`
- Create: `src/agent_foundations/command_output/parsers/base.py`
- Create: `src/agent_foundations/command_output/parsers/pytest.py`
- Create: `src/agent_foundations/command_output/parsers/ruff.py`
- Create: `src/agent_foundations/command_output/parsers/mypy.py`
- Create: `src/agent_foundations/command_output/parsers/vitest.py`
- Create: `src/agent_foundations/command_output/parsers/typescript.py`
- Create: `src/agent_foundations/command_output/parsers/build.py`
- Create: `src/agent_foundations/command_output/parsers/registry.py`
- Create: `tests/unit/command_output/test_sanitize.py`
- Create: `tests/unit/command_output/test_feedback.py`
- Create: `tests/unit/command_output/parsers/__init__.py`
- Create: `tests/unit/command_output/parsers/test_pytest.py`
- Create: `tests/unit/command_output/parsers/test_ruff.py`
- Create: `tests/unit/command_output/parsers/test_mypy.py`
- Create: `tests/unit/command_output/parsers/test_vitest.py`
- Create: `tests/unit/command_output/parsers/test_typescript.py`
- Create: `tests/unit/command_output/parsers/test_build.py`
- Create: `tests/fixtures/command-output/pytest/`
- Create: `tests/fixtures/command-output/ruff/`
- Create: `tests/fixtures/command-output/mypy/`
- Create: `tests/fixtures/command-output/vitest/`
- Create: `tests/fixtures/command-output/typescript/`
- Create: `tests/fixtures/command-output/build/`
- Modify: `src/agent_foundations/command_output/models.py`
- Modify: `src/agent_foundations/command_output/repository.py`

**Stable contract:**

```python
class Diagnostic(ValidatedCopyModel):
    diagnostic_id: str
    severity: DiagnosticSeverity
    tool: str
    file: str | None = None
    line: int | None = None
    column: int | None = None
    test_id: str | None = None
    error_type: str | None = None
    error_code: str | None = None
    message: str
    expected: str | None = None
    actual: str | None = None
    context: tuple[str, ...] = ()

class CommandFeedback(ValidatedCopyModel):
    command_category: CommandCategory
    argv_display: tuple[str, ...]
    cwd: str
    exit_code: int | None
    timed_out: bool
    cancelled: bool
    output_truncated: bool
    passed: int | None
    failed: int | None
    skipped: int | None
    diagnostics: tuple[Diagnostic, ...]
    repeated_diagnostics: int
    parser_status: Literal["complete", "partial", "failed"]
    unparsed_bytes: int
    unparsed_reason: str | None
    recommended_ranges: tuple[OutputRange, ...]
    artifact_id: str
    stdout_bytes: int
    stderr_bytes: int
    raw_sha256: str
```

处理顺序不得改变：完整 stdout/stderr → 保持两个 stream → UTF-8 replacement decode → 统一换行 → 删除 ANSI/终端控制字符 → Redactor 脱敏 → Tool-specific Parser → 去重、排序、关联有界上下文 → `CommandFeedback` → Agent。原始 bytes 始终保留在 Artifact；sanitized intermediate 不落入 SQLite JSON、Trace、Chat JSON 或 SSE。

首批 Parser 固定为 `PytestOutputParser`、`RuffOutputParser`、`MypyOutputParser`、`VitestOutputParser`、`TypeScriptOutputParser`、`BuildOutputParser`。能够使用原生 JSON/machine-readable 输出时，由可信 harness 根据 manifest 注入固定 reporter/format 参数，Agent 不得控制这些参数；否则使用 fixture 驱动的确定性文本 Parser。

diagnostics 排序固定为：启动/环境/依赖缺失 → collection/语法/编译/import → 最可能根因 → 普通测试失败 → 连锁失败 → warning/重复。保留全部失败 test ID；相同 fingerprint 的重复堆栈可以折叠并计数。Parser 不得猜测完整性：任何未覆盖 bytes、未知版本/格式或冲突 summary 必须返回 `partial`/`failed`、`unparsed_bytes`、原因和推荐读取范围；即使 Parser 失败，也必须保留真实 exit code、timeout/cancel/output-limit 状态。

- [x] **Step 1: 创建 evidence；fixture 只能使用虚构凭据占位符，不读取真实 `.env` 或本机日志**
- [x] **Step 2: 写 sanitize/feedback Red，覆盖两个 stream、非法 UTF-8、CRLF/CR、ANSI/OSC/控制字符、无换行、二进制、超长行、Token/Cookie/private-key/.env 形态、稳定 fingerprint、bounded context 和错误排序**
- [x] **Step 3: 运行 sanitize/feedback Red**

Run: `conda run -n agent-foundations python -m pytest tests/unit/command_output/test_sanitize.py tests/unit/command_output/test_feedback.py -q`
Expected: deterministic sanitation、diagnostic 排序或 Feedback 合同缺失导致 assertion failure。

- [x] **Step 4: 实现严格顺序的 decode/normalize/control-strip/redact 管线、bounded context、dedupe/sort 和 `CommandFeedback` builder；不得调用模型**
- [x] **Step 5: 为六类工具分别写 machine-readable 与文本 fixture Red，覆盖 pass/fail/skip、collection/compile/import、expected/actual、重复堆栈、未知版本、截断、无 summary、矛盾 exit/summary、partial/failed 和全部失败 test ID 保留**
- [x] **Step 6: 运行 Parser Red**

Run: `conda run -n agent-foundations python -m pytest tests/unit/command_output/parsers -q`
Expected: 六个 Parser、registry 或 completeness 判定缺失导致 assertion failure。

- [x] **Step 7: 实现六个 Parser 和可信 harness format injection；更新 Artifact metadata 的 parser status，但不得把 `CommandFeedback` JSON 持久化进 SQLite**
- [x] **Step 8: 运行 Target、Affected regression、fixture leakage scan、Ruff、mypy 和 `git diff --check`**
- [x] **Step 9: evidence 记录每个 Parser 的 supported format/version、完整/部分/失败 fixture matrix 和未解析原因并停止**

**Acceptance:** Agent 默认只获得确定性、脱敏、可审计的 `CommandFeedback`；六类 gates 的失败事实和全部失败 test ID 可用；Parser 对不确定性显式降级，绝不把 partial/failed 当作完整事实。
**User acceptance:** 2026-08-26 用户确认 `确认 Task 19 用户验收通过`；记录于本计划与 `docs/task-evidence/phase-2d-task-3.md` §9。满足 Task 20 前置依赖 `Task 19 accepted`。Task 20 仍需单独 executor 授权，未授权不得开始。
**Suggested commit after explicit authorization:** `feat: structure sandbox command feedback`

---

### Task 20：受限 Artifact 读取与 Chat/API/UI 生产闭环

**Task ID:** `phase-2d-task-4`
**Evidence:** `docs/task-evidence/phase-2d-task-4.md`
**Depends on:** Task 19 accepted
**TDD:** required

**Validation contract:**

- Target tests: `conda run -n agent-foundations python -m pytest tests/unit/command_output/test_access.py tests/unit/tools/command/test_output_tools.py tests/integration/test_command_output_access.py tests/integration/test_command_output_api.py tests/integration/test_command_feedback_agent_flow.py tests/e2e/test_chat_ui.py -q` and `npm run test:chat`
- Affected regression tests: `conda run -n agent-foundations python -m pytest tests/unit/chat tests/unit/security tests/unit/runtime tests/integration/test_chat_api.py tests/integration/test_chat_approval_flow.py tests/integration/test_run_command_flow.py -q`
- Full suite: `required`
- Full suite reason: 本 Task 把命令、结构化反馈和受限日志读取正式接入 AgentLoop/Chat，并新增 Capability 与本机 raw download 安全面。
- Additional gates: `npm run typecheck:chat`、`npm run build:chat`、Playwright UI、Artifact attack/leakage matrix、FakeModel correction E2E；不得调用真实模型。

**Files:**

- Create: `src/agent_foundations/command_output/access.py`
- Create: `src/agent_foundations/command_output/audit.py`
- Create: `src/agent_foundations/tools/command/read_output.py`
- Create: `src/agent_foundations/tools/command/search_output.py`
- Create: `web/chat/components/CommandFeedbackCard.tsx`
- Create: `tests/unit/command_output/test_access.py`
- Create: `tests/unit/tools/command/test_output_tools.py`
- Create: `tests/integration/test_command_output_access.py`
- Create: `tests/integration/test_command_output_api.py`
- Create: `tests/integration/test_command_feedback_agent_flow.py`
- Create: `tests/chat/command-feedback.test.tsx`
- Modify: `src/agent_foundations/command_output/repository.py`
- Modify: `src/agent_foundations/storage/migrations.py`
- Modify: `src/agent_foundations/runtime/tool_execution.py`
- Modify: `src/agent_foundations/runtime/loop.py`
- Modify: `src/agent_foundations/chat/models.py`
- Modify: `src/agent_foundations/chat/repository.py`
- Modify: `src/agent_foundations/chat/events.py`
- Modify: `src/agent_foundations/chat/tool_execution.py`
- Modify: `src/agent_foundations/chat/runner.py`
- Modify: `src/agent_foundations/chat/api.py`
- Modify: `src/agent_foundations/cli/main.py`
- Modify: `web/chat/state/types.ts`
- Modify: `web/chat/state/api.ts`
- Modify: `web/chat/state/reducer.ts`
- Modify: `web/chat/components/ToolActivityGroup.tsx`
- Modify: `web/chat/App.tsx`
- Modify: `tests/unit/storage/test_database.py`
- Modify: `tests/integration/test_chat_api.py`
- Modify: `tests/e2e/test_chat_ui.py`

**Tool contracts:**

```python
read_command_output(
    artifact_id: str,
    selector: StartLineSelector | AroundDiagnosticSelector | TailSelector,
    reason: str,
) -> SanitizedOutputPage

search_command_output(
    artifact_id: str,
    query: str,
    reason: str,
) -> SanitizedSearchResult
```

selector 只能是三种互斥结构：`start_line + line_count`、`around_diagnostic_id`、`stream + tail_lines`。不得接收路径、byte offset、glob、regex 或任意 SQL。单次最多 `200 lines / 64 KiB`；同一 run 累计最多 `1,000 lines / 256 KiB`；search 最多返回 `50` 个命中。读取前后都验证 artifact 属于当前 conversation/current run/current effect，Artifact 状态可读，Capability 精确绑定 run+artifact+selector 且一次性消费；跨 run、跨 conversation、跨 artifact replay 一律 hard-deny。

每次从原始 Artifact 读取后必须重新执行 Task 19 的 decode/control-strip/redact，再把 bounded sanitized content 返回模型。SQLite v10 的 `command_output_reads` 只记录 run_id、artifact_id、selector/range、reason、returned byte/line count、decision、created_at；Trace 只记录 artifact_id、区段、原因、计数和结果，不复制内容。Agent 在 `parser_status != complete` 时收到显式 warning；如果一次有界读取仍不足，Prompt policy 要求优先运行更精确的失败 test node ID，而不是无限读取。

Chat/API 默认只投影 command status、safe argv、cwd、exit code、关键 diagnostics、stdout/stderr 大小、output_truncated、parser status 和 artifact_id。`Show sanitized output` 通过有界分页 endpoint 展示脱敏内容；UI 展开不产生 Agent Tool call、不消耗 Agent budget、不改变上下文或授权。

`Download raw output` 只允许本机用户显式点击：先 POST 创建短时、一次性、conversation/run/artifact 绑定的 download ticket，再由浏览器导航下载；校验 loopback bind、Origin/CSRF、ticket expiry/consume 和 exact artifact ownership。raw download 不注册进 ToolRegistry，不通过 JSON/SSE 返回，不被前端预取，Agent 永远不能获得 ticket 或原始文件路径。

- [x] **Step 1: 创建 evidence，记录 Artifact 配额默认值、Task 19 parser matrix 和 pre-change Registry/API/UI shape**
- [x] **Step 2: 写 access/audit/Tool Red，覆盖四种 selector/search、预算边界、二次脱敏、partial warning、reason 必填、无路径输入、malformed/绝对/ADS/控制字符 ID、跨 run/conversation/artifact、Capability replay、deleted/pending Artifact 和 Trace/SQLite 不含内容**

```python
@pytest.mark.asyncio
async def test_read_command_output_rejects_cross_run_artifact() -> None:
    result = await output_tool.execute(
        current_run_id=run_b.id,
        artifact_id=artifact_from_run_a.artifact_id,
        selector={"stream": "stderr", "tail_lines": 20},
        reason="inspect parser gap",
    )
    assert result.error_code == "ARTIFACT_SCOPE_DENIED"
    assert "fixture-secret" not in trace_path.read_text(encoding="utf-8")
```

- [x] **Step 3: 运行 access Red**

Run: `conda run -n agent-foundations python -m pytest tests/unit/command_output/test_access.py tests/unit/tools/command/test_output_tools.py tests/integration/test_command_output_access.py -q`
Expected: scoped access、budget、re-redaction、v10 audit 或 Tool 合同缺失导致 assertion failure。

- [x] **Step 4: 实现 access service、预算账本、v10 audit 和两个 Tool；Capability 逐次精确绑定，返回前强制重新脱敏**
- [x] **Step 5: 写 API/UI/raw-download Red，覆盖默认折叠 summary、sanitized pagination、UI 展开不改变 Agent、ticket origin/expiry/replay/ownership、无自动 raw fetch、刷新恢复和 390×844 无横向溢出**
- [x] **Step 6: 运行 API/UI Red**

Run:

```powershell
conda run -n agent-foundations python -m pytest tests/integration/test_command_output_api.py tests/e2e/test_chat_ui.py -q
npm run test:chat
```

Expected: Feedback projection、sanitized pagination、raw download ticket 或前端展示缺失导致目标 assertion failure。

- [x] **Step 7: 实现 AgentLoop/Chat/API/UI 接线；默认模型只接收 `CommandFeedback`，UI 默认隐藏日志，raw download 保持本机用户专用**
- [x] **Step 8: 写 FakeModel correction E2E Red：全量 gate 失败 → 从 Feedback 找根因 → 只运行失败 node ID → `apply_patch` → 定向 Green → 受影响回归 Green；断言没有 raw output 进入模型、SQLite JSON、Trace、Chat JSON 或 SSE**
- [x] **Step 9: 实现完成该 E2E 所需的最小生产接线；不得在本 Task 新增 Parser、Git、Repo Map 或 compaction 能力**
- [x] **Step 10: 运行 Target、Affected regression、完整 Phase 1 基线、Chat gates、Playwright、Artifact attack/leakage matrix、Ruff、mypy、pip check 和 `git diff --check`**
- [x] **Step 11: evidence 记录 Tool/API/UI projection、Agent/UI budget 隔离、download ticket 安全矩阵和 FakeModel correction trace 并停止**

**Acceptance:** Agent 先靠结构化反馈纠错，只有信息不足时才能在同 run 内读取有界、再次脱敏的片段；UI 可独立查看 sanitized pages 或由本机用户显式下载 raw 文件，但两者都不改变 Agent 上下文或权限；敏感原始输出不会进入控制面 JSON/Trace/SSE。
**User acceptance:** 2026-08-26 用户确认 `确认 Task 20 用户验收通过`；记录于本计划与 `docs/task-evidence/phase-2d-task-4.md` §9。满足 Task 21 前置依赖 `Task 20 accepted`。Task 21 仍需单独 executor 授权，未授权不得开始。当前实现已独立复验通过；TDD 历史 Red 原文仍为 unavailable，不因本次验收补造。
**Suggested commit after explicit authorization:** `feat: expose bounded command feedback safely`

---

### Task 21：结构化只读 Git Tool

**Task ID:** `phase-2d-task-5`
**Evidence:** `docs/task-evidence/phase-2d-task-5.md`
**Depends on:** Task 20 accepted
**TDD:** required

**Validation contract:**

- Target tests: `conda run -n agent-foundations python -m pytest tests/unit/tools/git tests/integration/test_git_read_tools.py -q`
- Affected regression tests: `conda run -n agent-foundations python -m pytest tests/unit/security tests/unit/execution tests/unit/runtime/test_tool_execution.py tests/integration/test_command_feedback_agent_flow.py -q`
- Full suite: `required`
- Full suite reason: 本 Task 首次向 Agent 注册 Git repository read capability，属于 Tool 权限扩大。
- Additional gates: 临时仓库 mutation audit、sensitive diff leakage scan、Sandbox read-only smoke；不得运行当前真实仓库的变更型 Git 命令。

**Files:**

- Create: `src/agent_foundations/tools/git/__init__.py`
- Create: `src/agent_foundations/tools/git/models.py`
- Create: `src/agent_foundations/tools/git/service.py`
- Create: `src/agent_foundations/tools/git/status.py`
- Create: `src/agent_foundations/tools/git/diff.py`
- Create: `src/agent_foundations/tools/git/log.py`
- Create: `tests/unit/tools/git/__init__.py`
- Create: `tests/unit/tools/git/test_models.py`
- Create: `tests/unit/tools/git/test_service.py`
- Create: `tests/unit/tools/git/test_tools.py`
- Create: `tests/integration/test_git_read_tools.py`
- Modify: `src/agent_foundations/runtime/tool_execution.py`
- Modify: `src/agent_foundations/cli/main.py`

**Tool contracts:**

```text
git_status()
git_diff(path=null, staged=false, max_bytes=200000)
git_log(limit=20)
```

Model 不提供任意 Git 参数、ref、format、config 或 command。Service 固定 argv，统一加 `--no-pager`、`--no-ext-diff`、`--no-textconv`，并使用 `GIT_OPTIONAL_LOCKS=0`、`GIT_TERMINAL_PROMPT=0`、`GIT_CONFIG_NOSYSTEM=1`；为 HOME、XDG_CONFIG_HOME 和 global config 创建空的隔离目录，禁止读取用户/系统 alias、pager、filter、credential helper 和 hook 配置。

三个 Tool 通过 Sandbox read-only backend 执行，不进入 `run_command` manifest。Repository mount 只读；metadata 固定 `side_effect=NONE`、project repository、read。`git_diff` 的 path 只能是 strict-resolved project-relative regular file；敏感路径直接拒绝，输出再次脱敏和 bounded。不存在 add/commit/push/reset/checkout/clean/restore/rebase/merge/submodule update 或 arbitrary object read API。

- [x] **Step 1: 创建 evidence；所有 Git 测试使用临时仓库，并记录当前真实仓库 pre-test status 供 mutation audit**
- [x] **Step 2: 写 status/diff/log shape、untracked/staged、路径校验、输出上限、非仓库、malicious config/alias/pager/filter/textconv、submodule、sensitive path、symlink、禁止任意 ref/参数和不存在 write API 的 Red**
- [x] **Step 3: 运行 Red**

Run: `conda run -n agent-foundations python -m pytest tests/unit/tools/git tests/integration/test_git_read_tools.py -q`
Expected: Git model/service/Tool 或配置隔离行为缺失导致 assertion failure。

- [x] **Step 4: 实现固定 argv、隔离配置和 structured result 的 GitReadService；通过 read-only Sandbox 执行并复用 Redactor，不调用 shell**
- [x] **Step 5: 注册三个 read-only Tool 和 metadata；确认 `run_command` classifier 仍 hard-deny `git`，Registry 不存在任何 Git write Tool**
- [x] **Step 6: 运行 Target、Affected regression、完整 Phase 1 基线、Sandbox smoke、Ruff、mypy、pip check、前端 gates 和 `git diff --check`**
- [x] **Step 7: 对比真实仓库 pre/post status，evidence 记录固定 argv、config isolation、敏感路径和 mutation matrix 后停止**

**Acceptance:** Agent 能读取有限、结构化、脱敏的 Git status/diff/log；不能注入 Git 参数或宿主配置，不能写 index/worktree/remote，也不能借 `run_command` 绕过。
**User acceptance:** 2026-08-26 用户确认 `确认 Task 21 用户验收通过`；记录于本计划与 `docs/task-evidence/phase-2d-task-5.md` §9。满足 Task 22 前置依赖 `Task 21 accepted`。Task 22 仍需单独 executor 授权，未授权不得开始。当前实现已独立复验通过；TDD 过程证据为 complete，本次验收接受当前行为，不把 reviewer 复验当作独立见证的历史 Red→Green。
**Suggested commit after explicit authorization:** `feat: add isolated read-only git tools`

---

### Task 22：Repo Map、相关性与确定性 Context Selection

**Task ID:** `phase-2d-task-6`
**Evidence:** `docs/task-evidence/phase-2d-task-6.md`
**Depends on:** Task 21 accepted
**TDD:** required

**Validation contract:**

- Target tests: `conda run -n agent-foundations python -m pytest tests/unit/context tests/integration/test_agent_loop.py -q`
- Affected regression tests: `conda run -n agent-foundations python -m pytest tests/unit/runtime tests/unit/tools tests/integration/test_command_feedback_agent_flow.py tests/integration/test_git_read_tools.py -q`
- Full suite: `not-required`
- Full suite reason: 本 Task 只增加只读、确定性的 context source selection，不增加 Tool、Capability、migration 或模型调用。
- Additional gates: PathPolicy/sensitive/symlink corpus、cache invalidation matrix、Context Budget before/after Offline Eval；不得调用真实 compactor/model。

**Files:**

- Create: `src/agent_foundations/context/sources.py`
- Create: `src/agent_foundations/context/repo_map.py`
- Create: `src/agent_foundations/context/relevance.py`
- Create: `src/agent_foundations/context/cache.py`
- Create: `tests/unit/context/test_sources.py`
- Create: `tests/unit/context/test_repo_map.py`
- Create: `tests/unit/context/test_relevance.py`
- Create: `tests/unit/context/test_cache.py`
- Modify: `src/agent_foundations/context/budget.py`
- Modify: `src/agent_foundations/context/builder.py`
- Modify: `src/agent_foundations/runtime/loop.py`
- Modify: `tests/unit/context/test_builder.py`
- Modify: `tests/integration/test_agent_loop.py`

**Stable contract:**

```python
class ContextSource(ValidatedCopyModel):
    source_id: str
    kind: str
    content: str
    priority: int
    provenance: str
    fingerprint: str

class RepoMapBuilder:
    def build(self, root: Path, limits: RepoMapLimits) -> RepoMap: ...

class RelevanceScorer:
    def score(self, query: str, source: ContextSource) -> float: ...

class ContextBuilder:
    def build(
        self,
        messages: tuple[Message, ...],
        sources: tuple[ContextSource, ...] = (),
    ) -> tuple[Message, ...]: ...
```

Repo Map 使用 Python `ast` 和受限 TypeScript import/export parser，不 import/执行项目代码；跳过 `.git`、依赖、build/cache、敏感文件、二进制、数据库、Artifact 和 symlink/reparse point。Cache key 包含 project fingerprint、相对路径、size、mtime_ns 和内容 SHA-256；命中时仍重新验证 PathPolicy 和敏感规则。Task 22 只做确定性选择、排序、截断和 cache，不声称实现 compaction。

- [x] **Step 1: 创建 evidence，记录现有 Context Budget 行为和 Offline Eval baseline**
- [x] **Step 2: 写 ContextSource/Repo Map/Relevance/Cache Red，覆盖确定性排序、来源 provenance、Python/TS map、循环 import、敏感/二进制/Artifact/symlink 跳过、cache poisoning/失效、tiny budget、mandatory overflow 和 project fingerprint 漂移**
- [x] **Step 3: 运行 Red**

Run: `conda run -n agent-foundations python -m pytest tests/unit/context tests/integration/test_agent_loop.py -q`
Expected: ContextSource、Repo Map、selection 或 cache 合同缺失导致 assertion failure；既有 budget tests 正常收集。

- [x] **Step 4: 实现 deterministic Repo Map、词项相关性、来源排序、分层截断和 bounded LRU cache；不调用模型、不生成语义摘要**
- [x] **Step 5: Trace `context.snapshot` 只记录 source ID、provenance、fingerprint、字符数、score、截断/cache 决策，不默认复制完整源码或 Command Artifact**
- [x] **Step 6: 运行 Target、Affected regression、Offline Eval、Ruff、mypy 和 `git diff --check`**
- [x] **Step 7: evidence 对比 Context Budget 前后指标，记录 cache/PathPolicy matrix 并停止**

**Acceptance:** Repo Map 和 context selection 确定、可解释、可缓存且不越过 PathPolicy；被选/舍弃来源可审计；本 Task 不把截断包装成 compaction。
**User acceptance:** 2026-08-26 用户确认 `确认 Task 22 用户验收通过`；记录于本计划与 `docs/task-evidence/phase-2d-task-6.md` §9。满足 Task 23 前置依赖 `Task 22 accepted`。Task 23 仍需单独 executor 授权，未授权不得开始；真实 compactor 还须再经单独授权的人工验收。当前实现已独立复验通过（targeted verification）；TDD 过程证据为 complete。reviewer P3（snapshot `decision` 在 builder 丢弃前一律标 selected；`.sql` 路径名可入 map）不因本次验收要求立即返工。
**Suggested commit after explicit authorization:** `feat: select observable repository context`

---

### Task 23：Loss-aware Context Compaction 与 Rehydration

**Task ID:** `phase-2d-task-7`
**Evidence:** `docs/task-evidence/phase-2d-task-7.md`
**Depends on:** Task 22 accepted
**TDD:** required；真实 compactor 只进入经单独授权的人工验收

**Validation contract:**

- Target tests: `conda run -n agent-foundations python -m pytest tests/unit/context/test_critical_facts.py tests/unit/context/test_compaction.py tests/unit/context/test_rehydration.py tests/unit/context/test_model_compactor.py tests/integration/test_context_compaction_flow.py -q`
- Affected regression tests: `conda run -n agent-foundations python -m pytest tests/unit/context tests/unit/runtime tests/unit/chat tests/integration/test_agent_loop.py tests/integration/test_command_feedback_agent_flow.py -q`
- Full suite: `required`
- Full suite reason: 本 Task 修改共享 ContextBuilder/AgentLoop 的模型输入语义，错误压缩可能造成跨模块事实丢失或权限判断漂移。
- Additional gates: FakeCompactor quality corpus、critical fact recall `100%`、rehydration fingerprint/range matrix、raw Artifact exclusion/leakage scan；自动测试不得调用真实模型。

**Files:**

- Create: `src/agent_foundations/context/critical_facts.py`
- Create: `src/agent_foundations/context/compaction.py`
- Create: `src/agent_foundations/context/rehydration.py`
- Create: `src/agent_foundations/context/fake_compactor.py`
- Create: `src/agent_foundations/context/model_compactor.py`
- Create: `tests/unit/context/test_critical_facts.py`
- Create: `tests/unit/context/test_compaction.py`
- Create: `tests/unit/context/test_rehydration.py`
- Create: `tests/unit/context/test_model_compactor.py`
- Create: `tests/integration/test_context_compaction_flow.py`
- Create: `tests/fixtures/context/compaction-cases-v1.json`
- Modify: `src/agent_foundations/context/budget.py`
- Modify: `src/agent_foundations/context/builder.py`
- Modify: `src/agent_foundations/runtime/loop.py`
- Modify: `src/agent_foundations/chat/repository.py`
- Modify: `tests/integration/test_agent_loop.py`

**Stable contract:**

```python
class CriticalFact(ValidatedCopyModel):
    kind: CriticalFactKind
    value: str
    source_message_ids: tuple[UUID, ...]
    fingerprint: str

class CompactionRecord(ValidatedCopyModel):
    schema_version: Literal[1]
    source_message_ids: tuple[UUID, ...]
    source_fingerprint: str
    reason: CompactionReason
    summary: str
    critical_facts: tuple[CriticalFact, ...]
    original_units: int
    compacted_units: int

class ContextCompactor(Protocol):
    async def compact(self, request: CompactionRequest) -> CompactionRecord: ...
```

必须原样保留的 critical facts 至少包括：用户当前目标和已确认决策、Plan/Todo 状态、路径/line/test ID/run/effect/artifact/diagnostic ID、Policy/Approval/Capability 状态、失败 gate/exit code/parser partial warning、未完成项、安全约束和用户明确拒绝。旧的普通对话与重复 sanitized Tool 内容才允许语义压缩。SQLite 中原始 messages 永远不被 summary 覆盖或删除；`CompactionRecord` 只作为下一次模型输入的派生对象，Trace 只记录 version、message ID range、fingerprint、reason、单位数和 critical fact fingerprints，不记录完整 summary。

Rehydration 只能根据同一 conversation 中 `source_message_ids` 从 SQLite 原始消息恢复，经 fingerprint 验证后返回 bounded、再次脱敏的原文；不得接收任意 SQL、路径或跨 conversation ID。原始 Command Artifact 永不进入 compactor 输入；只有 `CommandFeedback` 和 Agent 已获授权读取的 sanitized片段可参与。

- [x] **Step 1: 创建 evidence，记录当前 Context Budget 截断行为、SQLite 原消息不变量和 compaction quality baseline**
- [x] **Step 2: 写 critical fact/compaction Red，覆盖上述事实类别、跨轮次决策、重复工具输出、parser partial、malicious summary 遗漏/篡改、stable fingerprint、budget trigger、recent turn 保留和原消息不变**
- [x] **Step 3: 运行 compaction Red**

Run: `conda run -n agent-foundations python -m pytest tests/unit/context/test_critical_facts.py tests/unit/context/test_compaction.py -q`
Expected: exact critical fact extraction、record validation 或 FakeCompactor 行为缺失导致 assertion failure。

- [x] **Step 4: 实现 deterministic critical fact extractor、`ContextCompactor` protocol、FakeCompactor 和 loss-aware merge；验证 compactor 输出包含所有 critical facts，否则拒绝该 summary 并采用安全 fallback**
- [x] **Step 5: 写 rehydration/AgentLoop Red，覆盖同 conversation/range、cross-conversation 拒绝、fingerprint drift、bounded read、重启后原消息仍可恢复、raw Artifact exclusion 和 compacted input provenance**
- [x] **Step 6: 实现 rehydration、严格结构化输出校验的 `ModelCompactor` Adapter 与 AgentLoop 接线；单元测试只注入 FakeProvider，SQLite originals 是唯一原文事实源，compacted context 不持久替代原消息**
- [x] **Step 7: 运行 Target、Affected regression、完整 Phase 1 基线、FakeCompactor quality corpus、Ruff、mypy、pip check、前端 gates 和 `git diff --check`**
- [x] **Step 8: evidence 报告 critical recall、压缩率、rehydration 结果和安全 fallback；未经付费 API 明确授权不运行真实 compactor**

**Acceptance:** 旧历史能在预算内压缩，但关键事实逐项精确保留；任何 compactor 不确定或遗漏都安全回退；原消息可按 provenance 恢复，原始 Command Artifact 从不被自动送入模型。
**User acceptance:** 2026-08-27 用户确认 `确认 Task 23 用户验收通过`；记录于本计划与 `docs/task-evidence/phase-2d-task-7.md` §9。满足 Task 24 前置依赖 `Task 23 accepted`。Task 24 仍需单独 executor 授权，未授权不得开始；真实 compactor 仍须再经单独授权的人工验收。当前实现已独立复验通过（Target/Affected）；完整 `pytest -q` 为 partial（Docker/`apply_patch` `PATCH_EFFECT_UNKNOWN`，与 compaction 无关），本次验收不得报告为 full suite passed。TDD 过程证据为 complete。
**Suggested commit after explicit authorization:** `feat: compact context without losing critical facts`

---

### Task 24：Provider Retry、Rate Limit 与 Durable Attempt Budget

**Task ID:** `phase-2d-task-8`
**Evidence:** `docs/task-evidence/phase-2d-task-8.md`
**Depends on:** Task 23 accepted
**TDD:** required

**Validation contract:**

- Target tests: `conda run -n agent-foundations python -m pytest tests/unit/providers/test_resilient.py tests/unit/runtime/test_rate_limit.py tests/unit/runtime/test_provider_attempt_budget.py tests/integration/test_provider_retry_recovery.py -q`
- Affected regression tests: `conda run -n agent-foundations python -m pytest tests/unit/providers tests/unit/durable tests/unit/runtime tests/integration/test_agent_loop.py -q`
- Full suite: `required`
- Full suite reason: 本 Task 修改 Provider/AgentLoop/Durable checkpoint 的共享请求语义，重复重试可能产生费用和不可恢复状态漂移。
- Additional gates: injected clock/sleeper、restart/crash matrix、SDK retry disabled assertion、no response-cache assertion；不得调用真实 Provider。

**Files:**

- Create: `src/agent_foundations/providers/resilient.py`
- Create: `src/agent_foundations/runtime/rate_limit.py`
- Create: `src/agent_foundations/runtime/provider_attempt_budget.py`
- Create: `tests/unit/providers/test_resilient.py`
- Create: `tests/unit/runtime/test_rate_limit.py`
- Create: `tests/unit/runtime/test_provider_attempt_budget.py`
- Create: `tests/integration/test_provider_retry_recovery.py`
- Modify: `src/agent_foundations/providers/openai_compatible.py`
- Modify: `src/agent_foundations/durable/models.py`
- Modify: `src/agent_foundations/durable/repository.py`
- Modify: `src/agent_foundations/runtime/loop.py`
- Modify: `src/agent_foundations/cli/main.py`
- Modify: `tests/unit/providers/test_openai_compatible.py`
- Modify: `tests/integration/test_agent_loop.py`

**Stable contract:**

```python
@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 0.25
    max_delay_seconds: float = 2.0
    max_retry_after_seconds: float = 10.0

class ProviderAttemptBudget:
    def reserve(self, run_id: UUID, request_id: UUID) -> AttemptReservation: ...

class TokenBucketRateLimiter:
    async def acquire(self, cost: int = 1) -> None: ...

class ResilientModelProvider:
    async def complete(self, request: ModelRequest) -> ModelResponse: ...
```

只重试明确 transient 的 rate-limit、timeout 和 temporary provider 错误；认证、无效响应、Policy、Tool、context/compaction 和 cancellation 不重试。`Retry-After` 解析后仍受上限限制，sleep 可取消，测试注入 clock/sleeper。OpenAI SDK 固定 `max_retries=0`，避免 Adapter 与 wrapper 双层重试。

每个 logical request 的累计 attempt budget 写入 Durable checkpoint，并在发起下一 attempt 前原子 reserve；崩溃/重启后沿用已消费次数，不重置预算。模型 response 不做隐式 cache，避免旧 Tool/Policy 决策重放；Repo Map cache 和 compaction 派生物仍按各自 fingerprint 规则管理。

- [x] **Step 1: 创建 evidence，记录 Provider Adapter 当前 retry 配置和 Durable checkpoint shape**
- [x] **Step 2: 写 bounded backoff、Retry-After cap、成功停止、non-retryable 单次、取消传播、token bucket 公平、无真实 sleep、SDK retry off、无 response cache 和 attempt reservation Red**
- [x] **Step 3: 写 crash-before/after-reserve、restart remaining budget、concurrent same request 和 exhausted budget integration Red**
- [x] **Step 4: 运行 Red**

Run: `conda run -n agent-foundations python -m pytest tests/unit/providers/test_resilient.py tests/unit/runtime/test_rate_limit.py tests/unit/runtime/test_provider_attempt_budget.py tests/integration/test_provider_retry_recovery.py -q`
Expected: wrapper、limiter 或 durable attempt budget 缺失导致 assertion failure。

- [x] **Step 5: 实现 injected Clock/Sleeper、bounded retry、rate limiter 和 checkpoint-backed attempt reservation；Trace 只记录 request fingerprint、error type、attempt 和 bounded delay**
- [x] **Step 6: CLI Provider 构建改为 SDK 无重试 + `ResilientModelProvider`；FakeModel/Eval 使用 deterministic adapter，不走真实 rate limit**
- [x] **Step 7: 运行 Target、Affected regression、完整 Phase 1 基线、restart matrix、Ruff、mypy、pip check、前端 gates 和 `git diff --check`**
- [x] **Step 8: evidence 记录错误分类、attempt state transition 和取消/恢复矩阵并停止**

**Acceptance:** Provider retry 有界、可取消、跨重启不重置累计预算；不存在重复 retry 层或 response cache 导致的陈旧决定；自动测试不产生真实模型费用。
**User acceptance:** 2026-08-27 用户确认 `确认 Task 24 用户验收通过`；记录于本计划与 `docs/task-evidence/phase-2d-task-8.md` §9。满足 Task 25 前置依赖 `Task 24 accepted`。Task 25 仍需单独 executor 授权，未授权不得开始。当前实现已独立复验通过（Target/Affected）；完整 `pytest -q` 为 partial（Docker/`apply_patch` `PATCH_EFFECT_UNKNOWN`，与 Provider retry 无关），本次验收不得报告为 full suite passed。TDD 过程证据为 complete。Chat 无 `CheckpointSink` 时 attempt 仅进程内累计（受保护文件，不因本次验收要求返工）。
**Suggested commit after explicit authorization:** `feat: make provider retries durable and bounded`

---

### Task 25：Phase 2 全量 Eval、E2E、文档与总验收

**Task ID:** `phase-2d-task-9`
**Evidence:** `docs/task-evidence/phase-2d-task-9.md`
**Depends on:** Task 24 accepted
**TDD:** required for integration/E2E；文档部分为 `not-applicable`

**Validation contract:**

- Target tests: `conda run -n agent-foundations python -m pytest tests/integration/test_phase2_coding_agent.py tests/integration/test_command_feedback_agent_flow.py tests/e2e/test_chat_ui.py -q` and `npm run test:chat`
- Affected regression tests: Phase 1/Phase 2 complete automated baseline below.
- Full suite: `required`
- Full suite reason: Phase 2 final gate；必须独立验证所有新增 Tool、安全边界、migration、恢复、Sandbox、Context 和 UI。
- Additional gates: Phase 1/2 Offline Eval、Docker matrix、Command Artifact attack/leakage matrix、compaction quality、FakeModel correction E2E；真实模型 3 类场景各连续 3/3 仅在用户单独批准付费 API 后执行。

**Files:**

- Create: `tests/fixtures/evals/phase-2-tasks-v1.json`
- Create: `tests/fixtures/evals/phase-2-responses-v1.json`
- Create: `docs/eval-baselines/phase-2-v1.json`
- Create: `docs/learning-notes/05-offline-eval-and-planning.md`
- Create: `docs/learning-notes/06-durable-execution.md`
- Create: `docs/learning-notes/07-security-and-controlled-tools.md`
- Create: `docs/learning-notes/08-command-feedback-and-context-compaction.md`
- Create: `tests/integration/test_phase2_coding_agent.py`
- Modify: `tests/e2e/test_chat_ui.py`
- Modify: `README.md`
- Modify: `docs/agent-plans/2026-07-20-agent-engineering-learning-design.md`
- Modify: `docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md`

**End-to-end scenario:** FakeModel 创建计划 → 读取代码 → 生成/校验 Patch → Policy/Approval → `apply_patch` → 全量 `run_command` 失败 → `CommandFeedback` 提取根因 → 只运行失败 test ID → 修复 → 定向 Green → 受影响回归 Green → `git_diff` → 完成。测试只使用临时虚构 Git 项目和固定 Sandbox，不触碰真实业务项目、不调用真实模型。

```python
@pytest.mark.asyncio
async def test_phase2_agent_recovers_from_structured_command_feedback(
    temporary_git_project: Path,
) -> None:
    result = await run_scripted_phase2_correction_flow(temporary_git_project)
    assert result.status is DurableRunStatus.COMPLETED
    assert result.targeted_reproduction_count == 1
    assert result.affected_regression_passed is True
    assert result.raw_output_exposed_to_model is False
    assert result.git_writes == ()
```

- [x] **Step 1: 创建 evidence，逐项列出 Task 1–24 evidence、reviewer 结论、用户 gate、migration v1–v10、Docker image ID 和所有未验证项**
- [x] **Step 2: 写最终 FakeModel E2E Red，覆盖 approve/deny/cancel、crash/lease takeover、profile version change、command timeout/output limit/artifact write failure、Parser partial→受限读取、定向复现、Git read-only、compaction/rehydration 和 Provider attempt restart**
- [x] **Step 3: 运行 Red**

Run:

```powershell
conda run -n agent-foundations python -m pytest tests/integration/test_phase2_coding_agent.py tests/integration/test_command_feedback_agent_flow.py tests/e2e/test_chat_ui.py -q
npm run test:chat
```

Expected: 只能因最终 fixture/production composition/文档接线缺失而失败；环境、Docker 未授权、import error 或真实 Provider 不得作为有效 Red。

- [x] **Step 4: 只补齐最终 fixture、composition 和文档，不在总验收 Task 新增 Parser、Artifact、Tool、Sandbox、Context 或 retry 架构**
- [x] **Step 5: 运行 Phase 1/2 Offline Eval 并保存可比较报告；解释成功率、步骤数、无效 Tool、安全拒绝、审批、恢复、CommandFeedback 使用、日志读取预算、critical fact recall、Token 和延迟变化**

Run:

```powershell
conda run -n agent-foundations agent-foundations evaluate --task-set tests/fixtures/evals/phase-1-tasks-v1.json --responses tests/fixtures/evals/phase-1-responses-v1.json --output .agent-foundations/evals/final-phase-1.json --runtime-revision working-tree
conda run -n agent-foundations agent-foundations evaluate --task-set tests/fixtures/evals/phase-2-tasks-v1.json --responses tests/fixtures/evals/phase-2-responses-v1.json --output .agent-foundations/evals/final-phase-2.json --runtime-revision working-tree
```

- [x] **Step 6: 运行完整新鲜自动化门禁**

Run:

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

Expected: 每条 gate 退出 `0`；记录本次精确通过数量、warning 和 skipped，不复制历史数字。

- [x] **Step 7: 运行经用户授权的 Docker、Artifact 和安全验收矩阵**

必须证明：

1. Container 无网络、非 root、资源受限，只接收 filtered snapshot；host conda、venv、`node_modules`、`.git`、`.env` 和凭据不进入容器。
2. `PROJECT_READ_ONLY` 拒绝命令/写；`ASK_ALWAYS` 每次 Patch/命令都询问；同一路径/命令再次访问需要新 Capability；deny 不产生副作用。
3. 敏感文件、项目外写、Shell、Git write、network 和系统修改不能通过审批绕过；`PROJECT_FULL_ACCESS` 仍受 hard Policy/Sandbox 限制。
4. 重启把未完成 run 标记 interrupted；committed Patch/command 不重复；UNKNOWN effect 要求 reconcile；Artifact finalize failure 保留真实 outcome。
5. `.env`、API Key、Token、Cookie、private key fixture 不进入 Agent input、SQLite JSON/raw scan、JSONL Trace、Chat JSON、SSE 或前端 DOM。
6. artifact_id 的 traversal、absolute path、ADS、控制字符、跨 run/conversation/artifact replay 稳定拒绝；Agent 永远拿不到原始路径/raw ticket。
7. 超长输出、二进制、非法 UTF-8、ANSI、无换行和 stdout/stderr 并发处理安全；Parser failed/partial 保留 exit code、unparsed bytes 和 recommended ranges。
8. 64 MiB/1 GiB/7 days 配额、reservation、oldest-completed eviction、pending_delete/delete_failed 不误删 active 或其他 run Artifact。
9. UI 默认仅显示 feedback；sanitized pagination 和显式 raw download 不改变 Agent context/permission；390×844 无横向溢出。
10. Registry 不包含 MCP、Memory、Skills、Hooks、Sub-Agent、Browser、network Tool、Git write 或 `HOST_FULL_ACCESS`。

- [x] **Step 8: 运行 compaction quality gate：critical fact recall 必须 100%，source fingerprint/range 可 rehydrate，raw Artifact exclusion 通过；压缩率只作报告，不得用低 recall 换高压缩率**
- [x] **Step 9: 更新学习笔记和 README，解释自研核心、Adapter 边界、Artifact/Feedback 数据流、loss-aware compaction、Eval 结论和刻意未解决能力**
- [x] **Step 10: 在用户另行明确批准真实付费 API 后，使用固定虚构临时项目做 3 类人工场景，每类连续 3/3，共 9 次；任何一次失败即该类失败，不追加次数挑选成功结果**

真实模型场景固定为：

1. Python：pytest 全量失败 → 结构化根因 → 定向 node ID → Patch → 定向及受影响回归通过。
2. TypeScript/Node：Vitest/typecheck/build 失败 → 对应 Parser/Feedback → 定向复现 → Patch → gates 通过。
3. 安全与恢复：ASK_FOR_ACCESS/deny/一次性 Capability、同一路径再次审批、重启 interrupted/不重复 effect、禁止敏感/项目外/Shell/Git write/network 绕过。

每次从全新 fixture snapshot 和 conversation 开始，只在 evidence 保存脱敏结果、run/session/artifact IDs 和 pass/fail，不保存真实 Provider 凭据或 raw output。未获本 Task 单独授权时标记 `not-run`，不得因此伪称 Phase 2 人工验收完成。

**User acceptance (Step 10):** 2026-09-09 用户确认 `确认「Task 25 Step 10 用户验收通过」`；记录于本计划与 `docs/task-evidence/phase-2d-task-9-step-10.md` §11。范围仅限 Round 3 付费 Chat UI 3×3 连续 9/9（`docs/agent-plans/2026-09-08-phase-2-task-25-step-10-manual-3x3.md`；TEMP `20260909`；Stop 中断）。独立 reviewer 复验 sqlite/traces/host 与 pin，支持 Python/Node/Security 各 3/3。2026-09-08 Round 2 记分（Node-3 `InvalidModelResponseError`）不得改写成通过。本确认不是 Task 25 整体完成，不是用户 Phase 2 完成；Step 11 保持未勾选。reviewer P3（Node-3 未调用 git 只读工具；Security-3 中断 apply 活动留 `running`/`executing`；evidence §8 仍为 Round 2 交接）不因本次确认要求立即返工。未授权 commit、push、付费重跑或 Phase 3。

- [x] **Step 11: reviewer 独立复验当前代码/diff/evidence，分别报告实现正确性、TDD 过程、自动门禁和人工验收；用户确认后才能勾选 Phase 2 完成**

**User acceptance (Step 11):** 2026-09-09 用户确认 `确认「Task 25 Step 11 用户验收通过」`；记录于本计划与 `docs/task-evidence/phase-2d-task-9-step-11.md` §12。范围仅限 Session B 独立复验：当前实现 pass；完整 Step 6（pytest 1541 passed / 14 skipped / 54 warnings；ruff / mypy 312 files / pip check / viewer+chat test/typecheck/`build:chat` / `git diff --check` exit 0）；`pytest -m docker` 21 passed；Offline Eval Phase 1 8/8 与 Phase 2 4/4 `success_rate=1.0`；人工 Step 10 Round 3 9/9 维持（未重跑付费）。Session A 的 13 failed / ruff F821 / mypy 4 errors **不得改写成通过**（随后由 Task 49 修绿并已用户验收）。TDD 过程对 Phase 2 整体为 partial；本次确认不独立见证各 Task 历史 Red→Green。reviewer P3（Chat 与 Durable 中断非同一 SQLite 事务；Step 10 Node-3 未用 git 只读；Security-3 Stop 后 apply 活动可能仍 `running`；`store.py` `__all__` 只导出两常量；同文件其它测试仍有 `{stream}`-only fixture；一次未复现的 sqlite disk I/O 抖动）不因本次确认要求立即返工。本确认勾选计划正文 Step 11，当时**不是**用户 Phase 2 完成。未授权 commit、push、付费 3×3 重跑或 Phase 3。

**User acceptance (Phase 2 complete):** 2026-09-09 用户确认 `确认「用户 Phase 2 完成」`；记录于本计划与 `docs/task-evidence/phase-2d-task-9-step-11.md` §13。范围：在 Step 10 Round 3 9/9 与 Step 11 Session B 独立复验已用户验收的前提下，关闭用户 Phase 2 总验收。Round 2 Node-3 `InvalidModelResponseError` **不得改写成通过**。Session A 13 failed **不得改写成通过**。P3 保留，不因本确认要求立即返工。本确认**不是** commit / push / Phase 3 授权；Step 12 仍生效，未获明确授权不得进入 Phase 3。

- [x] **Step 12: 未获 commit/push 明确授权时停止，不进入 Phase 3**

**Acceptance:** Agent 能在安全边界内计划、Patch、运行固定 gates、理解结构化失败、定向复现和回归、读取 Git、压缩并恢复 context、跨崩溃保持真实副作用状态；Artifact 原始输出和 Provider 凭据不泄漏；自动化全绿且真实模型三类各连续 3/3 后，才可请求用户 Phase 2 总验收。
**User acceptance (P1 only):** 2026-08-27 用户确认 `确认「本 P1 用户验收通过」`；记录于本计划与 `docs/task-evidence/phase-2d-task-9.md` §9。范围仅限 FakeModel E2E `_DIFF` 与 fixture `# noqa: B011` 对齐。独立复验：单测 1 passed；Target trio 14 passed；`pytest -q` 1396 passed / 9 skipped / exit 0；`npm run test:chat` 74 passed。TDD 过程证据对本 P1 为 complete；本次确认不独立见证历史 Red→Green。本确认不是 Task 25 完成，不是用户 Phase 2 完成；Step 10/11 保持未勾选。P3（占位 `final_image_id`、DualBackend≠生产 Docker、Chat 无 `CheckpointSink`）不因本次确认要求立即返工，各需单独授权。未授权 commit、push、付费 3×3 重跑或下一 Task。
**Suggested commit after explicit authorization:** `feat: complete controllable coding agent phase`

---

## 3. 规格覆盖映射

| 已确认设计要求 | 实施 Task | 主要证据 |
|---|---:|---|
| Phase 1 离线 Agent Eval 基线 | 1–3 | task set、Replay Agent、baseline report、CLI tests |
| Planning、Todo、受限重规划 | 4–5 | Plan CAS/DAG tests、Planning Tool、Trace、Eval |
| schema/version 与 Checkpoint | 6–7 | migration/repository tests |
| resume/retry/cancel | 9 | state-machine integration tests |
| run ownership/lease | 8–9 | concurrent owner/takeover tests |
| side-effect ledger 与幂等 | 10、15、18 | crash-point、UNKNOWN、replay tests |
| Unified Diff/Patch 预览 | 11 | parser/validator/persistence tests |
| Approval/Policy/Capability/Sandbox 分层 | 12–14 | decision matrix、capability consume、backend tests |
| Permission Profile 与防权限膨胀 | 12、13、16 | migration/API/recovery/UI tests |
| 项目内受控 `apply_patch` | 15–16 | rollback/recovery/E2E |
| 命令 manifest、filtered snapshot 与可复现 Sandbox | 17 | classifier、snapshot、image provenance/smoke |
| 受限 `run_command` 与 durable effect | 18 | process lifecycle、crash、replay tests |
| Command Output Artifact 生命周期 | 18 | v9 metadata、atomic write、quota、retention、delete tests |
| Tool-specific Parser 与 `CommandFeedback` | 19 | six parser fixture corpus、partial/failed tests |
| Agent 受限分段读取 | 20 | same-run Capability、budget、re-redaction、v10 audit tests |
| Chat/API/UI Artifact 投影与 raw local download | 20 | API/React/Playwright、ticket security、leakage tests |
| 只读 Git | 21 | isolated config、temporary repository integration tests |
| Repo Map、相关性、预算与缓存 | 22 | context determinism/provenance/cache tests |
| loss-aware compaction 与 rehydration | 23 | critical recall、fingerprint/range、FakeCompactor tests |
| retry、rate limiting 与 durable attempt budget | 24 | injected clock/sleeper、restart budget tests |
| Eval 回归与阶段总验收 | 5、11、16、25 | per-gate reports、full gates、Docker/Artifact/manual safety |
| MCP/ACP/A2A/SSE/Trace 协议分工保持 | 25 | Registry audit、learning notes、existing SSE/Trace regression |
| 不提前实现主机完全访问 | 12、16、25 | Profile/API/Registry negative tests |

## 4. 明确非目标

- 不实现 MCP、ACP、A2A、长期 Agent Memory、Skills、Hooks、Sub-Agent；Task 23 的 compaction 只处理当前 conversation 的模型输入预算，不形成跨 conversation 记忆。
- 不实现 Browser、桌面 GUI、通用 Computer Use、网络 Tool 或包安装。
- 不实现项目外写入、任意 Shell、Git 写操作、commit、push、PR 或部署。
- 不实现 `TrustedHostExecutor` 或 `HOST_FULL_ACCESS`。
- 不把 SSE 作为 durable log，不把 Trace 作为恢复、授权或控制事实源。
- 不引入第三方 Agent Runtime、Workflow 或 Durable Execution 框架替代自研核心。
- 不为了总门禁临时弱化测试、关闭规则、增加宽泛 ignore 或绕过 Sandbox。

## 5. Planner 到单 Task Prompt 的交接合同

后续另一个 planner 为单 Task 生成执行 prompt 时，必须从本计划复制并收窄以下内容：

1. 当前唯一 Task ID、依赖验收状态和 evidence 路径。
2. 精确 Files、稳定接口、Red/Green 命令和预期失败类别。
3. 当前 Task 的 Scope、Non-Scope、风险、回退和停止条件。
4. 当前子里程碑权限上限；不得把后续 Task 的 Tool 或权限提前加入。
5. Docker、依赖、真实模型、commit/push 等需要单独确认的动作。
6. executor 完成 evidence 后立即停止；prompt 不授权 reviewer、下一 Task 或下一子里程碑。

不得把 25 个 Task 合并成一个 executor prompt，也不得让 executor 自行选择下一个 Task。

---

## Appendix: Task 26（Chat 生产 SandboxManifest pin）

**Task ID:** `phase-2d-task-10`

**Evidence:** `docs/task-evidence/phase-2d-task-10.md`

**Depends on:** Task 25 P1 remediation user-accepted 2026-08-27

**TDD:** required

This appendix locates the follow-on Task. It does **not** rewrite Task 25 acceptance, does **not** check Step 10/11, and is **not** Phase 2 sign-off.

**Files:**

- Create: `docker/sandbox-manifest.phase2d.json`
- Modify: `src/agent_foundations/execution/sandbox_manifest.py` (`from_path` / `load_pinned` only; `verify_runtime` semantics unchanged)
- Modify: `src/agent_foundations/cli/main.py` (`_phase2d_sandbox_manifest` + two `DockerBackend(..., sandbox_manifest=)` factories)
- Modify: `tests/unit/execution/test_sandbox_manifest.py`
- Create: `docs/task-evidence/phase-2d-task-10.md`

**Target tests:** `pytest tests/unit/execution/test_sandbox_manifest.py -q`

**Affected regression:** `pytest tests/unit/tools/command/test_classifier.py tests/unit/tools/command/test_models.py tests/integration/test_run_command_flow.py tests/e2e/test_chat_ui.py -q`

**Full suite:** not-required

**User acceptance:** 2026-08-27 用户确认 `确认「Task 10 / phase-2d-task-10 用户验收通过」`；记录于本附录与 `docs/task-evidence/phase-2d-task-10.md` §9。范围仅限 Chat 生产 `SandboxManifest` 版本化 pin 与两处 `DockerBackend` 传入同一 pin。独立复验为 targeted：`test_sandbox_manifest.py` 16 passed；affected 87 passed / 1 skipped；只读 inspect 与 pin 一致；`pytest -m docker` 16 passed。TDD 过程证据为 complete；本次确认不独立见证历史 Red→Green。更早一轮 affected 中 `test_task16_browser_patch_profile_reload_approve_deny_and_no_duplicate_write` 的 `TypeError` 已用签名兼容 factory 修复，独立复验时该套件为绿，不作为本确认的失败依据。本确认不是 Task 25 完成，不是用户 Phase 2 完成；Step 10/11 保持未勾选。Chat CheckpointSink 与可选 DualBackend Docker 兄弟 E2E 不因本次确认要求立即返工，各需单独授权。未授权 commit、push、付费 3×3 重跑或下一 Task。

## Appendix: Task 27（Chat ConversationRunner CheckpointSink）

**Task ID:** `phase-2d-task-11`

**Evidence:** `docs/task-evidence/phase-2d-task-11.md`

**Depends on:** `phase-2d-task-10` user-accepted 2026-08-27

**TDD:** required

This appendix locates the follow-on Task. It does **not** rewrite Task 24/25 acceptance, does **not** check Step 10/11, and is **not** Phase 2 sign-off.

**Files:**

- Create: `src/agent_foundations/chat/durable_checkpoint.py`
- Modify: `src/agent_foundations/chat/runner.py`
- Modify: `src/agent_foundations/runtime/loop.py` (optional `provider_attempts` on `run()` only)
- Modify: `tests/unit/chat/test_runner.py`
- Create: `docs/task-evidence/phase-2d-task-11.md`

**Target tests:** `pytest tests/unit/chat/test_runner.py tests/integration/test_agent_loop.py -q -k provider`

**Affected regression:** `pytest tests/unit/chat/test_runner.py tests/integration/test_chat_api.py tests/e2e/test_chat_ui.py -q`

**Full suite:** not-required

**User acceptance:** 2026-08-27 用户确认 `确认「Task 11 / phase-2d-task-11 用户验收通过」`；记录于本附录与 `docs/task-evidence/phase-2d-task-11.md` §9。范围仅限 Chat `ConversationRunner` 无 lease 的 Durable `CheckpointSink`，以及将已保存 `provider_attempts` 注入 `AgentLoop.run`。独立复验为 targeted：`test_runner.py` 12 passed；`test_agent_loop.py -k provider` 6 passed；`test_provider_retry_recovery.py` 8 passed；affected 52 passed。TDD 过程证据为 complete；本次确认不独立见证历史 Red→Green。reviewer P3（crash-after-reserve 第二次未走 `runner2.run_turn()`）不因本次确认要求立即返工。本确认不是 Task 25 完成，不是用户 Phase 2 完成；Step 10/11 保持未勾选。可选 DualBackend Docker 兄弟 E2E 仍需单独授权。未授权 commit、push、付费 3×3 重跑或下一 Task。

## Appendix: Task 28（FakeModel 纠错流 Docker 兄弟 E2E）

**Task ID:** `phase-2d-task-12`

**Evidence:** `docs/task-evidence/phase-2d-task-12.md`

**Depends on:** `phase-2d-task-10` user-accepted 2026-08-27

**TDD:** required

This appendix locates the optional follow-on Task after user acceptance. It does **not** rewrite Task 25 acceptance, does **not** check Step 10/11, and is **not** Phase 2 sign-off. It does **not** replace the DualBackend locked FakeModel contract.

**Files:**

- Modify: `tests/integration/test_phase2_coding_agent.py` (append `@pytest.mark.docker` sibling only)
- Create: `docs/task-evidence/phase-2d-task-12.md`

**Target tests:** `pytest tests/integration/test_phase2_coding_agent.py -q` and `pytest tests/integration/test_phase2_coding_agent.py -m docker -q`

**Affected regression:** `pytest -m docker -q`

**Full suite:** not-required

**User acceptance:** 2026-08-27 用户确认 `确认「Task 12 / phase-2d-task-12 用户验收通过」`；记录于本附录与 `docs/task-evidence/phase-2d-task-12.md` §9。范围仅限 FakeModel 脚本化纠错流的 Docker 兄弟 E2E（真 `DockerBackend` + 生产 pin）。独立复验为 targeted：无 `-m docker` 时 5 passed / 1 skipped；该文件 `-m docker` 1 passed / 5 deselected；`pytest -m docker -q` 17 passed / 1395 deselected；inspect 与 pin 一致。TDD 过程证据为 complete；本次确认不独立见证历史 Red→Green。reviewer P3（测试包装在 Chat 漏传 manifest 时回退 pin；临时副本删除 `conftest.py`）不因本次确认要求立即返工。本确认不是 Task 25 完成，不是用户 Phase 2 完成；Step 10/11 保持未勾选。未授权 commit、push、付费 3×3 重跑或 Phase 3。

## Appendix: Task 29（Chat 人工验收缺陷修复）

**Task ID:** `phase-2d-task-13`

**Evidence:** `docs/task-evidence/phase-2d-task-13.md`

**Depends on:** Appendix Task 26–28 (`phase-2d-task-10/11/12`) user-accepted; 2026-08-28 人工测试报告

**TDD:** required（SSE 关闭路径允许以 `CancelledError` 吞没的最小测试；文档 not-applicable）

This appendix locates a Chat control-plane defect-fix Task. It is **not** plan-body Task 13 (Approval/Policy). It does **not** rewrite Task 13 or Task 25 acceptance, does **not** check Step 10/11, and is **not** Phase 2 sign-off.

**Files:**

- Create: `docs/task-evidence/phase-2d-task-13.md`
- Create: `tests/integration/test_chat_planning_tools.py`
- Create: `tests/integration/test_ask_always_run_command_twice.py`
- Modify: `src/agent_foundations/cli/main.py` (`runtime_factory` planning wiring only; `PlanningMode.DISABLED`)
- Modify: `src/agent_foundations/tools/git/service.py`
- Modify: `tests/unit/tools/git/test_service.py`
- Modify: `web/chat/components/CommandFeedbackCard.tsx`
- Modify: `tests/chat/command-feedback.test.tsx`
- Modify: `web/chat/components/ApprovalCard.tsx`
- Modify: `tests/chat/activity.test.tsx`
- Modify: `src/agent_foundations/chat/approvals.py`
- Modify: `src/agent_foundations/chat/api.py`
- Modify: `src/agent_foundations/viewer/app.py`
- Modify: `tests/unit/chat/test_approvals.py`

**Target tests:** `pytest tests/unit/tools/git/test_service.py tests/unit/chat/test_approvals.py tests/integration/test_chat_planning_tools.py tests/integration/test_ask_always_run_command_twice.py -q` and `npm run test:chat`

**Affected regression:** `pytest tests/unit/tools/git tests/unit/chat tests/unit/planning tests/integration/test_git_read_tools.py tests/integration/test_chat_approval_flow.py tests/integration/test_task16_production_wiring.py tests/integration/test_command_feedback_agent_flow.py -q` and `npm run typecheck:chat`

**Full suite:** not-required

**Steps:**

- [x] **Step 1:** 从模板创建 evidence；记录人工测试失败项与未授权 Docker/付费 API
- [x] **Step 2:** 写 Red，覆盖 Chat planning 工具、diff argv、unknown option 错误码、stdout-only sanitized、run_command 审批标题、ASK_ALWAYS 两次命令
- [x] **Step 3:** 在修改生产代码前运行 Red 并写入 evidence
- [x] **Step 4:** 最小实现 A–F（禁止 REQUIRED planning、禁止 v11、禁止改 Policy 矩阵）
- [x] **Step 5:** Target Green、Affected、Ruff、mypy、`git diff --check`、`npm run test:chat`、`npm run typecheck:chat`
- [x] **Step 6:** 本附录定位与 evidence 范围审计；停止

**User acceptance:** 2026-08-28 用户确认 `确认「Task 29 / phase-2d-task-13 用户验收通过」`；记录于本附录与 `docs/task-evidence/phase-2d-task-13.md` §9。范围仅限 Chat planning 接线、git argv/错误码、sanitized stdout-first、`run_command` 审批文案与 `project_internal` scope、ASK_ALWAYS 二次命令回归、Chat/Trace SSE 吞 `CancelledError`。独立复验为 targeted：Target pytest 33 passed；`npm run test:chat` 76 passed；affected 312 passed / 1 skipped；`npm run typecheck:chat` pass。TDD 过程证据对 argv/planning/scope/SSE/文案为 complete；ASK_ALWAYS 二次命令在 Red 上未复现，回归已保留。本次确认不独立见证历史 Red→Green。reviewer P3（git 分类看 stdout+stderr；`core.autocrlf` 的 Docker git 未复验；每 turn 新建 `PlanController`）不因本次确认要求立即返工。本确认不是 Task 25 完成，不是用户 Phase 2 完成；Step 10/11 保持未勾选。未授权 commit、push、付费 3×3 或 Phase 3。

## Appendix: Phase 2 reliability follow-on（不关闭 Phase 2）

可靠性补强（结构化 Patch、错误恢复、Chat Plan 持久化、提示优化、分层预算）的权威计划是：

`docs/agent-plans/2026-08-29-phase-2-reliability-follow-on-plan.md`

Task ID 从 appendix **Task 30 / `phase-2d-task-14`** 起。Task 30 已于 2026-08-29 由用户确认验收通过（targeted）；见 `docs/task-evidence/phase-2d-task-14.md` §9。Task 31 / `phase-2d-task-15` 已于 2026-08-29 由用户确认验收通过（targeted）；见 `docs/task-evidence/phase-2d-task-15.md` §9。Task 32 / `phase-2d-task-16` 已于 2026-08-29 由用户确认验收通过（targeted）；见 `docs/task-evidence/phase-2d-task-16.md` §9。Task 33 / `phase-2d-task-17` 已于 2026-08-29 由用户确认验收通过（targeted）；见 `docs/task-evidence/phase-2d-task-17.md` §9。Task 34 / `phase-2d-task-18` 已于 2026-09-04 由用户确认验收通过（targeted）；见 `docs/task-evidence/phase-2d-task-18.md` §10。该计划 **不得** 勾选本文件 Task 25 Step 10/11，不得写成用户 Phase 2 完成，不得在未另授权时重做付费 3×3。

## Appendix: Phase 2 product hardening（不关闭 Phase 2）

产品缺口（`gate_id`、Git 探测、审批 PolicyRequest、输出双标签、独立数据根、Artifact sweep、关闭语义）的权威计划是：

`docs/agent-plans/2026-09-04-phase-2-product-hardening-plan.md`

Task ID 从 appendix **Task 35 / `phase-2d-task-19`** 起。Task 35 / `phase-2d-task-19` 已于 2026-09-04 由用户确认验收通过（targeted）；见 `docs/task-evidence/phase-2d-task-19.md` §9。Task 36 / `phase-2d-task-20` 已于 2026-09-04 由用户确认验收通过（targeted）；见 `docs/task-evidence/phase-2d-task-20.md` §9。Task 37 / `phase-2d-task-21` 已于 2026-09-04 由用户确认验收通过（targeted）；见 `docs/task-evidence/phase-2d-task-21.md` §9。Task 38 / `phase-2d-task-22` 已于 2026-09-05 由用户确认验收通过（targeted）；见 `docs/task-evidence/phase-2d-task-22.md` §9。Task 39 / `phase-2d-task-23` 已于 2026-09-05 由用户确认验收通过（targeted）；见 `docs/task-evidence/phase-2d-task-23.md` §9。Task 40 / `phase-2d-task-24` 已于 2026-09-05 由用户确认验收通过（targeted）；见 `docs/task-evidence/phase-2d-task-24.md` §9。Task 41 / `phase-2d-task-25` 已于 2026-09-05 由用户确认验收通过（targeted）；见 `docs/task-evidence/phase-2d-task-25.md` §9。Patch/Planning/恢复/Prompt/分层预算仍以可靠性 follow-on 为准，不要在 hardening 计划里重做。本附录 **不得** 勾选 Task 25 Step 10/11，不得写成用户 Phase 2 完成。硬化计划无 Task 42。3×3 须另授权，仍走 Task 25 Step 10。

## Appendix: Phase 2 pre-3×3 gap remediation（不关闭 Phase 2）

付费 3×3 前必须处理的两项缺口（过期 Chat 静态包、CRLF 行文本）的权威计划是：

`docs/agent-plans/2026-09-08-phase-2-pre-3x3-gap-remediation-plan.md`

Task ID 从 appendix **Task 42 / `phase-2d-task-26`** 起。Task 42 / `phase-2d-task-26` 已于 2026-09-08 由用户确认验收通过（targeted）；见 `docs/task-evidence/phase-2d-task-26.md` §9。Task 43 / `phase-2d-task-27` 已于 2026-09-08 由用户确认验收通过（targeted）；见 `docs/task-evidence/phase-2d-task-27.md` §9。该计划无 Task 44（编号止于 Task 43）。Node sandbox overlay 是独立计划 Task 44 / `phase-2d-task-28`，已于 2026-09-08 由用户确认验收通过（targeted）；见 `docs/task-evidence/phase-2d-task-28.md` §9。本附录 **不得** 勾选 Task 25 Step 10/11，不得写成用户 Phase 2 完成。付费 3×3 须另授权，仍走 Task 25 Step 10。操作合同见 `docs/agent-plans/2026-09-08-phase-2-task-25-step-10-manual-3x3.md`。

## Appendix: Task 25 Step 10 付费 3×3 操作合同（不关闭 Phase 2）

计划正文 Task 25 Step 10 的可执行夹具、Profile、记分与启动方式锁定在：

`docs/agent-plans/2026-09-08-phase-2-task-25-step-10-manual-3x3.md`

本附录锁定 Step 10 操作合同。2026-09-08 Round 2 **不得**改写成通过。Round 3 连续 9/9 已于 2026-09-09 用户验收通过；计划正文 Task 25 Step 10 已勾选。计划正文 Step 11 与用户 Phase 2 完成已于 2026-09-09 记录（见 `docs/task-evidence/phase-2d-task-9-step-11.md` §12–§13）。本附录不授权 commit、push 或 Phase 3。历史 §5d 失败不得改写。

## Appendix: Node sandbox modules overlay（不关闭 Phase 2）

3×3 Node 预检 harness blocker（Vite 无法在只读 `node_modules` symlink 下 `mkdir .vite-temp`）的权威计划是：

`docs/agent-plans/2026-09-08-phase-2-node-sandbox-modules-overlay-plan.md`

用户可见 **Task 44** / `phase-2d-task-28`。Task 44 / `phase-2d-task-28` 已于 2026-09-08 由用户确认验收通过（targeted）；见 `docs/task-evidence/phase-2d-task-28.md` §9。该计划无 Task 45。本附录 **不得** 勾选 Task 25 Step 10/11，不得写成用户 Phase 2 完成。付费 3×3 须另授权，仍走 Task 25 Step 10；预检须用新 Node pin `sha256:12f2470f314aae00f8757a313d78da471472984f7d039bdfdf1c57a553cfc0e7`。2026-09-08 付费轮 Node 类失败，Step 10 保持未勾选；后续修复见 appendix 下节。

## Appendix: Phase 2 post-3×3 reliability fixes（不关闭 Phase 2）

2026-09-08 付费 3×3 记分失败后的四项可靠性修复（无效模型响应、选择器、中断/Durable、Stop）的权威计划是：

`docs/agent-plans/2026-09-08-phase-2-post-3x3-reliability-fixes-plan.md`

用户可见 **Task 45** / `phase-2d-task-29` 起。Task 45–48 已用户验收（targeted）。该计划本身无 Task 49。Step 6 基线修绿见 `docs/agent-plans/2026-09-09-phase-2-step-6-baseline-unblock-plan.md`。计划正文 Task 25 Step 10 已于 2026-09-09 用户验收通过（Round 3 9/9）；见 `docs/task-evidence/phase-2d-task-9-step-10.md` §11。计划正文 Step 11 与用户 Phase 2 完成已于 2026-09-09 记录（见 `docs/task-evidence/phase-2d-task-9-step-11.md` §12–§13）。本附录不授权 commit、push 或 Phase 3。

## Appendix: Step 6 baseline unblock（不关闭 Phase 2）

Step 11 指出的 pytest/ruff/mypy 基线失败，权威计划是：

`docs/agent-plans/2026-09-09-phase-2-step-6-baseline-unblock-plan.md`

用户可见 **Task 49** / `phase-2d-task-33` 已于 2026-09-09 用户验收通过（完整 Step 6；见 `docs/task-evidence/phase-2d-task-33.md` §9）。计划正文 Task 25 Step 11 已于 2026-09-09 用户验收通过（见 `docs/task-evidence/phase-2d-task-9-step-11.md` §12）。用户 Phase 2 已于 2026-09-09 确认完成（见同文件 §13）。本附录不授权 commit、push 或 Phase 3。
