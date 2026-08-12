# Task Evidence: structured-chat-rendering-task-3

## 1. Identity

- Task ID: `structured-chat-rendering-task-3`
- Authoritative plan: structured Chat rendering plan, Task 3
- Evidence status: completed
- TDD required: yes
- Started at: 2026-08-08

## 2. Pre-change Snapshot

- Branch: `main`, direct execution authorized.
- Existing user changes: preserved as recorded in Task 1; Task 1-2 changes are active and verified.
- Intended scope: `events.py`, `runner.py`, focused event/runner tests, this evidence.
- Expected rollback: remove Task 3 projection/sink/wiring changes only.

## 3. Red

- Recorded before production-code changes: yes
- Command / exit / output: `conda run -n agent-foundations python -m pytest tests/unit/chat/test_events.py tests/unit/chat/test_runner.py -q`; exit 1; 6 failed, 19 passed, 23 errors.
- Expected failure: source IDs, semantic summaries, durable persistence, and best-effort isolation absent.
- Observed reason: projector and sink reject the new `project_root`/`repository` contracts, and the runner persists zero activity rows.

## 4. Green

- Production files / command / exit / output: `events.py`, `runner.py`; target command exit 0, 48 passed in 0.86s.

## 5. Regression and Quality Gates

| Check | Command | Exit code | Result |
|---|---|---:|---|
| Target tests | focused events + runner | 0 | 48 passed |
| Regression | all Chat unit tests | 0 | 204 passed |
| Ruff | focused Task 3 | 0 | Passed after import-order correction |
| mypy | focused Task 3 | 0 | No issues in 4 source files |
| diff | `git diff --check` | 0 | Passed |

## 6. Scope Audit

- Final files: `events.py`, `runner.py`, event/runner tests, this evidence. No unrelated changes, secrets, generated artifacts, commit, push, paid call, or deployment.

## 7. Gaps and Limitations

- Remaining risk: HTTP recovery and frontend consumption remain Tasks 4-8.

## 8. Handoff Summary

- Current verification: pass
- TDD evidence: complete
