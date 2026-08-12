# Phase 2 Controllable Coding Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在保持自研 Runtime 核心和 Phase 1 回归基线的前提下，按权限递增门禁实现离线 Eval、Planning、Durable Execution、项目内受控 Patch、Sandbox 命令和只读 Git 反馈闭环。

**Architecture:** Phase 2 分成 2A–2D 四个顺序子里程碑。内部领域协议先稳定，再通过 `ToolCallExecutor`、Policy、Capability、`ExecutionBackend` 和 side-effect ledger 组合副作用；SQLite 中的 Durable、授权和副作用表保存控制面恢复事实，现有 `chat_tool_activities` 只保存脱敏、可替换的 UI read model，不得充当 Checkpoint、授权或副作用事实源。JSONL Trace 只负责观察，SSE/UI Event 只负责实时提示。外部框架只作对照，MCP、ACP、A2A 及主机完全访问不进入本计划。

**Tech Stack:** Python 3.12、Pydantic 2、SQLite、FastAPI、React 19、TypeScript、Vite、Vitest、Playwright、Docker CLI、pytest、Ruff、mypy；不新增 Agent 框架依赖。

---

## 0. 计划状态与执行规则

- 状态：planner 已生成实施计划；尚未授权任何 executor Task。
- 2026-08-09 migration 基线已同步到当前 Chat schema v2；本次同步没有开始或授权任何实现 Task。
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
├─ tools/command/         # 结构化 argv、命令分类与 run_command
├─ tools/git/             # 只读 git_status、git_diff、git_log
├─ context/               # 现有预算 + Repo Map、来源、相关性、压缩与缓存
├─ providers/             # 现有 Provider + bounded retry/rate-limit wrapper
├─ runtime/               # AgentLoop、ToolCallExecutor、Trace 和可恢复状态机
└─ chat/                  # Chat 业务状态、API、审批协调和 UI 投影

docker/
├─ agent-sandbox.Dockerfile
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
| 17 | `phase-2d-task-1` | 2D | 结构化命令模型与分类器 | 无执行 |
| 18 | `phase-2d-task-2` | 2D | Sandbox `run_command` | 受限项目命令 |
| 19 | `phase-2d-task-3` | 2D | 只读 Git Tool | 只读 Git |
| 20 | `phase-2d-task-4` | 2D | Repo Map 与 Context Engineering | 只读 |
| 21 | `phase-2d-task-5` | 2D | Provider retry 与 rate limit | 无新权限 |
| 22 | `phase-2d-task-6` | 2D Gate | 全量 Eval、E2E、文档与人工验收 | Phase 2 总验收 |

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

- [ ] **Step 1: 创建 evidence，复制 fixture 到临时目录；不得使用仓库真实文件作为写目标**
- [ ] **Step 2: 写 modify/create、多文件 staging、基线漂移、symlink swap、ADS/控制字符、跨 run patch、拒绝/delete、用户 deny、Capability 重放、第二文件失败全量回滚和四个 crash point 测试**

```python
@pytest.mark.asyncio
async def test_apply_patch_rolls_back_all_files_when_second_replace_fails() -> None:
    before = snapshot(project)
    result = await apply_with_injected_failure(project, fail_on_replace=2)
    assert result.success is False
    assert snapshot(project) == before
    assert (await ledger.latest()).status is EffectStatus.ROLLED_BACK
```

- [ ] **Step 3: 运行 Red**

Run: `conda run -n agent-foundations python -m pytest tests/unit/tools/patch tests/integration/test_controlled_patch_flow.py tests/integration/test_patch_crash_recovery.py -q`
Expected: apply/rollback/authorization/recovery 行为缺失导致断言失败。

- [ ] **Step 4: 实现临时 staging、备份、逐文件 replace、失败逆序回滚和执行后 hash 验证；不支持 delete/rename**
- [ ] **Step 5: 将 `apply_patch` 以 `PROJECT_WRITE` metadata 注册，只允许 Sandbox backend；`DirectToolCallExecutor` 不得执行它**
- [ ] **Step 6: 运行 Green、Docker integration（已授权环境）、安全回归、Ruff/mypy/diff**
- [ ] **Step 7: evidence 记录副作用/回滚/崩溃矩阵并停止**

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

- [ ] **Step 1: 创建 evidence**
- [ ] **Step 2: 写 migration、API shape、profile change conflict、write approval、deny、reload recovery、权限版本变化重新确认和前端可访问性 Red**
- [ ] **Step 3: 运行 Red**

Run:

```powershell
conda run -n agent-foundations python -m pytest tests/unit/chat tests/integration/test_chat_api.py tests/integration/test_chat_approval_flow.py tests/e2e/test_chat_ui.py -q
npm run test:chat
```

Expected: 新 profile/Patch authorization/UI 行为缺失导致断言失败；Phase 1 只读流程继续运行。

- [ ] **Step 4: 实现 schema/API/Runner 投影和 React 状态；HTTP/SQLite 是恢复事实，SSE 只触发刷新**
- [ ] **Step 5: 添加 Eval 任务覆盖四种新 Profile、保留 `PROJECT_READ_ONLY`、权限升级和 write deny/approve；不得开放 Shell/Git**
- [ ] **Step 6: 运行 Phase 2C 全量门禁**

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

- [ ] **Step 7: reviewer 独立验证 profile/approval/sandbox/rollback；等待用户确认 Phase 2C，未确认不得开始 Task 17**

**Acceptance:** 五个有效 Profile、通用 Approval、Capability、Sandbox 和 Patch 写入形成闭环；刷新恢复不重复副作用；电脑完全访问仍不可选。
**Suggested commit after explicit authorization:** `feat: expose controlled patch authorization in chat`

---

## Phase 2D：受限命令、只读 Git 与反馈闭环

### Task 17：结构化命令模型与确定性分类器

**Task ID:** `phase-2d-task-1`
**Evidence:** `docs/task-evidence/phase-2d-task-1.md`
**Depends on:** Phase 2C user-accepted
**TDD:** required

**Files:**

- Create: `src/agent_foundations/tools/command/__init__.py`
- Create: `src/agent_foundations/tools/command/models.py`
- Create: `src/agent_foundations/tools/command/classifier.py`
- Create: `tests/unit/tools/command/__init__.py`
- Create: `tests/unit/tools/command/test_models.py`
- Create: `tests/unit/tools/command/test_classifier.py`

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
    max_output_bytes: int = Field(ge=1, le=1_000_000)

class CommandClassifier:
    def classify(self, spec: CommandSpec, project: ProjectCommandConfig) -> CommandDecision: ...
```

首批 allowlist 只允许参数化收窄后的：

- `python -m pytest <project-relative targets>`
- `python -m ruff check <project-relative targets>`
- `python -m mypy <project-relative targets>`
- `python -m pip check`
- `npm run test:viewer|typecheck:viewer|test:chat|typecheck:chat|build:chat`

拒绝 shell 字符串、`shell=True`、pipeline/redirection、PowerShell/Bash/cmd、`python -c`、包安装、下载器、解释器脚本路径、Git、网络工具和项目外 cwd。

- [ ] **Step 1: 创建 evidence 并记录 Phase 2C 用户验收**
- [ ] **Step 2: 写 allowlist 正例、额外参数收窄、空 argv、绝对 cwd、`..`、ADS/控制字符、shell/metacharacter、package install、网络、Git 和未知命令测试**

```python
@pytest.mark.parametrize("argv", [
    ("pwsh", "-Command", "Get-ChildItem"),
    ("python", "-m", "pip", "install", "x"),
    ("curl", "https://example.invalid"),
    ("git", "status"),
])
def test_classifier_hard_denies_commands_outside_coding_allowlist(argv: tuple[str, ...]) -> None:
    assert classifier.classify(CommandSpec(argv=argv), config).decision == "deny"
```

- [ ] **Step 3: 运行 Red**

Run: `conda run -n agent-foundations python -m pytest tests/unit/tools/command -q`
Expected: CommandSpec/classifier 行为缺失导致 assertion failure。

- [ ] **Step 4: 实现纯数据模型、路径参数校验和 exact-prefix 分类；不调用 subprocess 或 Docker**
- [ ] **Step 5: 决策输出 rule ID、category、normalized argv、Sandbox profile 和 allow/ask/deny；UNKNOWN 默认 deny**
- [ ] **Step 6: 运行 Green、Ruff、mypy、diff**
- [ ] **Step 7: evidence 附命令矩阵并停止**

**Acceptance:** 模型只能表达结构化 argv；分类器确定性、默认拒绝且与 Approval 分离；不存在通用 Shell 入口。
**Suggested commit after explicit authorization:** `feat: classify bounded project commands`

---

### Task 18：Sandbox `run_command` 与进程生命周期

**Task ID:** `phase-2d-task-2`
**Evidence:** `docs/task-evidence/phase-2d-task-2.md`
**Depends on:** Task 17 accepted
**TDD:** required；构建/运行新增 image 需用户当前 Task 明确授权

**Files:**

- Create: `src/agent_foundations/tools/command/run_command.py`
- Create: `src/agent_foundations/execution/workspace.py`
- Create: `docker/agent-sandbox-node.Dockerfile`
- Create: `tests/unit/tools/command/test_run_command.py`
- Create: `tests/unit/execution/test_workspace.py`
- Create: `tests/integration/test_run_command_flow.py`
- Create: `tests/integration/test_run_command_cancellation.py`
- Modify: `src/agent_foundations/execution/models.py`
- Modify: `src/agent_foundations/execution/docker.py`
- Modify: `src/agent_foundations/execution/container_runner.py`
- Modify: `src/agent_foundations/durable/effects.py`
- Modify: `src/agent_foundations/runtime/tool_execution.py`
- Modify: `src/agent_foundations/cli/main.py`
- Modify: `docker/agent-sandbox.Dockerfile`
- Modify: `docker/README.md`

**Tool contract:**

```text
run_command(argv[], cwd=".", timeout_seconds=120, max_output_bytes=200000)
```

命令在 ephemeral workspace 中运行：Task 18 为 `ExecutionRequest` 增加 `workspace_mode="ephemeral_copy"`；真实项目只读挂载为 `/project-ro`，容器内 `/workspace` 为临时可写目录并先复制项目内容；命令结束后丢弃，不把测试缓存、构建产物或代码改动回写主机。需要修改项目只能使用 `apply_patch`。Python image 在本 Task 增加只读 Git binary，供 Task 19 使用；Node image 只承载固定 npm scripts。

- [ ] **Step 1: 创建 evidence，记录本机 Docker/image 可用性；不自动 pull/build**
- [ ] **Step 2: 写 Policy ask/allow/deny、Capability、ephemeral copy、超时、取消进程树、输出截断、UTF-8 replacement、非零退出码、ledger 和恢复不重复执行测试**

```python
@pytest.mark.asyncio
async def test_run_command_discards_workspace_writes() -> None:
    result = await run_allowed_test_that_creates_cache(project)
    assert result.exit_code == 0
    assert not (project / ".pytest_cache").exists()
```

- [ ] **Step 3: 运行 Red（FakeBackend）**

Run: `conda run -n agent-foundations python -m pytest tests/unit/tools/command tests/unit/execution/test_workspace.py tests/integration/test_run_command_flow.py tests/integration/test_run_command_cancellation.py -q`
Expected: run_command/workspace/process lifecycle 行为缺失导致失败。

- [ ] **Step 4: 实现 `RunCommandTool` 和 Controlled executor：classifier → Policy → Approval → Capability → ledger → DockerBackend**
- [ ] **Step 5: Python image 只承载 Python gates；Node image 只承载已固定 npm scripts。若用户批准，构建 image 并记录 base image ID、依赖安装输出和 image ID；不得把 API Key 或 `.env` COPY 进 image**
- [ ] **Step 6: 运行 Green 和经授权 Docker integration；Docker 失败时不得回退 host subprocess**
- [ ] **Step 7: evidence 记录每种终止状态并停止**

**Acceptance:** Agent 能运行明确 allowlist 的项目检查；命令没有 host Shell、网络或持久 workspace 写入；超时/取消能终止整个容器进程树。
**Suggested commit after explicit authorization:** `feat: run bounded commands in disposable sandboxes`

---

### Task 19：结构化只读 Git Tool

**Task ID:** `phase-2d-task-3`
**Evidence:** `docs/task-evidence/phase-2d-task-3.md`
**Depends on:** Task 18 accepted
**TDD:** required

**Files:**

- Create: `src/agent_foundations/tools/git/__init__.py`
- Create: `src/agent_foundations/tools/git/service.py`
- Create: `src/agent_foundations/tools/git/status.py`
- Create: `src/agent_foundations/tools/git/diff.py`
- Create: `src/agent_foundations/tools/git/log.py`
- Create: `tests/unit/tools/git/__init__.py`
- Create: `tests/unit/tools/git/test_service.py`
- Create: `tests/unit/tools/git/test_tools.py`
- Create: `tests/integration/test_git_read_tools.py`
- Modify: `src/agent_foundations/cli/main.py`

**Tool contracts:**

```text
git_status()
git_diff(path=null, staged=false, max_bytes=200000)
git_log(limit=20)
```

Model 不提供任意 Git 参数、ref、format 或 command。Service 固定环境：`GIT_OPTIONAL_LOCKS=0`、`GIT_TERMINAL_PROMPT=0`、`GIT_CONFIG_NOSYSTEM=1`；固定使用 `--no-ext-diff`，Repository 只读挂载，输出有上限。

- [ ] **Step 1: 创建 evidence；所有 Git 测试使用临时仓库，不修改当前仓库**
- [ ] **Step 2: 写 status/diff/log shape、untracked、staged flag、路径校验、输出上限、非仓库、submodule/外部 diff 禁用和禁止任意参数测试**
- [ ] **Step 3: 运行 Red**

Run: `conda run -n agent-foundations python -m pytest tests/unit/tools/git tests/integration/test_git_read_tools.py -q`
Expected: Git service/Tool 行为缺失导致断言失败。

- [ ] **Step 4: 实现固定 argv 的 GitReadService 和三个 Tool；通过 Sandbox read-only backend 执行，不进入 `run_command` allowlist**
- [ ] **Step 5: metadata 固定 `side_effect=NONE`、resource=project repository、operation=read；不存在 add/commit/push/reset/checkout API**
- [ ] **Step 6: 运行 Green、Registry/Policy/CLI 回归和质量门禁**
- [ ] **Step 7: evidence 证明当前真实仓库未被测试修改并停止**

**Acceptance:** Agent 可读取有限 Git 状态、Diff 和历史；不能构造任意 Git 命令或产生 index/worktree/remote 副作用。
**Suggested commit after explicit authorization:** `feat: add structured read-only git tools`

---

### Task 20：Repo Map、相关性与 Context Engineering

**Task ID:** `phase-2d-task-4`
**Evidence:** `docs/task-evidence/phase-2d-task-4.md`
**Depends on:** Task 19 accepted
**TDD:** required

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
    def build(self, messages: tuple[Message, ...],
              sources: tuple[ContextSource, ...] = ()) -> tuple[Message, ...]: ...
```

Repo Map 使用 Python `ast` 和受限 TypeScript import/export 解析，不运行项目代码；跳过 `.git`、依赖、构建产物、敏感文件、二进制和 symlink。Cache key 使用 root、相对路径、size、mtime_ns 和内容 hash；命中仍重验边界。

- [ ] **Step 1: 创建 evidence**
- [ ] **Step 2: 写确定性排序、预算优先级、来源可见、Python/TS map、循环 import、敏感/二进制/symlink 跳过、缓存失效、tiny budget 和 mandatory overflow 测试**
- [ ] **Step 3: 运行 Red**

Run: `conda run -n agent-foundations python -m pytest tests/unit/context tests/integration/test_agent_loop.py -q`
Expected: ContextSource/Repo Map/cache 行为缺失导致失败；现有 budget tests 仍运行。

- [ ] **Step 4: 实现确定性 Repo Map、词项相关性、来源排序、分层截断和有界 LRU cache；不调用模型做压缩**
- [ ] **Step 5: Trace `context.snapshot` 记录 source ID、provenance、字符数、分数、截断/缓存决策，不默认复制完整源码**
- [ ] **Step 6: 运行 Green、AgentLoop/Eval 回归、Ruff/mypy/diff**
- [ ] **Step 7: evidence 记录 Context Budget 前后 Eval 指标并停止**

**Acceptance:** Context 来源和舍弃决策可见、确定性且受预算控制；Repo Map/Cache 不越过 PathPolicy 或敏感规则。
**Suggested commit after explicit authorization:** `feat: add observable repo map context selection`

---

### Task 21：Provider Retry、Rate Limit 与缓存边界

**Task ID:** `phase-2d-task-5`
**Evidence:** `docs/task-evidence/phase-2d-task-5.md`
**Depends on:** Task 20 accepted
**TDD:** required

**Files:**

- Create: `src/agent_foundations/providers/resilient.py`
- Create: `src/agent_foundations/runtime/rate_limit.py`
- Create: `tests/unit/providers/test_resilient.py`
- Create: `tests/unit/runtime/test_rate_limit.py`
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

class TokenBucketRateLimiter:
    async def acquire(self, cost: int = 1) -> None: ...

class ResilientModelProvider:
    async def complete(self, request: ModelRequest) -> ModelResponse: ...
```

只重试明确 transient 的 rate-limit/timeout/temporary provider 错误；认证、无效响应、Policy、Tool 和上下文错误不重试。测试注入 clock/sleeper，不使用真实 sleep。OpenAI SDK `max_retries=0`，避免 Adapter 与 wrapper 双重重试。模型响应不做隐式缓存；Task 20 cache 只保存确定性 Repo Map/Context 派生物。

- [ ] **Step 1: 创建 evidence**
- [ ] **Step 2: 写 bounded backoff、Retry-After 上限、成功后停止、不可重试错误一次调用、取消传播、token bucket 公平性和无真实 sleep 测试**
- [ ] **Step 3: 运行 Red**

Run: `conda run -n agent-foundations python -m pytest tests/unit/providers/test_resilient.py tests/unit/runtime/test_rate_limit.py tests/unit/providers/test_openai_compatible.py tests/integration/test_agent_loop.py -q`
Expected: wrapper/limiter 行为缺失导致断言失败。

- [ ] **Step 4: 实现注入式 Clock/Sleeper、bounded retry 和 limiter；Trace 每次 retry 只记录错误类型、attempt 和 delay**
- [ ] **Step 5: CLI Provider 构建改为 SDK 无重试 + `ResilientModelProvider`；FakeModel/Eval 可绕过 limiter 保持确定性**
- [ ] **Step 6: 运行 Green、Provider/AgentLoop/Eval 回归和质量门禁**
- [ ] **Step 7: evidence 记录错误分类矩阵并停止**

**Acceptance:** retry/rate limiting 有界、可取消、可测试；不存在重复 retry 层或缓存导致的陈旧模型决定。
**Suggested commit after explicit authorization:** `feat: add bounded provider resilience controls`

---

### Task 22：Phase 2 全量 Eval、E2E、文档与总验收

**Task ID:** `phase-2d-task-6`
**Evidence:** `docs/task-evidence/phase-2d-task-6.md`
**Depends on:** Task 21 accepted
**TDD:** required for integration/E2E；文档部分为 `not-applicable`

**Files:**

- Create: `tests/fixtures/evals/phase-2-tasks-v1.json`
- Create: `tests/fixtures/evals/phase-2-responses-v1.json`
- Create: `docs/eval-baselines/phase-2-v1.json`
- Create: `docs/learning-notes/05-offline-eval-and-planning.md`
- Create: `docs/learning-notes/06-durable-execution.md`
- Create: `docs/learning-notes/07-security-and-controlled-tools.md`
- Create: `tests/integration/test_phase2_coding_agent.py`
- Modify: `tests/e2e/test_chat_ui.py`
- Modify: `README.md`
- Modify: `docs/agent-plans/2026-07-20-agent-engineering-learning-design.md`
- Modify: `docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md`

**End-to-end scenario:** FakeModel 创建计划 → 读取代码 → 生成/校验 Patch → Policy/Approval → `apply_patch` → `run_command` → `git_diff` → 根据失败重规划 → 完成；测试在临时 Git 仓库和 Sandbox 中运行，不触碰真实项目、不调用真实模型。

```python
@pytest.mark.asyncio
async def test_phase2_agent_recovers_after_patch_and_test_feedback(
    temporary_git_project: Path,
) -> None:
    result = await run_scripted_phase2_flow(temporary_git_project)
    assert result.status is DurableRunStatus.COMPLETED
    assert result.patch_effect_count == 1
    assert result.command_effect_count == 1
    assert result.git_writes == ()
```

- [ ] **Step 1: 创建 evidence，记录所有前序 Task evidence、reviewer 结论、Docker image ID 和用户验收状态**
- [ ] **Step 2: 先写完整 FakeModel E2E Red，覆盖 approve、deny、cancel、crash-after-effect、lease takeover、profile version change、command timeout 和 Git read-only**
- [ ] **Step 3: 运行 Red**

Run:

```powershell
conda run -n agent-foundations python -m pytest tests/integration/test_phase2_coding_agent.py tests/e2e/test_chat_ui.py -q
npm run test:chat
```

Expected: fixture/最终接线或 UI 行为缺失导致目标断言失败；不得以环境、Docker 未授权或导入错误作为 Red。

- [ ] **Step 4: 只补齐最终 fixture、接线和文档，不在总验收 Task 新增架构能力**
- [ ] **Step 5: 运行 Phase 1 与 Phase 2 Eval，保存可比较报告；解释成功率、步骤数、无效 Tool、安全拒绝、审批、恢复、Token 和延迟变化，不把新增功能本身当作改进证据**

Run:

```powershell
conda run -n agent-foundations agent-foundations evaluate --task-set tests/fixtures/evals/phase-1-tasks-v1.json --responses tests/fixtures/evals/phase-1-responses-v1.json --output .agent-foundations/evals/final-phase-1.json --runtime-revision working-tree
conda run -n agent-foundations agent-foundations evaluate --task-set tests/fixtures/evals/phase-2-tasks-v1.json --responses tests/fixtures/evals/phase-2-responses-v1.json --output .agent-foundations/evals/final-phase-2.json --runtime-revision working-tree
```

- [ ] **Step 6: 运行完整新鲜质量门禁**

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

Expected: 每条命令退出 `0`；报告本次真实 pass count 和警告，不复制旧结果。

- [ ] **Step 7: 运行经用户授权的 Docker 安全验收**

Manual/automated checklist:

1. Container 无网络、非 root、资源受限、只挂载指定项目。
2. `PROJECT_READ_ONLY` 拒绝所有写/命令。
3. `ASK_ALWAYS` 对 Patch/命令逐次询问。
4. `PROJECT_FULL_ACCESS` 只自动执行项目级已实现能力，不能读取项目外、访问网络或执行任意 Shell。
5. `CUSTOM` 未匹配规则默认拒绝。
6. 恢复不会重复 committed Patch/命令；UNKNOWN effect 要求人工 reconcile。
7. 同一 run 只有一个有效 owner；lease takeover 可审计。
8. Git Tool 不能写 index、worktree 或 remote。
9. UI 刷新从 HTTP/SQLite 恢复，不从 SSE 猜测事实。
10. Registry 不包含 MCP、Memory、Sub-Agent、Browser、network、Git write 或 `HOST_FULL_ACCESS`。

- [ ] **Step 8: 更新学习笔记和 README，解释自研核心、Adapter 边界、Eval 结论、Durable Execution、安全分层和刻意未解决的能力**
- [ ] **Step 9: 只在全部证据真实存在后更新本计划完成复选框；reviewer 独立复验并等待用户 Phase 2 总验收**
- [ ] **Step 10: 未获 commit/push 明确授权时停止，不进入 Phase 3**

**Acceptance:** Agent 能计划、生成和批准 Patch、在 Sandbox 运行受限项目检查、读取 Git 反馈并安全恢复；Eval 可比较 Phase 1/2；所有危险动作可见、可拒绝、可取消、可追踪；Phase 2 非目标仍不可用。
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
| 受限 `run_command` | 17–18 | classifier/process/Sandbox tests |
| 只读 Git | 19 | temporary repository integration tests |
| Repo Map、相关性、预算、压缩、缓存 | 20 | context determinism/provenance/cache tests |
| retry 与 rate limiting | 21 | injected clock/sleeper tests |
| Eval 回归与阶段总验收 | 5、11、16、22 | per-gate reports、full gates、manual safety |
| MCP/ACP/A2A/SSE/Trace 协议分工保持 | 22 | Registry audit、learning notes、existing SSE/Trace regression |
| 不提前实现主机完全访问 | 12、16、22 | Profile/API/Registry negative tests |

## 4. 明确非目标

- 不实现 MCP、ACP、A2A、Memory、Skills、Hooks、Sub-Agent。
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

不得把 22 个 Task 合并成一个 executor prompt，也不得让 executor 自行选择下一个 Task。
