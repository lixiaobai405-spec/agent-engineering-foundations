# Phase 2 Product Hardening Plan

**Date:** 2026-09-04  
**Status:** Task 35–41 均已用户验收通过（targeted）。本硬化计划无 Task 42。付费 3×3 前缺口见 `docs/agent-plans/2026-09-08-phase-2-pre-3x3-gap-remediation-plan.md`。不关闭 Task 25 / Phase 2 用户验收 / Step 10/11；付费 3×3 须另授权。  
**Role:** planner 维护；不实现生产代码  
**Parent:** `docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md`  
**Does not replace:** Task 25、Phase 2 用户验收、Step 10/11、已验收的可靠性 follow-on（Task 30–34）

## 0. 对提案的结论

方向正确，**不要合成一个超大 Task**，也 **不要重做** 已验收的 Patch / Planning / 恢复 / Prompt / 分层预算。

提案「一、Patch 与真实模型交互」与 `docs/agent-plans/2026-08-29-phase-2-reliability-follow-on-plan.md` Task 30–34 **已经落地并用户验收**。本计划从仍会卡住 Node 3×3 和产品体验的缺口开始。

**暂不包含（与提案第十节一致）：** 付费 3×3、真实 API、任意 Shell/网络/MCP/Browser/项目外写入、commit/push、放宽安全校验。

## 1. 现状对照（2026-09-04 代码）

| 提案 | 状态 | 说明 |
|---|---|---|
| 一、SHA-256 / 结构化修改 / Runtime Diff / 错误恢复 / Chat Planning / Prompt / 分层步数 | **已完成** | Task 30–34。Chat `max_steps=24` 且有 patch/argv/artifact 分层。不要再开「接线 set_plan」或「从零做 SHA-256」。 |
| 二、Node `gate_id` | **已完成（targeted）** | 模型提交 `gate_id`；Runtime 展开 argv 后再 classify。exact gate 拒绝 target/flags。2026-09-04 用户验收通过；evidence 见 `docs/task-evidence/phase-2d-task-19.md` §9。 |
| 三、Git 固定 argv + 错误码 | **已完成（targeted）** | Runtime 生成 argv；`--no-ext-diff` 已在 subcommand 之后；已有 `GIT_USAGE_ERROR` / `NOT_A_REPOSITORY` / `GIT_TIMEOUT` / `GIT_FAILED`。Task 36 增加每实例一次 `git --version` 探测与预定义 L1 fallback，以及 `legacy_patch` 镜像上 status/diff/log Docker 回归。2026-09-04 用户验收通过；evidence 见 `docs/task-evidence/phase-2d-task-20.md` §9。 |
| 四、stdout/stderr 双标签 | **已完成（targeted）** | `pages` 的 `stream` 必填（缺参 422）；`CommandFeedbackCard` tablist 分开展示 stdout/stderr，空态 `"No stdout"` / `"No stderr"`。2026-09-05 用户验收通过；evidence 见 `docs/task-evidence/phase-2d-task-22.md` §9。 |
| 五、审批卡 PolicyRequest | **已完成（targeted）** | SSE `approval.requested` 与 GET `pending_approval` 带 `operation` / `resource_kind` / `scope` / `policy_decision`；标题按 `resource_kind` 锁定；无 `capability_id`、无 sqlite 新列。2026-09-04 用户验收通过；evidence 见 `docs/task-evidence/phase-2d-task-21.md` §9。 |
| 六、分级 Artifact 读取 | **模型侧已有，UI 部分** | `run_command` 自动把 CommandFeedback 放进 Tool metadata；sanitized page 按 run/artifact/stream/行范围，`charge_budget=False`；raw 要 ticket。Task 38 已去掉 pages 静默默认 stderr 并分 tab 展示。 |
| 七、容量与清理 | **已完成（targeted）** | 单次上限仍是 64MB。总容量默认 **512 MiB**（canonical 在 `retention.py`）。Chat lifespan 启动 sweep + 默认 3600s 定期 sweep；本机 `usage` / `sweep` / `purge` HTTP。`reserve()` 语义未改。2026-09-05 用户验收通过；evidence 见 `docs/task-evidence/phase-2d-task-24.md` §9。 |
| 八、Artifact 独立根目录 | **已完成（targeted）** | Chat 共用已校验 data-root：`chat.sqlite3` / `command-output/` / `controller/` / `traces/`。优先级 `--data-root` > `AGENT_FOUNDATIONS_DATA_ROOT` > `default_artifact_root().parent`。拒绝 Git worktree；leftover 只提示不搬文件；HTTP `/command-artifacts/` 路由名不变。2026-09-05 用户验收通过；evidence 见 `docs/task-evidence/phase-2d-task-23.md` §9。 |
| 九、ASGI CancelledError | **已完成（targeted）** | SSE `generate` 继续吞 `CancelledError`。客户端断开 DEBUG、lifespan 关机 INFO、其它异常 ERROR（只记类型名）。Chat lifespan finally 先打关机旗标再 cancel sweep → coordinator → supervisor。订阅 `subscriber_count` 在 SSE 结束后为 0。2026-09-05 用户验收通过；evidence 见 `docs/task-evidence/phase-2d-task-25.md` §9。 |
| 十、3×3 | **暂缓** | 本计划 Task 35–41 已全部用户验收。付费 3×3 前须先完成 `docs/agent-plans/2026-09-08-phase-2-pre-3x3-gap-remediation-plan.md`。3×3 须另授权，仍走 Task 25 Step 10；不得因本计划完成而勾选 Step 10/11 或声称 Phase 2 完成。 |

## 2. 安全不变量（全部 Task）

```text
gate_id 只展开为白名单 argv，再走既有 classify → Policy → Approval → Capability → Sandbox
Git argv 只由 Runtime 生成；模型不得传 git 开关
Artifact 根目录不得落在 Git worktree / 项目目录
不把 raw 输出默认暴露给模型或未持票的 UI
不放宽 validate_patch / PathPolicy / 命令 metacharacter 拒绝
```

## 3. Task 顺序

| 用户可见 | Task ID | Evidence | 主题 |
|---|---|---|---|
| Task 35 | `phase-2d-task-19` | `docs/task-evidence/phase-2d-task-19.md` | `run_command` 的 `gate_id` 合同 |
| Task 36 | `phase-2d-task-20` | `docs/task-evidence/phase-2d-task-20.md` | Git 探测 + 预定义 fallback + Docker Git 回归 |
| Task 37 | `phase-2d-task-21` | `docs/task-evidence/phase-2d-task-21.md` | 审批 SSE 带 PolicyRequest；UI 按字段渲染 |
| Task 38 | `phase-2d-task-22` | `docs/task-evidence/phase-2d-task-22.md` | 命令输出 stdout/stderr 双标签 + 空态 |
| Task 39 | `phase-2d-task-23` | `docs/task-evidence/phase-2d-task-23.md` | 独立数据根（chat/artifacts/controller/traces） |
| Task 40 | `phase-2d-task-24` | `docs/task-evidence/phase-2d-task-24.md` | Chat 生命周期接入 sweep；容量 512MB；占用/清理入口 |
| Task 41 | `phase-2d-task-25` | `docs/task-evidence/phase-2d-task-25.md` | Chat 关闭：日志分级 + lifespan 测试 |

全部完成后 **停止**。3×3 须用户另授权，仍走 Task 25 Step 10 协议。一次只执行用户确认的一个 Task。Task 35 / `phase-2d-task-19` 已于 2026-09-04 用户验收通过；evidence 见 `docs/task-evidence/phase-2d-task-19.md` §9。Task 36 / `phase-2d-task-20` 已于 2026-09-04 用户验收通过；evidence 见 `docs/task-evidence/phase-2d-task-20.md` §9。Task 37 / `phase-2d-task-21` 已于 2026-09-04 用户验收通过；evidence 见 `docs/task-evidence/phase-2d-task-21.md` §9。Task 38 / `phase-2d-task-22` 已于 2026-09-05 用户验收通过；evidence 见 `docs/task-evidence/phase-2d-task-22.md` §9。Task 39 / `phase-2d-task-23` 已于 2026-09-05 用户验收通过；evidence 见 `docs/task-evidence/phase-2d-task-23.md` §9。Task 40 / `phase-2d-task-24` 已于 2026-09-05 用户验收通过；evidence 见 `docs/task-evidence/phase-2d-task-24.md` §9。Task 41 / `phase-2d-task-25` 已于 2026-09-05 用户验收通过；evidence 见 `docs/task-evidence/phase-2d-task-25.md` §9。本硬化计划无 Task 42。付费 3×3 与 Task 25 Step 10/11 须另授权。

---

## Task 35 / `phase-2d-task-19`：`run_command` 的 `gate_id` 合同

### Goal

模型提交 `gate_id`（及前缀门的结构化 `target` / `flags`），Runtime 生成 argv。**禁止**模型再传 `argv`。exact Node 门不能加参数。不绕过 Policy / Approval / Sandbox。

### Stable contract

`RunCommandTool.input_schema()`：

```text
required: ["gate_id"]
properties:
  gate_id          # 等于 CommandGate.rule_id，例如 manifest.node.test-chat
  target           # 仅非 exact 门；单一允许根或 tests/foo.py::node_id
  flags            # 仅非 exact 门；必须是该门 allowed_flags 的子集、无重复
  cwd              # 保持现有相对路径规则
  timeout_seconds
additionalProperties: false
不得出现 argv
```

展开规则：

```text
exact=true
→ argv = gate.argv_prefix；若出现 target 或 flags → COMMAND_GATE_ARGUMENTS_REJECTED

exact=false
→ 必须有 target；flags 缺省为空
→ argv = prefix + flags（声明顺序）+ target
→ 非法 target/flag → 现有 invalid-arguments / DENIED 语义，不执行

未知 gate_id → COMMAND_UNKNOWN_GATE
同时出现 argv（即使 schema 被绕过）→ COMMAND_ARGV_REJECTED，不 classify
```

内部 `CommandClassifier` 仍只吃展开后的 `CommandSpec.argv`。`inject_trusted_format`、Docker argv、Policy resource 仍基于展开后的 argv。`resolve_run_command_resource` 的 identifier 用 `gate_id`（可附 target），不要把模型伪造的 argv 当资源。

必须更新 Task 33 锁定句（否则 Prompt 仍教 argv）：

```text
Call run_command with gate_id from the command manifest; do not submit argv.
Do not add extra npm arguments or use npm test.
After a failing test, read CommandFeedback and call read_command_output before rerunning the same gate.
```

删除或替换旧句 `Command argv must match the whitelist exactly` 与 `before rerunning the same argv`。`tests/unit/runtime/test_coding_prompt.py` 一并改。

FakeModel / 集成测试凡走 Tool schema 的，改为 `gate_id`（pytest 用 `manifest.python.pytest` + `target` + `flags: ["-q"]`）。分类器单测可继续直接喂 argv。

### Files

- `src/agent_foundations/tools/command/run_command.py`（schema + 展开）
- 新增最小 `src/agent_foundations/tools/command/gate_expand.py`（可选，须单测）
- `src/agent_foundations/runtime/coding_prompt.py`
- `src/agent_foundations/tools/command/run_command.py` description
- 受影响 FakeModel 测试（command_feedback、phase2 coding、ask_always、run_command_flow 等）
- `tests/unit/tools/command/` 新 Red

### Tests（Red 在改生产代码前）

- `gate_id=manifest.node.test-chat` → 展开 `("npm", "run", "test:chat")`
- 同一 gate 加 flags/target → 拒绝且不执行
- `npm`/`argv` 直接提交 → `COMMAND_ARGV_REJECTED`
- pytest：`gate_id` + `target=tests` + `flags=["-q"]` 展开正确
- 未知 `gate_id` 拒绝
- Prompt 常量含新锁定句、不含旧 argv 教学句

### Verification contract

```text
Target tests：
conda run -n agent-foundations python -m pytest tests/unit/tools/command tests/unit/runtime/test_coding_prompt.py -q

Affected regression tests：
conda run -n agent-foundations python -m pytest tests/integration/test_run_command_flow.py tests/integration/test_command_feedback_agent_flow.py tests/integration/test_phase2_coding_agent.py tests/integration/test_ask_always_run_command_twice.py tests/integration/test_run_command_cancellation.py tests/unit/runtime/test_coding_budget.py tests/unit/runtime/test_recovery.py -q

Full suite：not-required
Full suite reason：不扩大权限；模型输入从 argv 改为 gate_id，内部仍走同一 classify/Policy/Sandbox。须覆盖所有走 Tool 参数的 FakeModel 命令测试。

Additional gates：
conda run -n agent-foundations python -m ruff check src/agent_foundations/tools/command src/agent_foundations/runtime/coding_prompt.py tests/unit/tools/command tests/unit/runtime/test_coding_prompt.py
conda run -n agent-foundations python -m mypy src/agent_foundations/tools/command src/agent_foundations/runtime/coding_prompt.py tests/unit/tools/command
git diff --check
```

禁止 Docker、付费 API、commit。Windows：`$env:PYTHONIOENCODING='utf-8'`。

**User acceptance:** 2026-09-04 用户确认 `确认「Task 35 / phase-2d-task-19 用户验收通过」`；记录于本计划与 `docs/task-evidence/phase-2d-task-19.md` §9。范围仅限 `run_command` schema 锁定 `gate_id`、classify 前展开 argv、exact 门拒绝 target/flags、未知门 / 绕过 schema 的 `argv` 不 classify、Prompt 改为 gate_id 锁定句。未改 Policy 矩阵、Sandbox、Git、Artifact、`max_steps`。独立复验为 targeted：Target 91 passed；Affected 37 passed / 3 skipped；ruff/mypy 通过（含额外 `recovery.py`）；`git diff --check` exit 0。TDD 过程证据为 complete；本次确认不独立见证历史 Red→Green。reviewer P3（Chat 活动文案仍读 `arguments["argv"]`；`allowed_flags` 在分类器而非 expand 层拒绝；recovery 文案仍写 same argv）不因本次确认要求立即返工。本确认不是 Task 25 完成，不是用户 Phase 2 完成；Step 10/11 保持未勾选。Task 36 仍需单独授权。未授权 commit、push、付费 3×3 或 Phase 3。

---

## Task 36 / `phase-2d-task-20`：Git 探测与 fallback

### Goal

Sandbox 内 Git 由 Runtime **探测一次**，失败时走 **预定义更短 argv**。模型不得传 Git 开关。错误码保持现有集合。补 Docker 镜像内 status/diff/log 回归。不要修 Task 35 P3。不要改 Policy、gate_id、Chat、Artifact、Dockerfile。不要 `docker pull` / `docker build`。

### 现状（不要重复建设）

- argv 已由 `STATUS_ARGV` / `build_diff_argv` / `build_log_argv` 生成；`--no-ext-diff` 已在 subcommand 之后。
- `_run` 已用 stdout+stderr 区分 `NOT_A_REPOSITORY` / `GIT_USAGE_ERROR` / `GIT_TIMEOUT` / `GIT_CANCELLED` / `GIT_FAILED`。
- `tests/integration/test_git_read_tools.py::test_sandbox_readonly_git_smoke` 已有 `-m docker` status 烟测。缺口：无 version 探测、无 fallback 阶梯、diff/log 无 Docker 回归。
- Git 走 `sandbox_profile="legacy_patch"`、镜像 `agent-foundations-sandbox:phase2`（`docker/agent-sandbox.Dockerfile` 已 `apt-get install git`）。Python/Node phase2d 镜像不含 git，不要改那些 Dockerfile。

### Stable contract

新增例如 `src/agent_foundations/tools/git/probe.py`（名称可微调）。`GitReadService` **每个实例**缓存一次探测结果；模型不可见、不可选 flag。

探测 argv **锁定**（仅此一条）：

```text
("git", "--version")
```

解析 stdout：`git version X.Y.Z`（允许后续后缀如 `.windows.1`）→ `(X, Y, Z)`；只有 `X.Y` 时 Z=0。`git --version` 非 0 或超时 → `GIT_FAILED` / `GIT_TIMEOUT`，**不**再跑 status/diff/log。解析失败但 exit 0 → 仍从 L0 起试。

阶梯锁定（同一操作最多再执行 **一次** L1）：

```text
status L0 = 现有 STATUS_ARGV
status L1 = ("git", "--no-pager", "status", "--porcelain", "-z")

diff L0 = 现有 build_diff_argv（含 --no-optional-locks / --no-ext-diff / --no-textconv）
diff L1 = ("git", "--no-pager", "diff", "--no-color") + 可选 --cached + 可选 -- path

log L0 = 现有 build_log_argv
log L1 = ("git", "--no-pager", "log", f"--max-count={limit}", "--pretty=format:%H%x09%s")
```

选择：

```text
若解析出版本且 version < (2, 15, 0) → 该实例直接用 L1（旧 git 无 --no-optional-locks）
否则 → 先 L0
若 L0 得到 GIT_USAGE_ERROR（unknown option 或 exit 129）→ 同一操作再执行一次 L1
NOT_A_REPOSITORY / GIT_TIMEOUT / GIT_CANCELLED / GIT_FAILED / PATH_* / SELECTOR_INVALID 不得触发 fallback
L1 仍 usage → GIT_USAGE_ERROR，停止
usage 不得再标成 NOT_A_REPOSITORY
```

L1 隔离弱于 L0，只允许作预定义兜底，不得成为现代 git 的默认路径。既有 `--no-ext-diff` 位于 subcommand 之后的 L0 测试必须保持绿。

禁止：模型 schema 增加 git 参数；循环尝试任意开关；为本 Task 改任何 Dockerfile；`docker pull` 新 tag；`docker build`；把 Python/Node phase2d 镜像当 Git 运行时。

现有 `test_unknown_option_and_timeout_are_not_missing_repository` 在引入 fallback 后必须更新语义：两次都 usage → 仍 `GIT_USAGE_ERROR`；timeout 仍不 fallback。新增 L0 usage → L1 成功的 FakeBackend 测试。

### Files

- `src/agent_foundations/tools/git/service.py`
- 新增 probe/fallback 最小模块
- `tests/unit/tools/git/`（FakeBackend：探测缓存、L0→L1、耗尽、not-a-repo 不 fallback）
- `tests/integration/test_git_read_tools.py` 增加 docker diff/log（可与现有 status smoke 同夹具或并列）

### Tests（Red 在改生产代码前）

- FakeBackend：第一次 preferred argv 返回 unknown option，第二次 L1 成功 → 工具成功且只 fallback 一次
- 两次都 usage → `GIT_USAGE_ERROR`，不是 `NOT_A_REPOSITORY`
- `fatal: not a git repository` → 不发 L1
- `git --version` 每个 `GitReadService` 实例只跑一次（计数 FakeBackend）
- 解析 `version < 2.15.0` 时跳过 L0，直接 L1
- 既有 `--no-ext-diff` 位于 subcommand 之后的测试保持绿
- Tool schema 仍 `additionalProperties: false`，status 无属性；diff 仍只有 path/staged/max_bytes；log 仍只有 limit
- Docker（Additional）：同一 `legacy_patch` 镜像上 status + diff + log 成功；无残留 `af-*` 容器。usage vs not-a-repo 用 FakeBackend 覆盖即可，不必在真实镜像里伪造 unknown option

### Verification contract

```text
Target tests：
conda run -n agent-foundations python -m pytest tests/unit/tools/git -q

Affected regression tests：
conda run -n agent-foundations python -m pytest tests/unit/tools/git tests/integration/test_git_read_tools.py -q

Full suite：not-required
Full suite reason：不扩大写权限；Git 仍只读、argv 仍由 Runtime 生成。Docker 子集放 Additional gates，不重跑 Phase 1 完整基线。

Additional gates：
conda run -n agent-foundations python -m pytest tests/integration/test_git_read_tools.py -m docker -q
conda run -n agent-foundations python -m ruff check src/agent_foundations/tools/git tests/unit/tools/git tests/integration/test_git_read_tools.py
conda run -n agent-foundations python -m mypy src/agent_foundations/tools/git tests/unit/tools/git
git diff --check
```

Docker 门禁（本 Task 仅此授权）：只使用本机已有 `agent-foundations-sandbox:phase2`；**禁止** `docker pull`、`docker build`、改 Dockerfile、prune。`-m` 必须恰好是 `docker`（现有 skip 判断是 `getoption("-m") != "docker"`）。若 daemon 或镜像不存在，或镜像内没有 `git`：evidence 将 Additional gate 标为 `blocked`，不要 skip 当通过，也不要为跑测试去拉/重建镜像。无 `-m docker` 时现有 skip 逻辑保持。

Windows：`$env:PYTHONIOENCODING='utf-8'`。禁止付费 API、commit、改 gate_id、修 Task 35 P3。

依赖：Task 35 已用户验收。

**User acceptance:** 2026-09-04 用户确认 `确认「Task 36 / phase-2d-task-20 用户验收通过」`；记录于本计划与 `docs/task-evidence/phase-2d-task-20.md` §9。范围仅限 Sandbox Git 每实例一次 `("git", "--version")` 探测、预定义 L0→L1 fallback（仅 `GIT_USAGE_ERROR`；旧 git `< 2.15.0` 直接 L1）、以及同一 `legacy_patch` 镜像上 status/diff/log Docker 回归。未改 Policy、gate_id、Chat、Artifact、Dockerfile、Task 35 P3。独立复验为 targeted：Target 17 passed；Affected 20 passed / 1 skipped；Docker Additional 1 passed / 3 deselected；本机已有 `agent-foundations-sandbox:phase2`（`sha256:250e993fbf4c…`），无 pull/build，测后无残留 `af-*` 容器；ruff/mypy/`git diff --check` exit 0。TDD 过程证据为 complete；本次确认不独立见证历史 Red→Green。reviewer P3（L1 隔离弱于 L0；探测失败按实例缓存）不因本次确认要求立即返工。本确认不是 Task 25 完成，不是用户 Phase 2 完成；Step 10/11 保持未勾选。Task 37 仍需单独授权。未授权 commit、push、付费 3×3 或 Phase 3。

---

## Task 37 / `phase-2d-task-21`：审批 PolicyRequest 渲染

### Goal

审批卡按 **PolicyRequest / PolicyOutcome** 字段渲染，不再靠「不是 patch 就当 External read」。Chat UI 保持 Task 29 英文标题。不改 Policy 矩阵、不签发提前的 capability_id、不做 schema migration。

### 现状（不要重复建设）

- Task 29 已按 `tool_name === "run_command"` / `apply_patch` 分支标题；`tests/chat/activity.test.tsx` 已断言命令卡不是 External read。
- SSE `approval.requested` 仍只有 `approval_id` / `tool_call_id` / `tool_name` / `canonical_path` / Chat `operation` / 启发式 `scope`。**没有** `resource_kind`、`policy_decision`。
- App 在 `approval.requested` 时把 `activeApproval` 置空并 **GET `/state`**；卡片真相是 `PendingApprovalState`，不是 SSE 解析。GET 同样没有 Policy 字段；`run_command` 的 sqlite `AccessOperation` 仍是 `read`，所以 meta 会显示 read。
- `request_capability` 已有 `PolicyRequest`，但 `request()` 发布事件时丢掉了。`run_command` / `apply_patch` 的 Chat 路径只调 `coordinator.request(ApprovalRequest)`。
- `ApprovalCard` 只在 patch 上显示 Policy/Resource；`activeApprovalFromPending` 对 apply 硬编码 `resource_kind=project_path`，对 command 不填。

### Stable contract

SSE `approval.requested` 与 GET `pending_approval` **同一组字段**（缺一则前端不得当成 External read）：

```text
tool_name
operation          # PolicyRequest.operation：read | apply | run（不是 Chat AccessOperation.READ 冒充命令）
resource_kind      # PolicyRequest.resource.kind：sandbox_command | project_path
scope              # PolicyRequest.resource.scope：project_internal | external_exact_path
policy_decision    # PolicyOutcome.decision：ask（审批卡出现时）
canonical_path     # 保持现有显示标识
```

禁止出现 `capability_id`。签发前可省略 capability 摘要。不要把 capability 写进 sqlite。

`_build_requested_event` 必须吃 `PolicyRequest` + `PolicyOutcome`（或经它们填好的视图）。`request()` / `request_capability` 把已有 PolicyRequest 传下去。filesystem 已有 `_external_policy_request`。`run_command` / `apply_patch` 的 Chat 调用方用现有 manifest 构造 PolicyRequest（`RUN_COMMAND_MANIFEST` operation=`run`；`APPLY_PATCH_MANIFEST` operation=`apply`），不要新编 Policy 规则。

GET 无 waiter 时：**禁止 schema migration**。用与上表一致的锁定推导（仅这三行）：

```text
tool_name=run_command → operation=run, resource_kind=sandbox_command, scope=project_internal, policy_decision=ask
tool_name=apply_patch 或 sqlite operation=apply → operation=apply, resource_kind=project_path, scope=project_internal, policy_decision=ask
其余（外部 read_file 等）→ operation=read, resource_kind=project_path, scope=external_exact_path, policy_decision=ask
```

sqlite 仍存现有 `AccessOperation`（`read`/`apply`）。视图层映射，不改库。

标题锁定（英文，与 Task 29 测试一致；**resource_kind 优先于 tool_name**）：

```text
resource_kind=sandbox_command
  → "Controlled command approval"
resource_kind=project_path 且 operation=apply
  → "Controlled patch approval"
resource_kind=project_path 且 scope=external_exact_path
  → "External read approval"
```

未知 `resource_kind` **不得** 回落到 External read（解析失败或通用 "Approval request"）。三种卡都显示 Policy 与 Resource kind。命令卡 meta 显示 `run` / `sandbox_command` / `project_internal`，不得显示成 read-only external path。

`parseApprovalFromEvent` 与 `activeApprovalFromPending` 必须读新字段；不要再对 apply 硬编码、对 command 留空。

禁止：改 PolicyEngine；改 gate_id；改 Git；stdout/stderr 双标签（Task 38）；Docker；付费 API；commit。

### Files

- `src/agent_foundations/chat/approvals.py`（事件载荷）
- `src/agent_foundations/chat/api.py`（`PendingApprovalState`）
- `src/agent_foundations/chat/tool_execution.py`（把 PolicyRequest 传入 request）
- `web/chat/components/ApprovalCard.tsx`
- `web/chat/state/{types,reducer}.ts`
- `tests/unit/chat/test_approvals.py`
- `tests/integration/test_chat_api.py`（pending_approval 精确字典）
- `tests/chat/activity.test.tsx` 及受影响 reducer/app 测试

### Tests（Red 在改生产代码前）

- `run_command` SSE：`operation=run`、`resource_kind=sandbox_command`、`scope=project_internal`、`policy_decision=ask`；无 `capability_id`
- GET pending `run_command`：同上，即使 sqlite operation 仍是 `read`
- `apply_patch`：`operation=apply`、`resource_kind=project_path`
- `read_file` 外部：`resource_kind=project_path`、`scope=external_exact_path`；标题 External read
- ApprovalCard：命令卡标题 Controlled command approval，queryByText External read 为 null；三种卡都有 Policy/Resource
- 缺 `resource_kind` 的事件：不渲染 External read
- 既有「SSE 只触发 refetch、卡片以 HTTP 为准」行为保持

### Verification contract

```text
Target tests：
conda run -n agent-foundations python -m pytest tests/unit/chat/test_approvals.py -q
npm run test:chat

Affected regression tests：
conda run -n agent-foundations python -m pytest tests/unit/chat/test_approvals.py tests/integration/test_chat_api.py tests/integration/test_chat_approval_flow.py tests/integration/test_ask_always_run_command_twice.py -q

Full suite：not-required
Full suite reason：只扩展审批视图字段，不改 Policy 决策或权限。Playwright e2e 不在本 Task。

Additional gates：
npm run typecheck:chat
conda run -n agent-foundations python -m ruff check src/agent_foundations/chat/approvals.py src/agent_foundations/chat/api.py src/agent_foundations/chat/tool_execution.py tests/unit/chat/test_approvals.py tests/integration/test_chat_api.py
conda run -n agent-foundations python -m mypy src/agent_foundations/chat/approvals.py src/agent_foundations/chat/api.py src/agent_foundations/chat/tool_execution.py tests/unit/chat/test_approvals.py
git diff --check
```

Windows：`$env:PYTHONIOENCODING='utf-8'`。禁止 Docker、付费 API、commit、改 gate_id/Git/Artifact。

依赖：Task 36 已用户验收。

**User acceptance:** 2026-09-04 用户确认 `确认「Task 37 / phase-2d-task-21 用户验收通过」`；记录于本计划与 `docs/task-evidence/phase-2d-task-21.md` §9。范围仅限审批 SSE/GET 的 PolicyRequest 视图字段与 ApprovalCard 按 `resource_kind` 渲染；sqlite 仍存 `read`/`apply`；无 `capability_id`、无 schema migration、未改 Policy 矩阵。独立复验为 targeted：Target pytest 28 passed；`npm run test:chat` 81 passed；Affected 67 passed；`npm run typecheck:chat`、ruff、mypy、`git diff --check` exit 0。TDD 过程证据为 complete；本次确认不独立见证历史 Red→Green。reviewer P3（GET 一律三行推导；未知 `tool_name` 映射为 external read 行；vitest 不是真浏览器）不因本次确认要求立即返工。本确认不是 Task 25 完成，不是用户 Phase 2 完成；Step 10/11 保持未勾选。Task 38 仍需单独授权。未授权 commit、push、付费 3×3 或 Phase 3。

---

## Task 38 / `phase-2d-task-22`：stdout/stderr 标签

### Goal

Chat 命令反馈把 stdout / stderr **分开展示**。API `pages` 的 `stream` **必须由调用方显式传递**。不改 sanitizer、raw ticket、Artifact 根目录、Policy、gate_id。

### 现状（不要重复建设）

- 后端已分文件保存 stdout/stderr；`CommandOutputAccessService.read` 的 selector **已经要求** `stream`。
- Chat UI `fetchCommandOutputPage` 已显式传 `stream`。缺口：`CommandFeedbackCard` 把两路拼进同一个 `<pre>`；空 stderr 与有内容 stdout 无法分开展示。
- FastAPI `get_command_output_page(..., stream: str = "stderr")` **静默默认 stderr**。漏传 query 时读到 stderr，不是 422。这是本 Task 要改的 API 合同。
- Task 29 已要求 stdout-first：展开后先能看到 stdout 行，空 stderr 不得覆盖 stdout。本 Task 用 tab 取代拼接，仍保持 stdout-first 默认选中。
- 模型 Tool `read_command_output` 的 selector 已要求 `stream`。**不要**改模型 Tool schema。

### Stable contract

API：

```text
GET .../command-artifacts/{artifact_id}/pages
query: stream, start_line, line_count
stream 必填，枚举 stdout | stderr
缺 stream → HTTP 422（不要默认 stderr）
非法 stream → 保持现有 AccessError / 400
charge_budget=False、sanitize、不返回 raw：保持不变
```

UI `CommandFeedbackCard`：

```text
点击 Show sanitized output 后才请求 pages；禁止预取 raw
一次展开拉 stdout 与 stderr 各一页（显式 stream），分开保存，禁止拼成一块
tablist：Stdout / Stderr（role=tab）
默认选中：stdout 有行 → stdout；否则 stderr 有行 → stderr；双空 → stdout
空态文案锁定：
  stdout 无行 → "No stdout"
  stderr 无行 → "No stderr"
四种夹具都要测：stdout-only / stderr-only / 双有 / 双空
Download raw 仍走 ticket；Show 路径不得出现 /raw
```

禁止：改 `parse_selector` 允许无 stream；把 raw 默认给 UI；改 Artifact 根、sweep、审批卡、Git、gate_id。

### Files

- `src/agent_foundations/chat/api.py`（去掉 `stream` 默认值）
- `web/chat/components/CommandFeedbackCard.tsx`
- `web/chat/styles.css`（仅 tab 最小样式）
- `tests/chat/command-feedback.test.tsx`
- `tests/integration/test_command_output_api.py`

### Tests（Red 在改生产代码前）

- GET `/pages` 不带 `stream` → 422，响应不是 stderr 内容
- GET 显式 `stream=stdout` / `stderr` 仍 sanitize（既有密钥断言保持）
- vitest：stdout-only 默认 Stdout tab 显示行，Stderr tab 为 "No stderr"
- stderr-only 默认 Stderr tab；Stdout tab 为 "No stdout"
- 双有：两 tab 各显示自己的行，互不覆盖
- 双空：两 tab 都是空态文案
- 展开前不 fetch；展开后 URL 含 `stream=stdout` 与 `stream=stderr`；无 `/raw`

### Verification contract

```text
Target tests：
npm run test:chat
conda run -n agent-foundations python -m pytest tests/integration/test_command_output_api.py -q

Affected regression tests：
conda run -n agent-foundations python -m pytest tests/integration/test_command_output_api.py tests/integration/test_command_output_access.py tests/unit/command_output/test_access.py -q

Full suite：not-required
Full suite reason：只改 Chat pages 默认值与反馈卡布局；sanitizer / raw ticket / 模型 Tool 不变。

Additional gates：
npm run typecheck:chat
conda run -n agent-foundations python -m ruff check src/agent_foundations/chat/api.py tests/integration/test_command_output_api.py
conda run -n agent-foundations python -m mypy src/agent_foundations/chat/api.py tests/integration/test_command_output_api.py
git diff --check
```

Windows：`$env:PYTHONIOENCODING='utf-8'`。禁止 Docker、付费 API、commit。Playwright e2e 不在本 Task。

依赖：Task 37 已用户验收。

**User acceptance:** 2026-09-05 用户确认 `确认「Task 38 / phase-2d-task-22 用户验收通过」`；记录于本计划与 `docs/task-evidence/phase-2d-task-22.md` §9。范围仅限 Chat `pages` 去掉 `stream` 静默默认、缺参 422，以及 `CommandFeedbackCard` stdout/stderr tab 与空态。未改 sanitizer、raw ticket、Artifact 根、sweep、Policy、gate_id、模型 `read_command_output` schema。独立复验为 targeted：`npm run test:chat` 84 passed；Target API 4 passed；Affected 12 passed；`npm run typecheck:chat`、ruff、mypy、`git diff --check` exit 0。TDD 过程证据为 complete；本次确认不独立见证历史 Red→Green。reviewer P3（vitest 不是真浏览器；tab 无 `aria-controls`/方向键；store 尾空串不算空态）不因本次确认要求立即返工。本确认不是 Task 25 完成，不是用户 Phase 2 完成；Step 10/11 保持未勾选。Task 39 仍需单独授权。未授权 commit、push、付费 3×3 或 Phase 3。

---

## Task 39 / `phase-2d-task-23`：独立数据根

### Goal

Chat 生产路径不再把 sqlite / artifacts / controller / traces 放进仓库或 `state_db.parent / "command-artifacts"`。一个数据根，默认同现有 `default_artifact_root()` 的父目录 `AgentFoundations`。**不要**写死 `D:\`。不接入 sweep（Task 40）。不改 HTTP `/command-artifacts/` 路由名。

### 现状（不要重复建设）

- `CommandArtifactStore.default_artifact_root()` 已是 `%LOCALAPPDATA%/AgentFoundations/command-output`（或 XDG 等价），且拒绝 Git worktree。
- Chat `build_chat_services` **实际**用 `state_db.parent / "command-artifacts"` 与 `state_db.parent / "controller"`。CLI 默认 `state_db=.agent-foundations/chat.sqlite3`、`trace_dir=traces`，从仓库启动会把数据放进 worktree，并在创建 store 时撞 `ArtifactRootError`。
- HTTP 路径仍是 `/command-artifacts/{id}/pages`。那是 API 名，不是磁盘目录。

### Stable contract

锁定名称（只此一种，不要再发明第二套）：

```text
CLI：agent-foundations chat --data-root PATH
环境变量：AGENT_FOUNDATIONS_DATA_ROOT
优先级：显式 --data-root > 环境变量 > default_artifact_root().parent
```

`chat` 命令 **去掉** `--state-db` 与 `--trace-dir`（改由 data-root 派生）。独立 `viewer` 命令仍可保留自己的 `--trace-dir`。

布局锁定：

```text
<data-root>/
  chat.sqlite3
  command-output/     # 必须等于该根下的 command-output，与 default_artifact_root() 在默认根时重合
  controller/
  traces/
```

`build_chat_services(data_root: Path)`：只接收已解析的绝对 data-root。测试传入 `tmp_path`（pytest 临时目录，不在本仓库 Git 树内）。**禁止**测试写真实 `%LOCALAPPDATA%`。

校验：整个 `data_root` 走现有 `ArtifactRootError` 语义（必须绝对路径、非 reparse、不是 Git worktree / 项目目录）。失败时 CLI exit 2，不要静默改回仓库内路径。

旧路径检测（仅提示，不搬文件）：若 CWD 下存在 `.agent-foundations/chat.sqlite3`、`.agent-foundations/command-artifacts` 或 `./traces`，向 console 打印 leftover 警告，写明新根路径。不要 copy/move/delete。

禁止：写死盘符；自动迁移生产数据；改 sweep / 512MB；改 Policy / gate_id / Git；改 pages/raw HTTP 合同。

### Files

- 新增最小 `src/agent_foundations/chat/data_root.py`（resolve + layout + leftover 检测；名称可微调）
- `src/agent_foundations/cli/main.py`（`chat` 选项与 `build_chat_services` 签名）
- 所有 `build_chat_services(traces, sqlite)` 调用方改为 `build_chat_services(tmp_path)`（或显式 data_root）
- `tests/unit/chat/` 新 Red（默认根、env、CLI 优先级、拒绝 git worktree、leftover 警告）
- `README.md` 仅改默认路径表那一行（若仍写 `.agent-foundations/command-artifacts/`）

### Tests（Red 在改生产代码前）

- 默认 data-root 是 `default_artifact_root().parent`，含 `AgentFoundations`，不含盘符字面量 `D:\\AgentFoundationsData`
- `--data-root` 覆盖环境变量；环境变量覆盖默认
- data-root 落在带 `.git` 的树内 → `ArtifactRootError` / CLI 2
- `build_chat_services(tmp_path)` 把 store 指到 `tmp_path / "command-output"`，controller 为 `tmp_path / "controller"`，sqlite 为 `tmp_path / "chat.sqlite3"`
- 生产 `build_chat_services` 源码不再出现 `command-artifacts` 磁盘路径
- leftover 文件存在时警告包含旧路径与新根；不创建/删除那些文件

### Verification contract

```text
Target tests：
conda run -n agent-foundations python -m pytest tests/unit/chat/test_data_root.py tests/unit/command_output/test_store.py -q

Affected regression tests：
conda run -n agent-foundations python -m pytest tests/unit/chat/test_data_root.py tests/unit/runtime/test_coding_prompt.py tests/unit/runtime/test_coding_budget.py tests/unit/chat/test_plan_persistence.py tests/integration/test_chat_planning_tools.py tests/integration/test_ask_always_run_command_twice.py tests/integration/test_command_feedback_agent_flow.py tests/integration/test_phase2_coding_agent.py tests/integration/test_task16_production_wiring.py tests/unit/tools/command/test_run_command.py -q

Full suite：not-required
Full suite reason：只改 Chat 本机数据布局；不扩大 Tool/权限。Playwright e2e 不在本 Task；若签名变更导致 `tests/e2e/test_chat_ui.py` 调用失败，一并改调用，不必跑浏览器。

Additional gates：
conda run -n agent-foundations python -m ruff check src/agent_foundations/chat/data_root.py src/agent_foundations/cli/main.py tests/unit/chat/test_data_root.py
conda run -n agent-foundations python -m mypy src/agent_foundations/chat/data_root.py src/agent_foundations/cli/main.py tests/unit/chat/test_data_root.py
git diff --check
```

Windows：`$env:PYTHONIOENCODING='utf-8'`。禁止 Docker、付费 API、commit、写真实用户数据目录做测试。

依赖：Task 38 已用户验收。

**User acceptance:** 2026-09-05 用户确认 `确认「Task 39 / phase-2d-task-23 用户验收通过」`；记录于本计划与 `docs/task-evidence/phase-2d-task-23.md` §9。范围仅限 Chat 独立数据根（`--data-root` / `AGENT_FOUNDATIONS_DATA_ROOT` / `default_artifact_root().parent`）、布局 `chat.sqlite3` + `command-output/` + `controller/` + `traces/`、去掉 chat `--state-db`/`--trace-dir`、leftover 警告不搬文件。未改 sweep/512MB、Policy、gate_id、pages/raw HTTP。独立复验为 targeted：Target 26 passed；Affected 49 passed / 1 skipped；ruff、mypy、`git diff --check` exit 0；另抽查 CLI chat 5 passed。TDD 过程证据为 complete；本次确认不独立见证历史 Red→Green。reviewer P3（leftover 只看 CWD；layout 测试未断言 controller；Playwright 未跑）不因本次确认要求立即返工。本确认不是 Task 25 完成，不是用户 Phase 2 完成；Step 10/11 保持未勾选。Task 40 仍需单独授权。未授权 commit、push、付费 3×3 或 Phase 3。

---

## Task 40 / `phase-2d-task-24`：sweep 接入 Chat

### Goal

把**已有** `ArtifactRetentionSweeper` 接入 Chat lifespan：启动时 sweep，运行中按常量间隔定期 sweep。默认全局容量改为 **512 MiB**。本机 loopback HTTP 提供占用查询、手动 sweep、按 run 清理。不新发明淘汰算法。不改 Policy、data-root、pages/raw、64 MiB 单次上限。不做 Task 41 日志分级。

TDD：required。

### 现状（不要重复建设）

- `reserve()` / `sweep_expired()` / `sweep_pending_delete()` 在 `ArtifactRetentionSweeper`；`mark_pending_delete_for_run()` 在 `CommandArtifactRepository`。Chat `run_command` 已调用 `reserve()`。`sweep_expired()` **只在单测调用**，lifespan 从不 sweep。
- `DEFAULT_GLOBAL_CAPACITY_BYTES` 现为 **1 GiB**，`retention.py` 与 `store.py` 各写一份。`command_output/__init__.py` 已从 `retention.py` 再导出。`tests/unit/command_output/test_retention.py` 断言 `1024 * 1024 * 1024`。
- `ChatServices` 无 sweeper 字段。大量测试用默认字段构造 `ChatServices`；**缺 sweeper 时 lifespan 必须 no-op**，不得把 retention 做成必填。
- `_require_local_user` 已有。Chat 仍绑 `127.0.0.1`。不要做公网 occupancy API，也不要另开 CLI。

权威默认是**本硬化计划**。Phase 2 实施计划 Task 18 里的历史「1 GiB」句子不要改写。

### Stable contract

容量（canonical 在 `retention.py`；`store.py` 必须导入同一名字，禁止再抄一份）：

```text
DEFAULT_GLOBAL_CAPACITY_BYTES = 512 * 1024 * 1024
EXECUTION_OUTPUT_LIMIT_BYTES = 64 * 1024 * 1024  不变
DEFAULT_RETENTION = timedelta(days=7)            不变
reserve() / _evict() 语义不变
```

允许顺手让 `store.py` 的 `EXECUTION_OUTPUT_LIMIT_BYTES` 也改为从 `retention.py` 导入；不要改 64 MiB 数值。

为 usage API 给 sweeper 增加只读访问器（不要让 handler 读 `_global_capacity_bytes`）：

```text
global_capacity_bytes -> int
retention_period      -> timedelta
```

生命周期：

```text
ChatServices 增加（均有默认，不得破坏现有构造）：
  retention: ArtifactRetentionSweeper | None = None
  artifact_sweep_interval_seconds: float = 3600.0

模块常量 ARTIFACT_SWEEP_INTERVAL_SECONDS = 3600.0，作为上述字段默认值。

build_chat_services() 必须传入真实 sweeper。
viewer-only（chat_services is None）不 sweep。
retention is None（现有多数 Chat 测试）不 sweep、三个新端点 404。

lifespan 顺序：
  1. repository.initialize()
  2. interrupt_unfinished()
  3. 若 retention 不是 None：在 thread 里 sweep_expired()；同 tick 允许再 sweep_pending_delete()
  4. 若 interval > 0：启动 asyncio 任务；循环先 sleep(interval) 再 sweep（启动时已 sweep，t=0 不要再扫一次）
  5. yield
  6. finally：先 cancel 定期任务并 await（吞掉该任务的 CancelledError，不要借此改全局日志分级）
  7. 再走现有 coordinator.shutdown() → supervisor.shutdown()，顺序不得对调

sync sqlite 工作用 asyncio.to_thread，不要把 sqlite 打进 event loop。
interval <= 0：不做定期任务；启动 sweep 仍做。
测试用 dataclasses.replace(..., artifact_sweep_interval_seconds=0.05, retention=recording) 注入。
```

本机控制面（挂在已有 `/api/chat` router；复用 `_require_local_user`；不要新鉴权；不要改 uvicorn host）：

```text
GET  /api/chat/artifacts/usage
     require_origin=False（与 raw GET 相同；若带了非法 Origin 仍 403）
     200: {
       "used_bytes": int,                 # repository.used_bytes()
       "capacity_bytes": int,             # sweeper.global_capacity_bytes
       "retention_seconds": int           # int(sweeper.retention_period.total_seconds())
                                          # 默认 604800
     }

POST /api/chat/artifacts/sweep
     require_origin=True（与 download-ticket 相同）
     to_thread: sweep_expired + sweep_pending_delete
     200: { "ok": true }

POST /api/chat/artifacts/runs/{run_id}/purge
     require_origin=True
     run_id: UUID（非法 → FastAPI 422）
     to_thread:
       ids = repository.mark_pending_delete_for_run(str(run_id))
       sweep_pending_delete()
     200: { "ok": true, "purged_artifact_ids": [...] }
     无该 run 的 artifact → 仍 200，purged_artifact_ids 为空（幂等）
     不得删除其他 run 的 artifact
```

缺 sweeper 或缺 artifact repository：三个端点 404 `not found`。不要返回 raw stdout/stderr。不要绑 `0.0.0.0`。不要新 CLI。不要 Chat UI / Playwright。

禁止：新的 LRU/加权淘汰；改 `reserve()`；改 data-root 布局；改 pages/raw ticket；改 64 MiB；改 Policy / gate_id / Git；做 Task 41 日志分级；改写 Phase 2 实施计划历史 1 GiB 文本；修 Task 35–39 reviewer P3。

### Files

- `src/agent_foundations/command_output/retention.py`
- `src/agent_foundations/command_output/store.py`（去掉重复容量常量，改为导入）
- `src/agent_foundations/chat/api.py`
- `src/agent_foundations/viewer/app.py`
- `src/agent_foundations/cli/main.py`（`build_chat_services` 传入 sweeper）
- `tests/unit/command_output/test_retention.py`（512 MiB）
- `tests/unit/chat/test_artifact_sweep.py`（新建：启动 sweep、interval 注入、退出后任务停、retention is None 不扫）
- `tests/integration/test_command_output_api.py`（usage / sweep / purge / 坏 Origin 403）

### Tests（Red 在改生产代码前）

- `DEFAULT_GLOBAL_CAPACITY_BYTES == 512 * 1024 * 1024`；不再等于 1 GiB；64 MiB 与 7 days 不变
- recording sweeper：TestClient 进入 lifespan 后 `sweep_expired` 至少 1 次；`retention is None` 为 0 次
- `artifact_sweep_interval_seconds=0.05` 时，短等待后调用次数 ≥ 2（启动 + 至少一次定期）；退出 TestClient 后不再增加
- GET usage：`capacity_bytes` 为 sweeper 配置值，`retention_seconds == 604800`（默认 retention 时）
- POST sweep：过期 retained 被清掉
- POST purge：只标记并删除该 `run_id`；另一 run 仍在
- POST 缺 Origin / `Origin: https://evil.example` → 403 `ARTIFACT_SCOPE_DENIED`
- 既有 `reserve` 淘汰单测保持绿
- `test_chat_lifespan_shuts_down_coordinator_before_supervisor` 保持绿

### Verification contract

```text
Target tests：
conda run -n agent-foundations python -m pytest tests/unit/command_output/test_retention.py tests/unit/chat/test_artifact_sweep.py tests/integration/test_chat_approval_flow.py::test_chat_lifespan_shuts_down_coordinator_before_supervisor tests/integration/test_command_output_api.py -q

Affected regression tests：
conda run -n agent-foundations python -m pytest tests/unit/command_output/test_retention.py tests/unit/command_output/test_store.py tests/integration/test_command_artifact_lifecycle.py tests/integration/test_command_output_api.py tests/integration/test_chat_approval_flow.py tests/unit/chat/test_artifact_sweep.py -q

Full suite：not-required
Full suite reason：只把已有 sweeper 接入 Chat 生命周期并改默认容量常量；不扩大 Tool/权限。不得写成 full suite passed。

Additional gates：
conda run -n agent-foundations python -m ruff check src/agent_foundations/command_output/retention.py src/agent_foundations/command_output/store.py src/agent_foundations/chat/api.py src/agent_foundations/viewer/app.py src/agent_foundations/cli/main.py tests/unit/command_output/test_retention.py tests/unit/chat/test_artifact_sweep.py tests/integration/test_command_output_api.py
conda run -n agent-foundations python -m mypy src/agent_foundations/command_output/retention.py src/agent_foundations/command_output/store.py src/agent_foundations/chat/api.py src/agent_foundations/viewer/app.py src/agent_foundations/cli/main.py
git diff --check
```

Windows：`$env:PYTHONIOENCODING='utf-8'`。evidence：`docs/task-evidence/phase-2d-task-24.md`。禁止 Docker、付费 API、commit、写真实 `%LOCALAPPDATA%`、Playwright、`npm`。

依赖：Task 39 已用户验收。

**User acceptance:** 2026-09-05 用户确认 `确认「Task 40 / phase-2d-task-24 用户验收通过」`；记录于本计划与 `docs/task-evidence/phase-2d-task-24.md` §9。范围仅限把已有 `ArtifactRetentionSweeper` 接入 Chat lifespan（启动 sweep + 默认 3600s 定期 sweep）、canonical 512 MiB 全局容量、本机 loopback `usage` / `sweep` / `purge` HTTP。未改 `reserve()` / 64 MiB / 7 天、data-root、pages/raw、Policy、gate_id、Task 41 日志分级。独立复验为 targeted：Target 20 passed；Affected 42 passed / 1 skipped；ruff、mypy、`git diff --check` exit 0。TDD 过程证据为 complete；本次确认不独立见证历史 Red→Green。reviewer P3（定期 sweep 为进程内 best-effort；无 sweeper 的 ChatServices 三端点 404；无 Chat UI 占用入口）不因本次确认要求立即返工。本确认不是 Task 25 完成，不是用户 Phase 2 完成；Step 10/11 保持未勾选。Task 41 仍需单独授权。未授权 commit、push、付费 3×3 或 Phase 3。

---

## Task 41 / `phase-2d-task-25`：关闭语义

### Goal

给 Chat / Trace SSE 与 Chat lifespan 补上**可测试的关闭日志分级**，并补 lifespan 层测试：SSE 取消后订阅队列清空、启动时 `interrupt_unfinished`、退出后 supervisor 清空。继续吞掉 SSE `CancelledError`（Task 29 合同保持）。不改 Policy、runner 中断语义、sweep、data-root。本 Task 是本硬化计划最后一项；完成后 **停止**，不得勾选 Task 25 Step 10/11，不得开始 3×3。

TDD：required。

### 现状（不要重复建设）

- Chat / Trace SSE `generate()` 已 `except CancelledError: return`（`test_chat_and_trace_sse_generate_swallows_cancelled_error`）。无 logger。
- lifespan 已 `initialize` → `interrupt_unfinished` → sweep → yield → cancel sweep → coordinator → supervisor。无 shutdown 日志，无 `app.state` 关机旗标。
- `interrupt_unfinished` / `RunSupervisor.shutdown` 已有单测，但没有「经 `create_app` lifespan」的接线测试。
- `ConversationRunner` 对 `CancelledError` 已 interrupt 再 raise。不要改成 error 日志，也不要吞掉。

### Stable contract

新建 `src/agent_foundations/chat/lifecycle.py`（Chat 与 Trace SSE 共用，禁止两套文案）：

```text
logger name: agent_foundations.chat.lifecycle

SSE_CLIENT_DISCONNECT = "sse cancelled: client disconnect"   # DEBUG
SSE_LIFESPAN_CANCEL   = "sse cancelled: lifespan shutdown"   # INFO
SSE_FAILED            = "sse failed"                         # ERROR + exc_info
CHAT_LIFESPAN_SHUTDOWN = "chat lifespan shutdown"            # INFO

app.state.chat_shutting_down: bool
is_shutting_down(request) 必须用 request.scope.get("app")；
直接调 route.endpoint、scope 无 app 时视为 False（现有 SSE 单测不得 KeyError）
```

分级：

```text
SSE generate() CancelledError：
  is_shutting_down → INFO SSE_LIFESPAN_CANCEL
  否则 → DEBUG SSE_CLIENT_DISCONNECT
  然后 return（继续吞掉，禁止 re-raise 成 ASGI 500）

SSE while 因 is_disconnected() 正常退出：
  DEBUG SSE_CLIENT_DISCONNECT 一次；不要和随后的 CancelledError 双记

SSE generate() 其它 Exception：
  ERROR SSE_FAILED（exc_info；只记 type 名，禁止 event payload / 用户 query / secret）
  再 raise（finally 仍要 aclose 订阅）

lifespan finally 开头（cancel sweep 之前）：
  若有 app：state.chat_shutting_down = True
  INFO CHAT_LIFESPAN_SHUTDOWN
  再走现有 sweep cancel → coordinator → supervisor，顺序不得对调

定期 sweep 的 CancelledError：继续 suppress；允许 DEBUG，禁止 ERROR
runner / durable CancelledError：不改
```

`source=` 仅为 `"chat"` 或 `"trace"`，写进同一句日志（例如 `sse cancelled: client disconnect (chat)`）。

订阅关闭：

```text
ChatEventBroker.subscriber_count(conversation_id) -> int
viewer.stream.EventBroker.subscriber_count(session_id) -> int
SSE generate() 结束后（cancel / disconnect / aclose）对应 count == 0
```

lifespan 行为（已有实现，本 Task 要有接线测试，不要重写算法）：

```text
TestClient 进入：先 interrupt_unfinished，把预先插入的 active run 标 interrupted
TestClient 退出：supervisor.is_active(*) is False；再 start() → ChatConflictError（已关闭）
既有 coordinator→supervisor 顺序测试保持绿
既有 SSE swallow 测试保持绿
```

禁止：改 Policy / gate_id / Git / pages/raw / data-root / 512 MiB / reserve；修 Task 35–40 reviewer P3；改 runner 中断路径；把客户端断开打成 ERROR；结构化日志后端 / Sentry；Chat UI；Docker；付费 API；commit；勾选 Task 25；声称 Phase 2 完成。

### Files

- `src/agent_foundations/chat/lifecycle.py`（新建）
- `src/agent_foundations/chat/api.py`
- `src/agent_foundations/chat/events.py`（`subscriber_count`）
- `src/agent_foundations/viewer/app.py`
- `src/agent_foundations/viewer/stream.py`（`subscriber_count`）
- `tests/unit/chat/test_lifecycle.py`（新建：三级日志、lifespan interrupt、supervisor 清空、订阅 count=0）
- 必要时扩展 `tests/unit/chat/test_approvals.py::test_chat_and_trace_sse_generate_swallows_cancelled_error`（仍须 swallow）

### Tests（Red 在改生产代码前）

- caplog：`CancellingRequest.is_disconnected` 抛 `CancelledError` → DEBUG 含 `SSE_CLIENT_DISCONNECT` 与 `(chat)` / `(trace)`；无 ERROR
- caplog：`app.state.chat_shutting_down=True` 时同样 CancelledError → INFO 含 `SSE_LIFESPAN_CANCEL`；无 ERROR
- caplog：`is_disconnected` 抛普通 `RuntimeError` → ERROR 含 `SSE_FAILED` 与异常类型名；无 payload
- caplog：TestClient 退出 Chat app → INFO 含 `CHAT_LIFESPAN_SHUTDOWN`
- SSE 结束后 `subscriber_count == 0`
- 预先插入 RUNNING run，TestClient 进入后变为 INTERRUPTED
- TestClient 退出后 supervisor 不再 active，`start()` 冲突
- 既有 swallow 与 coordinator→supervisor 顺序保持绿

### Verification contract

```text
Target tests：
conda run -n agent-foundations python -m pytest tests/unit/chat/test_lifecycle.py tests/unit/chat/test_approvals.py::test_chat_and_trace_sse_generate_swallows_cancelled_error tests/integration/test_chat_approval_flow.py::test_chat_lifespan_shuts_down_coordinator_before_supervisor -q

Affected regression tests：
conda run -n agent-foundations python -m pytest tests/unit/chat/test_lifecycle.py tests/unit/chat/test_approvals.py::test_chat_and_trace_sse_generate_swallows_cancelled_error tests/unit/chat/test_supervisor.py tests/unit/chat/test_repository.py::test_interrupt_unfinished_marks_running_activity_interrupted tests/integration/test_chat_approval_flow.py tests/integration/test_chat_api.py::test_chat_sse_connected_keepalive_and_events tests/integration/test_viewer_api.py -q

Full suite：not-required
Full suite reason：只补关闭日志与 lifespan 接线测试，不扩大 Tool/权限。这是硬化计划最后一项，但不是 Task 25 / Phase 2 最终验收。不得写成 full suite passed。

Additional gates：
conda run -n agent-foundations python -m ruff check src/agent_foundations/chat/lifecycle.py src/agent_foundations/chat/api.py src/agent_foundations/chat/events.py src/agent_foundations/viewer/app.py src/agent_foundations/viewer/stream.py tests/unit/chat/test_lifecycle.py
conda run -n agent-foundations python -m mypy src/agent_foundations/chat/lifecycle.py src/agent_foundations/chat/api.py src/agent_foundations/chat/events.py src/agent_foundations/viewer/app.py src/agent_foundations/viewer/stream.py
git diff --check
```

Windows：`$env:PYTHONIOENCODING='utf-8'`。evidence：`docs/task-evidence/phase-2d-task-25.md`。禁止 Docker、npm、Playwright、付费 API、commit、写真实 `%LOCALAPPDATA%`。

依赖：Task 40 已用户验收。完成后停止；3×3 / Task 25 Step 10 须另授权。

**User acceptance:** 2026-09-05 用户确认 `确认「Task 41 / phase-2d-task-25 用户验收通过」`；记录于本计划与 `docs/task-evidence/phase-2d-task-25.md` §9。范围仅限 Chat/Trace SSE 关闭日志分级、`app.state.chat_shutting_down`、`subscriber_count`，以及 lifespan 接线测试（interrupt / supervisor 清空 / coordinator→supervisor 顺序）。未改 Policy、runner 中断路径、sweep、data-root、pages/raw。独立复验为 targeted：Target 10 passed；Affected 31 passed；ruff、mypy、`git diff --check` exit 0。TDD 过程证据为 complete；本次确认不独立见证历史 Red→Green。reviewer P3（ERROR `exc_info` traceback 可能含异常消息；viewer-only 无 Chat lifespan 关机日志；interrupt 接线在 Red 时已绿）不因本次确认要求立即返工。本确认不是计划正文 Task 25 完成，不是用户 Phase 2 完成；Step 10/11 保持未勾选。本硬化计划无 Task 42。未授权 commit、push、付费 3×3 或 Phase 3。

---

## 4. 非目标

- 不重做 Task 30–34
- 不勾选 Task 25 Step 10/11
- 不把 `D:\AgentFoundationsData` 写进仓库默认值
- 不让模型传 git 或任意 argv
)
