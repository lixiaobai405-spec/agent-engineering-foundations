# Trace Viewer Conversation Navigation Implementation Plan

> **For executor:** Follow this plan one task at a time with TDD evidence in `docs/task-evidence/phase-1d-trace-navigation-improvement.md`. Do not commit without explicit user authorization.

**Goal:** Replace the Trace Viewer’s opaque flat session selector with a human-readable `Conversation -> Turn/Session` navigation while preserving standalone CLI traces, legacy APIs, and exact Chat deep links.

**Architecture:** Add a read-only aggregation layer beside the existing Trace API. It joins Chat SQLite metadata with JSONL trace availability by `session_id`, while keeping SQLite as the conversation index and JSONL as the detailed trace source. The native TypeScript Viewer renders this projection and continues loading trace detail from the existing `/api/sessions/{session_id}` endpoint.

**Tech Stack:** FastAPI, Pydantic, SQLite repository, JSONL trace replay, native TypeScript, Vitest/Node tests, Playwright.

---

## Task 1: Add the navigation API contract

**Files:**
- Modify: `tests/integration/test_viewer_api.py`
- Create: `src/agent_foundations/viewer/navigation.py`
- Modify: `src/agent_foundations/viewer/app.py`

1. Add an integration test proving `GET /api/trace-navigation` groups Chat runs beneath conversations, retains missing-trace turns with `trace_available=false`, and places unassociated JSONL traces beneath `standalone_runs`.
2. Run the targeted test and save the expected missing-endpoint Red.
3. Implement typed response models and a read-only aggregator using `ConversationRepository`, `trace_dir`, and exact `session_id` matching.
4. Register the route in both trace-only and Chat-enabled applications without changing `/api/sessions`.
5. Run the targeted tests to Green.

## Task 2: Replace the flat Viewer selector

**Files:**
- Modify: `src/agent_foundations/viewer/static/index.html`
- Modify: `src/agent_foundations/viewer/static/app.ts`
- Modify: `src/agent_foundations/viewer/static/state.ts`
- Modify: `src/agent_foundations/viewer/static/styles.css`
- Modify: `tests/viewer/session-query.test.mjs`
- Modify: `tests/e2e/test_trace_viewer.py`

1. Add browser/pure-state tests for conversation groups, turn labels, default-collapsed standalone runs, exact deep-link selection, and unavailable trace disabling.
2. Run the focused test to capture a behavior-level Red.
3. Render conversation and turn navigation with time, user-message preview, status, short ID, and an optional full-ID detail/copy control.
4. Keep `conversation_id + session_id` deep links exact; retain `session_id`-only links for standalone and backward compatibility.
5. Preserve live-event mode and the existing detail/timeline rendering.
6. Run Viewer unit and E2E tests to Green.

## Task 3: Regression and scope verification

**Files:**
- Update: `docs/task-evidence/phase-1d-trace-navigation-improvement.md`

1. Run focused Python tests and Viewer tests.
2. Run Ruff and mypy for affected Python modules/tests.
3. Run Viewer typecheck/build plus Chat tests/typecheck/build because Chat deep links depend on this Viewer contract.
4. Run `git diff --check`, inspect `git status --short`, and audit the diff for unrelated edits and sensitive data.
5. Record exact fresh results and any unexecuted manual checks in Task evidence.
