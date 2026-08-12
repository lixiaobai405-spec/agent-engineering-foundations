# Task Evidence: phase-2a-task-4

## 1. Identity

- Task ID: phase-2a-task-4
- Authoritative plan: `docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md` — Task 4
- Evidence status: completed
- TDD required: yes
- Depends on: `phase-2a-task-3` implementation accepted (user confirmed)
- Task 3 historical TDD evidence: incomplete (not modified in this Task)
- Started at: 2026-08-09

## 2. Pre-change Snapshot

- Branch: `main` @ `7b63584`
- Task 3: implementation accepted; Task 3 evidence not modified.
- Planning target paths: absent (fresh check confirmed).
- Existing user changes preserved: large Chat/Viewer/docs/evals dirty tree; no reset/restore/clean.
- Intended scope: create-only planning package and unit tests; no Runtime/Eval/CLI changes.
- Expected rollback: delete Task 4 new files after explicit user confirmation.

## 3. Red

- Recorded before production-code changes: yes
- Time: 2026-08-09
- Command: `conda run -n agent-foundations python -m pytest tests/unit/planning -q`
- Exit code: 1
- Relevant verbatim output:

```text
FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF                          [100%]
...
E       AssertionError: agent_foundations.planning package must exist
...
47 failed in 0.60s
```

- Expected failure category: assertion failure — planning package/models/controller missing
- Why this failure demonstrates the missing behavior: tests assert package existence and plan invariant/CAS behavior before any production code exists; pytest collection succeeded without import/environment errors.

## 4. Green

- Production files changed:
  - `src/agent_foundations/planning/__init__.py`
  - `src/agent_foundations/planning/models.py`
  - `src/agent_foundations/planning/controller.py`
- Command: `conda run -n agent-foundations python -m pytest tests/unit/planning -q`
- Exit code: 0
- Relevant verbatim output:

```text
47 passed in 0.17s
```

## 5. Regression and Quality Gates

| Check | Command | Exit code | Result |
|---|---|---:|---|
| Target tests | `conda run -n agent-foundations python -m pytest tests/unit/planning -q` | 0 | 47 passed |
| Ruff | `conda run -n agent-foundations python -m ruff check src/agent_foundations/planning tests/unit/planning` | 0 | All checks passed |
| mypy | `conda run -n agent-foundations python -m mypy src tests` | 0 | Success: no issues found in 104 source files |
| `git diff --check` | `git diff --check` | 0 | pass (LF/CRLF warnings on pre-existing user files only) |

### Verification summary

- CAS: stale `expected_version` raises `PlanVersionConflictError` without mutating state; success increments version by exactly 1.
- DAG: duplicate IDs, dangling deps, two-node and multi-node cycles rejected deterministically.
- Evidence gate: `COMPLETED` requires non-empty `evidence_refs`; controller rejects empty evidence on transition.
- Single in-progress: only one `IN_PROGRESS` step allowed.
- Replan: preserves completed steps/evidence; replaces pending/in-progress/blocked; `max_replans=2` allows two replans then `PlanReplanLimitError`; `last_replan_reason` stored on controller.

## 6. Scope Audit

- Final Task 4 created files:
  - `src/agent_foundations/planning/__init__.py`
  - `src/agent_foundations/planning/models.py`
  - `src/agent_foundations/planning/controller.py`
  - `tests/unit/planning/__init__.py`
  - `tests/unit/planning/test_models.py`
  - `tests/unit/planning/test_controller.py`
  - `docs/task-evidence/phase-2a-task-4.md`
  - `docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md` (Task 4 checkboxes only)
- Unrelated changes introduced: no
- Existing user changes preserved: yes
- Secrets or generated artifacts in Task scope: no
- Runtime/Eval/CLI/Tool/Trace/persistence wiring: no
- Task 5 not started; no commit/push/deploy

## 7. Gaps and Limitations

- Phase 1 full regression and Eval regression not run (out of Task 4 scoped gates)
- No execution fact journal or Tool fact validation (Task 5)
- In-memory only; no SQLite persistence (Phase 2B)

## 8. Handoff Summary

- Current verification status: pass
- TDD process evidence: complete
- Recommended reviewer commands:

```powershell
conda run -n agent-foundations python -m pytest tests/unit/planning -q
conda run -n agent-foundations python -m ruff check src/agent_foundations/planning tests/unit/planning
conda run -n agent-foundations python -m mypy src tests
```
