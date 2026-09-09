# Task Evidence: phase-2d-task-11

## 1. Identity

- Task ID: `phase-2d-task-11`
- Authoritative plan or task spec: user prompt 2026-08-27; `docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md` Appendix Task 27
- Evidence status: user-accepted 2026-08-27 (targeted verification); Task 25 overall **not complete**; user Phase 2 complete **not claimed**
- TDD required: yes
- Started at: 2026-08-27 (Asia/Shanghai)

## 2. Pre-change Snapshot

- Branch or revision: `codex/phase-2-next` (not `main`)
- `git status --short`: dirty working tree already present. Task 10 user-accepted. Pre-existing runner/loop/test_runner diffs (durable run create/transition, Resilient hydrate when sink present, repo-map message assertions) must be preserved.
- Existing user changes that must be preserved: entire pre-existing dirty tree, including runner durable-run wiring that did not yet pass `checkpoint_sink` / `provider_attempts` into `loop.run`.
- Intended modification scope: Chat ConversationRunner CheckpointSink without lease; inject saved `provider_attempts` into `AgentLoop.run` initial state; Chat runner tests; this evidence; plan appendix locating this Task. Not DualBackend Docker sibling, sandbox pin, paid API, Task 24/25 body, Step 10/11 checkboxes.
- Expected rollback: revert only this Task’s files; do not revert the pre-existing dirty tree.
- Interpreter: `$env:PYTHONIOENCODING='utf-8'; D:\anaconda\envs\agent-foundations\python.exe`
- Depends on: `phase-2d-task-10` user-accepted 2026-08-27 (`确认「Task 10 / phase-2d-task-10 用户验收通过」`). Proceeded.

## 3. Red

- Recorded before production-code changes: yes
- Time: 2026-08-27 (Asia/Shanghai)
- Test file and test name: `tests/unit/chat/test_runner.py` (`test_chat_crash_after_reserve_new_runner_does_not_recall_inner`, `test_run_turn_forwards_checkpoint_sink_and_does_not_treat_interrupt_as_retry`)
- Command: `$env:PYTHONIOENCODING='utf-8'; D:\anaconda\envs\agent-foundations\python.exe -m pytest tests/unit/chat/test_runner.py::test_chat_crash_after_reserve_new_runner_does_not_recall_inner tests/unit/chat/test_runner.py::test_run_turn_forwards_checkpoint_sink_and_does_not_treat_interrupt_as_retry -q`
- Exit code: 1
- Relevant verbatim output:

```text
FF                                                                       [100%]
_______ test_chat_crash_after_reserve_new_runner_does_not_recall_inner ________
>       assert second_inner.calls == 0
E       assert 1 == 0
_ test_run_turn_forwards_checkpoint_sink_and_does_not_treat_interrupt_as_retry _
>       assert seen.get("checkpoint_sink") is not None
E       AssertionError: assert None is not None
E        +    where {'history': (), 'session_id': '22222222-2222-4222-8222-222222222222'}.get
FAILED tests/unit/chat/test_runner.py::test_chat_crash_after_reserve_new_runner_does_not_recall_inner
FAILED tests/unit/chat/test_runner.py::test_run_turn_forwards_checkpoint_sink_and_does_not_treat_interrupt_as_retry
2 failed in 0.67s
```

- Expected failure category: Chat `loop.run` has no `checkpoint_sink`; reserved provider attempts are not persisted, so a new AgentLoop hydrates empty budget and calls inner again
- Why this failure demonstrates the missing behavior: inner was recalled (`calls == 1`) after crash-after-reserve; spy shows `run()` kwargs are only `history` and `session_id`. Not an import/environment error.
- If unavailable, why it cannot be verified:

## 4. Green

- Production files changed:
  - `src/agent_foundations/chat/durable_checkpoint.py` (lease-free repository sink + load attempts)
  - `src/agent_foundations/chat/runner.py` (`run_turn` passes sink and saved `provider_attempts`; interrupt still does not call `begin_retry`)
  - `src/agent_foundations/runtime/loop.py` (optional `provider_attempts` on `run()`, default `{}`; does not default to DurableRunController)
- Command: `$env:PYTHONIOENCODING='utf-8'; D:\anaconda\envs\agent-foundations\python.exe -m pytest tests/unit/chat/test_runner.py::test_chat_crash_after_reserve_new_runner_does_not_recall_inner tests/unit/chat/test_runner.py::test_run_turn_forwards_checkpoint_sink_and_does_not_treat_interrupt_as_retry -q`
- Exit code: 0
- Relevant verbatim output:

```text
..                                                                       [100%]
2 passed in 0.49s
```

## 5. Regression and Quality Gates

| Check | Command | Exit code | Result |
|---|---|---:|---|
| Target tests | `pytest tests/unit/chat/test_runner.py -q` | 0 | 12 passed (2 new + prior runner tests) |
| Target tests | `pytest tests/integration/test_agent_loop.py -q -k provider` | 0 | 6 passed, 30 deselected |
| Target expansion | `pytest tests/integration/test_provider_retry_recovery.py -q` | 0 | 8 passed (Task 24 crash-after-reserve / exhausted / begin_retry; recorded because `-k provider` on `test_agent_loop.py` does not select those tests) |
| Regression tests | `pytest tests/unit/chat/test_runner.py tests/integration/test_chat_api.py -q` | 0 | 44 passed |
| Regression tests | `pytest tests/e2e/test_chat_ui.py -q` | 0 | 8 passed |
| Ruff | `pytest` not used; `ruff check` on runner.py, durable_checkpoint.py, loop.py, test_runner.py | 0 | All checks passed |
| mypy | same four files | 0 | Success: no issues found in 4 source files |
| Frontend test, typecheck or build | not-required | | |
| Package or dependency check | not-required | | |
| `git diff --check` | Task files listed in §6 | 0 | pass |

## 6. Scope Audit

- Final changed files:
  - Create: `src/agent_foundations/chat/durable_checkpoint.py`
  - Modify: `src/agent_foundations/chat/runner.py`
  - Modify: `src/agent_foundations/runtime/loop.py`
  - Modify: `tests/unit/chat/test_runner.py`
  - Create: `docs/task-evidence/phase-2d-task-11.md`
  - Modify: `docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md` (Appendix Task 27 only; Task 24/25 body and Step 10/11 unchanged)
- Unrelated changes introduced: no
- Existing user changes preserved: yes
- Secrets or generated artifacts detected: no
- Commit, push, deployment, paid API call, or next Task performed: none

## 7. Gaps and Limitations

- Checks not run and reasons: Full suite not-required. Paid 3×3 not run. DualBackend Docker sibling not started.
- Environment warnings: Starlette/httpx TestClient deprecation in chat API; sqlite3 datetime adapter DeprecationWarning in chat UI e2e. `git diff --check` LF/CRLF warning from `core.autocrlf`.
- Process evidence gaps: none for this Task’s Red→Green. Pre-existing runner/loop dirty diffs were preserved and are not this Task’s historical Red.
- Remaining risks: Chat still does not full-resume tool history through DurableRunController. Same-session crash recovery hydrates attempt budget into a fresh `loop.run` initial state. Interrupt transitions durable `RUNNING`→`CANCELLED` and does not call `begin_retry`. Chat has no user-visible begin_retry API; none was added.

## 8. Handoff Summary

- Current verification status: **pass** (targeted verification passed; not full suite). Reviewer-fresh: `test_runner.py` 12 passed; `test_agent_loop.py -k provider` 6 passed / 30 deselected; `test_provider_retry_recovery.py` 8 passed; affected runner+API+chat UI 52 passed; ruff/mypy on the four Task files passed
- TDD process evidence: **complete**. Reviewer fresh checks prove current green, not the historical Red→Green sequence
- User acceptance: recorded in §9
- Reviewer acceptance: pass (current implementation, targeted) in the reviewer session that preceded this confirmation
- Reviewer findings retained: P3 `test_chat_crash_after_reserve_new_runner_does_not_recall_inner` injects saved attempts into `loop.run` and sets `checkpoint_sink=None` instead of calling `runner2.run_turn()`; production `run_turn` still loads attempts. Interrupt path does not call `begin_retry`. Chat is not upgraded to DurableRunController full resume
- Recommended reviewer commands (already run for this Task):

```powershell
$env:PYTHONIOENCODING='utf-8'
D:\anaconda\envs\agent-foundations\python.exe -m pytest tests/unit/chat/test_runner.py -q
D:\anaconda\envs\agent-foundations\python.exe -m pytest tests/integration/test_agent_loop.py -q -k provider
D:\anaconda\envs\agent-foundations\python.exe -m pytest tests/integration/test_provider_retry_recovery.py -q
D:\anaconda\envs\agent-foundations\python.exe -m pytest tests/unit/chat/test_runner.py tests/integration/test_chat_api.py tests/e2e/test_chat_ui.py -q
D:\anaconda\envs\agent-foundations\python.exe -m ruff check src/agent_foundations/chat/runner.py src/agent_foundations/chat/durable_checkpoint.py src/agent_foundations/runtime/loop.py tests/unit/chat/test_runner.py
D:\anaconda\envs\agent-foundations\python.exe -m mypy src/agent_foundations/chat/runner.py src/agent_foundations/chat/durable_checkpoint.py src/agent_foundations/runtime/loop.py tests/unit/chat/test_runner.py
git diff --check -- src/agent_foundations/chat/runner.py src/agent_foundations/chat/durable_checkpoint.py src/agent_foundations/runtime/loop.py tests/unit/chat/test_runner.py docs/task-evidence/phase-2d-task-11.md docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md
```

## 9. User Acceptance

- Confirmed at: 2026-08-27 +08:00.
- Exact user confirmation: `确认「Task 11 / phase-2d-task-11 用户验收通过」`.
- Result: Appendix Task 27 / `phase-2d-task-11` (Chat `ConversationRunner` Durable `CheckpointSink`) is user-accepted for the current implementation. This is **not** plan body Task 11 (Patch parser). Independent reviewer re-ran the targeted contract (runner 12 passed; agent_loop `-k provider` 6 passed; provider retry recovery 8 passed; affected 52 passed).
- Full suite note: this confirmation accepts **targeted verification passed**. It does not claim `full suite passed`, does not accept Task 25 as complete, does not accept paid 3×3, and does not mark user Phase 2 complete. Plan Task 25 Step 10 and Step 11 remain unchecked.
- TDD note: executor Red is internally consistent and marked complete; this confirmation does not independently witness the original Red→Green sequence.
- Boundary: this confirmation records `phase-2d-task-11` acceptance only. The optional DualBackend Docker sibling E2E still requires its own explicit single-Task executor authorization. No commit, push, paid API rerun, or next-Task implementation is authorized by this confirmation. Chat interrupt still does not call `begin_retry`; no user-visible begin_retry API was added.
