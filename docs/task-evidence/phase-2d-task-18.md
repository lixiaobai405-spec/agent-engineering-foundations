# Task Evidence: phase-2d-task-18

## 1. Identity

- Task ID: `phase-2d-task-18`
- Authoritative plan or task spec: `docs/agent-plans/2026-08-29-phase-2-reliability-follow-on-plan.md` Task 34 plus the user-confirmed executor prompt
- Evidence status: user-accepted 2026-09-04 (targeted verification); Task 25 Step 10/11 **not claimed**; Phase 2 complete **not claimed**
- TDD required: yes
- Started at: 2026-08-29 (Asia/Shanghai)

## 2. Pre-change Snapshot

- Branch or revision: `codex/phase-2-next` at `14ece4e` (not `main`)
- `git status --short`: dirty working tree already present (Phase 2A–2D, Chat hashed assets, Dockerfiles, evidence, Task 30–33 files). Exact listing is long.
- Existing user changes that must be preserved: all pre-existing modified and untracked files at Task start. Do not `restore`/`reset`/`clean`.
- Intended modification scope: `coding_budget.py` + `AgentConfig.coding_budget` + loop intercept after recovery + Chat factory production constants. Do not change default `max_steps=10`, `RetryPolicy.max_attempts`, Policy/Approval/whitelist/schema v11, Task 31 recovery mapping, Task 30 CRLF P2, reviewer P3, Docker, or Task 25 Step 10/11.
- Expected rollback: revert only this Task’s files; do not revert the pre-existing dirty tree.
- Interpreter: Windows `conda run` can crash pytest with GBK. Commands use `$env:PYTHONIOENCODING='utf-8'`. This does not shrink the verification contract.

## 3. Measurement (FakeModel, before locking production constants)

Constants were chosen from scripted FakeModel success paths (command_feedback ≈ 7 `ModelResponse`s plus injected `read_command_output`; phase2 coding ≈ 10 completions). Docker ignore omitted because `tests/eval/test_docker_sandbox_e2e.py` does not exist; `pytest -m docker` was not run.

- Command: `$env:PYTHONIOENCODING='utf-8'; conda run -n agent-foundations python -m pytest tests/integration/test_command_feedback_agent_flow.py tests/integration/test_phase2_coding_agent.py tests/integration/test_offline_eval.py tests/unit/evals -q --tb=line`
- Exit code: 0 (re-run after wiring still 0; Chat factory now carries layered budget and did not clip these paths)
- Relevant verbatim output:

```text
61 passed, 1 skipped, 10 warnings in 5.52s
```

- Observed from the scripted tests (not from pytest `-q` counts):
  - `test_command_feedback_agent_flow.py`: 7 scripted `ModelResponse`s. `FeedbackThenScriptProvider` injects `read_command_output` after a failing `run_command`. Success argv: `pytest tests` twice and `pytest NODE_ID` twice. Failed-patch repairs on the success path: 0 (one successful `validate_patch`, one successful `apply_patch`). Artifact reads: about 2.
  - `test_phase2_coding_agent.py`: 10 scripted completions (`set_plan`, `read_file`, two `run_command`, `validate_patch`, `apply_patch`, two more `run_command`, `git_diff`, final answer). Same argv twice for `tests` and twice for `NODE_ID`. Completions ≈ 7–10, well under Chat `max_steps=24`.
- Selected Chat constants and reason (all inside ceilings; each layered cap strictly `< CHAT_MAX_STEPS`):

| Constant | Ceiling | Selected | Reason |
|---|---|---:|---|
| `CHAT_MAX_STEPS` | 24–32 | 24 | Keep current Chat value; success paths ≈ 10 completions |
| `CHAT_MAX_PATCH_REPAIRS` | 3–8 | 4 | Success uses 0 failed repairs / 1 validate; room for a few retries |
| `CHAT_MAX_SAME_ARGV_COMMAND_RUNS` | 2–4 | 3 | Success uses 2 of the same argv; one extra retry |
| `CHAT_MAX_ARTIFACT_READS` | 6–16 | 8 | Feedback path injects ≈ 2 reads; headroom without approaching `max_steps` |

TDD injects small limits (`repairs=2`, `argv_runs=2`, `artifact_reads=2`, `max_steps=4`), not these production numbers.

## 4. Red

- Recorded before production-code changes: yes
- Time: 2026-08-29 (Asia/Shanghai), after `tests/unit/runtime/test_coding_budget.py` and before `coding_budget.py` / `AgentConfig.coding_budget` / loop intercept / Chat factory constants
- Test file and test name: `tests/unit/runtime/test_coding_budget.py` (9 failed, 1 passed: default `AgentConfig` already has `max_steps==10` and no `coding_budget`)
- Command: `$env:PYTHONIOENCODING='utf-8'; conda run -n agent-foundations python -m pytest tests/unit/runtime/test_coding_budget.py -q --tb=short`
- Exit code: 1
- Relevant verbatim output:

```text
.FFFFFFFFF                                                               [100%]
================================== FAILURES ===================================
_________ test_evaluate_budget_blocks_third_failed_patch_on_same_path _________
tests\unit\runtime\test_coding_budget.py:111: in test_evaluate_budget_blocks_third_failed_patch_on_same_path
    module = _budget_module()
tests\unit\runtime\test_coding_budget.py:44: in _budget_module
    assert spec is not None
E   assert None is not None
________ test_evaluate_budget_ignores_recovery_intercepts_for_repairs _________
E   assert None is not None
_____________ test_evaluate_budget_is_per_path_for_patch_repairs ______________
E   assert None is not None
___________ test_evaluate_budget_blocks_third_same_argv_run_command ___________
E   assert None is not None
_______________ test_evaluate_budget_blocks_third_artifact_read _______________
E   assert None is not None
____________ test_loop_does_not_execute_over_budget_validate_patch ____________
    assert "coding_budget" in AgentConfig.__dataclass_fields__
E   AssertionError: assert 'coding_budget' in {'max_steps': Field(...), ...}
_____________ test_loop_does_not_execute_over_budget_run_command ______________
E   AssertionError: assert 'coding_budget' in AgentConfig.__dataclass_fields__
____________ test_loop_does_not_execute_over_budget_artifact_read _____________
E   AssertionError: assert 'coding_budget' in AgentConfig.__dataclass_fields__
_________ test_chat_runtime_factory_installs_production_coding_budget _________
E   assert None is not None
9 failed, 1 passed in 1.70s
```

- Expected failure category: missing `agent_foundations.runtime.coding_budget` module; missing `AgentConfig.coding_budget` field. Tests themselves collected and ran (not syntax/import collection errors).
- Why this failure demonstrates the missing behavior: no layered `evaluate_budget`, no Chat production constants, no loop intercept. Default `test_agent_config_default_has_no_layered_budget` already passed (`max_steps==10`, no budget, `RetryPolicy.max_attempts==3`).
- If unavailable, why it cannot be verified:

## 5. Green

- Production files changed:
  - `src/agent_foundations/runtime/coding_budget.py` (new: `evaluate_budget`, Chat constants, `CodingBudgetLimits`)
  - `src/agent_foundations/runtime/agent.py` (optional `coding_budget`; default `None`; default `max_steps` remains 10)
  - `src/agent_foundations/runtime/loop.py` (budget after recovery allows, before executor)
  - `src/agent_foundations/cli/main.py` (Chat `runtime_factory` passes `CHAT_MAX_STEPS` + `CHAT_CODING_BUDGET`; CLI `build_runtime()` unchanged)
- Command: `$env:PYTHONIOENCODING='utf-8'; conda run -n agent-foundations python -m pytest tests/unit/runtime/test_coding_budget.py -q --tb=short`
- Exit code: 0
- Relevant verbatim output:

```text
..........                                                               [100%]
10 passed in 1.48s
```

## 6. Regression and Quality Gates

| Check | Command | Exit code | Result |
|---|---|---:|---|
| Target tests | `$env:PYTHONIOENCODING='utf-8'; conda run -n agent-foundations python -m pytest tests/unit/runtime/test_coding_budget.py -q` | 0 | 10 passed |
| Regression tests | `$env:PYTHONIOENCODING='utf-8'; conda run -n agent-foundations python -m pytest tests/unit/runtime tests/integration/test_agent_loop.py tests/integration/test_command_feedback_agent_flow.py tests/integration/test_phase2_coding_agent.py tests/integration/test_offline_eval.py tests/unit/evals -q` | 0 | 249 passed, 1 skipped (**targeted verification**, not full suite) |
| Ruff | `$env:PYTHONIOENCODING='utf-8'; conda run -n agent-foundations python -m ruff check src/agent_foundations/runtime/coding_budget.py src/agent_foundations/runtime/agent.py src/agent_foundations/runtime/loop.py src/agent_foundations/cli/main.py tests/unit/runtime/test_coding_budget.py` | 0 | All checks passed |
| mypy | `$env:PYTHONIOENCODING='utf-8'; conda run -n agent-foundations python -m mypy src/agent_foundations/runtime/coding_budget.py src/agent_foundations/runtime/agent.py src/agent_foundations/runtime/loop.py src/agent_foundations/cli/main.py tests/unit/runtime/test_coding_budget.py` | 0 | Success: no issues found in 5 source files |
| Frontend test, typecheck or build | not in contract | | not-run |
| Package or dependency check | not in contract | | not-run |
| `git diff --check` | `git diff --check -- src/agent_foundations/runtime/coding_budget.py src/agent_foundations/runtime/agent.py src/agent_foundations/runtime/loop.py src/agent_foundations/cli/main.py tests/unit/runtime/test_coding_budget.py docs/task-evidence/phase-2d-task-18.md` | 0 | no whitespace errors (LF/CRLF working-copy warnings only) |

## 7. Scope Audit

- Final changed files (this Task):
  - `src/agent_foundations/runtime/coding_budget.py` (new)
  - `src/agent_foundations/runtime/agent.py`
  - `src/agent_foundations/runtime/loop.py`
  - `src/agent_foundations/cli/main.py`
  - `tests/unit/runtime/test_coding_budget.py` (new)
  - `docs/task-evidence/phase-2d-task-18.md`
  - `docs/agent-plans/2026-08-29-phase-2-reliability-follow-on-plan.md` (status: executor completed, user acceptance pending)
  - `docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md` (appendix Task 34 executor note only; Step 10/11 not ticked)
- Unrelated changes introduced: no
- Existing user changes preserved: yes
- Secrets or generated artifacts detected: no
- Commit, push, deployment, paid API call, or next Task performed: no

## 8. Gaps and Limitations

- Checks not run and reasons: Phase 1 full baseline, frontend, `pip check`, Docker, paid 3×3 — contract `Full suite: not-required`; Docker and paid API forbidden.
- Environment warnings: Starlette/`httpx` deprecation; sqlite3 datetime adapter deprecation in command-feedback / phase2 tests.
- Process evidence gaps: measurement command was also re-run after Chat factory wiring (still 61 passed / 1 skipped). Scripted step/tool counts come from reading those tests, not from pytest `-q`.
- Remaining risks: Chat production constants are headroom over FakeModel success paths, not a paid-model measurement. Pathless `apply_patch` (`patch_id` only) shares an empty-path bucket and does not mix with a pathed `validate_patch` unless paths intersect.

## 9. Handoff Summary

- Current verification status: **pass** (targeted verification; not full suite). Reviewer-fresh: Target 10 passed; Affected 249 passed / 1 skipped; ruff/mypy 5 files passed; `git diff --check` exit 0
- TDD process evidence: **complete**. Reviewer fresh checks prove current green, not the historical Red→Green sequence
- User acceptance: recorded in §10
- Reviewer acceptance: pass (current implementation, targeted) in the reviewer session that preceded this confirmation
- Reviewer findings retained: P3 `coding_budget.py` depends on private recovery helpers; pathless `apply_patch` uses an empty-path bucket; production constants are FakeModel success-path headroom, not a paid-model measurement
- Recommended reviewer commands (already run for this Task):

```text
conda run -n agent-foundations python -m pytest tests/unit/runtime/test_coding_budget.py -q
conda run -n agent-foundations python -m pytest tests/unit/runtime tests/integration/test_agent_loop.py tests/integration/test_command_feedback_agent_flow.py tests/integration/test_phase2_coding_agent.py tests/integration/test_offline_eval.py tests/unit/evals -q
conda run -n agent-foundations python -m ruff check src/agent_foundations/runtime/coding_budget.py src/agent_foundations/runtime/agent.py src/agent_foundations/runtime/loop.py src/agent_foundations/cli/main.py tests/unit/runtime/test_coding_budget.py
conda run -n agent-foundations python -m mypy src/agent_foundations/runtime/coding_budget.py src/agent_foundations/runtime/agent.py src/agent_foundations/runtime/loop.py src/agent_foundations/cli/main.py tests/unit/runtime/test_coding_budget.py
git diff --check
```

## 10. User Acceptance

- Confirmed at: 2026-09-04 +08:00.
- Exact user confirmation: `确认「Task 34 / phase-2d-task-18 用户验收通过」`.
- Result: Follow-on Task 34 / `phase-2d-task-18` (layered budget + Offline Eval) is user-accepted for the current implementation. This is **not** plan body Task 18. Independent reviewer re-ran the targeted contract (10 passed on Target; 249 passed / 1 skipped on affected regression).
- Full suite note: this confirmation accepts **targeted verification passed**. It does not claim `full suite passed`, does not accept Task 25 as complete, does not accept paid 3×3, and does not mark user Phase 2 complete. Plan Task 25 Step 10 and Step 11 remain unchecked.
- TDD note: executor Red is internally consistent and marked complete; this confirmation does not independently witness the original Red→Green sequence.
- Boundary: this confirmation records `phase-2d-task-18` acceptance only. The reliability follow-on plan Tasks 30–34 are now all user-accepted. No commit, push, paid API rerun, Phase 2 complete checkbox, or Phase 3 is authorized by this confirmation. Reviewer P3 findings are retained and do not require immediate rework from this confirmation. Whether to rerun paid 3×3 still requires a separate user authorization under Task 25 Step 10.

