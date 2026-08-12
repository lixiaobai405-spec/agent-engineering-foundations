# Task Evidence: structured-chat-rendering-task-6

## Identity / Scope
- Task: `structured-chat-rendering-task-6`; TDD required; status complete.
- Branch: `main`; continuous execution authorized.
- Scope: deterministic turn projection, accessible per-run tool group, nested/fallback approval, and focused tests.

## Red
- Command: `npm run test:chat -- --run tests/chat/turns.test.ts tests/chat/activity.test.tsx --reporter=dot`.
- Exit code: `1`; 2 suites failed before collecting tests because `state/turns` and `ToolActivityGroup` did not exist.
- Expected cause: deterministic turn projection and the accessible per-run activity group had not been implemented.

## Green / Gates / Audit
- Target Green: `npm run test:chat -- --run tests/chat/turns.test.ts tests/chat/activity.test.tsx --reporter=dot` -> exit `0`; `11 passed`.
- Typecheck: `npm run typecheck:chat` -> exit `0`.
- Whitespace: `git diff --check` -> exit `0` (existing line-ending warnings only).
- Current verification status: `pass`; TDD process evidence: `complete`.
- Accessibility/scope audit: native button provides keyboard activation and `aria-expanded`; textual statuses do not rely on color; rows contain only projected summaries and timing; approval nests by exact `tool_call_id` with one fallback.
