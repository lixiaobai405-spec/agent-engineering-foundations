# Task Evidence: phase-2d-task-31

## 1. Identity

- Task ID: `phase-2d-task-31`
- Authoritative plan or task spec: `docs/agent-plans/2026-09-08-phase-2-post-3x3-reliability-fixes-plan.md` Task 47
- Evidence status: completed
- TDD required: yes
- Started at: 2026-09-08 (Asia/Shanghai)

## 2. Pre-change Snapshot

- Branch or revision: `codex/phase-2-next` @ `14ece4e`
- `git status --short`: dirty tree preserved. Allowed Task 47 files were already dirty/untracked: `src/agent_foundations/chat/repository.py` (`M`), `src/agent_foundations/chat/runner.py` (`M`), `src/agent_foundations/viewer/app.py` (`M`), `tests/unit/chat/test_repository.py` (`M`), `tests/unit/chat/test_runner.py` (`M`), `tests/unit/chat/test_lifecycle.py` (`??`). Not reset/restored/cleaned.
- Existing user changes that must be preserved: entire dirty tree including prior Task 45/46 work and unrelated Phase 2 files
- Intended modification scope: `src/agent_foundations/chat/repository.py`, `src/agent_foundations/chat/runner.py`, `src/agent_foundations/viewer/app.py` (lifespan pass durable repo only), related unit tests in `tests/unit/chat/test_repository.py`, `test_runner.py`, `test_lifecycle.py`, this evidence. Plan Task 47 has no Done when checkboxes; do not rewrite Task 47 goals; do not tick Task 48.
- Expected rollback: restore those Task 47 files only. Do not restore the rest of the dirty tree.

## 3. Red

- Recorded before production-code changes: yes
- Time: 2026-09-08 (Asia/Shanghai)
- Test file and test name: `test_interrupt_unfinished_cancels_cancelable_durable` (created/running/waiting_approval/paused); `test_interrupt_unfinished_does_not_reapply_committed_apply_patch`; `test_safe_interrupt_run_cancels_cancelable_durable` (created/waiting_approval/paused); `test_safe_interrupt_run_skips_terminal_durable`; `test_create_app_lifespan_cancels_matching_durable_running_run`
- Command: `D:\anaconda\envs\agent-foundations\python.exe -m pytest tests/unit/chat/test_repository.py::test_interrupt_unfinished_cancels_cancelable_durable tests/unit/chat/test_repository.py::test_interrupt_unfinished_does_not_reapply_committed_apply_patch tests/unit/chat/test_runner.py::test_safe_interrupt_run_cancels_cancelable_durable tests/unit/chat/test_runner.py::test_safe_interrupt_run_skips_terminal_durable tests/unit/chat/test_runner.py::test_safe_interrupt_run_skips_missing_durable_row tests/unit/chat/test_lifecycle.py::test_create_app_lifespan_cancels_matching_durable_running_run -q --tb=short`
- Exit code: 1
- Relevant verbatim output:

```text
FFFFFF.FFFFF.F                                                           [100%]
FAILED ...::test_interrupt_unfinished_cancels_cancelable_durable[created]
E   AssertionError: assert <DurableRunStatus.CREATED: 'created'> is <DurableRunStatus.CANCELLED: 'cancelled'>
FAILED ...::test_interrupt_unfinished_cancels_cancelable_durable[running]
E   AssertionError: assert <DurableRunStatus.RUNNING: 'running'> is <DurableRunStatus.CANCELLED: 'cancelled'>
FAILED ...::test_interrupt_unfinished_cancels_cancelable_durable[waiting_approval]
E   AssertionError: assert <DurableRunStatus.WAITING_APPROVAL: 'waiting_approval'> is <DurableRunStatus.CANCELLED: 'cancelled'>
FAILED ...::test_interrupt_unfinished_cancels_cancelable_durable[paused]
E   AssertionError: assert <DurableRunStatus.PAUSED: 'paused'> is <DurableRunStatus.CANCELLED: 'cancelled'>
FAILED ...::test_interrupt_unfinished_does_not_reapply_committed_apply_patch
E   AssertionError: assert <DurableRunStatus.RUNNING: 'running'> is <DurableRunStatus.CANCELLED: 'cancelled'>
FAILED ...::test_safe_interrupt_run_cancels_cancelable_durable[created]
E   DurableRunStatusConflictError: expected running, got created
FAILED ...::test_safe_interrupt_run_cancels_cancelable_durable[waiting_approval]
E   DurableRunStatusConflictError: expected running, got waiting_approval
FAILED ...::test_safe_interrupt_run_cancels_cancelable_durable[paused]
E   DurableRunStatusConflictError: expected running, got paused
FAILED ...::test_safe_interrupt_run_skips_terminal_durable[completed]
E   DurableRunStatusConflictError: expected running, got completed
FAILED ...::test_safe_interrupt_run_skips_terminal_durable[failed]
E   DurableRunStatusConflictError: expected running, got failed
FAILED ...::test_safe_interrupt_run_skips_terminal_durable[cancelled]
E   DurableRunStatusConflictError: expected running, got cancelled
FAILED ...::test_create_app_lifespan_cancels_matching_durable_running_run
E   AssertionError: assert <DurableRunStatus.RUNNING: 'running'> is <DurableRunStatus.CANCELLED: 'cancelled'>
12 failed, 2 passed in 5.61s
```

Ledger test first attempt used `DirectToolCallExecutor` and failed with `CONTROLLED_EXECUTION_REQUIRED` (invalid Red). Test-only fix to a counting downstream, then re-ran before production:

```text
FAILED ...::test_interrupt_unfinished_does_not_reapply_committed_apply_patch
E   AssertionError: assert <DurableRunStatus.RUNNING: 'running'> is <DurableRunStatus.CANCELLED: 'cancelled'>
1 failed in 1.10s
```

- Expected failure category: missing target behavior
- Why this failure demonstrates the missing behavior: `interrupt_unfinished` / lifespan only close Chat runs; matching Durable stays CREATED/RUNNING/WAITING_APPROVAL/PAUSED. `_safe_interrupt_run` hardcodes RUNNING→CANCELLED, so non-RUNNING Durable raises `DurableRunStatusConflictError` and can fail Chat interrupt. Missing Durable row already skipped (1 of the 2 passes). RUNNING Durable already cancels via the hardcoded path (the other pass).
- If unavailable, why it cannot be verified:

## 4. Green

- Production files changed: `src/agent_foundations/chat/repository.py`, `src/agent_foundations/chat/runner.py`, `src/agent_foundations/viewer/app.py`
- Command: `D:\anaconda\envs\agent-foundations\python.exe -m pytest tests/unit/chat/test_repository.py tests/unit/chat/test_runner.py tests/unit/chat/test_lifecycle.py -q --tb=short`
- Exit code: 0
- Relevant verbatim output:

```text
........................................................................ [ 70%]
..............................                                           [100%]
102 passed, 2 warnings in 6.37s
```

First Green attempt after implementation was 98 failed / 4 passed (`NameError: SqliteDatabase`) from a dropped storage import; that import was restored and the command above is the passing Green. Ledger regression lives in `tests/unit/chat/test_repository.py` (same Target/Affected files).

## 5. Regression and Quality Gates

| Check | Command | Exit code | Result |
|---|---|---:|---|
| Target tests | `pytest tests/unit/chat/test_repository.py tests/unit/chat/test_runner.py tests/unit/chat/test_lifecycle.py -q` | 0 | pass (102 passed) |
| Regression tests | same as Target | 0 | pass (102 passed) |
| Ruff | `ruff check` on Task 47 production + edited tests | 0 | pass |
| mypy | `mypy --strict` on `repository.py` `runner.py` `app.py` | 0 | pass |
| Frontend test, typecheck or build | not-required | | not-run |
| Package or dependency check | not-required | | not-run |
| `git diff --check` | scoped Task 47 files | 0 | pass |

Targeted verification passed; not full suite.

## 6. Scope Audit

- Final changed files:
  - `src/agent_foundations/chat/repository.py`
  - `src/agent_foundations/chat/runner.py`
  - `src/agent_foundations/viewer/app.py`
  - `tests/unit/chat/test_repository.py`
  - `tests/unit/chat/test_runner.py`
  - `tests/unit/chat/test_lifecycle.py`
  - `docs/task-evidence/phase-2d-task-31.md`
- Unrelated changes introduced: no (Task 47 edits only on allowed files; those src/test files were already dirty with prior Phase 2 work)
- Existing user changes preserved: yes
- Secrets or generated artifacts detected: no
- Commit, push, deployment, paid API call, or next Task performed: no. Did not start Task 48, Stop UI, `npm run build:chat`, Docker rebuild, or tick Step 10/11.

Plan Task 47 has no Done when checkboxes; goals/forbidden items were not rewritten; Task 48 was not ticked.

## 7. Gaps and Limitations

- Checks not run and reasons: full pytest suite not-required; frontend/npm/build:chat not-required and forbidden; `pip check` not-required
- Environment warnings: Starlette/`httpx` TestClient deprecation; sqlite3 default datetime adapter deprecation on the ledger test
- Process evidence gaps: ledger test's first Red used `DirectToolCallExecutor` (`CONTROLLED_EXECUTION_REQUIRED`, invalid). Test-only switch to counting downstream, then a valid missing-behavior Red (`Durable` still `running`) was recorded before production. First Green after impl failed on a dropped `SqliteDatabase` import; that was restored before the recorded Green.
- Remaining risks: Chat then Durable cancel is not one SQLite transaction. `_safe_fail_run` still hardcodes Durable `RUNNING→FAILED` (out of scope). No Stop API/UI (Task 48).

## 8. Handoff Summary

- Current verification status: **pass** (targeted verification; not full suite). Reviewer-fresh: Target/Affected 102 passed (2 preexisting deprecation warnings); ruff / mypy `--strict` / `git diff --check` exit 0.
- TDD process evidence: **complete**. Reviewer fresh checks prove current green, not the historical Red→Green sequence
- User acceptance: recorded in §9
- Reviewer acceptance: pass (current implementation, targeted) in the reviewer session that preceded this confirmation
- Reviewer findings retained: P3 Chat update and Durable `cancel_run` are not one SQLite transaction; `_safe_fail_run` still hardcodes Durable `RUNNING→FAILED` (out of scope); ledger regression re-executes via `IdempotentToolCallExecutor` rather than a full Chat resume path
- Recommended reviewer commands (already run for this Task):

```powershell
$env:PYTHONIOENCODING = 'utf-8'
$py = 'D:\anaconda\envs\agent-foundations\python.exe'
& $py -m pytest tests/unit/chat/test_repository.py tests/unit/chat/test_runner.py tests/unit/chat/test_lifecycle.py -q
& $py -m ruff check src/agent_foundations/chat/repository.py src/agent_foundations/chat/runner.py src/agent_foundations/viewer/app.py tests/unit/chat/test_repository.py tests/unit/chat/test_runner.py tests/unit/chat/test_lifecycle.py
& $py -m mypy --strict src/agent_foundations/chat/repository.py src/agent_foundations/chat/runner.py src/agent_foundations/viewer/app.py
git diff --check -- src/agent_foundations/chat/repository.py src/agent_foundations/chat/runner.py src/agent_foundations/viewer/app.py tests/unit/chat/test_repository.py tests/unit/chat/test_runner.py tests/unit/chat/test_lifecycle.py
```

## 9. User Acceptance

- Confirmed at: 2026-09-08 +08:00.
- Exact user confirmation: `确认「Task 47 / phase-2d-task-31 用户验收通过」`.
- Result: Chat interrupt also closes Durable Task 47 / `phase-2d-task-31` (`interrupt_unfinished` and `_safe_interrupt_run` share `cancel_durable_run_if_active`; cancelable Durable `CREATED`/`RUNNING`/`WAITING_APPROVAL`/`PAUSED` become `CANCELLED`; terminal Durable and missing rows are skipped; lifespan passes `services.durable_repository`; COMMITTED `apply_patch` is not re-applied) is user-accepted for the current implementation. Independent reviewer re-ran the targeted contract (102 passed; ruff/mypy `--strict`/`git diff --check` exit 0).
- Full suite note: this confirmation accepts **targeted verification passed**. It does not claim `full suite passed`, does not accept plan-body Task 25 as complete, does not accept paid 3×3, and does not mark user Phase 2 complete. Plan Task 25 Step 10 and Step 11 remain unchecked.
- TDD note: executor Red is internally consistent and marked complete (12 failed / 2 passed: Chat interrupted while Durable stayed cancelable; `_safe_interrupt_run` raised `DurableRunStatusConflictError` on non-RUNNING; lifespan did not cancel Durable). Ledger first Red via `DirectToolCallExecutor` was invalid; a valid missing-behavior Red was recorded before production. This confirmation does not independently witness the original Red→Green sequence.
- Boundary: this confirmation records `phase-2d-task-31` acceptance only. Task 48 still requires separate explicit authorization. Paid 3×3 still requires a separate explicit authorization and remains Task 25 Step 10. No commit, push, paid API rerun, Phase 2 complete checkbox, or Phase 3 is authorized by this confirmation. Reviewer P3 findings are retained and do not require immediate rework from this confirmation.

