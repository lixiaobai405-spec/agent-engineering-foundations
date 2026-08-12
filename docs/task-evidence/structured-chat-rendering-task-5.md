# Task Evidence: structured-chat-rendering-task-5

## Identity / Scope
- Task: `structured-chat-rendering-task-5`; TDD required; status complete.
- Branch: `main`; continuous execution and planned dependency installation authorized.
- Scope: frontend types/API/reducer/App and reducer/App tests. Existing changes preserved.

## Red
- Command: `npm run test:chat -- --run tests/chat/reducer.test.ts tests/chat/app.test.tsx --reporter=dot`
- Exit code: `1`.
- Result: `6 failed, 44 passed` across 2 files.
- Expected failures: the reducer still stored every SSE event as an activity and had no persisted-activity merge/error state; the App did not call the activities endpoint during recovery/catch-up, render the non-blocking retry, or refetch activities after terminal events.

## Green / Gates / Audit
- Target Green: `npm run test:chat -- --run tests/chat/reducer.test.ts tests/chat/app.test.tsx --reporter=dot` -> exit `0`; `50 passed`.
- Chat regression: `npm run test:chat -- --reporter=dot` -> exit `0`; `59 passed` across 4 files.
- Typecheck: `npm run typecheck:chat` -> exit `0`.
- Whitespace: `git diff --check` -> exit `0` (existing line-ending warnings only).
- Current verification status: `pass`; TDD process evidence: `complete`.
- Audit: activity recovery is non-blocking, initial HTTP state precedes SSE, catch-up runs immediately after connection, terminal activity wins over stale running state, and retry only reloads activities.
