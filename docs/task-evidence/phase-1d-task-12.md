# Task Evidence: phase-1d-task-12

## 1. Identity

- Task ID: `phase-1d-task-12`
- Task name: 端到端验收、刷新恢复、文档与 Phase 1D 总门禁
- Authoritative plan: `docs/agent-plans/2026-08-02-phase-1d-interactive-chat-ui-plan.md` Task 12
- Evidence status: `completed-awaiting-review` (includes 2026-08-07 remediation)
- TDD required: `yes` (docs: `not-applicable`)
- Started at: `2026-08-07T22:23+08:00`
- Completed at: `2026-08-07T23:05+08:00` (initial); remediation `2026-08-07T23:50+08:00`
- Executor role confirmed: `yes`

## 2. Pre-change Snapshot

- Branch: `main` (working tree dirty, unstaged)
- Staging area: empty (`git diff --cached --name-only` → no output)
- Task 12 plan checkboxes: all unchecked at start
- Chat baseline: `npm run test:chat` → exit 0, **34 passed**
- Chat typecheck: exit 0
- Viewer tests: **9 passed**
- Viewer typecheck: exit 0
- Python targeted baseline: `pytest tests/unit/chat/test_repository.py tests/integration/test_chat_api.py tests/integration/test_chat_approval_flow.py tests/integration/test_viewer_api.py -q` → exit 0, **71 passed**
- Existing user changes preserved: yes (Phase 1B/1C/1D untracked and modified files)
- Overlap with Task 12: none on recovery API / E2E (new work)
- Rollback: revert Task 12 recovery API, frontend recovery, E2E, docs, learning note, plan checkbox updates, and `static/chat/` build output from this task

## 3. Red

### 3.1 Python Repository/API

- Recorded before production-code changes: **yes** (tests committed before `repository.py` / `api.py` edits in executor session)
- Verbatim output in evidence file: **unavailable** (context summary before evidence write; not reconstructed post-hoc)
- Command: `conda run -n agent-foundations python -m pytest tests/unit/chat/test_repository.py tests/integration/test_chat_api.py -q`
- Expected failure category: missing `get_conversation_state`, missing `GET .../state`, assertion failures on recovery shape
- Why valid: new recovery tests referenced behavior not yet implemented

### 3.2 Frontend typed recovery

- Recorded before production-code changes: **yes** (tests/types committed before reducer/api/App production edits)
- Verbatim output in evidence file: **unavailable**
- Command: `npm run test:chat` ; `npm run typecheck:chat`
- Expected failure category: missing `getConversationState`, missing `conversation.state.loaded`, type errors on `PendingApprovalState` / `ConversationStateResponse`
- Why valid: recovery tests failed until typed client, reducer action, and App load order implemented

### 3.3 E2E

- Recorded before production-code changes: **yes** (`tests/e2e/test_chat_ui.py` added before full green)
- Verbatim output in evidence file: **unavailable**
- Command: `npm run build:chat` ; `conda run -n agent-foundations python -m pytest tests/e2e/test_chat_ui.py -q`
- Expected failure category: missing fresh reload recovery, Playwright assertions on `/state`, approval card, narrow viewport
- Why valid: E2E targeted Task 12 browser behaviors not present before HTTP recovery wiring

## 4. Green

### 4.1 Repository/API/Frontend

- Production files changed: `repository.py`, `api.py`, `types.ts`, `api.ts`, `reducer.ts`, `App.tsx`
- Command: `conda run -n agent-foundations python -m pytest tests/unit/chat/test_repository.py tests/integration/test_chat_api.py -q`
- Exit code: `0`
- Result: **80 passed**

- Command: `npm run test:chat`
- Exit code: `0`
- Result: **44 passed**

- Command: `npm run typecheck:chat`
- Exit code: `0`

### 4.2 E2E

- Command: `npm run build:chat` ; `conda run -n agent-foundations python -m pytest tests/e2e/test_chat_ui.py -q`
- Exit code: `0`
- Result: **6 passed**

E2E tests:

1. `test_chat_multi_turn_reload_trace_and_narrow_viewport`
2. `test_chat_reload_during_running_recovers_before_completion`
3. `test_chat_ask_access_approve_once_repeat_and_deny`
4. `test_chat_ask_access_deny_allows_completion`
5. `test_chat_reload_waiting_approval_reconstructs_card`
6. `test_chat_service_restart_invalidates_waiting_approval`

## 5. Regression and Quality Gates

| Check | Command | Exit code | Result |
|---|---|---:|---|
| Repository/API recovery | `pytest tests/unit/chat/test_repository.py tests/integration/test_chat_api.py tests/e2e/test_chat_ui.py -q` | 0 | **86 passed**, 1 Starlette/httpx deprecation warning |
| Full pytest | `pytest -q` | 0 | **580 passed**, 1 warning |
| Ruff | `ruff check .` | 0 | All checks passed |
| mypy | `mypy src tests` | 0 | Success: 83 source files |
| pip check | `pip check` | 0 | No broken requirements (invalid dist warning for unrelated package name only) |
| Viewer test | `npm run test:viewer` | 0 | **9 passed** |
| Viewer typecheck | `npm run typecheck:viewer` | 0 | pass |
| Chat test | `npm run test:chat` | 0 | **44 passed** |
| Chat typecheck | `npm run typecheck:chat` | 0 | pass |
| Chat build | `npm run build:chat` | 0 | `/chat-static/` assets under `static/chat/` |
| npm ls | `npm ls --depth=0` | 0 | 14 top-level deps |
| git diff --check | `git diff --check` | 0 | pass (CRLF warnings only) |
| Staging | `git diff --cached --name-only` | 0 | empty |

Environment warning retained: `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated`.

## 6. Scope Audit

### Created

- `docs/task-evidence/phase-1d-task-12.md`
- `tests/e2e/test_chat_ui.py`
- `docs/learning-notes/04-chat-control-plane.md`

### Modified (Task 12 scope)

- `src/agent_foundations/chat/repository.py` — `get_conversation_state`
- `src/agent_foundations/chat/api.py` — `GET /conversations/{id}/state`, response models
- `tests/unit/chat/test_repository.py` — 9 recovery tests
- `tests/integration/test_chat_api.py` — 8 `/state` tests
- `web/chat/state/types.ts` — `PendingApprovalState`, `ConversationStateResponse`
- `web/chat/state/api.ts` — `getConversationState`
- `web/chat/state/reducer.ts` — `conversation.state.loaded`, session split
- `web/chat/App.tsx` — HTTP-before-SSE, reload/reconnect recovery
- `tests/chat/reducer.test.ts`, `tests/chat/app.test.tsx`
- `README.md`
- `docs/agent-plans/2026-07-20-agent-engineering-learning-design.md` (minimal status)
- `docs/agent-plans/2026-07-21-phase-1-implementation-plan.md` (minimal status)
- `docs/agent-plans/2026-08-02-phase-1d-interactive-chat-ui-plan.md` (Task 12 steps, Phase 1D definition)
- `src/agent_foundations/viewer/static/chat/` (build output)

### Not modified

- `package.json`, `package-lock.json`
- `models.py`, SQLite schema
- Task 11 evidence
- `AGENTS.md`, `CLAUDE.md`
- Runtime/Tool permission core

- Unrelated changes introduced: **no** (within Task 12 files)
- Existing user changes preserved: **yes**
- Secrets or generated artifacts in evidence: **no**
- Commit / push / PR / paid API / Phase 2: **no**

## 7. Gaps and Limitations

- **TDD verbatim Red:** tests were written before production code in executor session, but verbatim Red command output was not persisted to this file before context summary → process evidence **incomplete** for verbatim Red text.
- **Manual safety acceptance (plan Step 7):** plan Step 7 reverted to `[ ]`; checklist in §9.6 for reviewer/user — **not executed** as independent manual smoke.
- **Sensitive filename hard-deny in ask mode:** covered by unit/integration path policy tests from prior tasks; not re-run as dedicated manual check in Task 12.
- **Real model / real API:** not used.

## 8. Handoff Summary

- **Current implementation:** pass (fresh gates above)
- **TDD process evidence:** incomplete (verbatim Red unavailable in evidence file; test-first order followed)
- **Docs TDD:** not-applicable (content + gates)

### Recovery contract delivered

- `get_conversation_state()` — latest run by message sequence; pending approval only for `waiting_approval` + `pending`
- `GET /api/chat/conversations/{conversation_id}/state` — exact `{ latest_run, pending_approval }` shape
- Pending projection fields: `approval_id`, `conversation_id`, `session_id`, `tool_call_id`, `tool_name`, `canonical_path`, `operation=read`, `scope=external_exact_path`, `status=pending`, `requested_at`
- Frontend HTTP-before-SSE; `activeSessionId` vs `latestSessionId`; recovered approval card; terminal Trace link

### Recommended reviewer commands

```powershell
conda run -n agent-foundations python -m pytest tests/unit/chat/test_repository.py tests/integration/test_chat_api.py tests/e2e/test_chat_ui.py -q
conda run -n agent-foundations python -m pytest -q
npm run test:chat && npm run typecheck:chat && npm run build:chat
```

**Phase 1D implementation completed, awaiting independent review/user acceptance.** Phase 2 not started.

---

## 9. Reviewer Remediation (2026-08-07)

### 9.1 Scope

Fix four reviewer gaps: remove synthetic recovery ChatEvent; strict deny E2E; waiting-approval reload E2E; 390×844 viewport geometry. Revert plan Step 7 to unchecked.

### 9.2 Remediation Red — synthetic approval view model

- Time: `2026-08-07T23:43:56+08:00`
- Command: `npm run test:chat`
- Exit code: `1`
- Verbatim output (excerpt):

```text
FAIL tests/chat/activity.test.tsx > ApprovalCard > parses live SSE approval.requested into the approval view model
TypeError: parseApprovalFromEvent is not a function

FAIL tests/chat/activity.test.tsx > ApprovalCard > shows one-time external read approval details...
TypeError: Cannot read properties of undefined (reading 'data')

Test Files  1 failed | 2 passed (3)
Tests  4 failed | 41 passed (45)
```

- Command: `npm run typecheck:chat`
- Exit code: `2`
- Category: valid Red — `ApprovalCard` still required `ChatEvent`; tests updated to `approval: ActiveApproval` first

E2E deny/reload/geometry: characterization strengthening on top of existing implementation; strict deny assertion validated after production test edits (no false Red from final-answer fallback).

### 9.3 Remediation Green

- `web/chat/components/ApprovalCard.tsx` — accepts `ActiveApproval`; exports `parseApprovalFromEvent` for SSE timeline only
- `web/chat/components/MessageTimeline.tsx` — parses SSE `approval.requested` to view model
- `web/chat/App.tsx` — HTTP recovery passes `activeApproval` directly; removed `approvalEventFromActive`
- `web/chat/styles.css` — minimal narrow-viewport layout (composer stays in viewport)
- Tests: `activity.test.tsx`, `app.test.tsx`, `tests/e2e/test_chat_ui.py`

- Command: `npm run test:chat` → exit 0, **45 passed**
- Command: `npm run typecheck:chat` → exit 0
- Command: `npm run build:chat` → exit 0
- Command: `pytest tests/e2e/test_chat_ui.py -q` → exit 0, **6 passed**

Scope scan (exit 0, no matches):

```text
rg "approvalEventFromActive|recovered-approval-|1970-01-01T00:00:00Z|dangerouslySetInnerHTML" web/chat
```

### 9.4 Fresh remediation gates

| Check | Exit code | Result |
|---|---:|---|
| Chat test/typecheck/build | 0 | **45 passed** / pass / pass |
| E2E | 0 | **6 passed** |
| Repository/API + E2E | 0 | **86 passed** |
| Security regression | 0 | **60 passed** |
| Full pytest | 0 | **580 passed** |
| Ruff / mypy / pip check | 0 | pass |
| Viewer test/typecheck | 0 | **9 passed** / pass |
| git diff --check / staging | 0 | empty staging |

### 9.5 Evidence status after remediation

| Item | Status |
|---|---|
| **Current implementation** | pass |
| **Original Task 12 TDD evidence** | **incomplete** (verbatim Red still unavailable; unchanged) |
| **Remediation TDD evidence** | **complete** (synthetic-event Red saved above) |
| **Manual safety acceptance** | **not executed** — plan Step 7 remains `[ ]` |
| **Unverified** | Independent manual smoke (see checklist below) |

### 9.6 Manual safety acceptance checklist (for reviewer/user)

- [ ] Registry exposes only `list_directory`, `read_file`, `search_text`
- [ ] No write/Shell/Git/network tools
- [ ] Sensitive paths hard-denied in both permission modes
- [ ] External approval is exact path + read + single tool call only
- [ ] Deny returns structured `access_denied` to model (automated E2E covers FakeModel path)
- [ ] Browser reload restores same pending approval ID (automated E2E)
- [ ] Server restart invalidates old approval; run `interrupted` (automated E2E)
- [ ] `/state` returns no stack, API key, or full Trace payload (integration tests)
- [ ] Chat UI uses no `dangerouslySetInnerHTML` (scope scan clean)
- [ ] Service binds `127.0.0.1` only (CLI/code review + E2E localhost)

Automated tests cover several items; **do not treat E2E as substitute for independent manual acceptance.**

---

## 10. Reviewer Remediation — app.test.tsx race (2026-08-08)

### 10.1 Issue

`loads HTTP state before opening SSE when selecting a conversation` cleared `callOrder` after `findByRole("Runtime study")`, before initial conversation A HTTP recovery finished. Under load, A's calls landed after the clear, mixing A/B in assertions.

### 10.2 Executor reproduction

- Command: 30× `npx vitest run tests/chat/app.test.tsx -t "loads HTTP state before opening SSE when selecting a conversation"`
- Result: **failed on iteration 8** (exit 1); prior 7 passed
- Category: valid pre-fix flake (not recorded as original Task 12 Red)

### 10.3 Fix

`tests/chat/app.test.tsx` only:

1. `waitFor` A EventSource URL + full A `callOrder` triple
2. Save `initialEventSource = latestEventSource()`
3. Clear `callOrder`, click B
4. `waitFor` B EventSource; assert `initialEventSource.closed`, B-only `callOrder`, B source open

No production code changes.

### 10.4 Post-fix verification

| Check | Exit code | Result |
|---|---|---|
| Target test (single) | 0 | 1 passed |
| Target test × 20 | 0 | all passed |
| `npm run test:chat` × 5 | 0 | **45 passed** each |
| typecheck:chat / build:chat | 0 | pass |
| E2E | 0 | **6 passed** |
| Full pytest | 0 | **580 passed**, 1 Starlette/httpx warning |
| Ruff / mypy / pip check | 0 | pass |
| Viewer test / typecheck | 0 | **9 passed** / pass |
| git diff --check / staging | 0 | empty staging |

### 10.5 Status

| Item | Status |
|---|---|
| Current implementation | pass |
| Original Task 12 TDD evidence | **incomplete** (unchanged) |
| This fix TDD | characterization / race fix (not original Red) |
| Manual safety (Step 7) | **not executed** — plan Step 7 `[ ]` |
| Step 8 | `[ ]` |
