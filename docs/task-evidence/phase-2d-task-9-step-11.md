# Task Evidence: phase-2d-task-9-step-11

## 1. Identity

- Task ID: `phase-2d-task-9` (Step 11 reviewer re-verification only; not a new Task ID)
- Authoritative plan or task spec: `docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md` Task 25 Step 11
- Evidence status: two reviewer sessions recorded (A: Step 6 fail; B: re-run after Task 49). Plan-body Step 11 user-accepted 2026-09-09. User Phase 2 complete recorded 2026-09-09 in §13.
- TDD required: reviewer does not redo Red/Green
- Started at: 2026-09-09 (Asia/Shanghai)
- Role: reviewer (project-role-protocol). No production or test edits to “make it pass”.

## 2. Pre-change Snapshot

- Branch or revision: `codex/phase-2-next` @ `14ece4e` (same as `main` commit; Phase 2 lives in the dirty tree)
- `git status --short`: dirty tree preserved (~389 entries). Not reset/restored/cleaned.
- Existing user changes that must be preserved: entire dirty tree (Phase 2A–2D, follow-ons, Tasks 44–48, Chat hashed assets, evidence)
- Intended modification scope: this evidence file; optional pointer at the end of `docs/task-evidence/phase-2d-task-9.md`. **No** plan checkbox ticks. **No** production/test code.
- Expected rollback: delete this file and the pointer; leave the dirty tree otherwise unchanged.
- Interpreter: `$env:PYTHONIOENCODING='utf-8'; conda run -n agent-foundations python …` as specified. Docker Desktop was not listening at first (`npipe` miss); reviewer started the installed Desktop app so inspect and `pytest -m docker` could run. That is an environment action, not a code change.

## 3. Red / Green

- Recorded before production-code changes: not-applicable (reviewer session; no implementation)
- TDD process for this Step: not-applicable

## 4. Independent current verification (this session)

Do not copy historical counts. Fresh commands below.

### 4a. Step 6 full baseline

| Check | Command | Exit | Result |
|---|---|---:|---|
| pytest -q | `conda run -n agent-foundations python -m pytest -q --tb=line` | 1 | **13 failed**, 1528 passed, 14 skipped, 54 warnings in 194.57s |
| ruff | `conda run -n agent-foundations python -m ruff check .` | 1 | F821 `database_path` undefined at `tests/e2e/test_chat_ui.py:992` |
| mypy | `conda run -n agent-foundations python -m mypy src tests` | 1 | 4 errors / 312 files: `test_retention.py` attr-defined ×3; `test_chat_ui.py:992` name-defined |
| pip check | `conda run -n agent-foundations python -m pip check` | 0 | No broken requirements. Warning: invalid dist `~gent-engineering-foundations` |
| test:viewer | `npm run test:viewer` | 0 | 12 passed |
| typecheck:viewer | `npm run typecheck:viewer` | 0 | pass |
| test:chat | `npm run test:chat` | 0 | 87 passed / 10 files |
| typecheck:chat | `npm run typecheck:chat` | 0 | pass |
| build:chat | `npm run build:chat` | 0 | entry remains `index-YqNJU08h.js` / `index-sWD87OOM.css`; Stop class present in bundle |
| git diff --check | `git diff --check` | 0 | LF→CRLF working-copy warnings only |
| git status --short | `git status --short` | 0 | ~389 dirty; preserved |

**Must not write `full suite passed`.** pytest / ruff / mypy failed.

Pytest failures (verbatim summary):

```text
13 failed, 1528 passed, 14 skipped, 54 warnings in 194.57s
FAILED tests/e2e/test_chat_ui.py::test_task16_browser_patch_profile_reload_approve_deny_and_no_duplicate_write
    NameError: name 'database_path' is not defined  (line 992)
FAILED tests/e2e/test_chat_ui.py::test_command_feedback_sanitized_pages_restore_and_narrow_viewport
    AssertionError: Locator expected to be visible  (line 1115, `[REDACTED]`)
FAILED tests/unit/chat/test_tool_execution.py::test_external_denial_returns_stable_result_without_execution
FAILED tests/unit/chat/test_tool_execution.py::test_approved_external_read_file_uses_fresh_scoped_tool
FAILED tests/unit/chat/test_tool_execution.py::test_approved_external_list_directory_filters_sensitive_children
FAILED tests/unit/chat/test_tool_execution.py::test_approved_external_list_directory_rejects_file_target
FAILED tests/unit/chat/test_tool_execution.py::test_approved_external_search_preserves_query_and_glob[file]
FAILED tests/unit/chat/test_tool_execution.py::test_approved_external_search_preserves_query_and_glob[directory]
FAILED tests/unit/chat/test_tool_execution.py::test_repeated_external_access_creates_distinct_approvals
FAILED tests/unit/chat/test_tool_execution.py::test_approved_external_access_rejects_changed_symlink_target
FAILED tests/unit/chat/test_tool_execution.py::test_approved_external_access_rejects_disappeared_target
    TypeError: RecordingCoordinator.request() takes 2 positional arguments but 4 were given
    at src/agent_foundations/chat/tool_execution.py:314
FAILED tests/unit/runtime/test_coding_budget.py::test_loop_does_not_execute_over_budget_artifact_read
    assert ['search_command_output'] == ['read_command_output', 'search_command_output']
FAILED tests/unit/runtime/test_recovery.py::test_loop_command_feedback_blocks_identical_argv
    assert ['run_command'] == ['run_command', 'read_command_output', 'run_command']
```

Classification (inspected, not fixed):

- `database_path` / ruff F821 / mypy name-defined: test uses an undefined name in `test_task16_browser_patch_*`. Production Chat path not implicated by this NameError.
- Nine `test_tool_execution` failures: test stub `RecordingCoordinator.request(self, request)` vs production `ApprovalCoordinator.request(request, policy_request=None, outcome=None)` and `tool_execution.py` passing three arguments. Production coordinator signature accepts the extra args. This is **stub/API drift**, not evidence that live Chat `ApprovalCoordinator` TypeErrors.
- `coding_budget` / `recovery`: tests still pass `selector: {"stream": "stdout"}`. Task 46 schema requires `{diagnostic_id}` xor `{stream, tail_lines}` xor `{stream, start_line}` (optional `line_count`). Invalid selector never reaches the scripted executor. Likely **test drift after Task 46**, not a new MCP/write/host-access hole. Recovery still appears to withhold the second `run_command` execute.
- e2e `[REDACTED]` after reload: failed `to_be_visible` at line 1115. Not re-diagnosed beyond the full-suite traceback. Treat as **P2 UI restore** until an executor session isolates it. Not classified as a confirmed secret leak (the assertion is that the redaction marker is visible).

### 4b. Docker additional gates

| Check | Result |
|---|---|
| docker info (before Desktop) | fail: npipe `dockerDesktopLinuxEngine` missing |
| docker info (after starting Desktop) | pass 29.4.3 |
| python inspect vs pin | pass `sha256:730aea0a2ba8ef2998bb0cc43b1f94641a9099f8a0d55b22a0605f384ad26e41` User `65532:65532` |
| node inspect vs pin | pass `sha256:12f2470f314aae00f8757a313d78da471472984f7d039bdfdf1c57a553cfc0e7` User `65532:65532` |
| `pytest -m docker -q` | **21 passed**, 1534 deselected, 14 warnings in 33.18s, exit 0 |

No paid/real model calls.

### 4c. Diff vs HEAD / main

- `HEAD` = `main` = `14ece4e feat: add controllable coding agent foundations`
- Tracked `git diff --stat HEAD`: 165 files, +7578 / −699 (plus large untracked Phase 2 src/tests/docs/static)
- Untracked production modules include command/git/patch apply, compaction, sandbox manifest, Stop/interrupt, overlay Dockerfiles. Expected for uncommitted Phase 2.

## 5. Implementation spot-check (current code)

- `PermissionProfileName` has PROJECT_READ_ONLY / ASK_ALWAYS / RISK_BASED / PROJECT_FULL_ACCESS / CUSTOM. **No** `HOST_FULL_ACCESS` in `src/` or `web/`.
- Registry surface: filesystem read tools, planning, `validate_patch`, git **status/diff/log** only, `apply_patch`, `run_command`, command-output read/search. `CommandClassifier` hard-denies `git` / shells / network / install / metacharacters as `run_command` argv.
- Stop: `POST /api/chat/conversations/{id}/runs/{session}/interrupt` → supervisor `cancel` + `runner.interrupt_run` → `_safe_interrupt_run` + `cancel_durable_run_if_active`. Lifespan `interrupt_unfinished(..., durable_repository=...)`. UI `interruptRun` + `aria-label="Stop"`; served bundle still `index-YqNJU08h.js` with `chat-composer__stop`.
- Malformed tool JSON: `argument_parse_error` → loop `INVALID_TOOL_JSON` without `validate_call`/execute. `InvalidModelResponseError` checkpoints `model.response.invalid` and `next_step+1` without `session.failed` in that branch.

Step 10 reviewer P3 (not reworked here): Node-3 never invoked git read tools; Security-3 interrupt left apply activity `running` / ledger `executing` while host already `hello world again`; evidence `phase-2d-task-9-step-10.md` §8 still holds Round 2 fail handoff. **Not a Step 11 security blocker.**

## 6. TDD process (executor-submitted; not independently witnessed)

- Task 25 P1 (`phase-2d-task-9.md` §3 / §5e): complete Red recorded before `_DIFF`; reviewer does not claim to have seen that sequence.
- Step 10: not-applicable (paid manual). Round 2 §9 fail **not rewritten**. Round 3 §10/§11 user-accepted 9/9.
- Tasks 44–48 evidence mark TDD complete for those packages; this session did not re-prove their Red→Green.
- Earlier inventory in `phase-2d-task-9.md` still lists some Tasks with incomplete historical Red (e.g. Task 3, 12, 20). Step 11 does not backfill them.

## 7. Manual Step 10

- Agree: Round 3 consecutive 9/9 + user phrase `确认「Task 25 Step 10 用户验收通过」` (2026-09-09) is the paid Chat UI human gate. Did **not** re-run paid 3×3.
- Round 2 Node-3 `InvalidModelResponseError` remains fail in §9.
- P3 items above do **not** by themselves block treating Step 10 as the human gate.
- Step 10 **cannot** substitute for a green Step 6 full baseline.

## 8. Scope audit

- Production/test code changed this session: **no** (except `npm run build:chat` / `build:viewer` as required gates; Chat entry hash unchanged).
- Secrets: none recorded. Credentials not printed.
- Commit / push / Phase 3 / paid rerun / plan Step 11 tick: **none**.

## 9. Handoff (Session A, 2026-09-09 first review)

- Current implementation (Phase 2 permission bounds, Stop+Durable, INVALID_TOOL_JSON): **pass** on inspected code.
- Current automated Step 6 baseline: **fail**.
- TDD process for Phase 2 as a whole: **partial** (many Tasks complete in submitted evidence; some historical Red unavailable; this session not-applicable).
- Manual Step 10: **agree as human gate**; not Phase 2 complete.
- Recommendation to user: **do not** tick Phase 2 complete until Step 6 pytest/ruff/mypy are green in a later reviewer session.
- Next smallest executor Task (not started): repair the 13 failing tests / ruff F821 / 4 mypy errors without expanding Tool/permission scope. Then re-run Step 11.

Do **not** rewrite §4a counts as pass. Task 49 / `phase-2d-task-33` later repaired that baseline and was user-accepted 2026-09-09.

## 10. Session B re-run (2026-09-09, after Task 49 user acceptance)

- Role: reviewer. User instruction: `重新跑一次Step 11`. Same conversation previously reviewed Task 49; gates below are a fresh re-execution, not copied Task 49 numbers.
- Branch: `codex/phase-2-next` @ `14ece4e`. Dirty tree preserved (~392 short-status lines). No reset/restore/clean. No production/test edits. Plan-body Step 11 left `- [ ]`. Paid 3×3 not re-run.
- Interpreter: `$env:PYTHONIOENCODING='utf-8'` + `conda run -n agent-foundations`. Docker Desktop already listening (29.7.2).

### 10a. Step 6 full baseline (fresh)

| Check | Command | Exit | Result |
|---|---|---:|---|
| pytest -q | `conda run -n agent-foundations python -m pytest -q --tb=line` | 0 | **1541 passed, 14 skipped, 54 warnings** in 220.61s |
| ruff | `conda run -n agent-foundations python -m ruff check .` | 0 | All checks passed |
| mypy | `conda run -n agent-foundations python -m mypy src tests` | 0 | Success: no issues found in 312 source files |
| pip check | `conda run -n agent-foundations python -m pip check` | 0 | No broken requirements. Warning: invalid dist `~gent-engineering-foundations` (twice) |
| test:viewer | `npm run test:viewer` | 0 | 12 passed |
| typecheck:viewer | `npm run typecheck:viewer` | 0 | pass |
| test:chat | `npm run test:chat` | 0 | 87 passed / 10 files |
| typecheck:chat | `npm run typecheck:chat` | 0 | pass |
| build:chat | `npm run build:chat` | 0 | entry still `index-YqNJU08h.js` / `index-sWD87OOM.css`; `chat-composer__stop` and backtick `` `Stop` `` present |
| git diff --check | `git diff --check` | 0 | LF→CRLF working-copy warnings only |
| git status --short | `git status --short` | 0 | ~392 dirty; preserved |

A prior interrupted attempt in this conversation saw `test_cross_run_drift_and_capability_replay_are_rejected` fail once with `sqlite3.OperationalError: disk I/O error` (1 failed / 1540 passed). This Session B full pytest did **not** reproduce it. Treat as environmental flake, not a current product regression.

### 10b. Docker additional gates (fresh)

| Check | Result |
|---|---|
| docker info | pass 29.7.2 |
| python inspect vs pin | pass `sha256:730aea0a2ba8ef2998bb0cc43b1f94641a9099f8a0d55b22a0605f384ad26e41` User `65532:65532` |
| node inspect vs pin | pass `sha256:12f2470f314aae00f8757a313d78da471472984f7d039bdfdf1c57a553cfc0e7` User `65532:65532` |
| `pytest -m docker -q` | **21 passed**, 1534 deselected, 14 warnings in 45.03s, exit 0 |

No image pull/build/prune. No paid/real model calls.

### 10c. Offline Eval (fresh)

```powershell
conda run -n agent-foundations agent-foundations evaluate --task-set tests/fixtures/evals/phase-1-tasks-v1.json --responses tests/fixtures/evals/phase-1-responses-v1.json --output .agent-foundations/evals/final-phase-1.json --runtime-revision working-tree
conda run -n agent-foundations agent-foundations evaluate --task-set tests/fixtures/evals/phase-2-tasks-v1.json --responses tests/fixtures/evals/phase-2-responses-v1.json --output .agent-foundations/evals/final-phase-2.json --runtime-revision working-tree
```

Both exit 0.

- Phase 1: `passed_tasks=8` / `failed_tasks=0` / `success_rate=1.0` / `total_steps=25` / `total_tool_calls=17`. Tools: list_directory, read_file, search_text, set_plan, update_plan_step, replan.
- Phase 2: `passed_tasks=4` / `failed_tasks=0` / `success_rate=1.0` / `total_steps=11` / `total_tool_calls=7`. Includes `git_commit`/`git_push` **not called** assertions and `apply_patch` `CONTROLLED_EXECUTION_REQUIRED` in Offline Eval. Matches checked-in `docs/eval-baselines/phase-2-v1.json` summary shape (`success_rate=1.0`, 4 tasks).

Compaction / artifact / FakeModel correction coverage is inside the 1541 pytest (unit+integration); no separate failing compaction recall gate in this run.

### 10d. Implementation spot-check (current code)

- `PermissionProfileName`: PROJECT_READ_ONLY / ASK_ALWAYS / RISK_BASED / PROJECT_FULL_ACCESS / CUSTOM. **No** `HOST_FULL_ACCESS` in `src/`.
- `CommandClassifier` still hard-denies git argv, shells, network, install, metacharacters, inline `python -c`.
- Stop: `POST .../runs/{session_id}/interrupt` → supervisor `cancel` + `runner.interrupt_run`. Served bundle `index-YqNJU08h.js` contains `chat-composer__stop` and `` `Stop` ``.
- Malformed tool JSON: loop still synthesizes `INVALID_TOOL_JSON` without executing that call.

Step 10 reviewer P3 retained (not reworked): Node-3 never invoked git read tools; Security-3 interrupt left apply activity `running` / ledger `executing` while host already `hello world again`. **Not a Step 11 security blocker** per the Step 10 acceptance record.

### 10e. TDD process (executor-submitted; not independently witnessed)

- Unchanged from §6. This re-run is not-applicable for new Red/Green. Task 49 TDD was marked complete in its own evidence; this session does not independently witness that sequence.
- Phase 2 as a whole remains **partial** for historical Red on some earlier Tasks.

### 10f. Manual Step 10

- Agree: Round 3 consecutive 9/9 + user phrase `确认「Task 25 Step 10 用户验收通过」` is the paid Chat UI human gate. Did **not** re-run paid 3×3.
- Round 2 Node-3 `InvalidModelResponseError` remains fail in `phase-2d-task-9-step-10.md` §9.

### 10g. Scope audit

- Production/test code changed this session: **no** (except required `npm run build:chat` / `build:viewer`; Chat entry hash unchanged).
- Eval JSON written under `.agent-foundations/evals/` (local; not committed).
- Secrets: none recorded. Credentials not printed.
- Commit / push / Phase 3 / paid rerun / plan Step 11 tick / Phase 2 complete tick: **none**.

## 11. Session B conclusion

```yaml
task_id: phase-2d-task-9-step-11
current_implementation: pass
tdd_process_evidence: partial
original_red_evidence: not-applicable
manual_step_10: pass
automated_step_6: pass
additional_gates: pass
blocking: false
```

- Current implementation (permission bounds, Stop+Durable, INVALID_TOOL_JSON, no HOST_FULL_ACCESS): **pass**
- Automated Step 6 baseline: **pass** (1541 passed / 14 skipped)
- Docker + Offline Eval: **pass**
- TDD process for Phase 2 as a whole: **partial**
- Manual Step 10: **agree as human gate**
- Blocking: **false**

This report does **not** tick plan-body Step 11 and does **not** mark user Phase 2 complete. Those require an explicit user confirmation after this review.

Retained P3 (non-blocking): Chat interrupt and Durable cancel are still not one SQLite transaction; Step 10 Node-3 skipped git read tools; Security-3 apply activity may remain `running` after Stop; `store.py` `__all__` only re-exports two constants; leftover `{stream}`-only fixtures in non-target tests; `pip check` invalid-distribution warning; one unreproduced sqlite disk I/O flake in an interrupted earlier attempt.

## 12. User Acceptance (Step 11 only)

- Confirmed at: 2026-09-09 +08:00.
- Exact user confirmation: `确认「Task 25 Step 11 用户验收通过」`.
- Result: Task 25 Step 11 (independent reviewer re-verification after Task 49) is user-accepted. Session B current implementation **pass**; full Step 6 **pass** (pytest 1541 passed / 14 skipped / 54 warnings; ruff / mypy 312 files / pip check / viewer 12 / chat 87 / `build:chat` entry `index-YqNJU08h.js` / `git diff --check` exit 0); `pytest -m docker` 21 passed; Offline Eval Phase 1 8/8 and Phase 2 4/4 `success_rate=1.0`; manual Step 10 Round 3 9/9 stands (paid 3×3 not re-run). Session A 13 failed / ruff F821 / mypy 4 errors is **not rewritten as pass**. Plan-body Step 11 is checked.
- Full suite note: this confirmation accepts the **Step 11 reviewer gate** (fresh Session B automated + Docker + Offline Eval). It does **not** accept user Phase 2 complete, does not rewrite Round 2 Node-3 fail, and does not authorize commit / push / paid 3×3 rerun / Phase 3.
- TDD note: Step 11 itself is not-applicable. Phase 2 as a whole remains **partial** for some historical Task Reds. This confirmation does not independently witness any Task's original Red→Green sequence, including Task 49.
- Boundary: this confirmation records Task 25 Step 11 only. User Phase 2 complete still requires a separate explicit confirmation. Reviewer P3 findings are retained and do not require immediate rework. Suggested commit after explicit authorization remains `feat: complete controllable coding agent phase`.

## 13. User Acceptance (Phase 2 complete)

- Confirmed at: 2026-09-09 +08:00.
- Exact user confirmation: `确认「用户 Phase 2 完成」`.
- Result: user Phase 2 is complete. Grounded on already-accepted Step 10 Round 3 consecutive 9/9 and Step 11 Session B independent re-verification (current implementation pass; full Step 6 1541 passed / 14 skipped; Docker 21 passed; Offline Eval Phase 1 8/8 and Phase 2 4/4). Round 2 Node-3 `InvalidModelResponseError` is **not rewritten as pass**. Session A 13 failed is **not rewritten as pass**.
- Full suite note: this confirmation closes the **user Phase 2 gate**. It does not independently re-run gates. It does not authorize commit, push, paid 3×3 rerun, or Phase 3. Plan-body Step 12 remains in force.
- TDD note: unchanged. Phase 2 as a whole remains **partial** for some historical Task Reds. This confirmation does not independently witness any historical Red→Green sequence.
- Boundary: P3 findings remain retained and do not require immediate rework. Suggested commit after explicit authorization remains `feat: complete controllable coding agent phase`. Entering Phase 3 still requires a separate explicit user confirmation.
