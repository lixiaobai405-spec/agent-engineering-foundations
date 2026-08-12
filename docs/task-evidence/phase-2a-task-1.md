# Task Evidence: phase-2a-task-1

## 1. Identity

- Task ID: phase-2a-task-1
- Authoritative plan or task spec: `docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md` — Task 1：Eval 领域模型与版本化任务集
- Evidence status: completed
- TDD required: yes
- Started at: 2026-08-09

## 2. Pre-change Snapshot

- Branch or revision: `main` @ `7b63584`
- `git status --short`:
  - Modified (preserved user work): `AGENTS.md`, `CLAUDE.md`, `README.md`, Phase 1 plan docs, Chat backend/frontend/tests, `package.json`, `package-lock.json`, viewer static assets, etc.
  - Untracked (preserved user work): Phase 2 plan docs, structured-chat plans/evidence, 300+ chat build asset files, new chat web components/tests.
  - Task 1 target paths (`src/agent_foundations/evals/*`, `tests/unit/evals/*`, `tests/fixtures/evals/phase-1-tasks-v1.json`, `docs/task-evidence/phase-2a-task-1.md`): absent before this Task; no concurrent overlap detected.
- Existing user changes that must be preserved: all modified and untracked files listed above; no reset/restore/clean.
- Intended modification scope:
  - Create: `src/agent_foundations/evals/__init__.py`, `models.py`, `task_sets.py`
  - Create: `tests/unit/evals/__init__.py`, `test_models.py`, `test_task_sets.py`
  - Create: `tests/fixtures/evals/phase-1-tasks-v1.json`
  - Create/update: `docs/task-evidence/phase-2a-task-1.md`
  - Checkbox-only update: Task 1 Steps 1–7 in Phase 2 plan
- Expected rollback: delete only Task 1 newly created files after explicit user confirmation; do not use git reset/restore/clean.

## 3. Red

- Recorded before production-code changes: yes
- Time: 2026-08-09
- Test file and test name: all tests in `tests/unit/evals/` (9 tests)
- Command: `conda run -n agent-foundations python -m pytest tests/unit/evals -q`
- Exit code: 1
- Relevant verbatim output:

```text
FFFFFFFFF                                                                [100%]
================================== FAILURES ===================================
...
E       AssertionError: agent_foundations.evals package must exist
...
9 failed in 0.35s
```

- Expected failure category: assertion failure — Eval package/models/loader not implemented
- Why this failure demonstrates the missing behavior: pytest collected 9 tests normally; each failed because `agent_foundations.evals` package and target models/loader are absent, proving Eval domain behavior is not yet implemented.

## 4. Green

- Production files changed:
  - `src/agent_foundations/evals/__init__.py`
  - `src/agent_foundations/evals/models.py`
  - `src/agent_foundations/evals/task_sets.py`
  - `tests/fixtures/evals/phase-1-tasks-v1.json`
- Command: `conda run -n agent-foundations python -m pytest tests/unit/evals -q`
- Exit code: 0
- Relevant verbatim output:

```text
.........                                                                [100%]
9 passed in 0.20s
```

## 5. Regression and Quality Gates

| Check | Command | Exit code | Result |
|---|---|---:|---|
| Target tests | `conda run -n agent-foundations python -m pytest tests/unit/evals -q` | 0 | pass (9 passed) |
| Ruff | `conda run -n agent-foundations python -m ruff check src/agent_foundations/evals tests/unit/evals` | 0 | pass |
| mypy | `conda run -n agent-foundations python -m mypy src tests` | 0 | pass (90 files) |
| `git diff --check` | `git diff --check` | 0 | pass (LF/CRLF warnings only on pre-existing user files) |

mypy note: initial run failed on helper typing in `tests/unit/evals/test_models.py`; fixed with `TYPE_CHECKING` imports before final pass.

## 6. Scope Audit

- Final changed files:
  - `src/agent_foundations/evals/__init__.py` (new)
  - `src/agent_foundations/evals/models.py` (new)
  - `src/agent_foundations/evals/task_sets.py` (new)
  - `tests/unit/evals/__init__.py` (new)
  - `tests/unit/evals/test_models.py` (new)
  - `tests/unit/evals/test_task_sets.py` (new)
  - `tests/fixtures/evals/phase-1-tasks-v1.json` (new)
  - `docs/task-evidence/phase-2a-task-1.md` (new)
  - `docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md` (checkbox-only Task 1 Steps 1–7)
- Unrelated changes introduced: no
- Existing user changes preserved: yes (no reset/restore/clean; no edits to Chat/Viewer/Runtime)
- Secrets or generated artifacts detected: no (fixture uses `sample_project` relative paths and stable assertion values only)
- Commit, push, deployment, paid API call, or next Task performed: no

Scope audit commands:

```text
git status --short -- src/agent_foundations/evals tests/unit/evals tests/fixtures/evals docs/task-evidence/phase-2a-task-1.md docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md
?? docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md
?? docs/task-evidence/phase-2a-task-1.md
?? src/agent_foundations/evals/
?? tests/fixtures/evals/
?? tests/unit/evals/

git diff --check -- src/agent_foundations/evals tests/unit/evals tests/fixtures/evals docs/task-evidence/phase-2a-task-1.md
(exit 0, no whitespace errors in Task 1 paths)
```

## 7. Gaps and Limitations

- Checks not run and reasons:
  - Phase 1 full regression baseline not run (out of Task 1 scope per plan)
  - Frontend tests/build not run (not in Task 1 gates)
  - Eval Runner / CLI / baseline report not implemented (Task 2+)
- Environment warnings: `git diff --check` reports LF→CRLF warnings on pre-existing user-modified files only.
- Process evidence gaps: none
- Remaining risks:
  - Windows drive-relative paths (`C:foo`) rejected via `Path.drive`; reviewer may add extra cases if needed.
  - Fixture JSON validates structure only; scoring against Agent behavior belongs to Task 2.

## 8. Handoff Summary

- Current verification status: pass
- TDD process evidence: complete
- Recommended reviewer commands:

```powershell
conda run -n agent-foundations python -m pytest tests/unit/evals -q
conda run -n agent-foundations python -m ruff check src/agent_foundations/evals tests/unit/evals
conda run -n agent-foundations python -m mypy src tests
git diff --check
git status --short -- src/agent_foundations/evals tests/unit/evals tests/fixtures/evals docs/task-evidence/phase-2a-task-1.md
```
