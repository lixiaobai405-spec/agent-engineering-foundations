# Task Evidence: phase-2d-task-19

## 1. Identity

- Task ID: `phase-2d-task-19`
- Authoritative plan or task spec: `docs/agent-plans/2026-09-04-phase-2-product-hardening-plan.md` Task 35 plus the user-confirmed executor prompt
- Evidence status: user-accepted 2026-09-04 (targeted verification); Task 25 Step 10/11 **not claimed**; Phase 2 complete **not claimed**
- TDD required: yes
- Started at: 2026-09-04 (Asia/Shanghai)

## 2. Pre-change Snapshot

- Branch or revision: `codex/phase-2-next` at `14ece4e` (not `main`)
- `git status --short`: dirty working tree already present (Phase 2A–2D, Chat hashed assets, Dockerfiles, evidence, Task 30–34 files, product-hardening plan). Exact listing is long.
- Existing user changes that must be preserved: all pre-existing modified and untracked files at Task start. Do not `restore`/`reset`/`clean`.
- Intended modification scope: `run_command` schema + `gate_id` expansion; Tool description; Task 33 locked Prompt sentences; FakeModel/integration Tool arguments that currently pass `argv`. Do not change Policy matrix, Sandbox, Git, Artifact paths, `max_steps`, Docker, paid API, Task 25 Step 10/11, or Tasks 36–41.
- Expected rollback: revert only this Task’s files; do not revert the pre-existing dirty tree.
- Interpreter: Windows `conda run` can crash pytest with GBK. Commands use `$env:PYTHONIOENCODING='utf-8'`. This does not shrink the verification contract.

## 3. Red

- Recorded before production-code changes: yes
- Time: 2026-09-04 (Asia/Shanghai), after new/updated tests and before `gate_expand.py` / schema / Prompt / executor expansion
- Test file and test name:
  - `tests/unit/tools/command/test_gate_expand.py` (schema, expand, reject argv/unknown/exact extras)
  - `tests/unit/tools/command/test_run_command.py::test_run_command_manifest_and_resource_contract`
  - `tests/unit/runtime/test_coding_prompt.py` locked sentences + description
- Command: `$env:PYTHONIOENCODING='utf-8'; conda run -n agent-foundations python -m pytest tests/unit/tools/command tests/unit/runtime/test_coding_prompt.py -q --tb=short`
- Exit code: 1
- Relevant verbatim output:

```text
........................................FFFFFF.......................... [ 79%]
........F....FF..F.                                                      [100%]
FAILED tests/unit/tools/command/test_gate_expand.py::test_run_command_schema_requires_gate_id_and_forbids_argv
E   AssertionError: assert ['argv'] == ['gate_id']
FAILED tests/unit/tools/command/test_gate_expand.py::test_exact_node_gate_expands_to_prefix_only
E   assert None is not None
FAILED tests/unit/tools/command/test_gate_expand.py::test_exact_gate_rejects_target_or_flags
FAILED tests/unit/tools/command/test_gate_expand.py::test_pytest_gate_expands_prefix_flags_then_target
FAILED tests/unit/tools/command/test_gate_expand.py::test_unknown_gate_id_is_rejected
FAILED tests/unit/tools/command/test_gate_expand.py::test_argv_is_rejected_without_classifying
FAILED tests/unit/tools/command/test_run_command.py::test_run_command_manifest_and_resource_contract
E   AssertionError: ... identifier='sandbox_command'
FAILED tests/unit/runtime/test_coding_prompt.py::test_controlled_coding_agent_prompt_constant_contains_locked_sentences
E   AssertionError: assert 'Call run_command with gate_id ...' in '... before rerunning the same argv.'
FAILED tests/unit/runtime/test_coding_prompt.py::test_chat_runtime_factory_uses_controlled_coding_prompt
FAILED tests/unit/runtime/test_coding_prompt.py::test_run_command_description_requires_gate_id_not_argv
E   AssertionError: assert 'gate_id' in '... argv must match the project command manifest exactly ...'
10 failed, 81 passed in 2.22s
```

- Expected failure category: missing `gate_expand` module; schema still requires `argv`; resource identifier not `gate_id`; Prompt/description still teach argv. Tests collected and ran (not syntax/import collection errors).
- Why this failure demonstrates the missing behavior: models still submit argv; Runtime does not expand `gate_id`; Chat prompt still says “same argv”.
- If unavailable, why it cannot be verified:

## 4. Green

- Production files changed:
  - `src/agent_foundations/tools/command/gate_expand.py` (new)
  - `src/agent_foundations/tools/command/run_command.py` (schema, description, expand before classify, resource identifier)
  - `src/agent_foundations/runtime/coding_prompt.py` (locked gate_id sentences)
  - `src/agent_foundations/runtime/recovery.py` (`_argv` canonical identity from `gate_id`+flags+target so Task 31 feedback matching still works)
- Command: `$env:PYTHONIOENCODING='utf-8'; conda run -n agent-foundations python -m pytest tests/unit/tools/command tests/unit/runtime/test_coding_prompt.py -q --tb=short`
- Exit code: 0
- Relevant verbatim output:

```text
........................................................................ [ 79%]
...................                                                      [100%]
91 passed in 1.40s
```

## 5. Regression and Quality Gates

| Check | Command | Exit code | Result |
|---|---|---:|---|
| Target tests | `$env:PYTHONIOENCODING='utf-8'; conda run -n agent-foundations python -m pytest tests/unit/tools/command tests/unit/runtime/test_coding_prompt.py -q` | 0 | 91 passed |
| Regression tests | `$env:PYTHONIOENCODING='utf-8'; conda run -n agent-foundations python -m pytest tests/integration/test_run_command_flow.py tests/integration/test_command_feedback_agent_flow.py tests/integration/test_phase2_coding_agent.py tests/integration/test_ask_always_run_command_twice.py tests/integration/test_run_command_cancellation.py tests/unit/runtime/test_coding_budget.py tests/unit/runtime/test_recovery.py -q` | 0 | 37 passed, 3 skipped (**targeted verification**, not full suite) |
| Ruff | `$env:PYTHONIOENCODING='utf-8'; conda run -n agent-foundations python -m ruff check src/agent_foundations/tools/command src/agent_foundations/runtime/coding_prompt.py tests/unit/tools/command tests/unit/runtime/test_coding_prompt.py` | 0 | All checks passed |
| mypy | `$env:PYTHONIOENCODING='utf-8'; conda run -n agent-foundations python -m mypy src/agent_foundations/tools/command src/agent_foundations/runtime/coding_prompt.py tests/unit/tools/command` | 0 | Success: no issues found in 15 source files |
| Frontend test, typecheck or build | not in contract | | not-run |
| Package or dependency check | not in contract | | not-run |
| `git diff --check` | `git diff --check` | 0 | no whitespace errors (LF/CRLF working-copy warnings only) |

## 6. Scope Audit

- Final changed files (this Task):
  - `src/agent_foundations/tools/command/gate_expand.py` (new)
  - `src/agent_foundations/tools/command/run_command.py`
  - `src/agent_foundations/runtime/coding_prompt.py`
  - `src/agent_foundations/runtime/recovery.py` (`_argv` identity only; recovery mapping unchanged)
  - `tests/unit/tools/command/test_gate_expand.py` (new)
  - `tests/unit/tools/command/test_run_command.py`
  - `tests/unit/runtime/test_coding_prompt.py`
  - `tests/unit/runtime/test_coding_budget.py`
  - `tests/unit/runtime/test_recovery.py`
  - `tests/integration/test_run_command_flow.py`
  - `tests/integration/test_command_feedback_agent_flow.py`
  - `tests/integration/test_phase2_coding_agent.py`
  - `tests/integration/test_ask_always_run_command_twice.py`
  - `tests/integration/test_run_command_cancellation.py`
  - `docs/task-evidence/phase-2d-task-19.md`
  - `docs/agent-plans/2026-09-04-phase-2-product-hardening-plan.md` (status: executor completed, user acceptance pending)
  - `docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md` (appendix Task 35 executor note only; Step 10/11 not ticked)
- Unrelated changes introduced: no
- Existing user changes preserved: yes
- Secrets or generated artifacts detected: no
- Commit, push, deployment, paid API call, or next Task performed: no

## 7. Gaps and Limitations

- Checks not run and reasons: Phase 1 full baseline, frontend, `pip check`, Docker (3 skipped docker-marked tests), paid 3×3 — contract `Full suite: not-required`; Docker and paid API forbidden.
- Environment warnings: Starlette/`httpx` deprecation; sqlite3 datetime adapter deprecation.
- Process evidence gaps: none for Red→Green of target tests. Classifier unit tests still feed argv directly, as allowed.
- Remaining risks: Chat activity text in `chat/events.py` still looks up `arguments["argv"]` for display (not in this Task’s file list). Illegal parameterized flags still expand then hit existing classifier `invalid-arguments`. `gate_id` cannot bypass classify → Policy → Approval → Capability → Sandbox.

## 8. Handoff Summary

- Current verification status: **pass** (targeted verification; not full suite). Reviewer-fresh: Target 91 passed; Affected 37 passed / 3 skipped; ruff/mypy passed including extra `recovery.py`; `git diff --check` exit 0
- TDD process evidence: **complete**. Reviewer fresh checks prove current green, not the historical Red→Green sequence
- User acceptance: recorded in §9
- Reviewer acceptance: pass (current implementation, targeted) in the reviewer session that preceded this confirmation
- Reviewer findings retained: P3 Chat activity text still reads `arguments["argv"]`; `allowed_flags` subset/dedup is enforced by the classifier after expand; recovery user-facing copy still says “same argv”
- Recommended reviewer commands (already run for this Task):

```text
conda run -n agent-foundations python -m pytest tests/unit/tools/command tests/unit/runtime/test_coding_prompt.py -q
conda run -n agent-foundations python -m pytest tests/integration/test_run_command_flow.py tests/integration/test_command_feedback_agent_flow.py tests/integration/test_phase2_coding_agent.py tests/integration/test_ask_always_run_command_twice.py tests/integration/test_run_command_cancellation.py tests/unit/runtime/test_coding_budget.py tests/unit/runtime/test_recovery.py -q
conda run -n agent-foundations python -m ruff check src/agent_foundations/tools/command src/agent_foundations/runtime/coding_prompt.py tests/unit/tools/command tests/unit/runtime/test_coding_prompt.py
conda run -n agent-foundations python -m mypy src/agent_foundations/tools/command src/agent_foundations/runtime/coding_prompt.py tests/unit/tools/command
git diff --check
```

## 9. User Acceptance

- Confirmed at: 2026-09-04 +08:00.
- Exact user confirmation: `确认「Task 35 / phase-2d-task-19 用户验收通过」`.
- Result: Product-hardening Task 35 / `phase-2d-task-19` (`run_command` `gate_id` contract) is user-accepted for the current implementation. This is **not** plan body Task 19. Independent reviewer re-ran the targeted contract (91 passed on Target; 37 passed / 3 skipped on affected regression).
- Full suite note: this confirmation accepts **targeted verification passed**. It does not claim `full suite passed`, does not accept Task 25 as complete, does not accept paid 3×3, and does not mark user Phase 2 complete. Plan Task 25 Step 10 and Step 11 remain unchecked.
- TDD note: executor Red is internally consistent and marked complete; this confirmation does not independently witness the original Red→Green sequence.
- Boundary: this confirmation records `phase-2d-task-19` acceptance only. Task 36 / `phase-2d-task-20` still requires its own explicit single-Task executor authorization. No commit, push, paid API rerun, Phase 2 complete checkbox, or Phase 3 is authorized by this confirmation. Reviewer P3 findings are retained and do not require immediate rework from this confirmation.

