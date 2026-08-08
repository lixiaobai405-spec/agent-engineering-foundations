# Chat Compact Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. This side conversation executes inline because subagents are unavailable. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the vertically expensive Chat shell with the approved compact two-column desktop layout and mobile overlay Drawer while preserving existing message, approval, Trace-link, recovery, and scroll behavior.

**Architecture:** `App.tsx` owns responsive Sidebar state and the compact Conversation Toolbar. `ChatComposer.tsx` owns textarea growth. `styles.css` owns the 240px/56px desktop Sidebar, 50px Toolbar, 900px content width, sticky Composer, and mobile overlay Drawer.

**Tech Stack:** React 19, TypeScript, CSS, Vitest, Testing Library, Python Playwright E2E.

---

### Task 1: Responsive Sidebar and compact Toolbar

**Files:**
- Modify: `tests/chat/app.test.tsx`
- Modify: `web/chat/App.tsx`
- Modify: `web/chat/styles.css`

- [x] **Step 1: Write failing layout-state tests**

Add tests that assert first desktop render is expanded, toggling persists `collapsed` in `localStorage`, a stored desktop preference is restored, mobile starts closed regardless of desktop preference, the menu opens an overlay Drawer, and the oversized global Header is absent.

- [x] **Step 2: Run the focused tests and save Red**

Run `npm run test:chat -- --run tests/chat/app.test.tsx`. Expected: fail because the Sidebar toggle, persistent state, Drawer contract, and compact Toolbar do not exist.

- [x] **Step 3: Implement minimal shell behavior**

Add responsive Sidebar state, `aria-controls`/`aria-expanded`, overlay dismissal, compact title/project/permission Toolbar, and a details disclosure for the full project path. Keep Conversation and permission APIs unchanged.

- [x] **Step 4: Run focused Green**

Run the same focused command. Expected: all `app.test.tsx` tests pass.

### Task 2: Compact auto-growing Composer

**Files:**
- Create: `tests/chat/composer.test.tsx`
- Modify: `web/chat/components/ChatComposer.tsx`
- Modify: `web/chat/styles.css`

- [x] **Step 1: Write failing Composer tests**

Assert the textarea starts at one row, grows to its measured content height, caps at six-line height with internal vertical scrolling, resets after successful submit, and retains the accessible `Send message` name.

- [x] **Step 2: Run the focused Composer test and save Red**

Run `npm run test:chat -- --run tests/chat/composer.test.tsx`. Expected: fail because the current textarea is fixed at three rows and has no growth/cap logic.

- [x] **Step 3: Implement minimal Composer behavior**

Use a textarea ref and a small resize helper. Keep controlled input/submission behavior, disable rules, and error propagation unchanged.

- [x] **Step 4: Run focused Green**

Run the same focused command. Expected: all Composer tests pass.

### Task 3: Responsive regression and completion gates

**Files:**
- Modify only if needed: `tests/e2e/test_chat_ui.py`
- Update: `docs/task-evidence/chat-compact-layout.md`

- [x] **Step 1: Verify desktop and 390x844 behavior**

Reuse the existing Chat Playwright flow and assert no horizontal overflow. If existing selectors do not cover the new Drawer, add a focused assertion that mobile starts closed and opens via the menu.

- [x] **Step 2: Run frontend and E2E gates**

Run:

```powershell
npm run test:chat
npm run typecheck:chat
npm run build:chat
conda run -n agent-foundations python -m pytest tests/e2e/test_chat_ui.py -q
git diff --check
git status --short
```

- [x] **Step 3: Audit scope**

Confirm no backend/data/protocol files, real credentials, model calls, deployment, commit, push, or unrelated user changes were touched.
