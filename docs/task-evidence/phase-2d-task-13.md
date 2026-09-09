# Task Evidence: phase-2d-task-13

## 1. Identity

- Task ID: `phase-2d-task-13`
- Authoritative plan or task spec: user prompt 2026-08-28 Appendix Task 29; `docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md` Appendix Task 29
- Evidence status: user-accepted 2026-08-28 (targeted verification); Task 25 overall **not complete**; user Phase 2 complete **not claimed**
- TDD required: yes
- Started at: 2026-08-28 (Asia/Shanghai)

## 2. Pre-change Snapshot

- Branch or revision: `codex/phase-2-next` (not `main`); HEAD `14ece4e`
- `git status --short`: dirty working tree on `codex/phase-2-next`. Pre-existing tracked and untracked Phase 2 files must be preserved.
- Existing user changes that must be preserved: entire dirty tree, including Chat static hashes, Dockerfiles, evidence, and prior Task 10–12 work. No reset/restore/clean/commit/push.
- Intended modification scope: Chat planning wiring in `runtime_factory` only; git argv/error-code mapping; CommandFeedbackCard stdout-first sanitized load; run_command approval copy/scope; ASK_ALWAYS two-command regression; SSE `CancelledError` swallow; tests and this evidence; plan appendix Task 29. No v11, no Policy matrix, no Dockerfiles, no eval baseline.
- Expected rollback: delete this Task’s new files; reverse this Task’s hunks in allowed Modify files.
- Interpreter: `$env:PYTHONIOENCODING='utf-8'; D:\anaconda\envs\agent-foundations\python.exe` (equivalent to `conda run -n agent-foundations` when gbk would crash pytest)
- Depends on: Appendix Task 26–28 (`phase-2d-task-10/11/12`) user-accepted. This Task ID is **not** plan-body Task 13.
- Docker / image: not-run / 未授权. Prove `git_diff` with FakeBackend + argv asserts.
- Real model / paid API / Task 25 Step 10: not-run / 未授权.

Observed pre-change defects (2026-08-28 manual test):

- Chat `runtime_factory` calls `build_tool_registry` without `controller`/`journal`, does not wrap `PlanningToolExecutor`, and does not pass `plan_controller=` into `AgentLoop`.
- `build_diff_argv` / `build_log_argv` place `--no-ext-diff` and `--no-textconv` before the `diff`/`log` subcommand.
- `GitReadService._run` maps timeout/cancel and any non-{0,1} exit to `NOT_A_REPOSITORY`.
- `CommandFeedbackCard.loadPage` hardcodes `stream: "stderr"`.
- `_build_requested_event` hardcodes `scope: "external_exact_path"`; `_pending_approval_state` uses `project_internal` only for `APPLY`.
- Chat/Trace SSE `generate()` has no top-level `CancelledError` swallow.

## 3. Red

- Recorded before production-code changes: yes
- Time: 2026-08-28 (Asia/Shanghai)
- Test file and test name: git argv/error-code; `test_run_command_approval_event_uses_project_internal_scope`; `test_chat_runtime_registers_optional_planning_tools`; `test_chat_and_trace_sse_generate_swallows_cancelled_error`; frontend command-copy and stdout sanitized tests
- Command: `$env:PYTHONIOENCODING='utf-8'; D:\anaconda\envs\agent-foundations\python.exe -m pytest tests/unit/tools/git/test_service.py tests/unit/chat/test_approvals.py tests/integration/test_chat_planning_tools.py tests/integration/test_ask_always_run_command_twice.py -q --tb=short`
- Exit code: 1
- Relevant verbatim output:

```text
FAILED tests/unit/tools/git/test_service.py::test_diff_and_log_argv_place_isolation_flags_after_subcommand
E   AssertionError: assert 2 > 4
E    +  where 2 = ...index('--no-ext-diff')
E    +  and   4 = ...index('diff')
FAILED tests/unit/tools/git/test_service.py::test_unknown_option_and_timeout_are_not_missing_repository
E   AssertionError: assert 'NOT_A_REPOSITORY' == 'GIT_USAGE_ERROR'
FAILED tests/unit/chat/test_approvals.py::test_run_command_approval_event_uses_project_internal_scope
E   AssertionError: assert 'external_exact_path' == 'project_internal'
FAILED tests/integration/test_chat_planning_tools.py::test_chat_runtime_registers_optional_planning_tools
E   AssertionError: assert {'replan', 'set_plan', 'update_plan_step'} <= {'apply_patch', ...}
5 failed, 28 passed, 2 warnings in 3.43s
```

SSE first attempt had an invalid `NameError` (`ApprovalCoordinator` not imported). Test was corrected **before production edits** and re-run:

```text
Command: ... pytest tests/unit/chat/test_approvals.py::test_chat_and_trace_sse_generate_swallows_cancelled_error -q --tb=short
Exit code: 1
E   asyncio.exceptions.CancelledError
  src/agent_foundations/chat/api.py:506: while not await request.is_disconnected()
```

Frontend Red (`npm run test:chat -- --run tests/chat/command-feedback.test.tsx tests/chat/activity.test.tsx`, exit 1):

```text
FAIL  tests/chat/activity.test.tsx > ApprovalCard > shows controlled command approval copy instead of external read
Unable to find an element with the text: Controlled command approval.
... <h3>External read approval</h3> ...
FAIL  tests/chat/command-feedback.test.tsx > command feedback card > renders stdout sanitized lines and does not let empty stderr overwrite them
Unable to find an element with the text: FAILED tests/test_boom.py::test_boom
... <pre class="command-feedback-card__page" /> ...
Tests  2 failed | 8 passed (10)
```

- Expected failure category: assertion failure from missing target behavior
- Why this failure demonstrates the missing behavior: argv order, usage mapped as `NOT_A_REPOSITORY`, Chat registry missing planning tools, run_command SSE scope hardcoded external, SSE cancel re-raised, UI still External read / stderr-only page. Not import/syntax errors after the SSE NameError was fixed.
- ASK_ALWAYS twice: `test_ask_always_run_command_asks_twice_in_same_conversation` **passed on Red** (28 passed included this file). Manual old-session skip **未复现**; capability already keyed by `run_id + tool_call_id`. Regression kept. Default Policy matrix not changed.

## 4. Green

- Production files changed: `src/agent_foundations/cli/main.py` (`runtime_factory`: per-turn `PlanController`+`ExecutionFactJournal`, registry planning tools, `PlanningToolExecutor(downstream=approval stack)`, `plan_controller=`, optional planning prompt, `PlanningMode.DISABLED`); `src/agent_foundations/tools/git/service.py`; `src/agent_foundations/chat/approvals.py`; `src/agent_foundations/chat/api.py`; `src/agent_foundations/viewer/app.py`; `web/chat/components/CommandFeedbackCard.tsx`; `web/chat/components/ApprovalCard.tsx`
- Command: `$env:PYTHONIOENCODING='utf-8'; D:\anaconda\envs\agent-foundations\python.exe -m pytest tests/unit/tools/git/test_service.py tests/unit/chat/test_approvals.py tests/integration/test_chat_planning_tools.py tests/integration/test_ask_always_run_command_twice.py -q --tb=line`
- Exit code: 0
- Relevant verbatim output:

```text
33 passed, 2 warnings in 3.22s
```

Fresh re-run after last test-typing/SSE helper cleanup: same 33 passed, exit 0.

`npm run test:chat` exit 0:

```text
Test Files  9 passed (9)
     Tests  76 passed (76)
```

## 5. Regression and Quality Gates

| Check | Command | Exit code | Result |
|---|---|---:|---|
| Target tests | `python -m pytest tests/unit/tools/git/test_service.py tests/unit/chat/test_approvals.py tests/integration/test_chat_planning_tools.py tests/integration/test_ask_always_run_command_twice.py -q` | 0 | 33 passed |
| Target frontend | `npm run test:chat` | 0 | 76 passed |
| Regression tests | `python -m pytest tests/unit/tools/git tests/unit/chat tests/unit/planning tests/integration/test_git_read_tools.py tests/integration/test_chat_approval_flow.py tests/integration/test_task16_production_wiring.py tests/integration/test_command_feedback_agent_flow.py -q` | 0 | 312 passed, 1 skipped |
| Ruff | `python -m ruff check` on affected modules listed in §6 | 0 | All checks passed |
| mypy | `python -m mypy` on the same affected modules | 0 | Success: no issues found in 9 source files |
| Frontend test, typecheck or build | `npm run typecheck:chat` | 0 | pass (`tsc --project tsconfig.chat.json --noEmit`) |
| Package or dependency check | not-run (not in contract) | | |
| `git diff --check` | `git diff --check` | 0 | pass (CRLF warnings only; this-Task files clean) |

Additional gates:

- argv: `index("--no-ext-diff") > index("diff"|"log")` asserted in `test_diff_and_log_argv_place_isolation_flags_after_subcommand`
- `unknown option` / exit 129 → `GIT_USAGE_ERROR`; `fatal: not a git repository` still `NOT_A_REPOSITORY`
- Chat registry has three planning tools; `planning_mode is DISABLED`; FakeModel `set_plan` then final answer; factory source has no `PlanningMode.REQUIRED`
- stdout-only sanitized UI renders stdout lines
- external read card still “External read approval”
- 真实 Provider: not-run / 未授权
- Docker: not-run / 未授权

## 6. Scope Audit

- Final changed files:
  - Create: `docs/task-evidence/phase-2d-task-13.md`
  - Create: `tests/integration/test_chat_planning_tools.py`
  - Create: `tests/integration/test_ask_always_run_command_twice.py`
  - Modify: `src/agent_foundations/cli/main.py` (`runtime_factory` only)
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
  - Modify: `docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md` (Appendix Task 29 after Task 28 only)
- Unrelated changes introduced: no
- Existing user changes preserved: yes
- Secrets or generated artifacts detected: no
- Commit, push, deployment, paid API call, or next Task performed: none
- Collateral not used: `tool_execution.py` display string unchanged; `test_chat_api.py` not updated (no mechanical pending-scope failure for external read)

## 7. Gaps and Limitations

- Checks not run and reasons: full Phase 1/2 suite not-required; `pytest -m docker` not-run / 未授权; real Provider / Task 25 Step 10 3×3 not-run / 未授权; `pip check` / viewer npm / `build:chat` not in this contract
- Environment warnings: sqlite3 datetime adapter DeprecationWarning; Starlette/httpx TestClient deprecation; git CRLF `LF will be replaced by CRLF` warnings
- Process evidence gaps: ASK_ALWAYS twice did not fail on Red (未复现 + 二次 ASK 回归已加). SSE Red had one discarded NameError; valid `CancelledError` Red was captured before production edits.
- Remaining risks: `git_diff` error classifier now inspects stdout+stderr because the existing unit fixture placed `fatal: not a git repository` on stdout. RISK_BASED command auto-ALLOW unchanged. This Task does not prove Docker git or paid-model Chat.

## 8. Handoff Summary

- Current verification status: **pass** (targeted verification passed; **not** full suite passed). Reviewer-fresh: Target pytest 33 passed; `npm run test:chat` 76 passed; affected 312 passed / 1 skipped; `npm run typecheck:chat` pass; ruff/mypy on 9 files passed
- TDD process evidence: **complete** for argv/error-code, planning wiring, approval scope, SSE cancel, sanitized UI, command copy; ASK_ALWAYS twice regression present but historical Red for that defect is unreproduced. Reviewer fresh checks prove current green, not the historical Red→Green sequence
- User acceptance: recorded in §9
- Reviewer acceptance: pass (current implementation, targeted) in the reviewer session that preceded this confirmation
- Reviewer findings retained: P3 git classifier inspects stdout+stderr because the fixture placed `fatal: not a git repository` on stdout; `GIT_CONFIG_COUNT=2` / `core.autocrlf=true` Docker git isolation not re-verified (contract Docker not-run); Chat creates a new `PlanController` each turn
- Recommended reviewer commands (already run for this Task):

```powershell
$env:PYTHONIOENCODING='utf-8'
D:\anaconda\envs\agent-foundations\python.exe -m pytest tests/unit/tools/git/test_service.py tests/unit/chat/test_approvals.py tests/integration/test_chat_planning_tools.py tests/integration/test_ask_always_run_command_twice.py -q
npm run test:chat
npm run typecheck:chat
```

Do not treat this evidence as Phase 2 user sign-off. Task 25 Step 10/11 remain unchecked.

## 9. User Acceptance

- Confirmed at: 2026-08-28 +08:00.
- Exact user confirmation: `确认「Task 29 / phase-2d-task-13 用户验收通过」`.
- Result: Appendix Task 29 / `phase-2d-task-13` (Chat manual-acceptance defect fixes) is user-accepted for the current implementation. This is **not** plan body Task 13 (Approval/Policy). Independent reviewer re-ran the targeted contract (Target pytest 33 passed; `npm run test:chat` 76 passed; affected 312 passed / 1 skipped; `npm run typecheck:chat` pass).
- Full suite note: this confirmation accepts **targeted verification passed**. It does not claim `full suite passed`, does not accept Task 25 as complete, does not accept paid 3×3, and does not mark user Phase 2 complete. Plan Task 25 Step 10 and Step 11 remain unchecked. Docker git isolation and real-model Chat were not part of this contract.
- TDD note: executor Red for argv/planning/scope/SSE/UI is internally consistent and marked complete; ASK_ALWAYS twice did not fail on Red (unreproduced) and the regression was kept. This confirmation does not independently witness the original Red→Green sequence.
- Boundary: this confirmation records `phase-2d-task-13` acceptance only. No commit, push, paid API rerun, Phase 2 complete checkbox, or Phase 3 is authorized by this confirmation. Suggested commit remains unauthorized: `fix: wire chat planning and correct git diff and command UI`.
