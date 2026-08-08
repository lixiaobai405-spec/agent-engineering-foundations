# Task Evidence: phase-1d-chat-message-first-ui

## 1. Identity

- Task ID: `phase-1d-chat-message-first-ui`
- Authoritative task spec: user-approved 2026-08-08 Chat message-first UI design in the current conversation
- Evidence status: complete
- TDD required: yes
- Started at: 2026-08-08T11:41:55+08:00

## 2. Pre-change Snapshot

- Branch or revision: `main`
- `git status --short`: existing tracked changes in project rules/plans/README/Python foundations plus large untracked Phase 1B-1D implementation, tests, frontend, and evidence directories
- Existing user changes that must be preserved: all pre-existing modified and untracked files; this Task will edit only the explicitly approved Chat UI/API projection scope and this evidence file
- Intended modification scope: conversation run listing projection; Chat frontend types/API/state/components/styles; focused unit/integration/E2E tests; generated Chat build only after Green
- Expected rollback: revert only this Task's hunks/files; do not reset, restore, clean, or affect other existing changes
- Secrets inspected or recorded: no; `.env` values will not be read or printed

## 3. Red

- Recorded before production-code changes: yes
- Time: 2026-08-08T11:45:28+08:00 to 2026-08-08T11:46:01+08:00
- Test files and test names:
  - `tests/chat/app.test.tsx`: message-only activity hiding, per-turn Trace links, paused auto-follow / jump-to-latest
  - `tests/unit/chat/test_repository.py::test_list_runs_returns_conversation_turns_in_message_order`
  - `tests/integration/test_chat_api.py::test_list_conversation_runs_returns_turn_mapping_and_stable_errors`
- Commands:
  - `npm run test:chat -- --run tests/chat/app.test.tsx`
  - `conda run -n agent-foundations python -m pytest tests/unit/chat/test_repository.py::test_list_runs_returns_conversation_turns_in_message_order tests/integration/test_chat_api.py::test_list_conversation_runs_returns_turn_mapping_and_stable_errors -q`
- Exit code:
  - frontend command: `1`
  - Python tool wrapper reported `0`, but pytest itself printed `2 failed` and Conda printed its failed-command error; treated as failed Red, not pass
- Relevant verbatim output:

```text
Frontend:
Test Files  1 failed (1)
Tests  3 failed | 18 passed (21)
Unable to find "Agent is working…"
Unable to find link "Open trace for this turn"
Unable to find button "Jump to latest"

Python:
FAILED test_list_runs_returns_conversation_turns_in_message_order
AttributeError: 'ConversationRepository' object has no attribute 'list_runs'
FAILED test_list_conversation_runs_returns_turn_mapping_and_stable_errors
assert 404 == 200
2 failed, 1 warning in 0.97s
```

- Expected failure category: current Repository/API lacks conversation run listing; current Chat renders Activity cards/UUID status, has only a latest-run Trace link, and lacks user-controlled auto-follow
- Why this failure demonstrates the missing behavior: every new assertion failed at the intended missing contract while the 18 existing App tests passed; backend failures were the absent method and absent route rather than environment/setup failures
- If unavailable, why it cannot be verified: n/a

## 4. Green

- Production files changed: Repository/API conversation-run projection; Chat API/state/App/MessageTimeline/styles; focused tests
- Commands:
  - `npm run test:chat -- --run tests/chat/app.test.tsx`
  - `conda run -n agent-foundations python -m pytest -q tests/unit/chat/test_repository.py::test_list_runs_returns_conversation_turns_in_message_order tests/integration/test_chat_api.py::test_list_conversation_runs_returns_turn_mapping_and_stable_errors`
- Exit code: `0` for both commands
- Relevant verbatim output:

```text
Test Files  1 passed (1)
Tests  21 passed (21)

..                                                                       [100%]
2 passed, 1 warning in 0.57s
```

## 5. Regression and Quality Gates

| Check | Command | Exit code | Result |
|---|---|---:|---|
| Target tests | focused Python tests + focused App tests | 0 | 2 Python and 21 App tests passed |
| Regression tests | `conda run -n agent-foundations python -m pytest -q` | 0 | 582 passed, 1 deprecation warning |
| Ruff | `conda run -n agent-foundations python -m ruff check .` | 0 | All checks passed |
| mypy | `conda run -n agent-foundations python -m mypy src tests` | 0 | 83 source files clean |
| Viewer frontend | `npm run test:viewer`; `npm run typecheck:viewer` | 0, 0 | 9 tests passed; typecheck passed |
| Chat frontend | `npm run test:chat`; `npm run typecheck:chat`; `npm run build:chat` | 0, 0, 0 | 48 tests passed; typecheck and production build passed |
| Package check | `conda run -n agent-foundations python -m pip check` | 0 | no broken requirements; existing invalid-distribution warning |
| `git diff --check` | `git diff --check` | 0 | no whitespace errors; existing LF-to-CRLF notices only |

## 6. Scope Audit

- Final changed files: `src/agent_foundations/chat/{repository.py,api.py}`; `web/chat/{App.tsx,styles.css,components/MessageTimeline.tsx,state/api.ts,state/reducer.ts}`; focused repository/API/App/E2E tests; generated Chat static build; this evidence
- Unrelated changes introduced: none identified
- Existing user changes preserved: yes; final `git status --short` retains the same broad pre-existing tracked/untracked categories and no reset/restore/clean was used
- Secrets or generated artifacts detected: generated Chat static bundle only; no `.env` values inspected or recorded
- Commit, push, deployment, paid API call, or next Task performed: no

## 7. Gaps and Limitations

- Checks not run and reasons: no real-model call; this UI/API change is fully covered by offline automated gates and the task does not require a paid smoke test
- Environment warnings: one Starlette/httpx deprecation warning; `pip check` reports an existing invalid-distribution warning for `~gent-engineering-foundations`; tracked files emit existing LF-to-CRLF notices
- Process evidence gaps: none at Task start
- Remaining risks: visual preference still requires user judgment; browser cache may require a hard refresh

## 8. Handoff Summary

- Current verification status: pass
- TDD process evidence: complete
- Completed at: 2026-08-08T12:06:04+08:00
- Local runtime check: existing idle Chat service restarted; `GET /chat` returned 200, the served bundle contains `Open trace for this turn` and `Jump to latest`, the new run-list route is present in OpenAPI, and the listener is bound only to `127.0.0.1:8765`
- Recommended reviewer commands: rerun the Phase 1 gates listed above and manually inspect `http://127.0.0.1:8765/chat`
