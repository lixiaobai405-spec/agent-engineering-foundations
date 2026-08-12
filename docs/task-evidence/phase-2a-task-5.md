# Task Evidence: phase-2a-task-5

## 1. Identity

- Task ID: phase-2a-task-5
- Authoritative plan: `docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md` — Task 5
- Evidence status: completed
- TDD required: yes
- Depends on: `phase-2a-task-4` accepted (user confirmed)
- Phase 2A independent review: pending (Step 7 not executor scope)
- Started at: 2026-08-09

## 2. Pre-change Snapshot

- Branch or revision: `main` @ `7b6358478ba0a65db31fba49c7245c40524041ff`
- Task 1–4 status:
  - Task 1–2: accepted, evidence pass, TDD complete
  - Task 3: implementation accepted; historical TDD evidence **incomplete** (not modified)
  - Task 4: accepted, evidence pass, TDD complete (52 planning tests at acceptance)
- Large dirty worktree preserved (Chat/Viewer/docs/static assets); overlap on `cli/main.py`, eval fixtures, `evals/`, `planning/` from prior Tasks
- Intended modification scope: Task 5 authorized files only + conditional `evals/replay.py`, `tests/unit/evals/test_replay.py`; gate-required `tests/e2e/test_cli.py`
- Eval adapter: minimal tag-based `PlanningMode` selection in `replay.py` (plan file list gap)
- Expected rollback: delete Task 5 new files; revert Task 5 deltas in authorized modify paths only (user-confirmed; no reset/restore/clean)
- Phase 2A max permission: read-only Runtime only

Scoped `git status --short` at start:

```text
 M src/agent_foundations/cli/main.py
 M src/agent_foundations/runtime/agent.py
 M src/agent_foundations/runtime/loop.py
 M tests/integration/test_agent_loop.py
?? docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md
?? src/agent_foundations/evals/
?? src/agent_foundations/planning/
?? tests/fixtures/evals/
?? tests/unit/evals/
?? tests/unit/planning/
```

Task 5 new files confirmed absent at planner check; created in this Task.

## 3. Red

- Recorded before production-code changes: **unavailable**
- Time: not persisted verbatim before first production edit
- Test files: `tests/unit/planning/test_tools.py`, `tests/unit/planning/test_execution.py`, `tests/integration/test_agent_loop.py` (Task 5 extensions)
- Command (plan-specified):

```text
conda run -n agent-foundations python -m pytest tests/unit/planning tests/integration/test_agent_loop.py -q
```

- Exit code: not recorded verbatim before production implementation
- Relevant verbatim output:

```text
unavailable — Red command output was not written to evidence before Task 5 production modules
(tools.py, execution.py) and Runtime wiring were created in the same executor session.
```

- Expected failure category: assertion failure — missing `planning.tools` / `planning.execution`, missing PlanningMode/Trace/final-answer gate behavior
- Why unavailable: AGENTS.md forbids reconstructing Red after implementation; session did not flush Red output to this file before Green
- Task 4 regression expectation at Red: prior 47–52 planning tests should remain passing

## 4. Green

- Production files changed:
  - `src/agent_foundations/planning/tools.py` — three Planning Tools, `PlanningToolExecutor`, `build_planning_tools`
  - `src/agent_foundations/planning/execution.py` — journal, evidence validation, `PlanningRequiredError`
  - `src/agent_foundations/runtime/agent.py` — `PlanningMode`, `AgentConfig.planning_mode`
  - `src/agent_foundations/runtime/loop.py` — REQUIRED final-answer gate, allowlisted plan events
  - `src/agent_foundations/cli/main.py` — `--planning-mode`, registry/executor wiring
  - `src/agent_foundations/evals/replay.py` — minimal planning-aware replay adapter
  - Fixtures: `phase-1-tasks-v1.json`, `phase-1-responses-v1.json` → `phase-2a-v1`
- Command:

```text
conda run -n agent-foundations python -m pytest tests/unit/evals tests/unit/planning tests/integration/test_offline_eval.py tests/integration/test_agent_loop.py tests/e2e/test_cli.py -q
```

- Exit code: 0
- Relevant verbatim output:

```text
191 passed in 2.35s
```

Planning unit total: 73 collected (Task 4 + Task 5 tests).

## 5. Regression and Quality Gates

| Check | Command | Exit code | Result |
|---|---|---:|---|
| Phase 2A pytest gate | `conda run -n agent-foundations python -m pytest tests/unit/evals tests/unit/planning tests/integration/test_offline_eval.py tests/integration/test_agent_loop.py tests/e2e/test_cli.py -q` | 0 | 191 passed |
| Offline Eval CLI | `conda run -n agent-foundations agent-foundations evaluate --task-set tests/fixtures/evals/phase-1-tasks-v1.json --responses tests/fixtures/evals/phase-1-responses-v1.json --output .agent-foundations/evals/phase-2a.json --runtime-revision working-tree` | 0 | 8/8 tasks passed |
| Ruff | `conda run -n agent-foundations python -m ruff check src tests` | 0 | All checks passed |
| mypy | `conda run -n agent-foundations python -m mypy src tests` | 0 | Success: no issues in 108 files |
| pip check | `conda run -n agent-foundations python -m pip check` | 0 | No broken requirements (invalid dist warning only) |
| `git diff --check` | `git diff --check` | 0 | pass (CRLF warnings only) |
| eval output ignored | `git check-ignore -v .agent-foundations/evals/phase-2a.json` | 0 | `.gitignore:13:.agent-foundations/` |

### Eval report summary (`.agent-foundations/evals/phase-2a.json`)

- `dataset_version`: `phase-2a-v1`
- `response_fixture_version`: `phase-2a-v1`
- `task_set_sha256`: `47658c0d0ef0be1aa35913cf75b5ca079df5af86abd8f08b81e65fbb06b23559`
- `response_fixture_sha256`: `a8fe6d1b324dd2f98c0608cfabb1ee89d86762a2c6a9911cd68b204c50f725ba`
- `runtime_revision`: `working-tree`
- `tool_set`: `list_directory`, `read_file`, `search_text`, `set_plan`, `update_plan_step`, `replan`
- Summary: 8 tasks, 8 passed, 0 failed, success_rate 1.0
- Planning scenarios:
  - `phase2a-planning-required`: pass (`set_plan`, `search_text`, evidence-gated `update_plan_step`)
  - `phase2a-planning-disabled`: pass (no `set_plan`; `list_directory` only)
  - `phase2a-replan-limit`: pass (2 successful `replan`, 3rd `PlanReplanLimitError` observed, task completed)

### Phase 1 canonical baseline vs Phase 2A increment (`docs/eval-baselines/phase-1-v1.json` — not modified)

| Field | Phase 1 baseline (Task 3) | Phase 2A increment |
|---|---|---|
| dataset_version | `v1` | `phase-2a-v1` |
| response_fixture_version | `v1` | `phase-2a-v1` |
| task_set_sha256 | `ce74350e2292351a9ebcc59167fb292e15bee487fa3e5a382d198d623baaeefc` | `47658c0d0ef0be1aa35913cf75b5ca079df5af86abd8f08b81e65fbb06b23559` |
| response_fixture_sha256 | `80ce345c80c853605e9e2f1c43f2b7849b563bb5b0aab4fc5c9ac3fb3e2a3bed` | `a8fe6d1b324dd2f98c0608cfabb1ee89d86762a2c6a9911cd68b204c50f725ba` |
| total_tasks | 5 | 8 |
| passed_tasks | 5 | 8 |
| tool_set | 3 readonly | 3 readonly + 3 planning |

No network, credentials, or external project reads during Eval.

## 6. Scope Audit

Final Task 5 changed files (scoped `git status --short`):

```text
 M src/agent_foundations/cli/main.py
 M src/agent_foundations/runtime/agent.py
 M src/agent_foundations/runtime/loop.py
 M tests/integration/test_agent_loop.py
 M tests/e2e/test_cli.py
?? docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md
?? docs/task-evidence/phase-2a-task-5.md
?? src/agent_foundations/evals/replay.py
?? src/agent_foundations/planning/
?? tests/fixtures/evals/phase-1-responses-v1.json
?? tests/fixtures/evals/phase-1-tasks-v1.json
?? tests/unit/evals/test_replay.py
?? tests/unit/planning/
```

- Unrelated changes introduced in Task 5 scope files: no (gate-required `test_cli.py` only)
- Task 1–4 evidence and `docs/eval-baselines/phase-1-v1.json`: not modified
- Chat, Viewer, Approval, SQLite: not modified in Task 5 work
- Registry tools: readonly filesystem + planning control tools only; no write/shell/git/network
- `PlanningMode.DISABLED` default preserved
- Secrets/generated artifacts in Task 5 scope: no
- Commit, push, deployment, paid API: not performed

## 7. Gaps and Limitations

- **TDD Red verbatim**: unavailable before production (see §3)
- Environment: `pip check` warns on invalid `~gent-engineering-foundations` dist (pre-existing)
- Phase 2A full regression baseline (Phase 1 npm viewer/chat): not run (out of Task 5 gate list)
- Phase 2A independent reviewer verification: not performed (executor scope)

## 9. Reviewer Fix Round (2026-08-09)

**Findings addressed:**

1. **P1 blank Schema → ValidationError crash**: `SetPlanTool` / `ReplanTool` now catch `ValidationError` and return `ToolResult(success=False, error_code="ValidationError")` instead of propagating to AgentLoop `Unexpected tool failure`.
2. **P1 ExecutionFact tampering**: `ExecutionFact` frozen (`ConfigDict(frozen=True)`); journal stores `fact.model_copy()` so caller-side mutation cannot flip recorded failure facts.

**Regression tests added:**

- `test_set_plan_blank_goal_returns_failed_tool_result`
- `test_set_plan_blank_step_description_returns_failed_tool_result`
- `test_replan_blank_replacement_step_returns_failed_tool_result`
- `test_execution_fact_is_frozen`
- `test_journal_rejects_evidence_when_failed_fact_reference_is_tampered`
- `test_journal_stored_fact_isolated_from_caller_model_copy`
- `test_set_plan_blank_goal_emits_tool_call_failed_not_unexpected_failure`

**Re-verification (fix round):**

| Check | Exit code | Result |
|---|---:|---|
| `pytest tests/unit/evals tests/unit/planning tests/integration/test_offline_eval.py tests/integration/test_agent_loop.py tests/e2e/test_cli.py -q` | 0 | 198 passed |
| Offline Eval CLI | 0 | 8/8 passed |
| Ruff | 0 | pass |
| mypy | 0 | pass |
| pip check | 0 | pass |
| `git diff --check` | 0 | pass |

## 8. Handoff Summary

- Current verification status: **pass**
- TDD process evidence: **incomplete** (Red unavailable)
- Phase 2A independent review: **pending**
- Recommended reviewer commands:

```powershell
conda run -n agent-foundations python -m pytest tests/unit/evals tests/unit/planning tests/integration/test_offline_eval.py tests/integration/test_agent_loop.py tests/e2e/test_cli.py -q
conda run -n agent-foundations agent-foundations evaluate --task-set tests/fixtures/evals/phase-1-tasks-v1.json --responses tests/fixtures/evals/phase-1-responses-v1.json --output .agent-foundations/evals/phase-2a.json --runtime-revision working-tree
conda run -n agent-foundations python -m ruff check src tests
conda run -n agent-foundations python -m mypy src tests
```
