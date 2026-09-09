# Task Evidence: phase-2d-task-16

## 1. Identity

- Task ID: `phase-2d-task-16`
- Authoritative plan or task spec: `docs/agent-plans/2026-08-29-phase-2-reliability-follow-on-plan.md` Task 32 plus the user-confirmed executor prompt
- Evidence status: user-accepted 2026-08-29 (targeted verification); Task 25 Step 10/11 **not claimed**; Phase 2 complete **not claimed**
- TDD required: yes
- Started at: 2026-08-29 (Asia/Shanghai)

## 2. Pre-change Snapshot

- Branch or revision: `codex/phase-2-next` at `14ece4e` (not `main`)
- `git status --short`: dirty working tree already present (Phase 2A–2D, Chat hashed assets, Dockerfiles, evidence, Task 30–31 files). Exact listing is long.
- Existing user changes that must be preserved: all pre-existing modified and untracked files at Task start. Do not `restore`/`reset`/`clean`.
- Intended modification scope: Chat plan persistence across turns (`AgentLoop.run(plan_snapshot=)`, runner load from durable checkpoints, GET state `plan`, `ChatEventType.PLAN_UPDATED`, Chat UI plan panel). Do not change PlanningMode to REQUIRED, re-register planning tools, schema v11, Policy/Approval/Sandbox/whitelist/`max_steps`, Task 30 CRLF P2, Task 31 reviewer P3, Docker, or Task 25 Step 10/11.
- Expected rollback: revert only this Task’s files; do not revert the pre-existing dirty tree.
- Interpreter: Windows `conda run` can crash pytest with GBK. Commands use `$env:PYTHONIOENCODING='utf-8'`. This does not shrink the verification contract.

## 3. Red

- Recorded before production-code changes: yes
- Time: 2026-08-29 (Asia/Shanghai), before production edits to loop/runner/events/api/UI
- Test file and test name:
  - `tests/integration/test_chat_planning_tools.py::test_chat_plan_survives_second_turn_and_blocks_second_set_plan`
  - `tests/unit/chat/test_plan_persistence.py::test_conversation_b_does_not_load_conversation_a_plan`
  - `tests/unit/chat/test_plan_persistence.py::test_replan_count_survives_turn_and_still_enforces_limit`
  - `tests/unit/chat/test_events.py::test_plan_trace_events_project_to_plan_updated_without_evidence`
- Command: `$env:PYTHONIOENCODING='utf-8'; conda run -n agent-foundations python -m pytest tests/integration/test_chat_planning_tools.py tests/unit/chat/test_plan_persistence.py tests/unit/chat/test_events.py tests/unit/planning -q --tb=short`
- Exit code: 1
- Relevant verbatim output:

```text
.FFF.....F.............................................................. [ 59%]
..................................................                       [100%]
================================== FAILURES ===================================
_______ test_chat_plan_survives_second_turn_and_blocks_second_set_plan ________
tests\integration\test_chat_planning_tools.py:168: in test_chat_plan_survives_second_turn_and_blocks_second_set_plan
    assert isinstance(plan, dict)
E   assert False
E    +  where False = isinstance(None, dict)
____________ test_conversation_b_does_not_load_conversation_a_plan ____________
tests\unit\chat\test_plan_persistence.py:116: in test_conversation_b_does_not_load_conversation_a_plan
    state_a = client.get(
E   KeyError: 'plan'
__________ test_replan_count_survives_turn_and_still_enforces_limit ___________
tests\unit\chat\test_plan_persistence.py:176: in test_replan_count_survives_turn_and_still_enforces_limit
    after_one = client.get(
E   KeyError: 'plan'
_______ test_plan_trace_events_project_to_plan_updated_without_evidence _______
tests\unit\chat\test_events.py:187: in test_plan_trace_events_project_to_plan_updated_without_evidence
    assert chat_event is not None
E   assert None is not None
=========================== short test summary info ===========================
FAILED tests/integration/test_chat_planning_tools.py::test_chat_plan_survives_second_turn_and_blocks_second_set_plan
FAILED tests/unit/chat/test_plan_persistence.py::test_conversation_b_does_not_load_conversation_a_plan
FAILED tests/unit/chat/test_plan_persistence.py::test_replan_count_survives_turn_and_still_enforces_limit
FAILED tests/unit/chat/test_events.py::test_plan_trace_events_project_to_plan_updated_without_evidence
4 failed, 118 passed, 1 warning in 3.76s
```

- Expected failure category: assertion / KeyError on missing GET `plan` and missing Chat projection of Trace `plan.*`
- Why this failure demonstrates the missing behavior: GET conversation state had no `plan`; Trace `plan.created` / `plan.step.updated` / `plan.replanned` projected to `None` instead of `plan.updated`. Not import/syntax errors. Existing optional-planning DISABLED test stayed green (the leading `.`).
- If unavailable, why it cannot be verified:

## 4. Green

- Production files changed:
  - `src/agent_foundations/runtime/loop.py` (`run(..., plan_snapshot=)`, restore before `_drive`, Trace plan payload without evidence)
  - `src/agent_foundations/chat/durable_checkpoint.py` (`load_latest_conversation_plan`, `execution_plan_to_chat_view`)
  - `src/agent_foundations/chat/runner.py` (load prior-run snapshot, pass into `loop.run`)
  - `src/agent_foundations/chat/models.py` (`ChatEventType.PLAN_UPDATED`)
  - `src/agent_foundations/chat/events.py` (project `plan.*` → `plan.updated`, strip evidence)
  - `src/agent_foundations/chat/api.py` (GET state `plan`, optional `ChatServices.durable_repository`)
  - `src/agent_foundations/cli/main.py` (pass durable repository into `ChatServices`)
  - `web/chat/state/types.ts`, `web/chat/state/reducer.ts`, `web/chat/App.tsx`, `web/chat/styles.css`, `web/chat/components/PlanPanel.tsx`
- Command: `$env:PYTHONIOENCODING='utf-8'; conda run -n agent-foundations python -m pytest tests/integration/test_chat_planning_tools.py tests/unit/chat/test_plan_persistence.py tests/unit/chat/test_events.py tests/unit/planning -q --tb=short`
- Exit code: 0
- Relevant verbatim output:

```text
122 passed, 1 warning in 2.41s
```

After first Green, `test_chat_plan_survives_second_turn_and_blocks_second_set_plan` failed on `provider.requests[2]` (tool result is on the *next* model request). Assertion was widened to scan all `set_plan` tool messages for `already exists`. Re-run of the same Target command then passed as above.

## 5. Regression and Quality Gates

| Check | Command | Exit code | Result |
|---|---|---:|---|
| Target tests | `$env:PYTHONIOENCODING='utf-8'; conda run -n agent-foundations python -m pytest tests/integration/test_chat_planning_tools.py tests/unit/chat/test_plan_persistence.py tests/unit/chat/test_events.py tests/unit/planning -q` | 0 | 122 passed (targeted) |
| npm test:chat | `npm run test:chat` | 0 | 10 files / 79 tests passed |
| npm typecheck:chat | `npm run typecheck:chat` | 0 | `tsc --noEmit` clean |
| Regression tests | `$env:PYTHONIOENCODING='utf-8'; conda run -n agent-foundations python -m pytest tests/unit/chat tests/integration/test_chat_api.py tests/integration/test_chat_planning_tools.py tests/unit/planning tests/unit/runtime/test_state_machine.py -q` | 0 | 337 passed (targeted) |
| Ruff | `$env:PYTHONIOENCODING='utf-8'; conda run -n agent-foundations python -m ruff check src/agent_foundations/chat src/agent_foundations/runtime/loop.py src/agent_foundations/planning tests/unit/chat tests/unit/planning tests/integration/test_chat_planning_tools.py` | 0 | All checks passed (after I001 import sort in the integration test) |
| mypy | `$env:PYTHONIOENCODING='utf-8'; conda run -n agent-foundations python -m mypy src/agent_foundations/chat src/agent_foundations/runtime/loop.py src/agent_foundations/planning tests/unit/chat tests/unit/planning` | 0 | Success: no issues found in 32 source files |
| Frontend test, typecheck or build | `npm run test:chat` / `typecheck:chat` | 0 | pass (no `build:chat` in contract) |
| Package or dependency check | not in contract | | not-run |
| `git diff --check` | `git diff --check` | 0 | no whitespace errors (CRLF warnings only) |

## 6. Scope Audit

- Final changed files (this Task):
  - `src/agent_foundations/runtime/loop.py`
  - `src/agent_foundations/chat/durable_checkpoint.py`
  - `src/agent_foundations/chat/runner.py`
  - `src/agent_foundations/chat/models.py`
  - `src/agent_foundations/chat/events.py`
  - `src/agent_foundations/chat/api.py`
  - `src/agent_foundations/cli/main.py`
  - `web/chat/state/types.ts`
  - `web/chat/state/reducer.ts`
  - `web/chat/App.tsx`
  - `web/chat/styles.css`
  - `web/chat/components/PlanPanel.tsx` (new)
  - `tests/integration/test_chat_planning_tools.py`
  - `tests/unit/chat/test_plan_persistence.py` (new)
  - `tests/unit/chat/test_events.py`
  - `tests/chat/plan-panel.test.tsx` (new)
  - `tests/integration/test_chat_api.py` (GET state exact JSON now includes `"plan": null`)
  - `docs/task-evidence/phase-2d-task-16.md`
- Unrelated changes introduced: no
- Existing user changes preserved: yes
- Secrets or generated artifacts detected: no
- Commit, push, deployment, paid API call, or next Task performed: no

## 7. Gaps and Limitations

- Checks not run and reasons: Phase 1 full suite not-required; Playwright `tests/e2e/test_chat_ui.py` forbidden; `pip check` / `build:chat` not in contract; npm Red not separately recorded (PlanPanel did not exist; pytest Red is the saved process evidence)
- Environment warnings: conda FastAPI TestClient Starlette/`httpx` deprecation; `git diff --check` CRLF working-copy warnings
- Process evidence gaps: first Green of the cross-turn test needed a test-index correction (`requests[2]` vs later tool-result request); not a production regression. Frontend vitest was not run as a pre-implementation Red
- Remaining risks: COMPLETED `evidence_refs` remain session-local (`ExecutionFactJournal` is not persisted across turns, per contract). GET `plan` and SSE `plan.updated` omit evidence on purpose

## 8. Handoff Summary

- Current verification status: **pass** (targeted verification; not full suite). Reviewer-fresh: Target pytest 122 passed; `npm run test:chat` 79 passed; `npm run typecheck:chat` pass; Affected 337 passed; ruff/mypy 32 files passed; `git diff --check` exit 0
- TDD process evidence: **complete** for pytest Target; frontend vitest Red not independently saved. Reviewer fresh checks prove current green, not the historical Red→Green sequence
- User acceptance: recorded in §9
- Reviewer acceptance: pass (current implementation, targeted) in the reviewer session that preceded this confirmation
- Reviewer findings retained: P3 frontend vitest has no historical Red; `ExecutionFactJournal` remains per-turn; `ChatServices.durable_repository` is optional; live Chat browser / Playwright not run
- Recommended reviewer commands (already run for this Task):

```text
conda run -n agent-foundations python -m pytest tests/integration/test_chat_planning_tools.py tests/unit/chat/test_plan_persistence.py tests/unit/chat/test_events.py tests/unit/planning -q
npm run test:chat
npm run typecheck:chat
conda run -n agent-foundations python -m pytest tests/unit/chat tests/integration/test_chat_api.py tests/integration/test_chat_planning_tools.py tests/unit/planning tests/unit/runtime/test_state_machine.py -q
conda run -n agent-foundations python -m ruff check src/agent_foundations/chat src/agent_foundations/runtime/loop.py src/agent_foundations/planning tests/unit/chat tests/unit/planning tests/integration/test_chat_planning_tools.py
conda run -n agent-foundations python -m mypy src/agent_foundations/chat src/agent_foundations/runtime/loop.py src/agent_foundations/planning tests/unit/chat tests/unit/planning
git diff --check
```

## 9. User Acceptance

- Confirmed at: 2026-08-29 +08:00.
- Exact user confirmation: `确认「Task 32 / phase-2d-task-16 用户验收通过」`.
- Result: Follow-on Task 32 / `phase-2d-task-16` (Chat Planning persistence and UI) is user-accepted for the current implementation. This is **not** plan body Task 16. Independent reviewer re-ran the targeted contract (122 passed on Target pytest; 79 passed on `npm run test:chat`; typecheck clean; 337 passed on affected regression).
- Full suite note: this confirmation accepts **targeted verification passed**. It does not claim `full suite passed`, does not accept Task 25 as complete, does not accept paid 3×3, and does not mark user Phase 2 complete. Plan Task 25 Step 10 and Step 11 remain unchecked.
- TDD note: executor pytest Red is internally consistent and marked complete; frontend vitest Red was not saved. This confirmation does not independently witness the original Red→Green sequence.
- Boundary: this confirmation records `phase-2d-task-16` acceptance only. Task 33 / `phase-2d-task-17` still requires its own explicit single-Task executor authorization. No commit, push, paid API rerun, Phase 2 complete checkbox, or Phase 3 is authorized by this confirmation. Reviewer P3 findings are retained and do not require immediate rework from this confirmation.

