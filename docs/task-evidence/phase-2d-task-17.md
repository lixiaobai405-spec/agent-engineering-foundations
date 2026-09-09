# Task Evidence: phase-2d-task-17

## 1. Identity

- Task ID: `phase-2d-task-17`
- Authoritative plan or task spec: `docs/agent-plans/2026-08-29-phase-2-reliability-follow-on-plan.md` Task 33 plus the user-confirmed executor prompt
- Evidence status: user-accepted 2026-08-29 (targeted verification); Task 25 Step 10/11 **not claimed**; Phase 2 complete **not claimed**
- TDD required: yes
- Started at: 2026-08-29 (Asia/Shanghai)

## 2. Pre-change Snapshot

- Branch or revision: `codex/phase-2-next` at `14ece4e` (not `main`)
- `git status --short`: dirty working tree already present (Phase 2A–2D, Chat hashed assets, Dockerfiles, evidence, Task 30–32 files). Exact listing is long.
- Existing user changes that must be preserved: all pre-existing modified and untracked files at Task start. Do not `restore`/`reset`/`clean`.
- Intended modification scope: `CONTROLLED_CODING_AGENT_PROMPT` used by Chat `runtime_factory`; Tool description and `validate_patch` schema field descriptions only. Do not change default `AgentConfig.system_prompt`, CLI `build_runtime()` prompt, Policy/Approval/Sandbox/whitelist/`max_steps`/schema v11/`PlanningMode`, Task 30 CRLF P2, Task 31/32 reviewer P3, Docker, or Task 25 Step 10/11.
- Expected rollback: revert only this Task’s files; do not revert the pre-existing dirty tree.
- Interpreter: Windows `conda run` can crash pytest with GBK. Commands use `$env:PYTHONIOENCODING='utf-8'`. This does not shrink the verification contract.

## 3. Red

- Recorded before production-code changes: yes
- Time: 2026-08-29 (Asia/Shanghai), before coding_prompt.py / description edits
- Test file and test name:
  - `tests/unit/runtime/test_coding_prompt.py::test_controlled_coding_agent_prompt_constant_contains_locked_sentences`
  - `tests/unit/runtime/test_coding_prompt.py::test_chat_runtime_factory_uses_controlled_coding_prompt`
  - `tests/unit/runtime/test_coding_prompt.py` description tests for read_file / validate_patch / run_command / read_command_output
  - `tests/unit/tools/patch/test_validate_patch.py::test_validate_patch_description_prefers_changes_from_read_file`
- Command: `$env:PYTHONIOENCODING='utf-8'; conda run -n agent-foundations python -m pytest tests/unit/runtime/test_coding_prompt.py tests/unit/tools/patch/test_validate_patch.py tests/tools/filesystem -q --tb=short`
- Exit code: 1
- Relevant verbatim output:

```text
.FFFFFF..F...                                                            [100%]
================================== FAILURES ===================================
___ test_controlled_coding_agent_prompt_constant_contains_locked_sentences ____
tests\unit\runtime\test_coding_prompt.py:42: in test_controlled_coding_agent_prompt_constant_contains_locked_sentences
    assert spec is not None
E   assert None is not None
___________ test_chat_runtime_factory_uses_controlled_coding_prompt ___________
tests\unit\runtime\test_coding_prompt.py:78: in test_chat_runtime_factory_uses_controlled_coding_prompt
    assert sentence in prompt
E   AssertionError: assert 'Before editing a file, call read_file.' in 'You are a controlled coding agent. ...'
_________ test_read_file_description_names_full_file_digest_metadata __________
E   AssertionError: assert 'sha256' in 'Read a bounded UTF-8 line range from a project-relative text file.'
____ test_validate_patch_description_prefers_changes_and_forbids_guessing _____
E   AssertionError: assert 'Prefer changes with expected_sha256 from read_file' in 'Validate a unified diff proposal against caller baselines without writing files.'
__________ test_run_command_description_requires_exact_manifest_argv __________
E   AssertionError: assert 'argv must match the project command manifest exactly' in 'Run one classified project gate command inside the fixed sandbox.'
________ test_read_command_output_description_follows_command_feedback ________
E   AssertionError: assert 'failing run_command' in 'Read a bounded sanitized slice of a command output artifact.'
_______ test_validate_patch_description_prefers_changes_from_read_file ________
E   AssertionError: assert 'Prefer changes with expected_sha256 from read_file' in 'Validate a unified diff proposal against caller baselines without writing files.'
7 failed, 6 passed in 2.03s
```

- Expected failure category: assertion on missing locked prompt sentences / Tool description keywords; missing `coding_prompt` module (`spec is not None`)
- Why this failure demonstrates the missing behavior: Chat prompt lacked the six locked English sentences; Tool descriptions lacked the contracted keywords; constant module did not exist. Default `AgentConfig` prompt and `validate_patch` oneOf tests stayed green. Not import/syntax collection errors.
- If unavailable, why it cannot be verified:

## 4. Green

- Production files changed:
  - `src/agent_foundations/runtime/coding_prompt.py` (`CONTROLLED_CODING_AGENT_PROMPT`)
  - `src/agent_foundations/cli/main.py` (Chat `runtime_factory` uses the constant; `build_runtime()` unchanged)
  - `src/agent_foundations/tools/filesystem/read_file.py` (description)
  - `src/agent_foundations/tools/patch/validate_patch.py` (description + schema field `description` only)
  - `src/agent_foundations/tools/command/run_command.py` (description)
  - `src/agent_foundations/tools/command/read_output.py` (description)
- Command: `$env:PYTHONIOENCODING='utf-8'; conda run -n agent-foundations python -m pytest tests/unit/runtime/test_coding_prompt.py tests/unit/tools/patch/test_validate_patch.py tests/tools/filesystem -q`
- Exit code: 0
- Relevant verbatim output:

```text
13 passed in 1.46s
```

## 5. Regression and Quality Gates

| Check | Command | Exit code | Result |
|---|---|---:|---|
| Target tests | `$env:PYTHONIOENCODING='utf-8'; conda run -n agent-foundations python -m pytest tests/unit/runtime/test_coding_prompt.py tests/unit/tools/patch/test_validate_patch.py tests/tools/filesystem -q` | 0 | 13 passed (targeted) |
| Regression tests | `$env:PYTHONIOENCODING='utf-8'; conda run -n agent-foundations python -m pytest tests/unit/chat/test_runner.py tests/integration/test_agent_loop.py tests/integration/test_chat_planning_tools.py tests/unit/tools/patch tests/tools/patch tests/unit/tools/command -q` | 0 | 178 passed (targeted) |
| Ruff | scoped files in Task 33 Additional gates | 0 | All checks passed (after wrapping locked sentences with implicit string concat; characters unchanged) |
| mypy | scoped files in Task 33 Additional gates | 0 | Success: no issues found in 7 source files |
| Frontend test, typecheck or build | not in contract | | not-run |
| Package or dependency check | not in contract | | not-run |
| `git diff --check` | `git diff --check` | 0 | no whitespace errors (CRLF warnings only) |

## 6. Scope Audit

- Final changed files (this Task):
  - `src/agent_foundations/runtime/coding_prompt.py` (new)
  - `src/agent_foundations/cli/main.py`
  - `src/agent_foundations/tools/filesystem/read_file.py`
  - `src/agent_foundations/tools/patch/validate_patch.py`
  - `src/agent_foundations/tools/command/run_command.py`
  - `src/agent_foundations/tools/command/read_output.py`
  - `tests/unit/runtime/test_coding_prompt.py` (new)
  - `tests/unit/tools/patch/test_validate_patch.py`
  - `docs/task-evidence/phase-2d-task-17.md`
- Unrelated changes introduced: no
- Existing user changes preserved: yes
- Secrets or generated artifacts detected: no
- Commit, push, deployment, paid API call, or next Task performed: no

## 7. Gaps and Limitations

- Checks not run and reasons: Full suite not-required; no frontend/Docker/paid API in contract
- Environment warnings: FastAPI TestClient Starlette/`httpx` deprecation on planning tools test; `git diff --check` CRLF working-copy warnings
- Process evidence gaps: none for pytest Red→Green; ruff E501 wrap did not change locked sentence characters
- Remaining risks: prompts and descriptions cannot replace Runtime validation (Task 30 hashes, Task 31 intercepts, argv whitelist)

## 8. Handoff Summary

- Current verification status: **pass** (targeted verification; not full suite). Reviewer-fresh: Target 13 passed; Affected 178 passed; ruff/mypy 7 files passed; `git diff --check` exit 0
- TDD process evidence: **complete**. Reviewer fresh checks prove current green, not the historical Red→Green sequence
- User acceptance: recorded in §9
- Reviewer acceptance: pass (current implementation, targeted) in the reviewer session that preceded this confirmation
- Reviewer findings retained: P3 Tool descriptions live on shared Tool classes (CLI/Eval also see them); Chat factory test uses `inspect.getsource` for `CONTROLLED_CODING_AGENT_PROMPT`
- Recommended reviewer commands (already run for this Task):

```text
conda run -n agent-foundations python -m pytest tests/unit/runtime/test_coding_prompt.py tests/unit/tools/patch/test_validate_patch.py tests/tools/filesystem -q
conda run -n agent-foundations python -m pytest tests/unit/chat/test_runner.py tests/integration/test_agent_loop.py tests/integration/test_chat_planning_tools.py tests/unit/tools/patch tests/tools/patch tests/unit/tools/command -q
conda run -n agent-foundations python -m ruff check src/agent_foundations/runtime/coding_prompt.py src/agent_foundations/cli/main.py src/agent_foundations/tools/filesystem/read_file.py src/agent_foundations/tools/patch/validate_patch.py src/agent_foundations/tools/command/run_command.py src/agent_foundations/tools/command/read_output.py tests/unit/runtime/test_coding_prompt.py
conda run -n agent-foundations python -m mypy src/agent_foundations/runtime/coding_prompt.py src/agent_foundations/cli/main.py src/agent_foundations/tools/filesystem/read_file.py src/agent_foundations/tools/patch/validate_patch.py src/agent_foundations/tools/command/run_command.py src/agent_foundations/tools/command/read_output.py tests/unit/runtime/test_coding_prompt.py
git diff --check
```

## 9. User Acceptance

- Confirmed at: 2026-08-29 +08:00.
- Exact user confirmation: `确认「Task 33 / phase-2d-task-17 用户验收通过」`.
- Result: Follow-on Task 33 / `phase-2d-task-17` (Prompt / Schema / Tool descriptions) is user-accepted for the current implementation. This is **not** plan body Task 17. Independent reviewer re-ran the targeted contract (13 passed on Target; 178 passed on affected regression).
- Full suite note: this confirmation accepts **targeted verification passed**. It does not claim `full suite passed`, does not accept Task 25 as complete, does not accept paid 3×3, and does not mark user Phase 2 complete. Plan Task 25 Step 10 and Step 11 remain unchecked.
- TDD note: executor Red is internally consistent and marked complete; this confirmation does not independently witness the original Red→Green sequence.
- Boundary: this confirmation records `phase-2d-task-17` acceptance only. Task 34 / `phase-2d-task-18` still requires its own explicit single-Task executor authorization. No commit, push, paid API rerun, Phase 2 complete checkbox, or Phase 3 is authorized by this confirmation. Reviewer P3 findings are retained and do not require immediate rework from this confirmation. Prompts and Tool descriptions do not replace Runtime validation.

