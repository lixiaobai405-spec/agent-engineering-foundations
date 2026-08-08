# Trace Navigation Scroll Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. This side conversation executes inline because subagents are unavailable. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make expanded Trace navigation groups vertically scrollable while preserving the existing native click-to-toggle interaction and fixed sidebar controls.

**Architecture:** Keep the current HTML and TypeScript behavior. Reproduce the clipping with a real browser, then change only the navigation CSS so expanded groups retain their natural height and overflow belongs to `#trace-navigation`.

**Tech Stack:** CSS, Python Playwright E2E, npm Viewer build/typecheck.

---

### Task 1: Restore Trace navigation scrolling

**Files:**
- Modify: `tests/e2e/test_trace_viewer.py`
- Modify: `src/agent_foundations/viewer/static/styles.css`
- Update: `docs/task-evidence/phase-1d-trace-navigation-scroll.md`

- [x] **Step 1: Write the failing browser regression test**

Extend the isolated Trace Viewer E2E fixture with enough standalone JSONL sessions to overflow the navigation region. Assert that opening `Standalone runs` gives `scrollHeight > clientHeight`, a wheel action increases `scrollTop`, and native summary clicks still close and reopen the group.

- [x] **Step 2: Run the focused test to verify Red**

Run:

```powershell
conda run -n agent-foundations python -m pytest tests/e2e/test_trace_viewer.py -q
```

Expected: fail because `#trace-navigation.scrollHeight` equals `clientHeight` or `scrollTop` remains `0` after the wheel action.

- [x] **Step 3: Implement the minimal CSS fix**

Update `#trace-navigation` to a vertical flex scroll container, prevent `.navigation-group` from shrinking, and add a narrow dark-theme scrollbar. Do not add HTML controls or TypeScript state.

- [x] **Step 4: Verify focused Green**

Run the focused E2E again. Expected: the scroll and native toggle assertions pass.

- [x] **Step 5: Run regression gates**

Run:

```powershell
npm run test:viewer
npm run typecheck:viewer
conda run -n agent-foundations python -m pytest tests/integration/test_viewer_api.py tests/e2e/test_trace_viewer.py -q
git diff --check
```

Expected: all commands exit `0` with no failures.

- [x] **Step 6: Audit scope and record evidence**

Confirm the implementation changes only Viewer CSS and the focused E2E, does not touch backend/data behavior, and contains no sensitive values. Record exact Red/Green output and remaining manual acceptance in Task evidence. Do not commit or push without explicit authorization.
