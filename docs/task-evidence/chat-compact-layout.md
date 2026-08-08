# Task Evidence: chat-compact-layout

## 1. Identity

- Task ID: `chat-compact-layout`
- Authoritative plan: `docs/superpowers/plans/2026-08-08-chat-compact-layout.md`
- Evidence status: complete
- TDD required: yes
- Started at: 2026-08-08 Asia/Shanghai

## 2. Pre-change Snapshot

- Branch: `main` with extensive pre-existing tracked and untracked user changes.
- Relevant existing files already modified before this task: `web/chat/App.tsx`, `web/chat/components/ChatComposer.tsx`, `web/chat/styles.css`, `tests/chat/app.test.tsx`, Chat E2E and Phase 1D implementation tree are untracked relative to HEAD.
- Existing changes must be preserved; no reset, restore, clean, broad staging, commit, or push.
- Intended scope: compact Chat shell, persistent desktop Sidebar, mobile Drawer, compact Toolbar, auto-growing Composer, and focused tests.
- Expected rollback: revert only files listed by this task and remove the new focused Composer test/evidence/plan if explicitly requested.

Initial `git status --short` included 11 tracked modifications and extensive untracked Phase 1B–1D implementation, including `web/`, `tests/chat/`, `tests/e2e/`, `docs/superpowers/`, and `docs/task-evidence/`.

## 3. Red

- Recorded before production-code changes: yes
- Test files: `tests/chat/app.test.tsx`, `tests/chat/composer.test.tsx`
- Command: `npm run test:chat -- tests/chat/app.test.tsx tests/chat/composer.test.tsx`
- Exit code: `1`
- Relevant verbatim output: `Test Files  2 failed (2)`; `Tests  6 failed | 22 passed (28)`
- Target-behavior failures: `Unable to find an accessible element with the role "button" and name "Collapse conversations"`; expected `rows="1"` but received `rows="3"`; expected inline `height: 96px; overflow-y: hidden`, but neither style existed.
- Expected failure category: approved compact layout behavior was absent. The failures were caused by missing Sidebar/Toolbar/Composer behavior, not syntax, import, environment, or unrelated failures.

## 4. Green

- Production files changed: `web/chat/App.tsx`, `web/chat/components/ChatComposer.tsx`, `web/chat/styles.css`
- Command: `npm run test:chat -- tests/chat/app.test.tsx tests/chat/composer.test.tsx`
- Exit code: `0`
- Relevant verbatim output: `Test Files  2 passed (2)`; `Tests  28 passed (28)`
- Implemented behavior: persistent desktop Sidebar, mobile overlay Drawer, compact Conversation Toolbar, details menu for the full project path, approximately 900px shared content width, and one-to-six-line auto-growing Composer.

## 5. Regression and Quality Gates

| Check | Command | Exit code | Result |
|---|---|---:|---|
| Target tests | `npm run test:chat -- tests/chat/app.test.tsx tests/chat/composer.test.tsx` | 0 | 28 passed |
| Chat regression | `npm run test:chat` | 0 | 4 files, 55 tests passed |
| Chat typecheck | `npm run typecheck:chat` | 0 | no TypeScript errors |
| Chat build | `npm run build:chat` | 0 | 24 modules transformed; production assets generated |
| Chat E2E focused debug | `conda run --no-capture-output -n agent-foundations python -m pytest tests/e2e/test_chat_ui.py::test_chat_multi_turn_reload_trace_and_narrow_viewport -q` | 0 | 1 passed in 17.70s |
| Chat E2E full | `conda run --no-capture-output -n agent-foundations python -m pytest tests/e2e/test_chat_ui.py -q` | 0 | 6 passed in 115.16s |
| `git diff --check` | `git diff --check` | 0 | no whitespace errors; pre-existing LF-to-CRLF warnings only |

## 6. Scope Audit

- Final source/test/docs files changed by this task: `web/chat/App.tsx`, `web/chat/components/ChatComposer.tsx`, `web/chat/styles.css`, `tests/chat/app.test.tsx`, `tests/chat/composer.test.tsx`, `tests/e2e/test_chat_ui.py`, this evidence file, and the task plan.
- Build refreshed: `src/agent_foundations/viewer/static/chat/index.html` and the hashed Chat JS/CSS assets.
- Existing user changes preserved: yes; no reset, restore, clean, broad stage, commit, or push was performed.
- Secrets detected: no. The browser QA used a temporary empty SQLite database and did not send a Chat message or invoke a model.
- Generated artifacts detected: expected Chat production bundle only. Temporary QA state was verified under `%TEMP%`, then its listener was stopped and the exact temporary directory was removed.
- Commit, push, deployment, paid API call, or next Task performed: no

## 7. Gaps and Limitations

- Checks not run and reasons: full Python/Viewer Phase 1 gates were outside this focused frontend task; no real-provider call was made.
- Environment warnings: `git diff --check` reported only pre-existing LF-to-CRLF conversion warnings for tracked files outside this task.
- Process evidence gaps: none for this task; valid Red was captured before production-code changes and Green/regression results were captured afterward.
- E2E debugging note: the first full E2E attempt found a Drawer transition timing assertion (`x=-309.6` while the 160ms transition was still running). The assertion was changed to condition-based `to_be_in_viewport()` waiting; the failed case then passed alone and the full suite passed.
- Browser visual QA: temporary `http://127.0.0.1:8766/chat`; desktop and 390x844 checked. At 390x844, `scrollWidth=390`, horizontal overflow was false, the mobile Drawer started closed and opened as an overlay, and no console warnings/errors were present.
- Remaining risks: visual QA covered Chromium only and one required mobile viewport; no real model response was sent during this task.

## 8. Handoff Summary

- Current verification status: pass
- TDD process evidence: complete
- Recommended reviewer commands: `npm run test:chat`; `npm run typecheck:chat`; `npm run build:chat`; `conda run --no-capture-output -n agent-foundations python -m pytest tests/e2e/test_chat_ui.py -q`; `git diff --check`
