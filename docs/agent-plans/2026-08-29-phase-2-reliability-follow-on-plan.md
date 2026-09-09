# Phase 2 Reliability Follow-on Plan

**Date:** 2026-08-29  
**Status:** Task 30–34 / `phase-2d-task-14`–`phase-2d-task-18` 已用户验收通过（targeted）；可靠性 follow-on 计划内 Task 已全部验收。Task 30 reviewer P2（CRLF `old_lines`）改由 `docs/agent-plans/2026-09-08-phase-2-pre-3x3-gap-remediation-plan.md` Task 43 跟踪，不重开 Task 30。不关闭 Task 25 / Phase 2 用户验收 / Step 10/11  
**Role:** planner 维护；不实现生产代码  
**Parent:** `docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md`  
**Does not replace:** Task 25、Phase 2 用户验收、Step 10/11

## 0. 定位

本计划是 Phase 2 已实现能力上的**可靠性 follow-on**，不是 Phase 3，也不是对 2026-08-27 付费 3×3 失败结果的改写。

采纳的方向（互补，禁止合成一个超大 Task）：

```text
结构化修改 → 减少坏 Diff
SHA-256 元数据 → 消除模型猜哈希
错误类型驱动 → 减少无效重试
更好的提示和工具描述 → 提高模型遵循率
分层步数预算 → 防止局部循环耗尽总预算
```

**明确不关闭：**

- Task 25 Step 10 / Step 11 保持未勾选，直到用户另授权新的付费 3×3 并 9/9。
- 不得把本计划任一 Task 勾选写成「Phase 2 完成」。
- 不得为了本计划安装 MCP、Memory、Skills、Hooks、Sub-Agent、Browser、网络 Tool、项目外写入、任意 Shell、Git 写、`TrustedHostExecutor`。
- 不得在本计划授权范围内调用真实付费 API 或重开 3×3。Offline Eval 只使用 FakeModel / 既有 fixture。
- 命令白名单仍以 `src/agent_foundations/tools/command/config.py` 的精确 argv 为准。Node 测试必须是 `npm run test:chat` / `typecheck:chat` / `build:chat`（及 viewer 别名），不得发明 `npm test`。

**已存在、不得重复建设：**

- `validate_patch` 已要求 `baselines[].sha256`；`apply_patch` 已在落盘前再核基线。缺口是 **`read_file` 不返回全文件 SHA-256 / size / encoding**，模型只能猜哈希。
- Chat 已在 appendix Task 29 注册 `set_plan` / `update_plan_step` / `replan`。缺口是 **每 turn 新建 `PlanController`、`PlanningMode.DISABLED`、无 Chat UI / 无跨 turn 持久化**。不得再做一次「接线工具」Task。
- Unified Diff 仍是 durable apply 合同。结构化修改必须 **编译成** 现有 `parse_and_validate_patch` → Policy → Approval → Capability → Sandbox → `apply_patch` 管道，不得另开写路径。

## 1. 安全不变量

结构化修改 **不得** 绕过：

```text
路径检查
→ SHA-256 基线检查（全文件字节）
→ 旧内容匹配
→ Diff 校验
→ Policy
→ Approval
→ Capability
→ Sandbox
→ apply_patch
```

截断的 `read_file` 行范围 **不得** 把部分内容的哈希冒充全文件 SHA-256。全文件哈希必须来自磁盘上完整可读字节（受现有 `max_bytes` 限制；超限仍失败，不返回假哈希）。

## 2. Task 顺序

| 用户可见 | Task ID | Evidence | 主题 |
|---|---|---|---|
| Task 30 | `phase-2d-task-14` | `docs/task-evidence/phase-2d-task-14.md` | Patch 合同升级 |
| Task 31 | `phase-2d-task-15` | `docs/task-evidence/phase-2d-task-15.md` | 错误类型驱动恢复 |
| Task 32 | `phase-2d-task-16` | `docs/task-evidence/phase-2d-task-16.md` | Chat Planning 持久化与 UI |
| Task 33 | `phase-2d-task-17` | `docs/task-evidence/phase-2d-task-17.md` | Prompt / Schema / Tool 描述 |
| Task 34 | `phase-2d-task-18` | `docs/task-evidence/phase-2d-task-18.md` | 分层预算 + Offline Eval 测步数 |

全部完成后 **停止**。是否重做付费 3×3 由用户另授权，仍走 Task 25 Step 10 协议，不得并入 Task 34。

一次只执行用户确认的一个 Task。未确认的 prompt 不得实施。Task 30 / `phase-2d-task-14` 已于 2026-08-29 用户验收通过；evidence 见 `docs/task-evidence/phase-2d-task-14.md` §9。Task 31 / `phase-2d-task-15` 已于 2026-08-29 用户验收通过；evidence 见 `docs/task-evidence/phase-2d-task-15.md` §9。Task 32 / `phase-2d-task-16` 已于 2026-08-29 用户验收通过；evidence 见 `docs/task-evidence/phase-2d-task-16.md` §9。Task 33 / `phase-2d-task-17` 已于 2026-08-29 用户验收通过；evidence 见 `docs/task-evidence/phase-2d-task-17.md` §9。Task 34 / `phase-2d-task-18` 已于 2026-09-04 用户验收通过；evidence 见 `docs/task-evidence/phase-2d-task-18.md` §10。本 follow-on 计划内 Task 已全部验收。不得勾选 Task 25 Step 10/11。是否重做付费 3×3 须用户另授权。

---

## Task 30 / `phase-2d-task-14`：Patch 合同升级

### Goal

让模型用 **结构化修改 + `read_file` 返回的全文件 SHA-256** 提出补丁；Runtime 生成 unified Diff 后走现有校验与 apply。保留纯 Diff 调用路径（测试与 CLI 仍可用）。

### Stable contract（本 Task 锁定）

`read_file` 成功 metadata **必须** 增加（名称锁定）：

```text
sha256          # 全文件 UTF-8 字节的 SHA-256，64 位小写 hex
size_bytes      # 全文件字节数
encoding        # 本阶段固定 "utf-8"
truncated       # 已有：返回行范围不是全文
```

现有 `path` / `start_line` / `returned_lines` 保留。`truncated=true` 时 `sha256` 仍是 **全文件** 哈希，不得改成切片哈希。

`validate_patch` 参数互斥：

```text
A. 现有：diff + baselines（回归必须绿）
B. 新增：changes（结构化修改）；禁止同时传 diff
```

`changes` 元素锁定为：

```text
path              # 项目相对 POSIX 路径
expected_sha256   # 必须等于 read_file 返回的 sha256；禁止模型编造
start_line        # 1-based
old_lines         # 将被替换的现有行（不含换行符），可为空列表表示纯插入
new_lines         # 替换后的行，可为空列表表示纯删除
```

Runtime 行为：

1. 按 path 读磁盘全文，计算 SHA-256；与 `expected_sha256` 不一致 → 现有基线不匹配错误族（不得静默改文件）。
2. 用 `old_lines` 在 `start_line` 对齐匹配；失败 → 内容不匹配错误，不生成 Diff。
3. 生成 unified Diff，**由 Runtime 填写** `baselines`（path + 实测 sha256）。
4. 调用现有 `parse_and_validate_patch`；成功则与今日一样写入 proposal repository。
5. `apply_patch` 仍只接受 `patch_id`；落盘前再次核对 SHA-256。本 Task **不改** Policy 矩阵、Approval 语义、Sandbox。

禁止：新的写 Tool；跳过 `validate_patch` 直接 apply；用行切片哈希代替全文件哈希；放宽路径 / symlink / 项目外路径。

### Files

- `src/agent_foundations/tools/filesystem/read_file.py`
- `src/agent_foundations/tools/patch/validate_patch.py`
- `src/agent_foundations/tools/patch/execution.py`
- 新增最小模块例如 `src/agent_foundations/tools/patch/structured.py`（结构化 → Diff）
- 对应 `tests/tools/filesystem/`、`tests/tools/patch/`
- Chat / Trace 若展示 validate 参数，sanitize 须覆盖 `changes`（不得把文件正文写入 Trace 明文超出现有 diff 策略）

### Tests（Red 必须在改生产代码前）

- `read_file` 返回 `sha256` / `size_bytes` / `encoding`；与 `hashlib.sha256(raw).hexdigest()` 一致。
- 只读部分行时 `truncated=true` 且 `sha256` 仍为全文件。
- `changes` 编译出的 Diff 经 `parse_and_validate_patch` 成功；`apply_patch` 后文件内容正确。
- 错误 `expected_sha256` → 不写文件。
- `old_lines` 与磁盘不符 → 不写文件。
- 同时传 `diff` 与 `changes` → 参数错误。
- 仅 `diff`+`baselines` 的既有测试全部保持绿。

### Verification contract

```text
Target tests：
conda run -n agent-foundations python -m pytest tests/tools/filesystem tests/tools/patch -q

Affected regression tests：
conda run -n agent-foundations python -m pytest tests/runtime tests/cli tests/eval -q --ignore=tests/eval/test_docker_sandbox_e2e.py --ignore=tests/eval/test_docker_command_artifact_e2e.py --ignore=tests/eval/test_sibling_docker_sandbox_e2e.py

Full suite：not-required
Full suite reason：不扩大写权限；apply 仍走既有 patch_id。Patch 校验是安全边界，故 Target 必须覆盖全部 filesystem+patch 测试，Affected 覆盖 runtime/cli/eval（排除 Docker E2E）。

Additional gates：
conda run -n agent-foundations python -m ruff check src/agent_foundations/tools/filesystem src/agent_foundations/tools/patch tests/tools/filesystem tests/tools/patch
conda run -n agent-foundations python -m mypy src/agent_foundations/tools/filesystem src/agent_foundations/tools/patch tests/tools/filesystem tests/tools/patch
git diff --check
```

Docker / 付费 API / commit：禁止。

**User acceptance:** 2026-08-29 用户确认 `确认「Task 30 / phase-2d-task-14 用户验收通过」`；记录于本计划与 `docs/task-evidence/phase-2d-task-14.md` §9。范围仅限 `read_file` 全文件 SHA-256 元数据、`validate_patch` 的互斥 `changes` 路径、Runtime 编译 unified Diff 后走既有 `parse_and_validate_patch`，以及 sanitize 覆盖 `changes` 正文。`apply_patch` 仍只接受 `patch_id`。独立复验为 targeted：`tests/tools/filesystem` + `tests/tools/patch` 8 passed；合同路径 `tests/runtime` / `tests/cli` / `tests/eval` 不存在；映射 affected + 既有 unit filesystem/patch 331 passed；ruff/mypy 本包通过。TDD 过程证据为 complete；本次确认不独立见证历史 Red→Green。reviewer P2（`read_file.splitlines()` 与 `structured._line_texts` 对 CRLF 不一致）与 P3（apply 证明未走 Chat `apply_patch` Tool；`ValidatePatchTool.description` 仍只写 unified diff）不因本次确认要求立即返工。本确认不是 Task 25 完成，不是用户 Phase 2 完成；Step 10/11 保持未勾选。Task 31 仍需单独授权。未授权 commit、push、付费 3×3 或 Phase 3。

---

## Task 31 / `phase-2d-task-15`：错误类型驱动恢复

### Goal

用 **确定性 Runtime 策略** 处理已知失败，而不是再调一次模型去「碰运气」。不是第二个 Agent。禁止只改 Prompt。禁止引入 schema v11。禁止改 Policy 矩阵、Approval 语义、Sandbox、命令白名单、`max_steps`（分层预算是 Task 34）。不要修 Task 30 的 CRLF `old_lines` P2。

### 现状（实现时对齐，不要重复建设）

- Patch 错误码已存在：`PATCH_BASELINE_MISMATCH`、`PATCH_PARSE_ERROR`、`PATCH_PATH_REJECTED`、`PATCH_VALIDATION_ERROR`（含 `old_lines` 不匹配）、`PATCH_INVALID_ARGUMENTS`、`POLICY_DENIED`。
- `run_command` 在测试失败时仍可能 `success=True`，失败信息在 metadata 的 CommandFeedback（`exit_code`、`failed`、`artifact_id`）。不得用 `ToolResult.success` 判断「测试失败」。
- Chat 审批：`ApprovalCoordinator.request` 在 `WAITING_APPROVAL` 时阻塞 tool execute，期间本来不会 `_request_model`。本 Task 仍须加守卫：未决审批不得再发起 completion。CLI 在无 `approval_decider` 时会返回 `APPROVAL_REQUIRED`，随后 loop 仍会再调模型——这是要堵的洞。
- 仓库没有 `tests/runtime/` 或 `tests/cli/test_chat_control_plane.py`。验证必须用下面锁定的真实路径。

### Stable mapping（错误码封闭集合）

策略是纯函数，输入为「最近一次相关 Tool 结果 + 模型即将发起的下一次 Tool 调用」，输出为是否允许执行 / 是否允许下一轮 `complete`。状态从 transcript 里的 tool 消息推导，不新增 SQLite 版本。

```text
STALE = {PATCH_BASELINE_MISMATCH, PATCH_VALIDATION_ERROR}
→ 下一次 Tool 必须是 read_file，且 path 属于失败那次 validate_patch/apply_patch 涉及的路径。
  在满足之前，禁止再执行 validate_patch 或 apply_patch（含相同或不同 payload）。
  拦截时返回 success=false，error_code=RECOVERY_READ_REQUIRED，不调用下游 executor。

PARSE = {PATCH_PARSE_ERROR, PATCH_INVALID_ARGUMENTS}
→ 禁止再执行与失败调用字节级相同的 validate_patch payload
  （name + canonical JSON arguments 的 SHA-256）。
  拦截时 error_code=RECOVERY_IDENTICAL_PAYLOAD_BLOCKED。
  允许不同的 changes/diff。

HARD_STOP_PAYLOAD = {PATCH_PATH_REJECTED, POLICY_DENIED, APPROVAL_DENIED}
→ 禁止再执行同一 tool 名 + 同一 canonical arguments。
  拦截时 error_code=RECOVERY_RETRY_BLOCKED。
  不结束整个 Agent run；模型仍可改用其他 Tool 或给出最终说明。

COMMAND_NEEDS_FEEDBACK
→ 最近一次 run_command 的 metadata 含 artifact_id，且
  exit_code not in {0, None} 或 timed_out 或 failed>0。
→ 在对该 artifact_id 成功执行 read_command_output 或 search_command_output 之前，
  禁止再执行 argv 规范相等的 run_command。
  拦截时 error_code=RECOVERY_FEEDBACK_READ_REQUIRED。

AWAITING_APPROVAL
→ Chat/durable 运行为 WAITING_APPROVAL，或最近 Tool 结果 error_code=APPROVAL_REQUIRED。
→ 不得调用 ModelProvider.complete。
  Chat 阻塞在 coordinator 内即可；CLI/无 decider 时不得为了重试同一写操作再烧一步。
```

Canonical arguments：`json.dumps(arguments, sort_keys=True, separators=(",", ":"), ensure_ascii=False)` 的 UTF-8 SHA-256。

### Files

- 新增 `src/agent_foundations/runtime/recovery.py`（纯策略 + 稳定枚举）
- `src/agent_foundations/runtime/loop.py` 最小接线：执行 Tool 前、发起 `_request_model` 前
- Chat 仅在现有 WAITING_APPROVAL 路径上加「不 complete」的测试或最小守卫；不改审批协议
- `tests/unit/runtime/test_recovery.py`（新建，Red 主文件）
- 必要时最小改 `tests/integration/test_agent_loop.py`

### Tests（Red 必须在改生产代码前）

- STALE 后立刻 `validate_patch` → 不执行，`RECOVERY_READ_REQUIRED`；随后同 path `read_file` 则允许再 validate
- PARSE 后提交相同 `changes`/`diff` → `RECOVERY_IDENTICAL_PAYLOAD_BLOCKED`；改 payload 则允许
- `PATCH_PATH_REJECTED` / `POLICY_DENIED` 后相同 payload → `RECOVERY_RETRY_BLOCKED`；不同 path/参数允许
- 测试失败 CommandFeedback 后相同 argv `run_command` → `RECOVERY_FEEDBACK_READ_REQUIRED`；读 artifact 后允许
- `APPROVAL_REQUIRED` 或 WAITING_APPROVAL 时 `complete()` 不被调用（FakeProvider 计数）
- 既有 `tests/integration/test_command_feedback_agent_flow.py` 与 `tests/integration/test_agent_loop.py` 保持绿

### Verification contract

```text
Target tests：
conda run -n agent-foundations python -m pytest tests/unit/runtime/test_recovery.py -q

Affected regression tests：
conda run -n agent-foundations python -m pytest tests/unit/runtime tests/integration/test_agent_loop.py tests/integration/test_command_feedback_agent_flow.py tests/unit/tools/patch tests/unit/chat/test_approvals.py tests/unit/chat/test_tool_execution.py -q

Full suite：not-required
Full suite reason：不扩大 Tool 权限；改变的是失败后是否执行/是否再调模型。

Additional gates：
conda run -n agent-foundations python -m ruff check src/agent_foundations/runtime tests/unit/runtime
conda run -n agent-foundations python -m mypy src/agent_foundations/runtime tests/unit/runtime
git diff --check
```

Windows：`conda run` 下 pytest 若 GBK 崩溃，evidence 允许 `$env:PYTHONIOENCODING='utf-8'`，不得缩小合同。禁止 Docker、付费 API、commit。

依赖：Task 30 合同已在工作区。

**User acceptance:** 2026-08-29 用户确认 `确认「Task 31 / phase-2d-task-15 用户验收通过」`；记录于本计划与 `docs/task-evidence/phase-2d-task-15.md` §9。范围仅限确定性 Runtime 从 transcript 推导义务、拦截 `validate_patch`/`apply_patch`/`run_command` 的已知无效重试（不调用下游 executor），以及 `APPROVAL_REQUIRED` 时不再调用 `complete()`。独立复验为 targeted：Target `tests/unit/runtime/test_recovery.py` 10 passed；Affected 269 passed；ruff/mypy 22 files 通过；`git diff --check` exit 0。TDD 过程证据为 complete；本次确认不独立见证历史 Red→Green。reviewer P3（PARSE 按失败 tool 名含 `apply_patch`；loop 未传入 Chat `run_status=waiting_approval`；STALE 依赖 arguments/metadata 路径；`evaluate_tool_call` 用原始 arguments）不因本次确认要求立即返工。本确认不是 Task 25 完成，不是用户 Phase 2 完成；Step 10/11 保持未勾选。Task 32 仍需单独授权。未授权 commit、push、付费 3×3 或 Phase 3。Task 30 CRLF P2 与 schema v11 仍不在本确认范围。

---

## Task 32 / `phase-2d-task-16`：Chat Planning 持久化与 UI

### Goal

每个 Conversation **一份** Plan；跨 turn 恢复；重规划次数受限（沿用 `ExecutionPlan.max_replans`，默认 2）；只有真实非 planning Tool 成功结果才能作为 `evidence_refs`（现有 `ExecutionFactJournal`，不要削弱）；计划变化进 Trace（已有 `plan.created` / `plan.step.updated` / `plan.replanned`）与 Chat UI。

**不是** 再次注册 planning 工具（Task 29 已做）。**不是** 把 `PlanningMode` 改成 `REQUIRED`。

### 必须改掉的现状

- `cli/main.py` `runtime_factory` 每个 Chat turn `PlanController()` 新实例，且 `AgentLoop.run` 把 `plan_snapshot=None`。Checkpoint 按 **run/session_id** 存，下一用户 turn 是新 session，所以计划丢了。
- 修复方式：从**同一 conversation** 先前 run 的 durable checkpoint 读取最新 `plan_snapshot`，经 `AgentLoop.run(..., plan_snapshot=...)` 注入 `initial_state` 并 `PlanController.restore`。禁止进程级单例 controller（会串 conversation）。
- Chat 前端无 plan 展示；`ConversationStateResponse` 无 plan 字段；SSE 无 plan 事件。
- `PlanningMode.DISABLED` 保持默认。

持久化 **禁止 schema v11**。权威事实是 `run_checkpoints.state_json` 里已有的 `plan_snapshot`。用 `runs.conversation_id` + `runs.session_id` = `durable_runs.run_id` 查找，不得把 `chat_tool_activities` 当事实源。

### Stable contract

```text
跨 turn
→ 同一 conversation 第二次 turn 的 PlanController 必须 restore 第一次 turn 结束时的
  plan_id / version / replan_count / steps 状态。
→ set_plan 在已有计划时仍失败（现有 PlanError）；继续用 update_plan_step / replan。

隔离
→ conversation B 不得读到 A 的 plan。

重规划
→ 沿用 PlanController：replan_count >= max_replans → PlanReplanLimitError。
  跨 turn 后 replan_count 不得清零。

证据
→ update_plan_step 标 COMPLETED 仍须指向本 session 内成功的非 planning tool_call_id。
  本 Task 不要求把 ExecutionFactJournal 跨 turn 持久化。

Chat 读模型（可刷新、可 SSE）
→ GET conversation state 增加可选 plan，字段锁定：
  plan_id, version, goal, replan_count, max_replans,
  steps[{step_id, status, description}]
  不得把 evidence 正文或文件内容塞进 UI。
→ 新增 ChatEventType.PLAN_UPDATED = "plan.updated"，由既有 Trace
  plan.created / plan.step.updated / plan.replanned 投影。
  前端展示 goal + 步骤状态；刷新后仍能从 GET state 恢复。
```

禁止：`PlanningMode.REQUIRED`；CLI REPL REQUIRED 抄进 Chat；新写 Tool；改 Policy；修 Task 30 CRLF P2 或 Task 31 reviewer P3。

### Files（最小）

- `src/agent_foundations/runtime/loop.py`：`run(..., plan_snapshot=)`
- `src/agent_foundations/chat/runner.py`：turn 开始加载本 conversation 最新 plan
- 查找 checkpoint 的最小仓库方法（durable 或 chat repository）
- `src/agent_foundations/chat/events.py`、`models.py`、`api.py`
- `web/chat/` 状态类型、reducer、一个小的 Plan 面板组件
- `tests/integration/test_chat_planning_tools.py` 扩展跨 turn
- 新建 `tests/unit/chat/test_plan_persistence.py`
- 新建 `tests/chat/plan-panel.test.tsx`（或等价 vitest）

仓库没有 `tests/cli/`、`tests/planning/`、`tests/runtime/` 根目录；验证用下面真实路径。

### Tests（Red 必须在改生产代码前）

- 同一 conversation 两 turn：第二 turn 看到同一 `plan_id`，且 `set_plan` 不再创建第二份计划
- 另一 conversation 无该计划
- `replan_count` 跨 turn 保留，超过 `max_replans` 仍拒绝
- GET state 在 set_plan 后返回锁定字段
- SSE/投影：`plan.updated` 进入 Chat 事件（单测即可）
- UI：步骤状态可见（vitest）
- `tests/integration/test_chat_planning_tools.py` 既有「可选 planning + DISABLED」保持绿

### Verification contract

```text
Target tests：
conda run -n agent-foundations python -m pytest tests/integration/test_chat_planning_tools.py tests/unit/chat/test_plan_persistence.py tests/unit/chat/test_events.py tests/unit/planning -q
npm run test:chat
npm run typecheck:chat

Affected regression tests：
conda run -n agent-foundations python -m pytest tests/unit/chat tests/integration/test_chat_api.py tests/integration/test_chat_planning_tools.py tests/unit/planning tests/unit/runtime/test_state_machine.py -q

Full suite：not-required
Full suite reason：不扩大写/命令权限。有 UI 故必须跑 npm chat 测试与 typecheck。

Additional gates：
conda run -n agent-foundations python -m ruff check src/agent_foundations/chat src/agent_foundations/runtime/loop.py src/agent_foundations/planning tests/unit/chat tests/unit/planning tests/integration/test_chat_planning_tools.py
conda run -n agent-foundations python -m mypy src/agent_foundations/chat src/agent_foundations/runtime/loop.py src/agent_foundations/planning tests/unit/chat tests/unit/planning
git diff --check
```

Windows：`$env:PYTHONIOENCODING='utf-8'` 若 conda pytest GBK 崩溃。禁止 Docker、付费 API、commit、Playwright 全量 e2e（除非 vitest 无法覆盖而必须补一条；默认不跑 `tests/e2e/test_chat_ui.py`）。

依赖：Task 31 已验收。

**User acceptance:** 2026-08-29 用户确认 `确认「Task 32 / phase-2d-task-16 用户验收通过」`；记录于本计划与 `docs/task-evidence/phase-2d-task-16.md` §9。范围仅限同一 conversation 跨 turn 从 durable checkpoint 恢复 `plan_snapshot`、注入该 turn 新建的 `PlanController`（非进程级单例）、GET state 可选 `plan` 锁定字段、Trace `plan.*` 投影为 `plan.updated`、Chat UI goal + 步骤状态并可从 GET 刷新恢复。未把 `PlanningMode` 改为 REQUIRED，未再注册 planning 工具，未引入 schema v11。独立复验为 targeted：Target pytest 122 passed；`npm run test:chat` 79 passed；`npm run typecheck:chat` 通过；Affected 337 passed；ruff/mypy 32 files 通过；`git diff --check` exit 0。TDD 过程证据对 pytest Target 为 complete；前端 vitest Red 未单独保存。本次确认不独立见证历史 Red→Green。reviewer P3（vitest 无历史 Red；`ExecutionFactJournal` 不跨 turn；`durable_repository` 可选；未跑真实浏览器/Playwright）不因本次确认要求立即返工。本确认不是 Task 25 完成，不是用户 Phase 2 完成；Step 10/11 保持未勾选。Task 33 仍需单独授权。未授权 commit、push、付费 3×3 或 Phase 3。

---

## Task 33 / `phase-2d-task-17`：Prompt / Schema / Tool 描述

### Goal

可用性优化：**不能** 代替 Runtime 校验（Task 30 哈希、Task 31 拦截、白名单 argv 仍是硬门）。禁止改 Policy 矩阵、放宽 Schema `oneOf`、改 `max_steps`、schema v11、REQUIRED planning。不要修 Task 30 CRLF P2、Task 31/32 reviewer P3。

### 现状（不要改错层）

- `ValidatePatchTool.input_schema()` 已有 `changes` / `diff` 互斥 `oneOf`；**description 仍只写 unified diff**（Task 30 reviewer P3）。
- Chat `runtime_factory` 的 coding `system_prompt` 在 `cli/main.py`，未要求 `read_file`+SHA-256、`changes`、精确 argv、硬拒绝不重试。
- `AgentConfig` **默认**仍是只读 Agent（`tests/unit/chat/test_runner.py`、`tests/integration/test_agent_loop.py` 断言全文相等）。**禁止**把 coding 说明写进默认 `AgentConfig.system_prompt`。
- CLI `build_runtime()` 仍用默认只读 prompt；本 Task 只升级 **Chat 可控 Coding Agent** 提示与相关 Tool description。

### Stable contract（测试锁定这些英文原句）

将 Chat coding prompt 抽到例如 `src/agent_foundations/runtime/coding_prompt.py` 的常量 `CONTROLLED_CODING_AGENT_PROMPT`，由 `cli/main.py` `runtime_factory` 使用。全文必须 **包含** 下列句子（可另有前后文，不得改这些字符）：

```text
Before editing a file, call read_file.
Use the sha256 returned by read_file; do not guess hashes.
Prefer validate_patch with changes; do not hand-write complex unified diffs.
Command argv must match the whitelist exactly; do not add extra npm arguments or use npm test.
Do not retry POLICY_DENIED, PATCH_PATH_REJECTED, or the same denied action.
After a failing test, read CommandFeedback and call read_command_output before rerunning the same argv.
```

保留现有 Chat 约束：只用提供的 Tool、`apply_patch` 经授权、`run_command` 跑门禁、只读 git、可选 planning 且非 REQUIRED。

Tool description 必须包含：

```text
ReadFileTool.description
→ sha256, size_bytes, encoding, truncated；sha256 is the full-file digest

ValidatePatchTool.description
→ Prefer changes with expected_sha256 from read_file; Runtime compiles unified diff.
  The diff+baselines path remains valid. Do not guess hashes.

RunCommandTool.description
→ argv must match the project command manifest exactly; extra flags are rejected.

ReadCommandOutputTool.description
→ Use after a failing run_command together with CommandFeedback.artifact_id.
```

`validate_patch` JSON Schema：可给 `changes` / 字段加 `description` 字符串；**不得**改 `oneOf`、required、`expected_sha256` pattern、互斥规则。

### Files

- 新增 `src/agent_foundations/runtime/coding_prompt.py`
- `src/agent_foundations/cli/main.py`（只替换 Chat system_prompt 来源）
- `read_file.py` / `validate_patch.py` / `run_command.py` / `read_output.py` 的 description（及 schema description）
- `tests/unit/runtime/test_coding_prompt.py`（新建）
- 扩展 `tests/unit/tools/patch/test_validate_patch.py`
- Chat factory 使用该常量的最小断言（放在 `test_coding_prompt.py`）

仓库没有 `tests/runtime/` 根目录。

### Tests（Red 必须在改生产代码前）

- `CONTROLLED_CODING_AGENT_PROMPT` 含上述六句
- Chat `runtime_factory` 的 `loop._config.system_prompt` 等于该常量（或以其为全文），不得用默认只读 prompt
- `AgentConfig().system_prompt` 仍为只读原文（既有相等断言保持绿）
- 四个 Tool description 含锁定关键词；`ValidatePatchTool.input_schema()` 仍 `oneOf` 互斥且 `changes` 项仍要求 `expected_sha256`

### Verification contract

```text
Target tests：
conda run -n agent-foundations python -m pytest tests/unit/runtime/test_coding_prompt.py tests/unit/tools/patch/test_validate_patch.py tests/tools/filesystem -q

Affected regression tests：
conda run -n agent-foundations python -m pytest tests/unit/chat/test_runner.py tests/integration/test_agent_loop.py tests/integration/test_chat_planning_tools.py tests/unit/tools/patch tests/tools/patch tests/unit/tools/command -q

Full suite：not-required
Full suite reason：不扩大权限；只改模型可见文案与 schema description。

Additional gates：
conda run -n agent-foundations python -m ruff check src/agent_foundations/runtime/coding_prompt.py src/agent_foundations/cli/main.py src/agent_foundations/tools/filesystem/read_file.py src/agent_foundations/tools/patch/validate_patch.py src/agent_foundations/tools/command/run_command.py src/agent_foundations/tools/command/read_output.py tests/unit/runtime/test_coding_prompt.py
conda run -n agent-foundations python -m mypy src/agent_foundations/runtime/coding_prompt.py src/agent_foundations/cli/main.py src/agent_foundations/tools/filesystem/read_file.py src/agent_foundations/tools/patch/validate_patch.py src/agent_foundations/tools/command/run_command.py src/agent_foundations/tools/command/read_output.py tests/unit/runtime/test_coding_prompt.py
git diff --check
```

Windows：`$env:PYTHONIOENCODING='utf-8'`。禁止 Docker、付费 API、commit、改 Policy。

依赖：Task 30–32 已验收。

**User acceptance:** 2026-08-29 用户确认 `确认「Task 33 / phase-2d-task-17 用户验收通过」`；记录于本计划与 `docs/task-evidence/phase-2d-task-17.md` §9。范围仅限 Chat 可控 Coding Agent 的 `CONTROLLED_CODING_AGENT_PROMPT`（含六句锁定英文原句）、Chat `runtime_factory` 使用该常量，以及四个 Tool description 与 `validate_patch` schema 字段 `description`。未改默认只读 `AgentConfig.system_prompt`、CLI `build_runtime()` prompt、`oneOf`/required/`expected_sha256` pattern、`max_steps`、`PlanningMode`。独立复验为 targeted：Target 13 passed；Affected 178 passed；ruff/mypy 7 files 通过；`git diff --check` exit 0。TDD 过程证据为 complete；本次确认不独立见证历史 Red→Green。reviewer P3（Tool description 挂在共享 Tool 类上，CLI/Eval 也会看到；Chat factory 用 `inspect.getsource`）不因本次确认要求立即返工。本确认不是 Task 25 完成，不是用户 Phase 2 完成；Step 10/11 保持未勾选。Task 34 仍需单独授权。未授权 commit、push、付费 3×3 或 Phase 3。提示与 description 不能代替 Runtime 校验。

---

## Task 34 / `phase-2d-task-18`：分层预算 + Offline Eval

### Goal

**禁止** 只把 Chat `max_steps` 从 24 改成更大整数。必须同时有分层上限。禁止付费 API、勾选 Task 25 Step 10/11、schema v11、改 Policy、削弱 Task 31 恢复映射、改 `RetryPolicy.max_attempts`（保持 3）。不要修既有 reviewer P3 / Task 30 CRLF。

默认只读 `AgentConfig.max_steps=10` **不要改**（CLI `build_runtime` 与既有相等/步数测试）。只给 Chat Coding Agent 挂分层预算。

### 现状（不要重复建设）

- 总步数：`AgentLoop` 已用 `max_steps`；Chat 已是 24。
- Provider：`ProviderAttemptBudget` / `RetryPolicy.max_attempts=3`（Task 24）。本 Task 只接线、不重写。
- 硬拒绝重试 / 审批不 `complete()`：Task 31 `recovery.py` 已做。本 Task 不得拆掉；预算在 recovery **允许之后** 再计数拦截。
- 没有 `tests/runtime/`、`tests/eval/` 根目录。用 `tests/unit/runtime`、`tests/unit/evals`、`tests/integration/test_offline_eval.py`。

### Stable contract

新增 `src/agent_foundations/runtime/coding_budget.py`：

```text
evaluate_budget(messages, tool_name, arguments, limits) -> BudgetDecision
```

计数从 transcript 推导，不改 `AgentRunState.schema_version`。

```text
max_steps              # 已有；Chat 生产值见下
max_patch_repairs      # 同一 path 上失败的 validate_patch/apply_patch 次数
                       # （含 executor 实际执行的失败结果；不含未执行的 recovery 拦截）
max_same_argv_command_runs  # 同一 canonical argv 的 run_command 次数（含第一次）
max_artifact_reads     # read_command_output + search_command_output 次数
provider attempts      # 不改；沿用 RetryPolicy.max_attempts=3
HARD_STOP / APPROVAL_REQUIRED  # 仍走 recovery，不烧 complete
```

拦截时不调用下游 executor，`success=false`，error_code 锁定：

```text
BUDGET_PATCH_REPAIRS_EXCEEDED
BUDGET_COMMAND_RETRIES_EXCEEDED
BUDGET_ARTIFACT_READS_EXCEEDED
```

超总步数仍 `MaxStepsExceededError`。

`AgentConfig` 可增加可选 `coding_budget: CodingBudgetLimits | None = None`。`None` 表示除 `max_steps` 外无分层上限（只读 CLI / 既有测试）。Chat `runtime_factory` 必须传入生产常量。

### 数字：先测后写，且有天花板

TDD 用 **注入的小上限**（例如 repairs=2, argv_runs=2, artifact_reads=2, max_steps=4），不依赖生产数字。

生产常量（Chat）必须在 evidence 里用下列测量写明理由，且落在天花板内：

测量命令（FakeModel only；禁止 Docker / 付费）：

```text
conda run -n agent-foundations python -m pytest tests/integration/test_command_feedback_agent_flow.py tests/integration/test_phase2_coding_agent.py tests/integration/test_offline_eval.py tests/unit/evals -q --ignore=tests/eval/test_docker_sandbox_e2e.py
```

（Docker ignore 若路径不存在可省略，不得因此去跑 `pytest -m docker`。）

对照脚本化成功路径的 `ModelResponse` 条数（command_feedback 约 7 次 completion，phase2 coding 约 10 次）。evidence 记录：命令、退出码、观察到的步数/工具次数、选定常量。

Chat 生产天花板（不得超出；可低于上限）：

```text
CHAT_MAX_STEPS                 24–32（含）
CHAT_MAX_PATCH_REPAIRS         3–8
CHAT_MAX_SAME_ARGV_COMMAND_RUNS 2–4
CHAT_MAX_ARTIFACT_READS        6–16
```

分层上限必须都 **严格小于** `CHAT_MAX_STEPS`。禁止把 `CHAT_MAX_STEPS` 设成 100+ 却无分层。

### Files

- `src/agent_foundations/runtime/coding_budget.py`（新）
- `src/agent_foundations/runtime/agent.py`（可选字段）
- `src/agent_foundations/runtime/loop.py`（recovery 之后、execute 之前；`READY_FOR_MODEL` 仍先 `should_request_model`）
- `src/agent_foundations/cli/main.py` Chat `runtime_factory` 接线
- `tests/unit/runtime/test_coding_budget.py`（新，Red 主文件）

### Tests（Red 必须在改生产代码前）

- 注入 `max_patch_repairs=2`：两次失败 validate_patch 后第三次不执行，`BUDGET_PATCH_REPAIRS_EXCEEDED`
- 注入 argv 上限：同一 argv 第三次 `run_command` 拦截
- 注入 artifact 读上限
- Chat factory 传入非 None 的 coding_budget，且常量在天花板内
- `AgentConfig()` 默认 `coding_budget is None`，`max_steps==10`
- `tests/unit/runtime/test_provider_attempt_budget.py` 与 recovery 测试保持绿
- FakeProvider：`APPROVAL_REQUIRED` 时 `complete` 次数不增加（既有语义）

### Verification contract

```text
Target tests：
conda run -n agent-foundations python -m pytest tests/unit/runtime/test_coding_budget.py -q

Affected regression tests：
conda run -n agent-foundations python -m pytest tests/unit/runtime tests/integration/test_agent_loop.py tests/integration/test_command_feedback_agent_flow.py tests/integration/test_phase2_coding_agent.py tests/integration/test_offline_eval.py tests/unit/evals -q

Full suite：not-required
Full suite reason：不扩大 Tool 权限；只增加停止条件。不得勾选 Task 25 Step 10。

Additional gates：
conda run -n agent-foundations python -m ruff check src/agent_foundations/runtime/coding_budget.py src/agent_foundations/runtime/agent.py src/agent_foundations/runtime/loop.py src/agent_foundations/cli/main.py tests/unit/runtime/test_coding_budget.py
conda run -n agent-foundations python -m mypy src/agent_foundations/runtime/coding_budget.py src/agent_foundations/runtime/agent.py src/agent_foundations/runtime/loop.py src/agent_foundations/cli/main.py tests/unit/runtime/test_coding_budget.py
git diff --check
```

Windows：`$env:PYTHONIOENCODING='utf-8'`。禁止 Docker、付费 3×3、commit。完成后 **停止**；是否重做 3×3 由用户另授权。

依赖：Task 30–33 已验收。

**User acceptance:** 2026-09-04 用户确认 `确认「Task 34 / phase-2d-task-18 用户验收通过」`；记录于本计划与 `docs/task-evidence/phase-2d-task-18.md` §10。范围仅限 Chat Coding Agent 的分层预算（`evaluate_budget` 从 transcript 推导；recovery 允许之后、executor 之前拦截；Chat 生产常量 `CHAT_MAX_STEPS=24`、`CHAT_MAX_PATCH_REPAIRS=4`、`CHAT_MAX_SAME_ARGV_COMMAND_RUNS=3`、`CHAT_MAX_ARTIFACT_READS=8`）。未改默认只读 `max_steps=10`、CLI `build_runtime()`、`RetryPolicy.max_attempts=3`、Task 31 recovery 映射。独立复验为 targeted：Target 10 passed；Affected 249 passed / 1 skipped；ruff/mypy 5 files 通过；`git diff --check` exit 0。TDD 过程证据为 complete；本次确认不独立见证历史 Red→Green。reviewer P3（依赖 recovery 私有 helper；无 path 的 `apply_patch` 空桶；生产常量来自 FakeModel 成功路径余量而非付费测量）不因本次确认要求立即返工。本确认不是 Task 25 完成，不是用户 Phase 2 完成；Step 10/11 保持未勾选。未授权 commit、push、付费 3×3 或 Phase 3。可靠性 follow-on 计划内 Task 已全部验收；是否重做付费 3×3 须用户另授权。

---

## 3. 非目标（全部 Task）

- 不重写 Task 25 验收标准
- 不把 2026-08-27 3×3 标为通过
- 不引入 schema v11（除非独立 migration Task 且用户确认）
- 不实现 MCP / 通用 Computer Use / 包安装 Tool
- 不把结构化修改做成「直接写文件」

## 4. 用户确认门

确认本文件后，planner 每次只发 **一个** executor prompt，从 Task 30 开始。
)
