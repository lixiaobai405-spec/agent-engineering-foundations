# Phase 2 Step 6 Baseline Unblock

**Date:** 2026-09-09  
**Status:** Task 49 / `phase-2d-task-33` 已于 2026-09-09 用户验收通过（完整 Step 6）。计划正文 Task 25 Step 11 已于 2026-09-09 用户验收通过。用户 Phase 2 已于 2026-09-09 确认完成。不得把本文件写成 Phase 3 授权。  
**Role:** planner 维护；本文件不实现生产代码  
**Parent:** `docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md` Task 25 Step 6 / Step 11  
**Source:** Step 11 reviewer evidence `docs/task-evidence/phase-2d-task-9-step-11.md`；用户验收结论：唯一阻塞是 Step 6 完整基线未绿  
**Does not replace:** Task 25 验收标准、Step 10 人工门、Tasks 45–48 已验收范围

## 0. 结论锁定

- 阻塞原因只有一条：Task 25 **Step 6 完整基线**未绿（pytest / ruff / mypy）。
- Step 10 Round 3 连续 9/9 仍是人工门；Round 2 失败记录保持失败。
- Step 10 的 9/9、权限边界抽查、Stop + Durable cancel、畸形 tool JSON **不是**本次否决点。
- Step 10 P3（Node-3 未用 git 只读；Security-3 interrupt 后 apply 活动可能仍 `running`）**不单独否决** Phase 2，本 Task **不修**。
- 本 Task 完成后 **停止**。下一步是另开 **reviewer** 重跑 Step 11；executor **不得**勾选 Step 11 或 Phase 2 完成。

## 1. Task 顺序

| 顺序 | 用户可见 | Task ID | Evidence | 主题 |
|---|---|---|---|---|
| 1 | Task 49 | `phase-2d-task-33` | `docs/task-evidence/phase-2d-task-33.md` | 修绿 Step 6 pytest/ruff/mypy；不扩权限 |

一次只执行用户确认的这一个 Task。

**明确不修：** MCP / ACP / A2A / Memory / Skills / Hooks / Sub-Agent / Browser / 网络 Tool / Git 写 / `HOST_FULL_ACCESS` / TrustedHostExecutor / 付费 3×3 / Step 10 P3 / 历史 Red 补造 / commit / push / Phase 3。

Python：`$env:PYTHONIOENCODING='utf-8'` + `conda run -n agent-foundations python`（Windows PowerShell）。

---

## Task 49 / `phase-2d-task-33`：修绿 Step 6 完整基线

### Goal

让 Task 25 Step 6 命令块全部 exit 0。优先按 Step 11 分类修测试/门禁漂移；只有 `test_command_feedback_sanitized_pages_restore_and_narrow_viewport` 在合法测试修正后仍证明生产行为缺失时，才允许最小 Chat/pages 修复。不得扩大 Tool 或权限。

### 失败清单（权威来源：Step 11 `phase-2d-task-9-step-11.md` §4a）

13 failed pytest（1528 passed / 14 skipped / exit 1）、ruff F821、mypy 4 errors。分类如下。

#### A. 测试未跟上生产 API（11 个）— 默认只改测试

1. `tests/e2e/test_chat_ui.py::test_task16_browser_patch_profile_reload_approve_deny_and_no_duplicate_write`  
   约 L992：`sqlite3.connect(database_path)` 但 `database_path` 未定义。同一处是 ruff `F821` 与 mypy name-defined。  
   **锁定修复：** 使用该测试已有的 `repository`（`_build_chat_app` 返回值），与同文件 `test_command_feedback_sanitized_pages_restore_and_narrow_viewport` 一致：`db_path = repository._database_path`，再 `sqlite3.connect(db_path)`。不要为这一行改生产 Chat。

2. `tests/unit/chat/test_tool_execution.py` 共 9 个（Step 11 已列名）  
   桩 `RecordingCoordinator.request(self, request)` 只收 1 个业务参数；生产 `ApprovalAwareToolExecutor` 在 `src/agent_foundations/chat/tool_execution.py` 约 L314 调用 `request(request, policy_request, outcome)`；生产 `ApprovalCoordinator.request` 已接受这 3 个参数。  
   **锁定修复：** 只改桩签名，使其与 `src/agent_foundations/chat/approvals.py` 的 `request(request, policy_request=None, outcome=None)` 兼容（未用参数可忽略）。**禁止**把生产改回单参数来迁就桩。不得改变这 9 个测试的审批/拒绝断言意图。

3. `tests/unit/runtime/test_coding_budget.py::test_loop_does_not_execute_over_budget_artifact_read`  
   `tests/unit/runtime/test_recovery.py::test_loop_command_feedback_blocks_identical_argv`  
   仍使用非法选择器 `{"stream": "stdout"}`。Task 46 合同：三种互斥 shape 为 `{diagnostic_id}` / `{stream, tail_lines}` / `{stream, start_line}`（缺 `line_count` 时默认 40）。非法 selector 进不了 scripted executor，断言对不上。  
   **锁定修复：** 把这两处 `read_command_output` 的 `selector` 改成合法 shape（推荐 `{ "stream": "stdout", "tail_lines": 40 }` 或带默认的 `{ "stream": "stdout", "start_line": 1 }`）。保持原测试意图：budget 第三次 artifact read 被拦；recovery 在读 feedback 前挡住重复 argv，读合法 slice 后允许再跑命令。  
   **禁止**放宽 Task 46 选择器；**禁止**为迁就旧调用改 `ReadCommandOutputTool` 再接受 `{stream}` only。

#### B. 行为未证实（1 个）— 先诊断，再最小修复

`tests/e2e/test_chat_ui.py::test_command_feedback_sanitized_pages_restore_and_narrow_viewport`

- Step 11 traceback：**L1115** `expect(...get_by_text("[REDACTED]")).to_be_visible()`，发生在 **reload 之前**（点击 Show sanitized output 之后）。用户叙述「reload 后」不得覆盖这条 traceback；executor 必须以当场复跑为准。
- 测试 fixture：`stdout=b"ok\n"`，密钥在 **stderr**。`web/chat/components/CommandFeedbackCard.tsx` 在 stdout 非空时默认选中 **Stdout** 标签；Stdout 面板不会出现 `[REDACTED]`。这是首选假设，必须用一次失败截图或 DOM/tab 状态证实或证伪。
- **不得**把失败当成已证实密钥泄漏；**不得**在未看 DOM 的情况下声称已排除泄漏。若 `get_by_text(secret)` 计数 > 0，立即停止扩修并交回 planner。
- **允许的测试修正：** 在断言 `[REDACTED]` 之前切换到 **Stderr** tab（`role=tab`，名称 Stderr），然后断言标记可见；全页 `secret` 计数仍为 0；reload 后仍要求 conversation + “Show sanitized output” 可见，以及 390×844 无横向溢出。不要删掉脱敏断言。
- **允许的生产最小修复：** 仅当切到 Stderr 后标记仍缺失、或 pages API 未脱敏、或 reload 后卡片/按钮本应存在却不存在时，可改 `web/chat/**` 和/或现有 command-output pages 投影，并仅经 `npm run build:chat` 更新静态包。不得新开 raw 默认展示，不得把密钥写入 evidence。

#### C. mypy（测试导入隐式再导出）

`tests/unit/command_output/test_retention.py`：`store_mod.DEFAULT_GLOBAL_CAPACITY_BYTES` / `EXECUTION_OUTPUT_LIMIT_BYTES` attr-defined。常量定义在 `src/agent_foundations/command_output/retention.py`，`store.py` 从 retention import 供默认参数使用，但模块无 `__all__`，strict mypy 不把它们当作 `store` 的导出。  
**锁定修复（二选一，优先更小）：**

1. 给 `store.py` 增加显式 `__all__`（或等价显式再导出），使现有 `test_store_imports_capacity_constant_from_retention` 的 identity 断言继续成立；或  
2. 只改测试，改为从 `retention` 断言常量，并仍证明 `store.py` 源码不重复定义 `DEFAULT_GLOBAL_CAPACITY_BYTES = 512|1024`。

不得把 512 MiB 改回 1 GiB，不得改 sweeper 行为。

### Files

允许：

- `tests/e2e/test_chat_ui.py`
- `tests/unit/chat/test_tool_execution.py`
- `tests/unit/runtime/test_coding_budget.py`
- `tests/unit/runtime/test_recovery.py`
- `tests/unit/command_output/test_retention.py`
- `src/agent_foundations/command_output/store.py`（仅 `__all__` / 显式再导出，若选 C.1）
- 仅当 B 需要：`web/chat/**`、现有 command-output pages API 投影、Chat 静态包（只经 `npm run build:chat`）
- `docs/task-evidence/phase-2d-task-33.md`
- 本文件勾选；**不得**勾选父计划 Step 11

禁止：Policy / Capability / Permission Profile / Sandbox / Docker / Registry 新 Tool / Git 写 / Stop/Durable 状态机 / Task 46 selector 生产合同 / 付费 API。

### TDD

- **适用，但是「已有 Red」：** 修改任何测试或生产代码前，复跑下方 Target tests，把 13 failed / ruff / mypy 的命令、退出码和关键原文写入 evidence。Step 11 文件可引用，但 **不能替代** 本 Task 的当场 Red。
- 不要为了制造 Red 去破坏已经通过的测试。
- A/C 的 Green 是同一批测试与门禁通过。
- B：若只改测试，Red 必须仍是「目标断言失败或 NameError 一类目标失败」，Green 后 `[REDACTED]` 可见且 `secret` 计数为 0。若必须改生产，先固定能证明缺失行为的断言再改 UI/API。

### 验证合同

```text
Target tests：
  conda run -n agent-foundations python -m pytest -q --tb=line ^
    tests/e2e/test_chat_ui.py::test_task16_browser_patch_profile_reload_approve_deny_and_no_duplicate_write ^
    tests/e2e/test_chat_ui.py::test_command_feedback_sanitized_pages_restore_and_narrow_viewport ^
    tests/unit/chat/test_tool_execution.py ^
    tests/unit/runtime/test_coding_budget.py::test_loop_does_not_execute_over_budget_artifact_read ^
    tests/unit/runtime/test_recovery.py::test_loop_command_feedback_blocks_identical_argv ^
    tests/unit/command_output/test_retention.py

Affected regression tests：
  conda run -n agent-foundations python -m pytest -q --tb=line ^
    tests/unit/chat/test_tool_execution.py ^
    tests/unit/runtime/test_coding_budget.py ^
    tests/unit/runtime/test_recovery.py ^
    tests/unit/command_output/test_retention.py ^
    tests/e2e/test_chat_ui.py

Full suite：required
Full suite reason：本 Task 的目标就是 Task 25 Step 6 完整基线变绿；targeted 不能替代。
Additional gates：Step 6 命令块其余项（见下）；若改了 web/chat 或静态包，必须包含 npm run test:chat、typecheck:chat、build:chat。
```

Step 6 完整基线（必须全部 exit 0，记录本次精确 passed/skipped/warning，禁止抄历史数字）：

```powershell
$env:PYTHONIOENCODING='utf-8'
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

本 Task **不要求** Docker `pytest -m docker`、Offline Eval、付费 3×3。那些属于后续 Step 11 reviewer，不构成本 Task 完成条件。

### Acceptance

- [x] 上述 13 个失败测试全部通过；无新的同文件回归
- [x] ruff `F821` 消失；`ruff check .` exit 0
- [x] `mypy src tests` exit 0（含 retention/store 再导出）
- [x] Step 6 完整基线每条 exit 0；evidence 写明精确计数
- [x] 未扩大 Tool/权限；未勾选 Step 11；未 commit/push/付费
- [x] B 项 evidence 写明：失败行号、是否切过 Stderr tab、`secret` 是否出现在 DOM、最终是测试修正还是生产修正
- [x] 保留全部既有未提交改动；范围审计无无关重构

**Suggested commit after explicit authorization:** `test: unblock phase 2 step 6 baseline gates`

**User acceptance:** 2026-09-09 用户确认 `确认「Task 49 / phase-2d-task-33 用户验收通过」`；记录于本计划与 `docs/task-evidence/phase-2d-task-33.md` §9。范围仅限修绿 Task 25 Step 6 完整基线：A.1 `services.repository._database_path`（该测试实际是 `build_chat_services`）；A.2 审批桩改为三参数；A.3 两处 loop 测试改为合法 `{stream, tail_lines: 40}`；B 只改测试（断言 `[REDACTED]` 前点 Stderr tab）；C.1 `store.py` `__all__` 再导出两个容量常量。未改 Chat/pages 生产源码、未放宽 Task 46 选择器、未扩 Tool/权限、未勾选 Step 11。独立复验为 **full Step 6**：Target 41 passed；Affected 65 passed；pytest 1541 passed / 14 skipped / 54 warnings；ruff、mypy（312 files）、`pip check`、viewer 12 pass + typecheck、chat 87 passed + typecheck、`build:chat`（入口仍 `index-YqNJU08h.js`）、`git diff --check` 均为 exit 0。reviewer 重建了 Chat 静态包，入口 hash 未变。TDD 过程证据为 complete；本次确认不独立见证历史 Red→Green。B Red 在 L1115、reload 之前；L1114 `secret` 计数 0。reviewer P3（A.1 计划措辞 vs `build_chat_services`；`__all__` 只导出两常量；同文件其它测试仍留 `{stream}`-only fixture；B 无截图；`pip check` 损坏发行版 warning）不因本次确认要求立即返工。本确认不是计划正文 Task 25 完成，不是用户 Phase 2 完成；Step 11 保持未勾选。未跑 Docker / Offline Eval / 付费 3×3。未授权 commit、push、付费 3×3、Step 11 勾选或 Phase 3。

---

## Executor prompt（用户确认后才能实施）

```text
你是 executor。遵守仓库 CLAUDE.md / AGENTS.md 的流程与安全规则。
只执行我在本条消息中确认的一个 Task：Task 49 / phase-2d-task-33。
合同以 docs/agent-plans/2026-09-09-phase-2-step-6-baseline-unblock-plan.md 的 Task 49 为准。
未在本条确认的范围不要实现。不要用常驻文档里的历史阶段描述否决本 Task。
不要勾选 Task 25 Step 11，不要声称 Phase 2 完成，不要扩 Tool/权限。

每个改动都要先把当前 13 failed / ruff / mypy 记进 docs/task-evidence/phase-2d-task-33.md，再做最小修复。
A/C 默认只修测试或 store 显式再导出；B 先用 traceback 行号诊断，优先 Stderr tab，密钥可见则停止并交回。
完成后必须跑合同里的 Full suite（Step 6 命令块），不得写成 targeted 替代 full suite。
未经我明确授权，不要安装依赖、调用真实模型、commit、push、创建 PR。
```

完成后 **停止**。用户另开 reviewer 会话重跑 Step 11。
