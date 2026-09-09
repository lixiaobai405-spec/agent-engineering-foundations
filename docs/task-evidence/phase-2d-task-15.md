# Task Evidence: phase-2d-task-15

## 1. Identity

- Task ID: `phase-2d-task-15`
- Authoritative plan or task spec: `docs/agent-plans/2026-08-29-phase-2-reliability-follow-on-plan.md` Task 31 plus the user-confirmed executor prompt
- Evidence status: user-accepted 2026-08-29 (targeted verification); Task 25 Step 10/11 **not claimed**; Phase 2 complete **not claimed**
- TDD required: yes
- Started at: 2026-08-29 (Asia/Shanghai)

## 2. Pre-change Snapshot

- Branch or revision: `codex/phase-2-next` at `14ece4e` (not `main`)
- `git status --short`: dirty working tree already present (Phase 2A–2D, Chat hashed assets, Dockerfiles, evidence files, `.agents/`, `.gate-backup/`, Task 30 files). Exact listing is long.
- Existing user changes that must be preserved: all pre-existing modified and untracked files listed by `git status --short` at Task start. Do not `restore`/`reset`/`clean`.
- Intended modification scope: `src/agent_foundations/runtime/recovery.py` (new), `src/agent_foundations/runtime/loop.py` (consult recovery before tool execute and before `_request_model`), `tests/unit/runtime/test_recovery.py` (new), this evidence. Do not change Policy, Approval protocol, Sandbox, command whitelist, `max_steps`, schema v11, Task 30 CRLF P2, Docker, or Task 25 Step 10/11.
- Expected rollback: delete this Task’s new files and revert only this Task’s `loop.py` edits; do not revert the pre-existing dirty tree.
- Interpreter: Windows `conda run` can crash pytest with `UnicodeEncodeError: gbk`. Commands below use `$env:PYTHONIOENCODING='utf-8'` with `conda run -n agent-foundations`. This does not shrink the verification contract.

## 3. Red

- Recorded before production-code changes: yes (strategy stub always allowed; loop not yet consulting recovery)
- Time: 2026-08-29 (Asia/Shanghai)
- Test file and test name: `tests/unit/runtime/test_recovery.py` (10 tests)
- Command: `$env:PYTHONIOENCODING='utf-8'; conda run -n agent-foundations python -m pytest tests/unit/runtime/test_recovery.py -q --tb=line`
- Exit code: 1
- Relevant verbatim output:

```text
FFFFFFFFFF                                                               [100%]
D:\codex-pj\search_agent\tests\unit\runtime\test_recovery.py:127: AssertionError: assert True is False
D:\codex-pj\search_agent\tests\unit\runtime\test_recovery.py:167: AssertionError: assert True is False
D:\codex-pj\search_agent\tests\unit\runtime\test_recovery.py:185: AssertionError: assert True is False
D:\codex-pj\search_agent\tests\unit\runtime\test_recovery.py:207: AssertionError: assert True is False
D:\codex-pj\search_agent\tests\unit\runtime\test_recovery.py:244: AssertionError: assert True is False
D:\codex-pj\search_agent\tests\unit\runtime\test_recovery.py:254: assert True is False
D:\codex-pj\search_agent\tests\unit\runtime\test_recovery.py:273: AssertionError: unexpected extra execute for apply_patch
D:\codex-pj\search_agent\tests\unit\runtime\test_recovery.py:273: AssertionError: unexpected extra execute for apply_patch
D:\codex-pj\search_agent\tests\unit\runtime\test_recovery.py:417: AssertionError: assert 2 == 1
D:\codex-pj\search_agent\tests\unit\runtime\test_recovery.py:273: AssertionError: unexpected extra execute for run_command
10 failed in 0.40s
```

- Expected failure category: missing recovery policy (always-allow stub) and missing AgentLoop intercept / complete() guard
- Why this failure demonstrates the missing behavior: unit tests fail because `evaluate_tool_call` allows STALE/PARSE/HARD_STOP/COMMAND retries and `should_request_model` allows `APPROVAL_REQUIRED`; loop tests fail because the downstream executor is called again or `complete()` runs a second time. Not import, syntax, or environment errors.
- If unavailable, why it cannot be verified: n/a

## 4. Green

- Production files changed: `src/agent_foundations/runtime/recovery.py` (new); `src/agent_foundations/runtime/loop.py`; `src/agent_foundations/tools/patch/execution.py` (`change_paths` list so TraceEvent freeze accepts validate_patch sanitization). Tests: `tests/unit/runtime/test_recovery.py`; `tests/integration/test_command_feedback_agent_flow.py` (FakeModel reads artifact before same-argv retry).
- Command: `$env:PYTHONIOENCODING='utf-8'; conda run -n agent-foundations python -m pytest tests/unit/runtime/test_recovery.py -q`
- Exit code: 0
- Relevant verbatim output:

```text
..........                                                               [100%]
10 passed in 0.39s
```

## 5. Regression and Quality Gates

| Check | Command | Exit code | Result |
|---|---|---:|---|
| Target tests | `pytest tests/unit/runtime/test_recovery.py -q` | 0 | 10 passed |
| Regression tests | `pytest tests/unit/runtime tests/integration/test_agent_loop.py tests/integration/test_command_feedback_agent_flow.py tests/unit/tools/patch tests/unit/chat/test_approvals.py tests/unit/chat/test_tool_execution.py -q` | 0 | 269 passed |
| Ruff | scoped `src/agent_foundations/runtime tests/unit/runtime` | 0 | All checks passed |
| mypy | scoped `src/agent_foundations/runtime tests/unit/runtime` | 0 | Success: no issues found in 22 source files |
| Frontend test, typecheck or build | not in contract | | not-run |
| Package or dependency check | not in contract | | not-run |
| `git diff --check` | `git diff --check` | 0 | pass (LF/CRLF warnings only) |

## 6. Scope Audit

- Final changed files:
  - `src/agent_foundations/runtime/recovery.py` (new)
  - `src/agent_foundations/runtime/loop.py`
  - `src/agent_foundations/tools/patch/execution.py` (`change_paths` tuple → list)
  - `tests/unit/runtime/test_recovery.py` (new)
  - `tests/integration/test_command_feedback_agent_flow.py` (scripted model reads artifact)
  - `docs/task-evidence/phase-2d-task-15.md`
- Unrelated changes introduced: no (sanitize list is JSON-safety for existing validate_patch traces, not Policy/Approval/Sandbox)
- Existing user changes preserved: yes
- Secrets or generated artifacts detected: no
- Commit, push, deployment, paid API call, or next Task performed: no

## 7. Gaps and Limitations

- Checks not run and reasons: full pytest suite not-required; Docker E2E not-run (forbidden); npm/frontend not in contract
- Environment warnings: `PYTHONIOENCODING=utf-8` used with conda run; `git diff --check` LF/CRLF warnings on the pre-existing dirty tree
- Process evidence gaps: none for Red→Green of Target tests. A no-op always-allow stub existed so Red was assertion/executor-call failure rather than ImportError.
- Remaining risks: PARSE identical-payload block is applied to the failed tool name (including `apply_patch` with `PATCH_INVALID_ARGUMENTS`), not only `validate_patch`. Chat `WAITING_APPROVAL` still blocks inside the coordinator; loop additionally skips `complete()` when the latest tool error is `APPROVAL_REQUIRED`. `AgentRunState.schema_version` unchanged.

## 8. Handoff Summary

- Current verification status: **pass** (targeted verification; not full suite). Reviewer-fresh: Target `tests/unit/runtime/test_recovery.py` 10 passed; Affected 269 passed; ruff/mypy 22 files passed; `git diff --check` exit 0
- TDD process evidence: **complete**. Reviewer fresh checks prove current green, not the historical Red→Green sequence
- User acceptance: recorded in §9
- Reviewer acceptance: pass (current implementation, targeted) in the reviewer session that preceded this confirmation
- Reviewer findings retained: P3 PARSE identical-payload block applies to the failed tool name (including `apply_patch` + `PATCH_INVALID_ARGUMENTS`); loop `should_request_model` does not pass Chat `run_status=waiting_approval`; STALE paths depend on failed-call arguments/metadata; `evaluate_tool_call` uses raw `call.arguments`
- Recommended reviewer commands (already run for this Task):

```text
conda run -n agent-foundations python -m pytest tests/unit/runtime/test_recovery.py -q
conda run -n agent-foundations python -m pytest tests/unit/runtime tests/integration/test_agent_loop.py tests/integration/test_command_feedback_agent_flow.py tests/unit/tools/patch tests/unit/chat/test_approvals.py tests/unit/chat/test_tool_execution.py -q
conda run -n agent-foundations python -m ruff check src/agent_foundations/runtime tests/unit/runtime
conda run -n agent-foundations python -m mypy src/agent_foundations/runtime tests/unit/runtime
git diff --check
```

## 9. User Acceptance

- Confirmed at: 2026-08-29 +08:00.
- Exact user confirmation: `确认「Task 31 / phase-2d-task-15 用户验收通过」`.
- Result: Follow-on Task 31 / `phase-2d-task-15` (error-type driven recovery) is user-accepted for the current implementation. This is **not** plan body Task 15. Independent reviewer re-ran the targeted contract (10 passed on `tests/unit/runtime/test_recovery.py`; 269 passed on affected regression).
- Full suite note: this confirmation accepts **targeted verification passed**. It does not claim `full suite passed`, does not accept Task 25 as complete, does not accept paid 3×3, and does not mark user Phase 2 complete. Plan Task 25 Step 10 and Step 11 remain unchecked.
- TDD note: executor Red is internally consistent and marked complete; this confirmation does not independently witness the original Red→Green sequence.
- Boundary: this confirmation records `phase-2d-task-15` acceptance only. Task 32 / `phase-2d-task-16` still requires its own explicit single-Task executor authorization. No commit, push, paid API rerun, Phase 2 complete checkbox, or Phase 3 is authorized by this confirmation. Reviewer P3 findings and Task 30 CRLF P2 are retained and do not require immediate rework from this confirmation.
