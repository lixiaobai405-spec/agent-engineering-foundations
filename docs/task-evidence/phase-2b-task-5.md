# Task Evidence: phase-2b-task-5

## 1. Identity

- Task ID: phase-2b-task-5
- Authoritative plan or task spec: `docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md` — Task 10
- Evidence status: completed
- TDD required: yes
- Depends on: phase-2b-task-4 user-accepted
- Started at: 2026-08-11

## 2. Pre-change Snapshot

- Branch: `main` (dirty worktree; large user changes preserved)
- Intended scope: effects ledger v5 migration, idempotent executor, fault injection, tests
- Rollback: delete effects.py/faults.py and new tests; revert v5 migration and executor wrapper only

## 3. Red

- Recorded before production-code changes: yes
- Command:

```text
conda run -n agent-foundations python -m pytest tests/unit/durable/test_effects.py tests/integration/test_idempotent_tool_execution.py -q
```

- Exit code: 1
- Relevant verbatim output:

```text
15 failed, 1 passed
FAILED test_effect_status_has_six_stable_values ... find_spec effects is None
FAILED test_classifier_none_skips_ledger ... ImportError: IdempotentToolCallExecutor
```

- Expected failure category: assertion failure / missing module behavior (ledger, v5, idempotent executor)

## 4. Green

- Command:

```text
conda run -n agent-foundations python -m pytest tests/unit/durable/test_effects.py tests/integration/test_idempotent_tool_execution.py -q
```

- Exit code: 0
- Result: 28 passed

## 5. Regression and Quality Gates

| Check | Command | Exit code | Result |
|---|---|---:|---|
| Durable/Runtime/AgentLoop/Chat regression | `conda run -n agent-foundations python -m pytest tests/unit/storage tests/unit/durable tests/unit/runtime tests/integration/test_agent_loop.py tests/integration/test_idempotent_tool_execution.py tests/unit/chat/test_repository.py tests/unit/chat/test_runner.py -q` | 0 | 344 passed |
| Ruff | `conda run -n agent-foundations python -m ruff check src/agent_foundations/durable src/agent_foundations/storage/migrations.py src/agent_foundations/runtime/tool_execution.py tests/unit/durable tests/unit/storage tests/integration/test_idempotent_tool_execution.py tests/integration/test_agent_loop.py tests/unit/chat/test_repository.py tests/unit/chat/test_runner.py` | 0 | pass |
| mypy | `conda run -n agent-foundations python -m mypy src tests` | 0 | pass |
| git diff --check | `git diff --check` | 0 | pass (LF/CRLF warnings only) |

## 6. Scope Audit

- v5 `side_effects` migration added; `user_version` 5; v6 rejected in tests
- `SideEffectLedger` CAS transitions via `BEGIN IMMEDIATE`; no full arguments in DB
- `IdempotentToolCallExecutor` with classifier, keyed lock, fault injection, observer sanitization
- Crash recovery: BEFORE/AFTER_INTENT re-execute once; AFTER_CLAIM/AFTER_EXECUTE → UNKNOWN; AFTER_COMMIT returns saved result
- COMMITTED/FAILED dedup; UNKNOWN/ROLLED_BACK require `EffectResolutionRequiredError`
- No Patch/command/write Tools, reconcile API, or Task 11 scope
- Task 9 evidence untouched; preserved user dirty worktree

## 7. Handoff Summary

- Task 10 complete; ready for reviewer independent verification
- Recommended reviewer commands: target pytest + regression table above
- Next authorized Task: `phase-2b-task-6` (Task 11) after user acceptance — do not start without prompt

## 8. Reviewer Fix Round (P1 terminal result validation)

- Issue: illegal `COMMITTED`/`FAILED` transitions could commit DB row then fail Pydantic in `_row_to_side_effect()`, corrupting ledger
- Fix: `_validate_pending_side_effect_record()` runs before `UPDATE`; explicit `result.success` checks for terminal transitions
- Tests added: `test_invalid_committed_result_leaves_executing`, `test_invalid_failed_result_leaves_executing`
- Verification:

```text
conda run -n agent-foundations python -m pytest tests/unit/durable/test_effects.py tests/integration/test_idempotent_tool_execution.py -q
→ 30 passed

conda run -n agent-foundations python -m pytest tests/unit/storage tests/unit/durable tests/unit/runtime tests/integration/test_agent_loop.py tests/integration/test_idempotent_tool_execution.py tests/unit/chat/test_repository.py tests/unit/chat/test_runner.py -q
→ 346 passed

mypy src tests → pass
ruff (repository + test_effects) → pass
```
