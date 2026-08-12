# Task Evidence: phase-2a-task-2

## 1. Identity

- Task ID: phase-2a-task-2
- Authoritative plan or task spec: `docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md` — Task 2：Offline Eval Runner、评分与原子报告
- Evidence status: completed
- TDD required: yes
- Started at: 2026-08-09
- Depends on: `phase-2a-task-1` accepted (user confirmed)

## 2. Pre-change Snapshot

- Branch or revision: `main` @ `7b63584`
- Task 1 status: accepted; Task 1 files not modified.
- `git status --short`: large user dirty tree preserved; Task 1 eval files untracked under `src/agent_foundations/evals/`, `tests/unit/evals/`, `tests/fixtures/evals/`.
- Task 2 target paths before start: absent.
- Existing user changes preserved: yes; no reset/restore/clean.
- Intended modification scope: Task 2 create-only files per prompt.
- Expected rollback: delete Task 2 new files only after explicit user confirmation.

## 3. Red

- Recorded before production-code changes: yes
- Time: 2026-08-09
- Command: `conda run -n agent-foundations python -m pytest tests/unit/evals tests/integration/test_offline_eval.py -q`
- Exit code: 1
- Relevant verbatim output:

```text
...FFFFFFFFFFFFFFFFFFFFFF......FFFFFF                                    [100%]
...
E       AssertionError: agent_foundations.evals.reporting must exist
...
28 failed, 9 passed in 0.61s
```

- Task 1 passed: 9
- Task 2 failed: 28
- Expected failure category: assertion failure — runner/scoring/reporting modules missing
- Why this failure demonstrates the missing behavior: pytest collected all tests; Task 1 tests passed; Task 2 tests failed on missing `reporting`/`scoring`/`runner` modules and target behavior.

## 4. Green

- Production files changed:
  - `src/agent_foundations/evals/runner.py`
  - `src/agent_foundations/evals/scoring.py`
  - `src/agent_foundations/evals/reporting.py`
- Command: `conda run -n agent-foundations python -m pytest tests/unit/evals tests/integration/test_offline_eval.py -q`
- Exit code: 0
- Relevant verbatim output:

```text
.....................................                                    [100%]
37 passed in 0.23s
```

- Atomic replace rollback test: `test_write_report_atomic_preserves_existing_file_on_replace_failure` — monkeypatch `os.replace` raises OSError; original target preserved; no `*.tmp` leftover.

## 5. Regression and Quality Gates

| Check | Command | Exit code | Result |
|---|---|---:|---|
| Target tests | `conda run -n agent-foundations python -m pytest tests/unit/evals tests/integration/test_offline_eval.py -q` | 0 | pass (37 passed) |
| Provider/AgentLoop regression | `conda run -n agent-foundations python -m pytest tests/unit/providers tests/integration/test_agent_loop.py -q` | 0 | pass (34 passed) |
| Ruff | `conda run -n agent-foundations python -m ruff check src/agent_foundations/evals tests/unit/evals tests/integration/test_offline_eval.py` | 0 | pass |
| mypy | `conda run -n agent-foundations python -m mypy src tests` | 0 | pass (96 files) |
| `git diff --check` | `git diff --check` | 0 | pass (LF/CRLF warnings on pre-existing user files only) |

## 6. Scope Audit

- Final changed files:
  - `src/agent_foundations/evals/runner.py` (new)
  - `src/agent_foundations/evals/scoring.py` (new)
  - `src/agent_foundations/evals/reporting.py` (new)
  - `tests/unit/evals/test_scoring.py` (new)
  - `tests/unit/evals/test_reporting.py` (new)
  - `tests/integration/test_offline_eval.py` (new)
  - `docs/task-evidence/phase-2a-task-2.md` (new)
  - `docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md` (Task 2 Step 1–7 checkboxes only)
- Task 1 files unchanged: `models.py`, `task_sets.py`, `__init__.py`, Task 1 tests, fixture JSON
- Unrelated changes introduced: no
- Existing user changes preserved: yes
- Secrets or generated artifacts detected: no
- Commit, push, deployment, paid API call, or next Task performed: no

Scope audit commands:

```text
git status --short -- src/agent_foundations/evals tests/unit/evals tests/integration/test_offline_eval.py docs/task-evidence/phase-2a-task-2.md docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md
?? docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md
?? docs/task-evidence/phase-2a-task-2.md
?? src/agent_foundations/evals/
?? tests/integration/test_offline_eval.py
?? tests/unit/evals/
```

## 7. Gaps and Limitations

- Checks not run: Phase 1 full baseline, frontend tests, CLI/replay (Task 3 scope)
- Environment warnings: `git diff --check` LF→CRLF on pre-existing user files only
- Process evidence gaps: none
- Remaining risks: `runtime_revision="working-tree"` is explicit caller input only; canonical baseline report belongs to Task 3

## 9. Reviewer Fix (duration_ms finite validation)

- Issue: `duration_ms` used `mode="before"` validator; string inputs like `"nan"` / `"inf"` passed Pydantic coercion and leaked into reports or aggregation.
- Fix: single post-conversion validator on `duration_ms` using `math.isfinite()` after type coercion; removed `mode="before"`.
- Tests added: `test_observation_rejects_non_finite_duration_strings` for `nan`, `inf`, `-inf`, `NaN`, `INF`, `-INF` via `model_validate`.
- Verification after fix:

```text
conda run -n agent-foundations python -m pytest tests/unit/evals tests/integration/test_offline_eval.py -q
43 passed in 0.24s

conda run -n agent-foundations python -m pytest tests/unit/providers tests/integration/test_agent_loop.py -q
34 passed in 1.14s

conda run -n agent-foundations python -m ruff check src/agent_foundations/evals tests/unit/evals tests/integration/test_offline_eval.py
All checks passed!

conda run -n agent-foundations python -m mypy src tests
Success: no issues found in 96 source files
```

## 8. Handoff Summary

- Current verification status: pass
- TDD process evidence: complete
- Recommended reviewer commands:

```powershell
conda run -n agent-foundations python -m pytest tests/unit/evals tests/integration/test_offline_eval.py -q
conda run -n agent-foundations python -m pytest tests/unit/providers tests/integration/test_agent_loop.py -q
conda run -n agent-foundations python -m ruff check src/agent_foundations/evals tests/unit/evals tests/integration/test_offline_eval.py
conda run -n agent-foundations python -m mypy src tests
git diff --check
git status --short -- src/agent_foundations/evals tests/unit/evals tests/integration/test_offline_eval.py docs/task-evidence/phase-2a-task-2.md
```
