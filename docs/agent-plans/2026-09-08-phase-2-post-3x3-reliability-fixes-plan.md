# Phase 2 Post-3×3 Reliability Fixes

**Date:** 2026-09-08  
**Status:** Task 45–48 / `phase-2d-task-29`–`phase-2d-task-32` 已于 2026-09-08–2026-09-09 用户验收通过（targeted）。本文件仍无 Task 49 实现项；Step 6 基线修绿见 `docs/agent-plans/2026-09-09-phase-2-step-6-baseline-unblock-plan.md`（Task 49 / `phase-2d-task-33`）。计划正文 Task 25 Step 10 已于 2026-09-09 用户验收通过（Round 3 9/9；见 `docs/task-evidence/phase-2d-task-9-step-10.md` §11）。§0 表仍是 2026-09-08 Round 2 核对快照，不得改写成通过。计划正文 Step 11 与用户 Phase 2 完成已于 2026-09-09 在父计划记录（见 `docs/task-evidence/phase-2d-task-9-step-11.md` §12–§13）。本文件不授权 commit、push 或 Phase 3。  
**Role:** planner 维护；本文件不实现生产代码  
**Parent:** `docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md`  
**Does not replace:** Task 25、3×3 操作合同、Task 42–44、可靠性 follow-on、产品硬化

## 0. 本轮 3×3 验收（planner 核对）

对照 `docs/task-evidence/phase-2d-task-9-step-10.md` §9 与当前代码：

| 结论 | 核对 |
|---|---|
| Step 10 不得勾选 | **同意。** Node attempt 3 失败则该类失败；无第 4 次重试。计划正文 Step 10 保持 `- [ ]`。 |
| 整轮失败原因是 Node-3 `InvalidModelResponseError` | **同意。** `AgentLoop` 在 `ProviderError`（含 `InvalidModelResponseError`）上把 session 标 `FAILED` 再抛出。`ResilientModelProvider` 把它列为 **non-retryable**（与 auth/HTTP 400 同类）。不是门禁 ID / 沙箱写不进：Node-1/2 已闭环。 |
| `SELECTOR_INVALID` 更普遍 | **同意作摩擦，不是本轮失败判据。** 选择器必须恰好三种互斥 shape；schema 只写了 `"selector": {"type": "object"}`。 |
| Chat `interrupted` vs Durable `running` | **同意为 P2 控制面缺口。** `ConversationRunner._safe_interrupt_run` 会尝试 Durable `RUNNING→CANCELLED`；但杀进程后的 lifespan `interrupt_unfinished` **只改 Chat `runs`**，不碰 `durable_runs`。且 Durable 转换只预期 `RUNNING`，冲突除 `NotFound` 外会冒出来。 |
| 无 Stop | **同意。** Chat UI/API 没有 Stop；合同用杀进程。 |
| 「第三张审批卡不存在」 | **同意改表述。** 以 sqlite 为准：安全类 `apply_patch` 1 deny + 4 approve。不要单开 Task 去修「卡不存在」。 |
| `PATCH_NOT_FOUND` | **同意：成立但不是 Step 10 失败原因。** 本计划不修。 |
| CLI `-m agent_foundations` | **同意。** 仓库无 `__main__.py`；入口是 `agent-foundations` 或 `-m agent_foundations.cli.main`。3×3 合同启动命令在本轮 planner 修订里改掉。不单开实现 Task。 |
| 旧 pin 根 symlink | **同意：不是本轮 blocker。** Task 44 新 pin 预检三门 0。 |
| 损坏 Node `build:chat=0` | **同意合理**（Vite 不跑 tsc）。 |

**不接受 Step 10 通过。不勾选 Step 11。不声称 Phase 2 完成。不授权本文件范围内重开付费 9 轮。**

挡住勾选的是 **畸形 tool `arguments` JSON 被升格成 Provider 崩溃、整轮判死**。2026-09-08 用户确认 Task 45 主路径改为「指出 JSON 错误点并作为工具失败让模型重发」，空包才走无 `tool_calls` 的可恢复 Provider 路径。后三项降低下次人工门的噪声与中断成本，仍须单独授权，禁止合成一个超大 Task。

## 1. Task 顺序

| 顺序 | 用户可见 | Task ID | Evidence | 主题 |
|---|---|---|---|---|
| 1 | Task 45 | `phase-2d-task-29` | `docs/task-evidence/phase-2d-task-29.md` | 畸形 tool JSON → 指出错误并让模型重发；空包可恢复 |
| 2 | Task 46 | `phase-2d-task-30` | `docs/task-evidence/phase-2d-task-30.md` | `read_command_output` 选择器 |
| 3 | Task 47 | `phase-2d-task-31` | `docs/task-evidence/phase-2d-task-31.md` | 中断同时收 Durable |
| 4 | Task 48 | `phase-2d-task-32` | `docs/task-evidence/phase-2d-task-32.md` | Chat Stop |

一次只执行用户确认的一个 Task。未确认的 prompt 不得实施。本文件不新增 Task 49；后续基线修绿不在本四项可靠性范围内。

**明确不修：** PathPolicy、gate_id、Sandbox pin、Task 42/43/44、审批矩阵、`PATCH_NOT_FOUND`、MCP/Browser、commit/push、付费 3×3。

Python：`$env:PYTHONIOENCODING='utf-8'` + `D:\anaconda\envs\agent-foundations\python.exe`。

---

## Task 45 / `phase-2d-task-29`：畸形 tool JSON 降成可恢复工具失败

**Lock revision（2026-09-08 用户确认）：** 不以「把整类 `InvalidModelResponseError` 丢进 `_RETRYABLE` + 无 `tool_calls` 继续」为主路径。Node-3 根因是 `validate_patch` 的 `function.arguments` 非法 JSON（`JSONDecodeError` at char 357），HTTP/`finish_reason=tool_calls` 均成功。主路径必须 **指出错误点并作为 TOOL 失败写回**，让模型重发同一工具。空 `choices` / 缺 `message` / 缺 `tool_call.id|name` 才走无 `tool_calls` 的可恢复 Provider 路径。

### Goal

付费轮遇到「完整 completion、某个 tool `arguments` 不是合法 JSON 对象」时，不得 `runs.status=failed` + `InvalidModelResponseError`。必须扣一步、给出可定位的 JSON 错误、让模型再调用同一工具。真正的空包不得一票否决整轮，但 **不得** 用同一 `request_id` 默默重试去修 Node-3 那种语法错误。

### 两路失败，两套收口

| 形态 | 适配器 | Loop |
|---|---|---|
| A. 有 `tool_call.id` 与 `name`，仅 `arguments` 无法 `json.loads` 成 JSON **object**（含 Node-3；亦含 `"42"` / 数组） | **不**抛 `InvalidModelResponseError`；返回带该 call 的 `ModelResponse` | 当 **工具失败** 写回，**禁止执行** |
| B. 空 `choices`、缺 `message`、任一 call 缺 `id` 或 `name` | 仍抛 `InvalidModelResponseError`（保留 `raw_response`） | **不** `session.failed`；无 `tool_calls` 短文案后 `next_step+1` |

同一 completion 里多个 call：**逐个**解析。合法 call 照常 `validate_call` / execute；非法 `arguments` 的 call 走 A。若 **任一** call 缺 `id` 或 `name`：整份 completion 改走 B，**这份响应里的 call 一个都不要执行**（fail-closed）。

### 锁定行为

#### A. 畸形 `arguments`（本 Task 主路径，打在 Node-3）

1. `ToolCall` 增加可选字段 `argument_parse_error: str | None = None`（默认 `None`）。有值即表示 arguments 未解析成功。`arguments` 仍必须是 JSON object：存 `{}`，**不要**把坏字符串塞进 `arguments`，也 **不要** 存完整 raw arguments。
2. `OpenAICompatibleProvider`：对每个 `tool_calls[]` 单独 `json.loads`。`JSONDecodeError`、解析结果不是 `dict`、或因此无法通过现有 `ToolCall` 校验时：填 `argument_parse_error`，`arguments={}`，**整次 `complete()` 成功返回**。禁止 `json_repair` 或任何「猜着补括号再执行」。
3. `argument_parse_error` 文案锁定为 **一条短字符串**（总长 ≤ 512），必须同时含：
   - 工具名
   - 异常类名与 `JSONDecodeError`/`TypeError` 消息（消息截断 160 字符）
   - 出错位置：`JSONDecodeError.pos`（若无则 `0`）
   - 该位置前后合计 **80** 字符窗口（不足则能截多少截多少）
   - 固定指令：`Repair the JSON and call the same tool again; do not resend the identical broken string.`
   - 禁止：完整 `raw_response`、凭据、`.env`、超过窗口的整段 `arguments`
4. `AgentLoop._execute_next_tool`：若 `call.argument_parse_error` 非空，**立即**合成
   `ToolResult(success=False, content=call.argument_parse_error, error_code="INVALID_TOOL_JSON")`
   然后走现有 `tool.call.failed` + TOOL 消息 + checkpoint + `next_step` 逻辑。
   **禁止** `registry.validate_call`、`tool_executor.execute`、Durable prepare、Policy 评估、recovery `evaluate_tool_call`。resume 从 `MODEL_RESPONSE_PERSISTED` 也必须认这个字段，不得把 `{}` 当真参数去跑 `validate_patch`/`apply_patch`。
5. 发给 OpenAI 的 assistant `tool_calls.function.arguments` 仍只序列化 `call.arguments`（即 `{}`）；模型靠 TOOL 消息里的 snippet 修 JSON。不要把 `argument_parse_error` 塞进 provider 的 function.arguments。
6. **不要**把 `INVALID_TOOL_JSON` 加入 `PARSE_ERROR_CODES` / `HARD_STOP_ERROR_CODES`。下一轮合法 `changes`/`diff` 必须能执行。

#### B. 结构无效 completion（辅路径）

1. `ResilientModelProvider`：仅将 `InvalidModelResponseError` 加入现有 `_RETRYABLE`（最多 `RetryPolicy.max_attempts=3`，**不要**改大）。A 路不再抛该异常，因此这 **不会** 对 Node-3 同类坏 `arguments` 做同一请求重试。`ProviderAuthenticationError`、普通 `ProviderError`（HTTP 400）、`FakeModelExhaustedError`、`ProviderAttemptExhaustedError` 仍一次失败。
2. 重试耗尽后 `AgentLoop` **不再** `session.status=FAILED` 再抛出 `InvalidModelResponseError`。改为：
   - 事件 `model.response.invalid`，payload `error=InvalidModelResponseError`；`raw_response` 走现有 `_safe_raw_response`（bytes → omitted）
   - transcript 追加 **无 tool_calls** 的 assistant，文案短、含稳定码 `INVALID_MODEL_RESPONSE`；**不得**把 raw body / 凭据写入 messages
   - `next_step` +1，下一轮新 `request_id`（受 `max_steps`）
3. 其它 `ProviderError` 与意外 `Exception` 仍 `session.failed` + 抛出（`test_unexpected_provider_error_marks_session_failed` 保持）。持续抛 `InvalidModelResponseError` 的 Provider 必须被 `max_steps` 停住，不得死循环。
4. Chat：loop 不再因 A/B 进入 `_safe_fail_run`。`max_steps` 用尽仍 `MaxStepsExceededError`。

禁止：把全部 `ProviderError` 做成可恢复；无限重试；把 raw 响应当 context 主体；自动修复 JSON 后执行 patch；改选择器 / Stop / Durable interrupt（Task 46–48）；改 `validate_patch` schema 或 prompt 优先 `diff`（预防层，本 Task 不做）。

### Files

允许：

- `src/agent_foundations/domain/tool.py`（仅 `ToolCall.argument_parse_error`）
- `src/agent_foundations/providers/openai_compatible.py`
- `src/agent_foundations/providers/resilient.py`
- `src/agent_foundations/runtime/loop.py`（及 loop 直接依赖的最小 emit/sanitize）
- `tests/unit/providers/test_openai_compatible.py`
- `tests/unit/providers/test_resilient.py`
- `tests/integration/test_agent_loop.py`
- `docs/task-evidence/phase-2d-task-29.md`
- 本计划勾选

若 Chat runner 单测因 loop 不再抛 `InvalidModelResponseError` 而红，允许最小改 `tests/unit/chat/test_runner.py` 断言，不改 Chat UI/API。

禁止：Policy、gate_id、Chat UI、Durable interrupt、选择器 schema、Stop、Docker、付费 API、`json_repair` 依赖、`validate_patch`/`apply_patch` 参数形状。

必须改写的既有断言（目标行为，不是削弱）：

- `test_malformed_response_preserves_raw_response`：`empty-choices` 仍 `InvalidModelResponseError` + 保留 raw；`invalid-json-arguments` 与 `non-object-arguments` 改为 **返回** `ModelResponse`，对应 call 带 `argument_parse_error`，不抛
- `test_non_retryable_errors_fail_after_single_attempt` 不再把 `InvalidModelResponseError` 放在 non-retryable 列表；另测它会重试且耗尽后仍 raise 给 loop
- `test_invalid_provider_raw_response_does_not_mask_original_error`：首步不得 `session.failed`；bytes raw 仍 omitted；后续合法 final answer 能完成。另：永远抛该错误时由 `max_steps` 终止

### 验证合同

```text
Target tests：
  pytest tests/unit/providers/test_openai_compatible.py tests/unit/providers/test_resilient.py tests/integration/test_agent_loop.py -q
Affected regression tests：
  pytest tests/integration/test_agent_loop.py tests/unit/providers/test_openai_compatible.py tests/unit/chat/test_runner.py -q
Full suite：not-required
Full suite reason：只改 tool-call JSON 解析分级与 loop 对两类无效响应的收口；不扩权限。
Additional gates：受影响 ruff/mypy；git diff --check；none docker
```

TDD required。生产代码前 Red 至少覆盖：

1. 适配器：非法 `arguments` JSON 当前抛 `InvalidModelResponseError`；新测试期望返回 parse-error `ToolCall`（此时应失败）。
2. Loop：带 `argument_parse_error` 的 `validate_patch` call 之后仍能 final answer；当前会把 `{}` 送进 schema 或整轮失败。
3. Loop：`InvalidModelResponseError` 一次后成功作答；当前 `session.failed`。

### Done when

- [x] A 路：非法 arguments 不杀 session；TOOL `error_code=INVALID_TOOL_JSON`；content 含位置与 ≤80 字符窗口；未执行该工具
- [x] B 路：空包不杀 session；有 `model.response.invalid`；`InvalidModelResponseError` 可按现有上限重试
- [x] 其它 ProviderError / 意外异常仍 `session.failed`
- [x] 未引入 json_repair、未改选择器、未勾选 Step 10/11
- [x] evidence 完整；targeted 验证（不得写成 full suite passed）

**User acceptance:** 2026-09-08 用户确认 `确认「Task 45 / phase-2d-task-29 用户验收通过」`；记录于本计划与 `docs/task-evidence/phase-2d-task-29.md` §9。范围仅限畸形 tool `arguments` JSON 降成可恢复 `INVALID_TOOL_JSON` 工具失败（指出位置与 ≤80 字符窗口、禁止执行该 call），以及空包/缺 `id`|`name` 的 `InvalidModelResponseError` 按现有上限重试后 loop 不 `session.failed`。未引入 `json_repair`、未把 `INVALID_TOOL_JSON` 加入 `PARSE_ERROR_CODES`、未改选择器 / Stop / Durable interrupt、未改 `validate_patch` 参数形状。独立复验为 targeted：Target 62 passed；Affected 63 passed；四文件并集 74 passed；ruff、mypy、`git diff --check` exit 0。TDD 过程证据为 complete；本次确认不独立见证历史 Red→Green。reviewer P3（无适配器→loop 一条龙与 Durable 崩溃恢复专测；混合合法/非法 arguments 无单测但 probe 通过；窗口测试用 8 字符命中；Red 前已加 `argument_parse_error` 字段）不因本次确认要求立即返工。本确认不是计划正文 Task 25 完成，不是用户 Phase 2 完成；Step 10/11 保持未勾选。Task 46–48 仍须单独授权。未授权 commit、push、付费 3×3 或 Phase 3。

---

## Task 46 / `phase-2d-task-30`：read_command_output 选择器仍安全地可被模型写对

### Goal

模型仍不能用 path/offset/glob/regex/SQL 做选择器，但 **三种合法 shape 必须出现在 tool schema / description / `SELECTOR_INVALID` 文案里**；对仍安全的残缺 shape 做最小补全，避免 Python/Node 轮里反复 `SELECTOR_INVALID`。

### 锁定

合法 shape 不变：

- `{diagnostic_id}`
- `{stream, tail_lines}`
- `{stream, start_line, line_count}`

允许的最小放宽（仅这些）：

1. 去掉 **非禁止** 的多余键后再解析（禁止键集合保持：path、offset、glob、regex、SQL）。
2. `{stream, start_line}` 缺 `line_count` 时默认 `40`（不得超过现有 `MAX_LINES_PER_READ`）。
3. `SELECTOR_INVALID` 的 `ToolResult.content` 必须列出上述三种 shape（短句即可）。
4. `ReadCommandOutputTool.input_schema` 用 `oneOf`（或等价 JSON Schema）描述三种 shape，不再是光秃 `{"type":"object"}`。description 同步。

禁止：默认返回整份 artifact；放宽到任意键；把失败改成 session 级崩溃；改 search_command_output 的 query 安全边界（除非同一 parse 函数强制要动，保持 query 仍无 path/SQL）。

### Files

允许：`src/agent_foundations/command_output/access.py`、`src/agent_foundations/tools/command/read_output.py`、对应 unit 测试、`docs/task-evidence/phase-2d-task-30.md`。

禁止：Artifact raw ticket、pages HTTP、Policy、loop、Chat UI。

### 验证合同

```text
Target tests：新增或扩展的 selector 单测 + 现有 command_output access 测试
Affected：pytest tests/unit 下 command_output 与 tools/command 中 read_output/access 相关文件 -q
Full suite：not-required
Additional gates：ruff/mypy；git diff --check
```

TDD required。Red：schema 无 oneOf；`{stream, start_line}` 现为 `SELECTOR_INVALID`。

**User acceptance:** 2026-09-08 用户确认 `确认「Task 46 / phase-2d-task-30 用户验收通过」`；记录于本计划与 `docs/task-evidence/phase-2d-task-30.md` §9。范围仅限 `read_command_output` 选择器仍只允许三种安全 shape：禁止键仍先拒绝；剥非禁止多余键；`{stream, start_line}` 缺 `line_count` 时默认 40（不超过 `MAX_LINES_PER_READ`）；shape 失败文案列出三 shape；`input_schema` 改为 `oneOf` 且 description 同步并保留 `failing run_command` / `CommandFeedback.artifact_id`。未默认整份 artifact、未放宽禁止键、未改 search query、未改 Stop / Durable interrupt / pages HTTP。独立复验为 targeted：Target 12 passed；Affected 68 passed；coding-prompt description 2 passed；ruff、mypy、`git diff --check` exit 0。TDD 过程证据为 complete；本次确认不独立见证历史 Red→Green。reviewer P3（字段非法 `line_count=201` 文案不列三 shape；无 `ToolResult.content` 层断言；`{stream, start_line}` 加无害多余键默认 40 仅 probe）不因本次确认要求立即返工。本确认不是计划正文 Task 25 完成，不是用户 Phase 2 完成；Step 10/11 保持未勾选。Task 47–48 仍须单独授权。未授权 commit、push、付费 3×3 或 Phase 3。

---

## Task 47 / `phase-2d-task-31`：Chat 中断同时收口 Durable

### Goal

Chat run 标 `interrupted` 时，对应 `durable_runs` 不得再留 `running`。杀进程重启（lifespan `interrupt_unfinished`）与 in-process interrupt 走同一收口。

### 锁定

1. `interrupt_unfinished` 在更新 Chat `runs` 之后，对每个被打断的 `session_id` 把 Durable 从 **任意允许转到 CANCELLED 的非终态**（至少 `RUNNING`、`WAITING_APPROVAL`、`PAUSED`、`CREATED`）转到 `CANCELLED`。已是 `COMPLETED`/`FAILED`/`CANCELLED` 则跳过。
2. `ConversationRunner._safe_interrupt_run` 不得只硬编码 `RUNNING→CANCELLED`；按当前 Durable 状态走允许转换。`DurableRunNotFoundError` 仍忽略。
3. 已提交的 Patch 不因这次收口而重放（现有 ledger；加回归：interrupt 后 resume 不再二次 apply）。
4. 不改 Policy，不新增 Stop UI（那是 Task 48）。

### Files

允许：`src/agent_foundations/chat/repository.py`、`src/agent_foundations/chat/runner.py`、`src/agent_foundations/viewer/app.py`（仅当 lifespan 需要把 durable repo 传入 interrupt）、相关 unit/integration、`docs/task-evidence/phase-2d-task-31.md`。

禁止：Chat 前端、npm build、Provider、选择器。

### 验证合同

```text
Target tests：interrupt_unfinished + _safe_interrupt_run 的 Chat/Durable 成对状态测试
Affected：tests/unit/chat/test_repository.py tests/unit/chat/test_runner.py tests/unit/chat/test_lifecycle.py
Full suite：not-required
Additional gates：ruff/mypy；git diff --check
```

TDD required。Red：只 interrupt Chat run 时 Durable 仍 `running`。

**User acceptance:** 2026-09-08 用户确认 `确认「Task 47 / phase-2d-task-31 用户验收通过」`；记录于本计划与 `docs/task-evidence/phase-2d-task-31.md` §9。范围仅限 Chat `interrupted` 时把匹配 Durable 从可取消非终态（至少 `CREATED`/`RUNNING`/`WAITING_APPROVAL`/`PAUSED`）转到 `CANCELLED`：`interrupt_unfinished` 可选传入 Durable repo，lifespan 传入 `services.durable_repository`，`_safe_interrupt_run` 复用 `cancel_run`；`NotFound` 与已终态 `Conflict` 跳过；COMMITTED `apply_patch` 不因这次收口二次 apply。未改 Policy、未新增 Stop UI/API、未改 Durable 状态机转换表。独立复验为 targeted：Target/Affected 102 passed；ruff、mypy `--strict`、`git diff --check` exit 0。TDD 过程证据为 complete；本次确认不独立见证历史 Red→Green。ledger 第一次 Red 因 `DirectToolCallExecutor` 无效，改测试后、改生产代码前留下 Durable 仍 `running` 的有效 Red。reviewer P3（Chat 与 Durable 不是同一 SQLite 事务；`_safe_fail_run` 仍 `RUNNING→FAILED`；ledger 回归不是完整 Chat resume）不因本次确认要求立即返工。本确认不是计划正文 Task 25 完成，不是用户 Phase 2 完成；Step 10/11 保持未勾选。Task 48 仍须单独授权。未授权 commit、push、付费 3×3 或 Phase 3。

---

## Task 48 / `phase-2d-task-32`：真 Stop

### Goal

用户不必杀 Chat 进程。运行中的 run 可以点 Stop：Chat `interrupted` + Durable `cancelled`（复用 Task 47 收口）。

### 锁定

1. HTTP：对 active run（至少 `queued`/`running`；`waiting_approval` 须同时 invalidate pending 审批）提供显式 interrupt，绑定 `127.0.0.1` 现有 Chat API，不新开端口。
2. `web/chat`：active run 时可见、可点的 **Stop** 按钮（可见英文 `Stop`）；调用该 API。
3. 必须 `npm run build:chat` 打进 `src/agent_foundations/viewer/static/chat`（`emptyOutDir: true`）。禁止手改 hashed assets。探针跟 `index.html` 的 script src，断言产物含 `Stop`。
4. 依赖 Task 47 已验收；不要在本 Task 重做 Durable 转换表。

禁止：付费 3×3；改 Policy/gate_id；Playwright 对真实模型。

### Files

允许：`src/agent_foundations/chat/api.py`、`web/chat/**`、Chat 静态包（仅经 `npm run build:chat`）、Chat/前端测试、`docs/task-evidence/phase-2d-task-32.md`。

### 验证合同

```text
Target tests：Chat API interrupt 单测 + web/chat vitest（Stop）
Affected：npm run test:chat；npm run typecheck:chat
Full suite：not-required
Additional gates：npm run build:chat；静态包探针；ruff/mypy 受影响 Python；git diff --check
```

TDD required。前端 Red：无 Stop。API Red：无 interrupt 路由。

**User acceptance:** 2026-09-09 用户确认 `确认「Task 48 / phase-2d-task-32 用户验收通过」`；记录于本计划与 `docs/task-evidence/phase-2d-task-32.md` §9。范围仅限现有 Chat API 上的 `POST .../runs/{session}/interrupt`（404/422/409 沿用现有细节）、按 conversation 取消 supervisor task、公开 `interrupt_run` 复用 Task 47 收口、active run 可见可点英文 Stop（`waiting_approval` 时 Send 仍禁用）、Chat 静态包仅经 `npm run build:chat`。未改 Durable 转换表、未改 Policy/`gate_id`、未对真实模型做 Playwright、未重开付费 3×3。独立复验为 targeted：Python 64 passed；`npm run test:chat` 87 passed；`typecheck:chat` exit 0；静态探针 2 passed（入口 `index-YqNJU08h.js`）；ruff、mypy `--strict`、`git diff --check` exit 0。reviewer 未重建 Chat 静态包。TDD 过程证据为 complete；本次确认不独立见证历史 Red→Green。静态探针 Red 用 `'"Stop"'`，压缩后为反引号，Green 前探针改为接受引号或反引号并断言 `chat-composer__stop`。reviewer P3（Chat 与 Durable 不是同一 SQLite 事务；Stop 只 invalidate conversation-state 上该 session 的 pending 审批；无新 SSE；无真浏览器点 Stop）不因本次确认要求立即返工。本确认不是计划正文 Task 25 完成，不是用户 Phase 2 完成；Step 10/11 保持未勾选。本计划无 Task 49。未授权 commit、push、付费 3×3 或 Phase 3。

---

完成后 **停止**。是否重开付费 3×3 由用户另授权，仍走 Task 25 Step 10；至少 Task 45 验收前不要重开 9 轮挑绿。
