# Task Evidence: phase-2d-task-21

## 1. Identity

- Task ID: `phase-2d-task-21`
- Authoritative plan or task spec: `docs/agent-plans/2026-09-04-phase-2-product-hardening-plan.md` Task 37 plus the user-confirmed executor prompt
- Evidence status: user-accepted 2026-09-04 (targeted verification); Task 25 Step 10/11 **not claimed**; Phase 2 complete **not claimed**
- TDD required: yes
- Started at: 2026-09-04 (Asia/Shanghai)

## 2. Pre-change Snapshot

- Branch or revision: `codex/phase-2-next` at `14ece4e` (not `main`)
- `git status --short`: dirty working tree already present (Phase 2A–2D, Chat hashed assets, Dockerfiles, evidence, Task 30–36 files). Exact listing is long.
- Existing user changes that must be preserved: all pre-existing modified and untracked files at Task start. Do not `restore`/`reset`/`clean`.
- Intended modification scope: SSE `approval.requested` and GET `pending_approval` PolicyRequest view fields; Chat callers pass existing manifests; ApprovalCard titles by `resource_kind`. Do not change Policy matrix, gate_id, Git, Artifact, `max_steps`, Dockerfiles, schema migration, Task 35/36 P3, Tasks 38–41, or stdout/stderr dual tabs.
- Expected rollback: revert only this Task’s files; do not revert the pre-existing dirty tree.
- Interpreter: Windows `conda run` can crash pytest with GBK. Commands use `$env:PYTHONIOENCODING='utf-8'`. This does not shrink the verification contract.

## 3. Red

- Recorded before production-code changes: yes
- Time: 2026-09-04 (Asia/Shanghai), after new/updated approval view tests and before `approvals.py` / `api.py` / `tool_execution.py` / ApprovalCard / reducer changes
- Test file and test name:
  - `tests/unit/chat/test_approvals.py` (SSE Policy fields, sqlite `read` mapped to `run`, GET resource_kind)
  - `tests/chat/activity.test.tsx` (Policy/Resource on cards, missing `resource_kind` must not parse as External read)
  - `tests/chat/reducer.test.ts` (`activeApprovalFromPending` must copy HTTP Policy fields)
- Command: `$env:PYTHONIOENCODING='utf-8'; conda run -n agent-foundations python -m pytest tests/unit/chat/test_approvals.py -q --tb=short` then `npm run test:chat`
- Exit code: 1 (both)
- Relevant verbatim output:

```text
..FFFFF.....................                                             [100%]
FAILED tests/unit/chat/test_approvals.py::test_approval_events_contain_safe_metadata_only
E   Right contains 2 more items: {'policy_decision': 'ask', 'resource_kind': 'project_path'}
FAILED tests/unit/chat/test_approvals.py::test_run_command_approval_event_uses_project_internal_scope
E   AssertionError: assert 'read' == 'run'
FAILED tests/unit/chat/test_approvals.py::test_apply_patch_approval_event_uses_project_path_apply
E   KeyError: 'resource_kind'
FAILED tests/unit/chat/test_approvals.py::test_pending_approval_state_maps_sqlite_read_run_command_to_policy_view
E   AssertionError: assert 'read' == 'run'
FAILED tests/unit/chat/test_approvals.py::test_pending_approval_state_maps_apply_and_external_read
E   KeyError: 'resource_kind'
5 failed, 23 passed in 2.62s

 Test Files  2 failed | 8 passed (10)
      Tests  5 failed | 76 passed (81)
 FAIL  tests/chat/activity.test.tsx > ApprovalCard > shows one-time external read approval details and action buttons
 Unable to find an element with the text: /Policy: ask/i
 FAIL  tests/chat/activity.test.tsx > ApprovalCard > shows controlled command approval copy instead of external read
 Unable to find an element with the text: sandbox_command
 FAIL  tests/chat/activity.test.tsx > ApprovalCard > does not treat a missing resource_kind as External read
 expected { …(6) } to be null
 FAIL  tests/chat/reducer.test.ts > restores waiting approval and pending approval from HTTP recovery
 FAIL  tests/chat/reducer.test.ts > restores run_command pending approval from HTTP policy fields
```

- Expected failure category: SSE/GET still omit `resource_kind` / `policy_decision`; `run_command` view operation still sqlite `read`; ApprovalCard still hides Policy except on patch; parse still succeeds without `resource_kind`. Tests collected and ran (not syntax/import collection errors).
- Why this failure demonstrates the missing behavior: missing Policy fields still parse as External read; command cards still cannot show `run` / `sandbox_command`; GET cannot recover those fields from sqlite `read`.
- If unavailable, why it cannot be verified:

## 4. Green

- Production files changed:
  - `src/agent_foundations/chat/approvals.py` (`approval_view_fields`; `_build_requested_event` uses PolicyRequest + PolicyOutcome; `request()` / `request_capability` pass them)
  - `src/agent_foundations/chat/api.py` (`PendingApprovalState` view fields; GET maps sqlite `read` `run_command` → `run` / `sandbox_command`)
  - `src/agent_foundations/chat/tool_execution.py` (run_command / apply_patch construct PolicyRequest from existing manifests)
  - `web/chat/components/ApprovalCard.tsx` (title by `resource_kind`; Policy/Resource on all cards; parse requires new fields)
  - `web/chat/state/types.ts` / `web/chat/state/reducer.ts` (HTTP pending copies Policy fields; no apply-only hardcode)
- Command: `$env:PYTHONIOENCODING='utf-8'; conda run -n agent-foundations python -m pytest tests/unit/chat/test_approvals.py -q --tb=short`
- Exit code: 0
- Relevant verbatim output:

```text
............................                                             [100%]
28 passed in 3.09s
```

Frontend Green: `npm run test:chat` exit 0, `Test Files  10 passed (10)` / `Tests  81 passed (81)`. After Green, `patch-preview.test.tsx` used `getAllByText(/project_path/i)` because Resource + meta both show `project_path`. `test_chat_approval_flow.py` no longer substring-matches `"source"` inside `resource_kind`; it asserts `"source" not in requested.data`.

## 5. Regression and Quality Gates

| Check | Command | Exit code | Result |
|---|---|---:|---|
| Target tests | `$env:PYTHONIOENCODING='utf-8'; conda run -n agent-foundations python -m pytest tests/unit/chat/test_approvals.py -q` | 0 | 28 passed (**targeted verification**) |
| Target tests | `npm run test:chat` | 0 | 81 passed (**targeted verification**) |
| Regression tests | `$env:PYTHONIOENCODING='utf-8'; conda run -n agent-foundations python -m pytest tests/unit/chat/test_approvals.py tests/integration/test_chat_api.py tests/integration/test_chat_approval_flow.py tests/integration/test_ask_always_run_command_twice.py -q` | 0 | 67 passed, 3 warnings (**targeted verification**, not full suite) |
| Ruff | `$env:PYTHONIOENCODING='utf-8'; conda run -n agent-foundations python -m ruff check src/agent_foundations/chat/approvals.py src/agent_foundations/chat/api.py src/agent_foundations/chat/tool_execution.py tests/unit/chat/test_approvals.py tests/integration/test_chat_api.py` | 0 | All checks passed |
| mypy | `$env:PYTHONIOENCODING='utf-8'; conda run -n agent-foundations python -m mypy src/agent_foundations/chat/approvals.py src/agent_foundations/chat/api.py src/agent_foundations/chat/tool_execution.py tests/unit/chat/test_approvals.py` | 0 | Success: no issues found in 4 source files |
| Frontend test, typecheck or build | `npm run typecheck:chat` | 0 | tsc --noEmit passed |
| Package or dependency check | not in contract | | not-run |
| `git diff --check` | `git diff --check` | 0 | no whitespace errors (LF/CRLF working-copy warnings only) |

## 6. Scope Audit

- Final changed files (this Task):
  - `src/agent_foundations/chat/approvals.py`
  - `src/agent_foundations/chat/api.py`
  - `src/agent_foundations/chat/tool_execution.py`
  - `web/chat/components/ApprovalCard.tsx`
  - `web/chat/state/types.ts`
  - `web/chat/state/reducer.ts`
  - `tests/unit/chat/test_approvals.py`
  - `tests/integration/test_chat_api.py`
  - `tests/integration/test_chat_approval_flow.py`
  - `tests/chat/activity.test.tsx`
  - `tests/chat/reducer.test.ts`
  - `tests/chat/app.test.tsx`
  - `tests/chat/patch-preview.test.tsx`
  - `docs/task-evidence/phase-2d-task-21.md`
  - `docs/agent-plans/2026-09-04-phase-2-product-hardening-plan.md` (status / 现状对照 / executor note only; Task 37 contract text unchanged)
- Unrelated changes introduced: no
- Existing user changes preserved: yes
- Secrets or generated artifacts detected: no
- Commit, push, deployment, paid API call, or next Task performed: no
- Not done: Task 35/36 P3; Policy matrix; gate_id; Git; Artifact; `max_steps`; Dockerfiles; schema migration; stdout/stderr dual tabs (Task 38); Task 38–41; Task 25 Step 10/11

## 7. Gaps and Limitations

- Checks not run and reasons: Phase 1 full baseline not-required by contract. Playwright e2e not in contract. pip check not in contract.
- Environment warnings: Windows conda pytest uses `PYTHONIOENCODING=utf-8`. Starlette TestClient deprecation; sqlite3 datetime adapter deprecation in ask-always integration. `git diff --check` prints LF/CRLF working-copy warnings on the pre-existing dirty tree.
- Process evidence gaps: none for Red→Green of Policy view fields. `patch-preview` matcher and `resource_kind` vs `"source"` substring were adjusted after Green exposed false-positive collisions.
- Remaining risks: GET without waiter still derives the locked three-row mapping; sqlite still stores AccessOperation `read`/`apply`. Unknown `resource_kind` renders generic "Approval request", not External read. `capability_id` is not in SSE/GET.

## 8. Handoff Summary

- Current verification status: **pass** (targeted verification; not full suite). Reviewer-fresh: Target pytest 28 passed; `npm run test:chat` 81 passed; Affected 67 passed; `npm run typecheck:chat` / ruff / mypy / `git diff --check` exit 0
- TDD process evidence: **complete**. Reviewer fresh checks prove current green, not the historical Red→Green sequence
- User acceptance: recorded in §9
- Reviewer acceptance: pass (current implementation, targeted) in the reviewer session that preceded this confirmation
- Reviewer findings retained: P3 GET `/state` always uses the locked three-row derivation even if a waiter still holds a live PolicyRequest; unknown `tool_name` on GET maps to the external-read row; Chat checks are vitest, not a live browser (Playwright e2e not in contract)
- Recommended reviewer commands (already run for this Task):

```text
$env:PYTHONIOENCODING='utf-8'
conda run -n agent-foundations python -m pytest tests/unit/chat/test_approvals.py -q
npm run test:chat
conda run -n agent-foundations python -m pytest tests/unit/chat/test_approvals.py tests/integration/test_chat_api.py tests/integration/test_chat_approval_flow.py tests/integration/test_ask_always_run_command_twice.py -q
npm run typecheck:chat
conda run -n agent-foundations python -m ruff check src/agent_foundations/chat/approvals.py src/agent_foundations/chat/api.py src/agent_foundations/chat/tool_execution.py tests/unit/chat/test_approvals.py tests/integration/test_chat_api.py
conda run -n agent-foundations python -m mypy src/agent_foundations/chat/approvals.py src/agent_foundations/chat/api.py src/agent_foundations/chat/tool_execution.py tests/unit/chat/test_approvals.py
git diff --check
```

## 9. User Acceptance

- Confirmed at: 2026-09-04 +08:00.
- Exact user confirmation: `确认「Task 37 / phase-2d-task-21 用户验收通过」`.
- Result: Product-hardening Task 37 / `phase-2d-task-21` (approval PolicyRequest rendering) is user-accepted for the current implementation. This is **not** plan body Task 21. Independent reviewer re-ran the targeted contract (28 passed on Target pytest; 81 passed on `npm run test:chat`; 67 passed on affected regression; typecheck / ruff / mypy / `git diff --check` exit 0).
- Full suite note: this confirmation accepts **targeted verification passed**. It does not claim `full suite passed`, does not accept Task 25 as complete, does not accept paid 3×3, and does not mark user Phase 2 complete. Plan Task 25 Step 10 and Step 11 remain unchecked.
- TDD note: executor Red is internally consistent and marked complete; this confirmation does not independently witness the original Red→Green sequence.
- Boundary: this confirmation records `phase-2d-task-21` acceptance only. Task 38 / `phase-2d-task-22` still requires its own explicit single-Task executor authorization. No commit, push, paid API rerun, Phase 2 complete checkbox, or Phase 3 is authorized by this confirmation. Reviewer P3 findings are retained and do not require immediate rework from this confirmation.
