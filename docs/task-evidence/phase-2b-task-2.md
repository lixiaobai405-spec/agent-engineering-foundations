# Task Evidence: phase-2b-task-2

## 1. Identity

- Task ID: phase-2b-task-2
- Authoritative plan or task spec: `docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md` — Task 7
- Evidence status: completed
- TDD required: yes
- Depends on: phase-2b-task-1 user-accepted
- Started at: 2026-08-09

## 2. Pre-change Snapshot

- Branch or revision: `main` @ `7b6358478ba0a65db31fba49c7245c40524041ff`
- `git status --short`: large dirty worktree (Chat, Planning, Eval, Storage, Viewer, plans, evidence); preserved without reset/restore/clean
- Existing user changes that must be preserved: all pre-existing modified/untracked files
- Intended modification scope:
  - New: `src/agent_foundations/durable/*`, `tests/unit/durable/*`
  - Modify: `storage/migrations.py`, `chat/repository.py`, migration regression tests
- Expected rollback: delete durable module/tests; revert application migration wiring and test assertion updates only

## 3. Red

- Recorded before production-code changes: yes
- Time: 2026-08-09
- Test file and test name: `tests/unit/durable/test_models.py` (all), `tests/unit/durable/test_repository.py` (all)
- Command:

```text
conda run -n agent-foundations python -m pytest tests/unit/durable/test_models.py tests/unit/durable/test_repository.py -q
```

- Exit code: 1
- Relevant verbatim output:

```text
36 failed in 0.61s
AssertionError: agent_foundations.durable package must exist
assert None is not None
```

- Expected failure category: assertion failure — durable package/models/repository and v3 schema absent
- Why this failure demonstrates the missing behavior: pytest collected tests; failures are missing-module assertions, not import/collection errors

## 4. Green

- Production files changed:
  - `src/agent_foundations/durable/__init__.py`
  - `src/agent_foundations/durable/models.py`
  - `src/agent_foundations/durable/repository.py`
  - `src/agent_foundations/durable/schema.py`
  - `src/agent_foundations/storage/migrations.py` (`get_application_migrations`)
  - `src/agent_foundations/chat/repository.py` (application migration chain)
- Command:

```text
conda run -n agent-foundations python -m pytest tests/unit/durable/test_models.py tests/unit/durable/test_repository.py -q
```

- Exit code: 0
- Relevant verbatim output:

```text
36 passed in 0.52s
```

## 5. Regression and Quality Gates

| Check | Command | Exit code | Result |
|---|---|---:|---|
| Target tests | `pytest tests/unit/durable/test_models.py tests/unit/durable/test_repository.py -q` | 0 | 36 passed |
| Regression tests | `pytest tests/unit/storage tests/unit/durable tests/unit/chat/test_repository.py -q` | 0 | 115 passed |
| Ruff | `ruff check src/agent_foundations/durable ... tests/unit/durable ...` | 0 | pass |
| mypy | `mypy src tests` | 0 | 121 files |
| `git diff --check` | `git diff --check` | 0 | pass (CRLF warnings only) |

## 6. Scope Audit

- Final changed files (this Task):
  - `src/agent_foundations/durable/` (new)
  - `src/agent_foundations/storage/migrations.py`
  - `src/agent_foundations/chat/repository.py`
  - `tests/unit/durable/` (new)
  - `tests/unit/storage/test_database.py`
  - `tests/unit/chat/test_repository.py`
  - `docs/task-evidence/phase-2b-task-2.md`
  - `docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md` (Task 7 steps only)
- Unrelated changes introduced: no (scoped to durable + migration wiring)
- Existing user changes preserved: yes
- Secrets or generated artifacts detected: no
- Commit, push, deployment, paid API call, or next Task performed: no

## 7. Gaps and Limitations

- Checks not run and reasons: Phase 1 full regression baseline not required for single Task
- Environment warnings: CRLF line-ending warnings from `git diff --check`
- Process evidence gaps: none
- Remaining risks: none within Task scope; resume/lease/controller not implemented (by design)

## 8. Reviewer Fix Round (P1 cross-run ExecutionFact)

- Trigger: acceptance blocked — `save_checkpoint` did not verify `last_committed_tool_fact.session_id == run_id`
- Fix: `ExecutionFactRunMismatchError` raised before transaction write when fact session differs from `run_id`
- Test: `test_save_checkpoint_rejects_cross_run_execution_fact` — rejects cross-run fact; `state_version`, checkpoint count, and latest checkpoint unchanged
- Command:

```text
conda run -n agent-foundations python -m pytest tests/unit/durable/test_models.py tests/unit/durable/test_repository.py -q
conda run -n agent-foundations python -m pytest tests/unit/storage tests/unit/durable tests/unit/chat/test_repository.py -q
```

- Result: **37 passed** target; **116 passed** regression; Ruff/mypy pass
- Evidence status: **completed** (awaiting re-acceptance)

## 9. Handoff Summary

- Current verification status: pass
- TDD process evidence: complete
- Recommended reviewer commands:

```powershell
conda run -n agent-foundations python -m pytest tests/unit/durable/test_models.py tests/unit/durable/test_repository.py -q
conda run -n agent-foundations python -m pytest tests/unit/storage tests/unit/durable tests/unit/chat/test_repository.py -q
conda run -n agent-foundations python -m ruff check src/agent_foundations/durable src/agent_foundations/storage/migrations.py src/agent_foundations/chat/repository.py tests/unit/durable tests/unit/storage tests/unit/chat/test_repository.py
conda run -n agent-foundations python -m mypy src tests
git diff --check
```
