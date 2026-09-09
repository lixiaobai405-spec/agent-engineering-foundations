# Phase 2 Pre-3×3 Gap Remediation Plan

**Date:** 2026-09-08  
**Status:** Task 42–43 均已用户验收通过（targeted）。本计划无 Task 44。不关闭 Task 25 / Phase 2 用户验收 / Step 10/11；付费 3×3 须另授权。  
**Role:** planner 维护；不实现生产代码  
**Parent:** `docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md`  
**Does not replace:** Task 25、Phase 2 用户验收、Step 10/11、可靠性 follow-on（Task 30–34）、产品硬化（Task 35–41）

## 0. 结论

2026-09-08 reviewer 在付费 3×3 前检出 **两个** 必须处理的缺口。它们文件树不重叠，**拆成两个 Task**，禁止合成一个含糊大包。不要顺手修其它已记录 P3（argv 活动摘要、recovery 文案、GET 审批推导、leftover CWD、Git L1、占用 UI 等）。

| 缺口 | 用户可见 | Task ID | Evidence | 优先级 |
|---|---|---|---|---|
| Chat 静态包过期 | Task 42 | `phase-2d-task-26` | `docs/task-evidence/phase-2d-task-26.md` | P1，先做 |
| `read_file` 与 structured patch 切行不一致 | Task 43 | `phase-2d-task-27` | `docs/task-evidence/phase-2d-task-27.md` | P2，Task 42 验收后 |

Task 43 **不依赖** Task 42 的代码。顺序只按 P1→P2 与「一次一个 Task」。本计划无 Task 44。完成后 **停止**；3×3 仍走计划正文 Task 25 Step 10，须另授权。操作合同：`docs/agent-plans/2026-09-08-phase-2-task-25-step-10-manual-3x3.md`。Node 预检 harness blocker 不在本计划内，见 `docs/agent-plans/2026-09-08-phase-2-node-sandbox-modules-overlay-plan.md` Task 44 / `phase-2d-task-28`。Task 42 / `phase-2d-task-26` 已于 2026-09-08 由用户确认验收通过（targeted）；evidence 见 `docs/task-evidence/phase-2d-task-26.md` §9。Task 43 / `phase-2d-task-27` 已于 2026-09-08 由用户确认验收通过（targeted）；evidence 见 `docs/task-evidence/phase-2d-task-27.md` §9。

这不是硬化计划的 Task 42：硬化计划 Task 35–41 已验收且声明无后续项。本文件是新的 follow-on。

**全计划禁止：** 付费 3×3、真实模型、commit/push、Phase 3、MCP/Browser、项目外写入、任意 Shell、`git reset` / `git clean`、勾选 Task 25 Step 10/11、声称 Phase 2 完成。

Python（Windows）：`$env:PYTHONIOENCODING='utf-8'` 后使用 `D:\anaconda\envs\agent-foundations\python.exe`。不要用会 GBK 崩掉的裸 `conda run` 作为主路径。

---

## Task 42 / `phase-2d-task-26`：把已验收的 Chat UI 打进被服务的静态包

### Goal

`create_app()` 从 `src/agent_foundations/viewer/static/chat` 提供 Chat UI。当前 `index.html` 指向 `assets/index-k5D9Loaj.js`（约 2026-08-27）。`web/chat` 里 Task 37/38 的源码是 2026-09-04 之后。本机 Chat / 未来 3×3 仍看到旧审批标题和拼在一起的 stdout/stderr。

用正式 `npm run build:chat` 把 **已经验收** 的 `web/chat` 打进 `outDir`。不是重做 UI，不是改 Policy/API。

TDD：required。先写「读取 **当前被 index.html 引用的** JS」的探针测试并保存 Red，再 build，再 Green。禁止手改 hashed 文件去让探针变绿。

### 现状

- `vite.config.ts`：`root: web/chat`，`outDir: src/agent_foundations/viewer/static/chat`，`emptyOutDir: true`，`base: /chat-static/`。
- 工作区已有一批旧 hash 的 `D` 和新 hash 的 `??`；本次 build 只会再写这个目录。必须保留仓库其余未提交改动。
- Task 37/38 当时只跑了源码 vitest，没有把包打进 viewer。

### Stable contract

探针（Target 测试必须这样找文件，禁止写死 `index-k5D9Loaj.js`）：

```text
读 CHAT_BUILD_DIR / index.html
解析 <script type="module" ... src="/chat-static/assets/<hash>.js">
读该 JS（utf-8）
必须含：
  Controlled command approval
  sandbox_command
  No stdout
  No stderr
  tablist
仍可含：Controlled patch approval、External read approval
build 后 index.html 不得再引用 index-k5D9Loaj.js
```

允许：

- 运行 `npm run build:chat`（Vite 清空并重写 **仅** `static/chat`）
- 新增 `tests/unit/viewer/test_chat_static_bundle.py`
- 更新本计划勾选与 evidence
- build 导致的 `static/chat/index.html` + `assets/*` hash 更替（预期副作用）

禁止：

- 手改任何 `assets/*.js` / `*.css` / 伪造 hash
- 改 `web/chat/**` 源码（源码已验收）
- 改 Policy、gate_id、pages/raw、Chat Python API
- `git reset` / `restore` / `clean`（含事后把 static 还原成 HEAD `14ece4e`）
- 改 `.gate-backup/`
- Playwright / 付费 API / 下一 Task

回退：只还原 **本 Task 开始时** `static/chat` 的文件树 + 删除本 Task 新增测试/evidence；不要还原整个 dirty tree。开始前必须在 evidence 记下当时 `index.html` 的 script src。

### Files

- 允许修改：`src/agent_foundations/viewer/static/chat/**`（仅经由 `npm run build:chat`）
- 允许新增：`tests/unit/viewer/test_chat_static_bundle.py`、`docs/task-evidence/phase-2d-task-26.md`
- 允许勾选：本文件 Task 42
- 禁止修改：`web/chat/**`、`vite.config.ts`（除非发现 outDir 已漂移且先向 planner 报告）

### Tests（Red 在 build 前）

- 探针断言上述字符串；当前包应 Red（缺 command 标题 / 空态 / tablist）
- Green：同一探针通过，且 script src ≠ `index-k5D9Loaj.js`

### Verification contract

```text
Target tests：
$env:PYTHONIOENCODING='utf-8'; D:\anaconda\envs\agent-foundations\python.exe -m pytest tests/unit/viewer/test_chat_static_bundle.py -q

Affected regression tests：
$env:PYTHONIOENCODING='utf-8'; D:\anaconda\envs\agent-foundations\python.exe -m pytest tests/unit/viewer/test_chat_static_bundle.py tests/unit/viewer/test_stream.py tests/integration/test_chat_api.py::test_chat_enabled_routes_with_present_build_200 -q

Full suite：not-required
Full suite reason：只刷新已验收 UI 的 hashed 产出，不扩大 Tool/权限，不改 API。不得写成 full suite passed。

Additional gates：
npm run typecheck:chat
npm run build:chat
（build 后立刻再跑 Target；evidence 记录新 script hash 与字符串抽查的原文片段，不要整包粘贴）
git diff --check
```

`npm run test:chat` 不在本 Task（Task 37/38 已验收源码）。Playwright 不在本 Task。Vite chunk-size warning 若仍非零退出以外的 warning，记入 evidence，不视为失败。

依赖：无代码依赖。建议在 Task 43 之前执行。

**User acceptance:** 2026-09-08 用户确认 `确认「Task 42 / phase-2d-task-26 用户验收通过」`；记录于本计划与 `docs/task-evidence/phase-2d-task-26.md` §9。范围仅限用正式 `npm run build:chat` 把已验收的 `web/chat` 打进 `src/agent_foundations/viewer/static/chat`，以及跟 `index.html` script src 的探针（不得写死 hash）。未改 `web/chat` 源码、`vite.config.ts`、Policy、gate_id、pages/raw、Chat Python API。独立复验为 targeted：Target 1 passed；Affected 20 passed；`npm run typecheck:chat`、`git diff --check` exit 0。Reviewer 未重跑 `npm run build:chat`（避免再写 hashed 产出）。TDD 过程证据为 complete；本次确认不独立见证历史 Red→Green。reviewer P3（字符串探针不是真浏览器；下次 build 会换 hash，探针必须继续跟 `index.html`）不因本次确认要求立即返工。本确认不是计划正文 Task 25 完成，不是用户 Phase 2 完成；Step 10/11 保持未勾选。Task 43 仍需单独授权。未授权 commit、push、付费 3×3 或 Phase 3。

---

## Task 43 / `phase-2d-task-27`：read_file 与 structured patch 同一套 UTF-8 行文本

### Goal

让 `read_file`（含 `read_lines`）与 structured `validate_patch` / 随后 `apply_patch` 使用同一套 UTF-8 **行文本**约定，使「用 `read_file` 返回的行去填 `old_lines`」在 **CRLF / LF / 无结尾换行** 上都能通过校验并写出。不要放宽 PathPolicy，不要改 unified diff 文本格式，不要改 `gate_id`。

这是 Task 30 reviewer **P2**（当时明确推迟），不是新的 Tool 调用协议。

TDD：required。必须先有因 CRLF 行尾不一致而失败的 Red，再最小实现变绿。

### 现状（不要只改一处）

- `ReadFileTool`：`raw.decode("utf-8").splitlines()` → 行内 **没有** `\r`。
- `structured._line_texts`：`split("\n")`，CRLF 文件每行留下 `\r`。
- `StructuredChange` **禁止** line texts 含 `\n` 或 `\r` → 模型按 `read_file` 填的 `old_lines` 与 disk 侧必然对不上 → `PATCH_VALIDATION_ERROR` / `old_lines mismatch`。
- 即便只把 `_line_texts` 改成 `splitlines()`，编译出的 unified diff 仍是 LF 行；`validator._file_lines_for_hunks` 与 `applier._lines` 仍按 `"\n"` split，会对 CRLF 磁盘行留下 `\r`，在 `parse_and_validate_patch` / `prepare_patch` 上变成 `hunk context mismatch` / `hunk baseline drifted`。本 Task **必须**让这三处比较用同一套无 `\r` 行文本。
- `applier._apply_hunks` 现在用 `"\n"` 拼回文件。改切行后，写回时 **必须保留原文件换行约定**（磁盘是 CRLF 则仍写 `\r\n`，是 LF 则仍写 `\n`），避免 Windows 3×3 把整个文件变成 LF。这不是改 diff 格式；diff 仍是 LF unified diff。

### Stable contract

```text
行文本：decode UTF-8 后，每行不含 \n 也不含 \r（与 StructuredChange 校验一致）。
空文件 → 零行。
CRLF、LF、无结尾换行：read_file.read_lines(path) == structured 用于匹配的行元组。
用这些行作 old_lines/new_lines 的 validate_patch(changes=...) 必须 success；
随后 apply_patch 必须写出 new_lines 对应内容，且：
  原文件为 CRLF → 写回仍以 \r\n 分隔（若文件以换行结束则仍以换行结束）
  原文件为 LF → 仍为 \n
禁止行内再出现 \r。
混合换行（同一文件既有 \n 又有 \r\n）不在范围：不要发明策略。
旧 Mac 单独 \r 不在范围。
```

允许抽一个 **单一** helper（例如放在 filesystem 侧或 `tools` 下小模块），供 `read_file` / `structured._line_texts` / `validator._file_lines_for_hunks` / `applier._lines` 使用。禁止再抄第二套 split。

禁止：放宽 PathPolicy；改 `gate_id` / Policy / Approval；改 unified diff header 语法；改 `validate_patch` 的 `diff` vs `changes` 互斥；修其它 P3；改 Chat UI / 静态包（那是 Task 42）。

回退：只还原本 Task 改的 Python/测试/evidence；保留 dirty tree 其余部分。

### Files

- 允许：`src/agent_foundations/tools/filesystem/read_file.py`
- 允许：`src/agent_foundations/tools/patch/structured.py`
- 允许：`src/agent_foundations/tools/patch/validator.py`（`_file_lines_for_hunks` 对齐）
- 允许：`src/agent_foundations/tools/patch/applier.py`（切行对齐 + 按原文件换行写回）
- 允许新增：共享 helper 小模块（若避免 patch↔filesystem 循环导入）
- 允许测试：`tests/tools/patch/test_structured_validate_patch.py` 和/或 `tests/unit/tools/filesystem/test_read_file.py`、`tests/unit/tools/patch/` 下最小新测试
- 允许：`docs/task-evidence/phase-2d-task-27.md`、本计划勾选
- 禁止：`parser.py` 的 diff 文档切行（解析的是 unified diff 字符串，不是仓库文件）；`web/chat/**`；`static/chat/**`

### Tests（Red 在改生产代码前）

CRLF 文件 `b"alpha\r\nbeta\r\n"`：

- `read_lines` == `("alpha", "beta")`，任一行都没有 `\r`
- 同一 raw 上 structured 匹配行与 `read_lines` 相等
- `old_lines` 取自 `read_lines`、改第二行为 `gamma` 的 `validate_patch(changes=...)` 在实现前必须因 mismatch 失败（`PATCH_VALIDATION_ERROR` 或随后 hunk mismatch，以当前真实失败码为准，记入 evidence）
- Green：validate success，apply 后字节为 `b"alpha\r\ngamma\r\n"`（保留 CRLF）

另覆盖：LF 文件既有行为保持；无结尾换行的 CRLF/LF 各至少一例（apply 后仍无结尾换行）。

既有 `tests/tools/patch/test_structured_validate_patch.py` LF README 用例保持绿。

### Verification contract

```text
Target tests：
$env:PYTHONIOENCODING='utf-8'; D:\anaconda\envs\agent-foundations\python.exe -m pytest tests/tools/patch/test_structured_validate_patch.py tests/tools/filesystem/test_read_file_metadata.py tests/unit/tools/filesystem/test_read_file.py tests/unit/tools/patch/test_applier.py tests/unit/tools/patch/test_validate_patch.py -q

Affected regression tests：
$env:PYTHONIOENCODING='utf-8'; D:\anaconda\envs\agent-foundations\python.exe -m pytest tests/tools/patch tests/tools/filesystem tests/unit/tools/patch tests/unit/tools/filesystem tests/integration/test_controlled_patch_flow.py tests/integration/test_patch_crash_recovery.py -q

Full suite：not-required
Full suite reason：对齐已有 Tool 的行文本切分，不扩大权限、不改 schema 互斥。不得写成 full suite passed。

Additional gates：
$env:PYTHONIOENCODING='utf-8'; D:\anaconda\envs\agent-foundations\python.exe -m ruff check src/agent_foundations/tools/filesystem/read_file.py src/agent_foundations/tools/patch/structured.py src/agent_foundations/tools/patch/validator.py src/agent_foundations/tools/patch/applier.py tests/tools/patch/test_structured_validate_patch.py tests/unit/tools/filesystem/test_read_file.py
$env:PYTHONIOENCODING='utf-8'; D:\anaconda\envs\agent-foundations\python.exe -m mypy src/agent_foundations/tools/filesystem/read_file.py src/agent_foundations/tools/patch/structured.py src/agent_foundations/tools/patch/validator.py src/agent_foundations/tools/patch/applier.py
git diff --check
```

若新增 helper 模块或测试文件，把路径加入 Target / ruff / mypy，不要用它们替换上列文件。若 ruff 因新增测试路径报错，把该测试文件补进 ruff 行。

依赖：建议 Task 42 用户验收之后；无代码依赖。不要在本 Task 跑 `npm run build:chat`。

**User acceptance:** 2026-09-08 用户确认 `确认「Task 43 / phase-2d-task-27 用户验收通过」`；记录于本计划与 `docs/task-evidence/phase-2d-task-27.md` §9。范围仅限 `read_file` / structured / validator / applier 共用一套无 `\r` UTF-8 行文本，写回保留原 `\r\n` 或 `\n`，以及无结尾换行文件在编译 diff 中发出标准 `\ No newline at end of file`。未改 PathPolicy、`gate_id`、Policy、Approval、unified diff header、`diff` vs `changes` 互斥、`parser.py`、Chat UI / 静态包。独立复验为 targeted：Target 31 passed；Affected 145 passed；ruff、mypy、`git diff --check` exit 0。TDD 过程证据为 complete；本次确认不独立见证历史 Red→Green。`read_lines` 对 CRLF/空文件在 Red 时已绿；有效 Red 是 structured 留下 `\r` 与 `PATCH_VALIDATION_ERROR`。reviewer P3（`utf8_newline` 以是否出现 `\r\n` 决定整文件换行；`splitlines` 还会切 Unicode 行分隔符；structured 把原文件结尾换行状态抄到更新后文件；Docker applier 写主机已算好的字节且未重跑 `-m docker`）不因本次确认要求立即返工。本确认不是计划正文 Task 25 完成，不是用户 Phase 2 完成；Step 10/11 保持未勾选。本计划无 Task 44。未授权 commit、push、付费 3×3 或 Phase 3。

---

## 4. 非目标

- 不重做 Task 30–41
- 不勾选 Task 25 Step 10/11
- 不修硬化/可靠性计划里未列入上表的 reviewer P3
- 不把 `D:\AgentFoundationsData` 写进仓库默认值
- 不授权 3×3
