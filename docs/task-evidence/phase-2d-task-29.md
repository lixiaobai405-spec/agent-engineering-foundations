# Task Evidence: phase-2d-task-29

## 1. Identity

- Task ID: `phase-2d-task-29`
- Authoritative plan or task spec: `docs/agent-plans/2026-09-08-phase-2-post-3x3-reliability-fixes-plan.md` Task 45 (2026-09-08 lock revision)
- Evidence status: completed
- TDD required: yes
- Started at: 2026-09-08 (Asia/Shanghai)

## 2. Pre-change Snapshot

- Branch or revision: `codex/phase-2-next` @ `14ece4e`
- `git status --short`: dirty tree preserved (hundreds of pre-existing modified/untracked paths including Task 44 overlay, Chat static, plans, evidence). Not reset/restored/cleaned.
- Existing user changes that must be preserved: entire dirty tree
- Intended modification scope: `src/agent_foundations/domain/tool.py` (optional `ToolCall.argument_parse_error` only); `providers/openai_compatible.py`; `providers/resilient.py`; `runtime/loop.py`; the three target test files; this evidence; plan Task 45 Done when. Chat runner tests only if they go red because loop no longer raises `InvalidModelResponseError`.
- Expected rollback: restore those files only. Do not restore the rest of the dirty tree.

## 3. Red

- Recorded before production-code changes: yes
- Time: 2026-09-08 (Asia/Shanghai)
- Test file and test name: `test_malformed_tool_arguments_return_parse_error_call`, `test_invalid_arguments_json_includes_position_and_window`, `test_invalid_model_response_retries_*`, `test_invalid_provider_raw_response_does_not_mask_original_error`, `test_persistent_invalid_model_response_stops_at_max_steps`, `test_argument_parse_error_is_tool_failure_without_execute`
- Command: `D:\anaconda\envs\agent-foundations\python.exe -m pytest tests/unit/providers/test_openai_compatible.py tests/unit/providers/test_resilient.py tests/integration/test_agent_loop.py -q --tb=short`
- Exit code: 1
- Relevant verbatim output:

```text
.........FFF.....FF..............FFF..........................           [100%]
FAILED tests/unit/providers/test_openai_compatible.py::test_malformed_tool_arguments_return_parse_error_call[invalid-json-arguments]
E   agent_foundations.domain.errors.InvalidModelResponseError: provider returned an invalid response
FAILED tests/unit/providers/test_openai_compatible.py::test_malformed_tool_arguments_return_parse_error_call[non-object-arguments]
E   agent_foundations.domain.errors.InvalidModelResponseError: provider returned an invalid response
FAILED tests/unit/providers/test_openai_compatible.py::test_invalid_arguments_json_includes_position_and_window
E   agent_foundations.domain.errors.InvalidModelResponseError: provider returned an invalid response
FAILED tests/unit/providers/test_resilient.py::test_invalid_model_response_retries_then_raises_to_loop
E   assert 1 == 3
FAILED tests/unit/providers/test_resilient.py::test_invalid_model_response_retries_until_success
E   InvalidModelResponseError: provider returned an invalid response
FAILED tests/integration/test_agent_loop.py::test_invalid_provider_raw_response_does_not_mask_original_error
E   InvalidModelResponseError: invalid response
FAILED tests/integration/test_agent_loop.py::test_persistent_invalid_model_response_stops_at_max_steps
E   InvalidModelResponseError: invalid response
FAILED tests/integration/test_agent_loop.py::test_argument_parse_error_is_tool_failure_without_execute
E   AssertionError: assert 'UnknownToolError' == 'INVALID_TOOL_JSON'
8 failed, 54 passed in 3.22s
```

- Expected failure category: missing target behavior
- Why this failure demonstrates the missing behavior: adapter still wrapped illegal tool arguments as `InvalidModelResponseError`; Resilient did not retry that error; loop still failed the session; a persisted parse-error `ToolCall` still went through `validate_call` (`UnknownToolError`) instead of `INVALID_TOOL_JSON`.
- If unavailable, why it cannot be verified:

Note: `ToolCall.argument_parse_error` was added before this Red so the loop test could construct the call. That field alone did not make any of the eight failures pass.

## 4. Green

- Production files changed: `src/agent_foundations/domain/tool.py`, `src/agent_foundations/providers/openai_compatible.py`, `src/agent_foundations/providers/resilient.py`, `src/agent_foundations/runtime/loop.py`
- Command: `D:\anaconda\envs\agent-foundations\python.exe -m pytest tests/unit/providers/test_openai_compatible.py tests/unit/providers/test_resilient.py tests/integration/test_agent_loop.py -q --tb=short`
- Exit code: 0
- Relevant verbatim output:

```text
..............................................................           [100%]
62 passed in 2.15s
```

After ruff line-length test edits, the same target set plus chat runner still passed (see §5).

## 5. Regression and Quality Gates

| Check | Command | Exit code | Result |
|---|---|---:|---|
| Target tests | `pytest tests/unit/providers/test_openai_compatible.py tests/unit/providers/test_resilient.py tests/integration/test_agent_loop.py -q` | 0 | pass (62 passed; later 74 with runner in combined affected run) |
| Regression tests | `pytest tests/integration/test_agent_loop.py tests/unit/providers/test_openai_compatible.py tests/unit/chat/test_runner.py -q` | 0 | pass (63 then 74 in combined rerun; `test_runner.py` not edited this Task) |
| Ruff | `ruff check` on Task 45 production + target test files | 0 | pass |
| mypy | `mypy` on `tool.py` `openai_compatible.py` `resilient.py` `loop.py` | 0 | pass |
| Frontend test, typecheck or build | not-required | | not-run |
| Package or dependency check | not-required | | not-run |
| `git diff --check` | scoped to Task 45 files | 0 | pass (CRLF warnings only) |

Combined affected rerun after ruff/mypy fixes: 74 passed in 2.53s, exit 0. Targeted verification passed; not full suite.

## 6. Scope Audit

- Final changed files:
  - `src/agent_foundations/domain/tool.py`
  - `src/agent_foundations/providers/openai_compatible.py`
  - `src/agent_foundations/providers/resilient.py`
  - `src/agent_foundations/runtime/loop.py`
  - `tests/unit/providers/test_openai_compatible.py`
  - `tests/unit/providers/test_resilient.py`
  - `tests/integration/test_agent_loop.py`
  - `docs/task-evidence/phase-2d-task-29.md`
  - `docs/agent-plans/2026-09-08-phase-2-post-3x3-reliability-fixes-plan.md` (Task 45 Done when only)
- Unrelated changes introduced: no
- Existing user changes preserved: yes (`tests/unit/chat/test_runner.py` remains pre-existing dirty; not edited this Task)
- Secrets or generated artifacts detected: no
- Commit, push, deployment, paid API call, or next Task performed: none. Task 46/47/48 not started. Task 25 Step 10/11 not ticked.

## 7. Gaps and Limitations

- Checks not run and reasons: full pytest -q not-required; no docker; no paid API
- Environment warnings: git CRLF `LF will be replaced by CRLF` on some touched files
- Process evidence gaps: none for the recorded Red/Green
- Remaining risks: Chat UI still has no Stop; Durable interrupt still unsynced (Task 47/48). A-path TOOL content is a short snippet, not json_repair.

## 8. Handoff Summary

- Current verification status: **pass** (targeted verification; not full suite). Reviewer-fresh: Target 62 passed; Affected (contract three files) 63 passed; union of target+affected 74 passed; ruff / mypy / `git diff --check` exit 0. Reviewer probe: mixed valid+invalid arguments in one completion parsed per call; window constant 80; full broken JSON not copied into the TOOL string.
- TDD process evidence: **complete**. Reviewer fresh checks prove current green, not the historical Red→Green sequence
- User acceptance: recorded in §9
- Reviewer acceptance: pass (current implementation, targeted) in the reviewer session that preceded this confirmation
- Reviewer findings retained: P3 no adapter-complete→loop end-to-end test and no Durable crash-resume case for `argument_parse_error`; mixed A-path lacks a unit test (probe passed); window test hits an 8-character snippet rather than asserting ≤80; `ToolCall.argument_parse_error` existed before the recorded Red (executor disclosed; the eight failures were still missing-behavior)
- Recommended reviewer commands (already run for this Task):

```powershell
$env:PYTHONIOENCODING = 'utf-8'
$py = 'D:\anaconda\envs\agent-foundations\python.exe'
& $py -m pytest tests/unit/providers/test_openai_compatible.py tests/unit/providers/test_resilient.py tests/integration/test_agent_loop.py -q
& $py -m pytest tests/integration/test_agent_loop.py tests/unit/providers/test_openai_compatible.py tests/unit/chat/test_runner.py -q
```

## 9. User Acceptance

- Confirmed at: 2026-09-08 +08:00.
- Exact user confirmation: `确认「Task 45 / phase-2d-task-29 用户验收通过」`.
- Result: malformed tool JSON Task 45 / `phase-2d-task-29` (A-path illegal `arguments` → recoverable `INVALID_TOOL_JSON` tool failure with position/window; B-path empty/missing id|name → `InvalidModelResponseError` retryable within existing max 3, loop `model.response.invalid` + `next_step+1`, no `session.failed`) is user-accepted for the current implementation. Independent reviewer re-ran the targeted contract (Target 62 passed; Affected 63 passed; union 74 passed; ruff/mypy/`git diff --check` exit 0).
- Full suite note: this confirmation accepts **targeted verification passed**. It does not claim `full suite passed`, does not accept plan-body Task 25 as complete, does not accept paid 3×3, and does not mark user Phase 2 complete. Plan Task 25 Step 10 and Step 11 remain unchecked.
- TDD note: executor Red is internally consistent and marked complete (8 failed / 54 passed: adapter still raised `InvalidModelResponseError`; Resilient did not retry it; loop still `session.failed`; parse-error still `UnknownToolError`). This confirmation does not independently witness the original Red→Green sequence.
- Boundary: this confirmation records `phase-2d-task-29` acceptance only. Task 46–48 still require separate explicit authorization. Paid 3×3 still requires a separate explicit authorization and remains Task 25 Step 10. No commit, push, paid API rerun, Phase 2 complete checkbox, or Phase 3 is authorized by this confirmation. Reviewer P3 findings are retained and do not require immediate rework from this confirmation.
