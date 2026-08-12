# Task Evidence: structured-chat-rendering-task-8

## Identity / Scope
- Task: `structured-chat-rendering-task-8`; TDD required; status complete.
- Branch: `main`; continuous execution authorized.
- Scope: integrate turn projection, safe Markdown, grouped tool activity, exact Trace links, and responsive containment into the live Chat timeline.

## Red
- Command: `npm run test:chat -- --run tests/chat/app.test.tsx tests/chat/activity.test.tsx tests/chat/markdown-message.test.tsx --reporter=dot`.
- Exit code: `1`; `4 failed, 35 passed` across 3 files.
- Expected failures: live transcript still rendered raw text, omitted grouped persisted activities, and linked to the legacy `/trace` route instead of the exact `/viewer?conversation_id=...&session_id=...` deep link.
- Supplemental Red after route audit: `npm run test:chat -- --run tests/chat/app.test.tsx --reporter=dot` -> exit `1`; `1 failed, 28 passed`. A newly posted run was not added to `runsByConversation`, so its live activity could not be placed in a turn while active.

## Green / Gates / Audit
- Focused Green: `npm run test:chat -- --run tests/chat/app.test.tsx tests/chat/activity.test.tsx tests/chat/markdown-message.test.tsx tests/chat/turns.test.ts --reporter=dot` -> exit `0`; `41 passed`.
- Full Chat regression: `npm run test:chat -- --reporter=dot` -> exit `0`; `67 passed` across 6 files.
- `npm run typecheck:chat` -> exit `0`.
- `npm run build:chat` -> exit `0`; 656 modules transformed. Build emitted a known >500 kB chunk warning for lazy Shiki language chunks, without failing.
- `git diff --check` -> exit `0` (existing line-ending warnings only).
- Generated asset audit: 312 files after build, 0 source maps. The additional hashed chunks are Shiki language/theme/runtime chunks produced by the intentional dynamic import; previous hashed entry assets are replaced by Vite as expected.
- Legacy audit: `ActivityCard` and `activity-card` references are `0`; the unused component was removed only after the search.
- Plan deviation: Task 8's isolated example used `/viewer`, but the higher-priority Phase 1D design, README, existing E2E, and mounted application route all define `/trace`. The implementation therefore keeps the working exact deep link `/trace?conversation_id=...&session_id=...`; `/viewer` would return 404.
- Supplemental Green: `npm run test:chat -- --run tests/chat/app.test.tsx --reporter=dot` -> exit `0`; `29 passed`. After posting, Chat now reloads both messages and runs, allowing live activity to appear in its active expanded turn.
- Current verification status: `pass`; TDD process evidence: `complete`.
