# Task Evidence: phase-2d-task-23

## 1. Identity

- Task ID: `phase-2d-task-23`
- Authoritative plan or task spec: `docs/agent-plans/2026-09-04-phase-2-product-hardening-plan.md` Task 39 plus the user-confirmed executor prompt
- Evidence status: user-accepted 2026-09-05 (targeted verification); Task 25 Step 10/11 **not claimed**; Phase 2 complete **not claimed**
- TDD required: yes
- Started at: 2026-09-05 (Asia/Shanghai)

## 2. Pre-change Snapshot

- Branch or revision: `codex/phase-2-next` at `14ece4e` (not `main`)
- `git status --short` (this Task files before production edits): `M README.md`, `M src/agent_foundations/cli/main.py`. Broader dirty tree (Phase 2A–2D, Chat hashed assets, evidence, Task 30–38 files) already present.
- Existing user changes that must be preserved: all pre-existing modified and untracked files at Task start. Do not `restore`/`reset`/`clean`.
- Intended modification scope: Chat data-root (`--data-root` / `AGENT_FOUNDATIONS_DATA_ROOT` / `default_artifact_root().parent`), layout `chat.sqlite3` + `command-output/` + `controller/` + `traces/`, leftover warnings. Do not change Policy, gate_id, Git, sweep, 512MB, pages/raw HTTP, sanitizer, Tasks 40–41, or Task 35–38 P3. Do not write tests into real `%LOCALAPPDATA%`. Do not hard-code `D:\`. Do not auto-migrate files.
- Expected rollback: revert only this Task’s files; do not revert the pre-existing dirty tree.
- Interpreter: Windows `conda run` can crash pytest with GBK. Commands use `$env:PYTHONIOENCODING='utf-8'`. This does not shrink the verification contract.

## 3. Red

- Recorded before production-code changes: yes
- Time: 2026-09-05 (Asia/Shanghai)
- Test file and test name: `tests/unit/chat/test_data_root.py` (12 tests)
- Command: `$env:PYTHONIOENCODING='utf-8'; conda run -n agent-foundations python -m pytest tests/unit/chat/test_data_root.py -q --tb=line`
- Exit code: 1
- Relevant verbatim output:

```text
D:\codex-pj\search_agent\tests\unit\chat\test_data_root.py:19: AssertionError: chat data_root is missing
D:\codex-pj\search_agent\tests\unit\chat\test_data_root.py:131: AssertionError: assert ['trace_dir', 'state_db'] == ['data_root']
D:\codex-pj\search_agent\tests\unit\chat\test_data_root.py:136: assert 'command-artifacts' not in 'def build_c...ry,\n    )\n'
D:\codex-pj\search_agent\tests\unit\chat\test_data_root.py:147: AssertionError: assert ['trace_dir', 'state_db'] == ['data_root']
D:\codex-pj\search_agent\tests\unit\chat\test_data_root.py:193: AssertionError: assert '--data-root' in '... --state-db ... --trace-dir ...'
D:\codex-pj\search_agent\tests\unit\chat\test_data_root.py:211: AssertionError: assert 'No such option' not in '... --data-root\n'
12 failed in 1.92s
```

Layout test was first TypeError (`state_db` missing); the test was adjusted **before production edits** to assert the signature first, then re-run:

```text
FAILED ...::test_build_chat_services_layout_under_tmp_path
AssertionError: assert ['trace_dir', 'state_db'] == ['data_root']
```

- Expected failure category: assertion failure from missing data-root module / CLI option / still using `command-artifacts` + `--state-db`
- Why this failure demonstrates the missing behavior: Chat still takes `trace_dir`/`state_db`, stores artifacts next to sqlite as `command-artifacts`, and rejects `--data-root` as an unknown option instead of validating a Git worktree. Not syntax or import crashes after the layout test was ordered to assert the signature first.
- If unavailable, why it cannot be verified: n/a

## 4. Green

- Production files changed:
  - `src/agent_foundations/chat/data_root.py`: resolve/layout/leftover
  - `src/agent_foundations/cli/main.py`: `--data-root`, drop chat `--state-db`/`--trace-dir`, `build_chat_services(data_root)`
  - `src/agent_foundations/command_output/store.py`: public `validate_artifact_root` alias of existing `_validated_root` (no new rules)
  - Callers of `build_chat_services` now pass `tmp_path` / explicit data-root
  - `README.md`: data-root table and chat CLI
- Command: `$env:PYTHONIOENCODING='utf-8'; conda run -n agent-foundations python -m pytest tests/unit/chat/test_data_root.py tests/unit/command_output/test_store.py -q`
- Exit code: 0
- Relevant verbatim output:

```text
26 passed in 1.43s
```

## 5. Regression and Quality Gates

| Check | Command | Exit code | Result |
|---|---|---:|---|
| Target tests | `$env:PYTHONIOENCODING='utf-8'; conda run -n agent-foundations python -m pytest tests/unit/chat/test_data_root.py tests/unit/command_output/test_store.py -q` | 0 | 26 passed |
| Regression tests | `$env:PYTHONIOENCODING='utf-8'; conda run -n agent-foundations python -m pytest tests/unit/chat/test_data_root.py tests/unit/runtime/test_coding_prompt.py tests/unit/runtime/test_coding_budget.py tests/unit/chat/test_plan_persistence.py tests/integration/test_chat_planning_tools.py tests/integration/test_ask_always_run_command_twice.py tests/integration/test_command_feedback_agent_flow.py tests/integration/test_phase2_coding_agent.py tests/integration/test_task16_production_wiring.py tests/unit/tools/command/test_run_command.py -q` | 0 | 49 passed, 1 skipped, 13 warnings |
| Ruff | `$env:PYTHONIOENCODING='utf-8'; conda run -n agent-foundations python -m ruff check src/agent_foundations/chat/data_root.py src/agent_foundations/cli/main.py tests/unit/chat/test_data_root.py` | 0 | All checks passed |
| mypy | `$env:PYTHONIOENCODING='utf-8'; conda run -n agent-foundations python -m mypy src/agent_foundations/chat/data_root.py src/agent_foundations/cli/main.py tests/unit/chat/test_data_root.py` | 0 | Success: no issues found in 3 source files |
| Frontend test, typecheck or build | not in contract | | not-run |
| Package or dependency check | not in contract | | not-run |
| `git diff --check` | `git diff --check` | 0 | pass (CRLF working-copy warnings only) |

Targeted verification passed. Full suite not-required and not run.

## 6. Scope Audit

- Final changed files (this Task):
  - Create: `src/agent_foundations/chat/data_root.py`
  - Create: `tests/unit/chat/test_data_root.py`
  - Create: `docs/task-evidence/phase-2d-task-23.md`
  - Modify: `src/agent_foundations/cli/main.py`
  - Modify: `src/agent_foundations/command_output/store.py` (`validate_artifact_root` public alias only)
  - Modify: `README.md` (data location table + chat CLI)
  - Modify callers: `tests/unit/runtime/test_coding_prompt.py`, `tests/unit/runtime/test_coding_budget.py`, `tests/unit/chat/test_plan_persistence.py`, `tests/integration/test_chat_planning_tools.py`, `tests/integration/test_ask_always_run_command_twice.py`, `tests/integration/test_command_feedback_agent_flow.py`, `tests/integration/test_phase2_coding_agent.py`, `tests/integration/test_task16_production_wiring.py`, `tests/e2e/test_chat_ui.py` (call only; browser not run), `tests/e2e/test_cli.py` (chat options; not run)
- Unrelated changes introduced: no. Pre-existing dirty tree from Tasks 30–38 preserved.
- Existing user changes preserved: yes
- Secrets or generated artifacts detected: no
- Commit, push, deployment, paid API call, or next Task performed: no

## 7. Gaps and Limitations

- Checks not run and reasons: full suite, Docker, Playwright e2e, paid API — not in contract / not authorized. `tests/e2e/test_cli.py` and `tests/e2e/test_chat_ui.py` were mechanically updated; browser not run.
- Environment warnings: Starlette/`httpx` TestClient deprecation; sqlite3 datetime adapter; `git diff --check` CRLF warnings on pre-existing files.
- Process evidence gaps: layout test originally TypeError; signature assertion was added before production edits and re-run as valid assertion Red.
- Remaining risks: leftover warning uses CWD, so launching Chat from a repo that still has `./traces` prints a warning but does not migrate. Reviewer should re-run the verification contract.

## 8. Handoff Summary

- Current verification status: **pass** (targeted verification; not full suite). Reviewer-fresh: Target 26 passed; Affected 49 passed / 1 skipped; ruff / mypy / `git diff --check` exit 0. Extra probe: `tests/e2e/test_cli.py` chat-related 5 passed (CliRunner, not browser)
- TDD process evidence: **complete**. Reviewer fresh checks prove current green, not the historical Red→Green sequence
- User acceptance: recorded in §9
- Reviewer acceptance: pass (current implementation, targeted) in the reviewer session that preceded this confirmation
- Reviewer findings retained: P3 leftover warnings use process CWD only; layout test does not assert `controller`; Playwright `test_chat_ui.py` callers were updated but the browser was not run
- Recommended reviewer commands (already run for this Task):

```text
$env:PYTHONIOENCODING='utf-8'
conda run -n agent-foundations python -m pytest tests/unit/chat/test_data_root.py tests/unit/command_output/test_store.py -q
conda run -n agent-foundations python -m pytest tests/unit/chat/test_data_root.py tests/unit/runtime/test_coding_prompt.py tests/unit/runtime/test_coding_budget.py tests/unit/chat/test_plan_persistence.py tests/integration/test_chat_planning_tools.py tests/integration/test_ask_always_run_command_twice.py tests/integration/test_command_feedback_agent_flow.py tests/integration/test_phase2_coding_agent.py tests/integration/test_task16_production_wiring.py tests/unit/tools/command/test_run_command.py -q
conda run -n agent-foundations python -m ruff check src/agent_foundations/chat/data_root.py src/agent_foundations/cli/main.py tests/unit/chat/test_data_root.py
conda run -n agent-foundations python -m mypy src/agent_foundations/chat/data_root.py src/agent_foundations/cli/main.py tests/unit/chat/test_data_root.py
git diff --check
```

## 9. User Acceptance

- Confirmed at: 2026-09-05 +08:00.
- Exact user confirmation: `确认「Task 39 / phase-2d-task-23 用户验收通过」`.
- Result: Product-hardening Task 39 / `phase-2d-task-23` (independent Chat data root) is user-accepted for the current implementation. This is **not** plan body Task 23. Independent reviewer re-ran the targeted contract (Target 26 passed; Affected 49 passed / 1 skipped; ruff / mypy / `git diff --check` exit 0) and additionally probed CLI chat tests (5 passed).
- Full suite note: this confirmation accepts **targeted verification passed**. It does not claim `full suite passed`, does not accept Task 25 as complete, does not accept paid 3×3, and does not mark user Phase 2 complete. Plan Task 25 Step 10 and Step 11 remain unchecked.
- TDD note: executor Red is internally consistent and marked complete; this confirmation does not independently witness the original Red→Green sequence.
- Boundary: this confirmation records `phase-2d-task-23` acceptance only. Task 40 / `phase-2d-task-24` still requires its own explicit single-Task executor authorization. No commit, push, paid API rerun, Phase 2 complete checkbox, or Phase 3 is authorized by this confirmation. Reviewer P3 findings are retained and do not require immediate rework from this confirmation.
