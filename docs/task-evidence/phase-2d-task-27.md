# Task Evidence: phase-2d-task-27

## 1. Identity

- Task ID: `phase-2d-task-27`
- Authoritative plan or task spec: `docs/agent-plans/2026-09-08-phase-2-pre-3x3-gap-remediation-plan.md` Task 43 plus the user-confirmed executor prompt
- Evidence status: user-accepted / current implementation pass; TDD process evidence complete
- TDD required: yes
- Started at: 2026-09-08 (Asia/Shanghai)

## 2. Pre-change Snapshot

- Branch or revision: `codex/phase-2-next` at `14ece4e` (not `main`)
- `git status --short` (this Task files before production edits): `M src/agent_foundations/tools/filesystem/read_file.py`, `?? src/agent_foundations/tools/patch/applier.py`, `?? src/agent_foundations/tools/patch/structured.py`, `?? tests/tools/patch/test_structured_validate_patch.py`. Broader dirty tree (Phase 2A–2D, Task 30–42, static/chat) already present.
- Existing user changes that must be preserved: all pre-existing modified and untracked files at Task start. Do not `restore`/`reset`/`clean`.
- Intended modification scope: one shared UTF-8 line-text helper used by `read_file`, `structured._line_texts`, `validator._file_lines_for_hunks`, and `applier._lines` / write-back. Do not change PathPolicy, gate_id, Policy, Approval, unified diff headers, diff vs changes, parser.py, web/chat, static/chat.
- Expected rollback: revert only this Task’s Python/tests/evidence; do not revert the rest of the dirty tree.
- Interpreter: Windows `$env:PYTHONIOENCODING='utf-8'`; pytest/ruff/mypy via `D:\anaconda\envs\agent-foundations\python.exe`.

## 3. Red

- Recorded before production-code changes: yes
- Time: 2026-09-08 (Asia/Shanghai)
- Test file and test name: `tests/tools/patch/test_structured_validate_patch.py` (CRLF match / validate / no-trailing-newline)
- Command: `$env:PYTHONIOENCODING='utf-8'; D:\anaconda\envs\agent-foundations\python.exe -m pytest tests/tools/patch/test_structured_validate_patch.py::test_structured_matching_lines_equal_read_lines_on_crlf tests/tools/patch/test_structured_validate_patch.py::test_crlf_read_lines_validate_and_apply_preserves_crlf tests/tools/patch/test_structured_validate_patch.py::test_lf_without_trailing_newline_apply_keeps_lf tests/tools/patch/test_structured_validate_patch.py::test_crlf_without_trailing_newline_apply_keeps_crlf tests/unit/tools/filesystem/test_read_file.py::test_read_lines_crlf_has_no_carriage_returns tests/unit/tools/filesystem/test_read_file.py::test_read_lines_empty_file_is_zero_lines -q --tb=short`
- Exit code: 1
- Relevant verbatim output:

```text
assert ('alpha\r', 'beta\r') == ('alpha', 'beta')
AssertionError: PATCH_VALIDATION_ERROR
  ToolResult(success=False, content='old_lines mismatch', error_code='PATCH_VALIDATION_ERROR', ...)
AssertionError: PATCH_VALIDATION_ERROR
  ToolResult(success=False, content='newline state mismatch', error_code='PATCH_VALIDATION_ERROR', ...)
4 failed, 2 passed
```

`read_lines` on CRLF and empty file already passed (existing `splitlines()`). Valid Red is structured `split("\n")` leaving `\r`, then `validate_patch(changes=...)` with `old_lines` from `read_lines`. LF file without trailing newline failed later as `newline state mismatch` (compiled diff has no `\\ No newline at end of file`).

- Expected failure category: assertion failure from CRLF line-text mismatch / PATCH_VALIDATION_ERROR
- Why this failure demonstrates the missing behavior: `read_file` strips `\r`; structured matching lines keep `\r`; filling `old_lines` from `read_lines` cannot validate. Not import/syntax errors.
- If unavailable, why it cannot be verified: n/a

## 4. Green

- Production files changed:
  - `src/agent_foundations/tools/utf8_lines.py` — single helper: `utf8_file_lines` / `utf8_line_texts` / `utf8_newline` / `join_utf8_file_lines`
  - `src/agent_foundations/tools/filesystem/read_file.py` — execute + `read_lines` use `utf8_line_texts`
  - `src/agent_foundations/tools/patch/structured.py` — `_line_texts` wraps helper; compile emits `\\ No newline at end of file` when the last line had no newline
  - `src/agent_foundations/tools/patch/validator.py` — `_file_lines_for_hunks` uses helper
  - `src/agent_foundations/tools/patch/applier.py` — `_lines` uses helper; write-back joins with original `utf8_newline`
- Command: `$env:PYTHONIOENCODING='utf-8'; D:\anaconda\envs\agent-foundations\python.exe -m pytest tests/tools/patch/test_structured_validate_patch.py tests/tools/filesystem/test_read_file_metadata.py tests/unit/tools/filesystem/test_read_file.py tests/unit/tools/patch/test_applier.py tests/unit/tools/patch/test_validate_patch.py -q`
- Exit code: 0
- Relevant verbatim output:

```text
...............................                                          [100%]
31 passed in 0.81s
```

CRLF apply result: `b"alpha\r\nbeta\r\n"` → `old_lines` from `read_lines` → second line `gamma` → disk `b"alpha\r\ngamma\r\n"`.

## 5. Regression and Quality Gates

| Check | Command | Exit code | Result |
|---|---|---:|---|
| Target tests | `$env:PYTHONIOENCODING='utf-8'; D:\anaconda\envs\agent-foundations\python.exe -m pytest tests/tools/patch/test_structured_validate_patch.py tests/tools/filesystem/test_read_file_metadata.py tests/unit/tools/filesystem/test_read_file.py tests/unit/tools/patch/test_applier.py tests/unit/tools/patch/test_validate_patch.py -q` | 0 | 31 passed |
| Regression tests | `$env:PYTHONIOENCODING='utf-8'; D:\anaconda\envs\agent-foundations\python.exe -m pytest tests/tools/patch tests/tools/filesystem tests/unit/tools/patch tests/unit/tools/filesystem tests/integration/test_controlled_patch_flow.py tests/integration/test_patch_crash_recovery.py -q` | 0 | 145 passed, 10 warnings |
| Ruff | `$env:PYTHONIOENCODING='utf-8'; D:\anaconda\envs\agent-foundations\python.exe -m ruff check src/agent_foundations/tools/utf8_lines.py src/agent_foundations/tools/filesystem/read_file.py src/agent_foundations/tools/patch/structured.py src/agent_foundations/tools/patch/validator.py src/agent_foundations/tools/patch/applier.py tests/tools/patch/test_structured_validate_patch.py tests/unit/tools/filesystem/test_read_file.py` | 0 | All checks passed |
| mypy | `$env:PYTHONIOENCODING='utf-8'; D:\anaconda\envs\agent-foundations\python.exe -m mypy src/agent_foundations/tools/utf8_lines.py src/agent_foundations/tools/filesystem/read_file.py src/agent_foundations/tools/patch/structured.py src/agent_foundations/tools/patch/validator.py src/agent_foundations/tools/patch/applier.py` | 0 | Success: no issues found in 5 source files |
| Frontend test, typecheck or build | not in contract; `npm run build:chat` forbidden | | not-run |
| Package or dependency check | not in contract | | not-run |
| `git diff --check` | `git diff --check` | 0 | pass (CRLF working-copy warnings only; no whitespace errors) |

Targeted verification passed. Full suite not-required and not run.

## 6. Scope Audit

- Final changed files (this Task):
  - Create: `src/agent_foundations/tools/utf8_lines.py`
  - Create: `docs/task-evidence/phase-2d-task-27.md`
  - Modify: `src/agent_foundations/tools/filesystem/read_file.py`
  - Modify: `src/agent_foundations/tools/patch/structured.py`
  - Modify: `src/agent_foundations/tools/patch/validator.py`
  - Modify: `src/agent_foundations/tools/patch/applier.py`
  - Modify: `tests/tools/patch/test_structured_validate_patch.py`
  - Modify: `tests/unit/tools/filesystem/test_read_file.py`
  - Modify: `docs/agent-plans/2026-09-08-phase-2-pre-3x3-gap-remediation-plan.md` (status only; Task 43 contract body not rewritten)
- Unrelated changes introduced: no. PathPolicy, gate_id, Policy, Approval, unified diff headers, diff vs changes, parser.py, web/chat, static/chat untouched. No `npm run build:chat`.
- Existing user changes preserved: yes
- Secrets or generated artifacts detected: no
- Commit, push, deployment, paid API call, or next Task performed: no

## 7. Gaps and Limitations

- Checks not run and reasons: full suite, Docker, Playwright, npm, paid 3×3 — not in contract / not authorized.
- Environment warnings: sqlite3 datetime adapter DeprecationWarning on integration tests; `git diff --check` CRLF warnings on pre-existing files.
- Process evidence gaps: `read_lines` on CRLF/empty already passed during Red (existing `splitlines()`). Valid Red is structured `\r` mismatch and `PATCH_VALIDATION_ERROR`.
- Remaining risks: mixed newlines and old Mac `\r` remain out of scope. Reviewer should re-run the verification contract.

## 8. Handoff Summary

- Current verification status: **pass** (targeted verification; not full suite). Reviewer-fresh: Target 31 passed; Affected 145 passed; ruff / mypy / `git diff --check` exit 0
- TDD process evidence: **complete**. Reviewer fresh checks prove current green, not the historical Red→Green sequence
- User acceptance: recorded in §9
- Reviewer acceptance: pass (current implementation, targeted) in the reviewer session that preceded this confirmation
- Reviewer findings retained: P3 `utf8_newline` treats any `\r\n` as whole-file CRLF (mixed newlines remain out of scope); `splitlines(keepends=True)` also splits Unicode line separators; structured compile copies original trailing-newline state onto the updated file; Docker applier writes host-prepared bytes and `-m docker` was not re-run
- Recommended reviewer commands (already run for this Task):

```text
$env:PYTHONIOENCODING='utf-8'
D:\anaconda\envs\agent-foundations\python.exe -m pytest tests/tools/patch/test_structured_validate_patch.py tests/tools/filesystem/test_read_file_metadata.py tests/unit/tools/filesystem/test_read_file.py tests/unit/tools/patch/test_applier.py tests/unit/tools/patch/test_validate_patch.py -q
D:\anaconda\envs\agent-foundations\python.exe -m pytest tests/tools/patch tests/tools/filesystem tests/unit/tools/patch tests/unit/tools/filesystem tests/integration/test_controlled_patch_flow.py tests/integration/test_patch_crash_recovery.py -q
D:\anaconda\envs\agent-foundations\python.exe -m ruff check src/agent_foundations/tools/utf8_lines.py src/agent_foundations/tools/filesystem/read_file.py src/agent_foundations/tools/patch/structured.py src/agent_foundations/tools/patch/validator.py src/agent_foundations/tools/patch/applier.py tests/tools/patch/test_structured_validate_patch.py tests/unit/tools/filesystem/test_read_file.py
D:\anaconda\envs\agent-foundations\python.exe -m mypy src/agent_foundations/tools/utf8_lines.py src/agent_foundations/tools/filesystem/read_file.py src/agent_foundations/tools/patch/structured.py src/agent_foundations/tools/patch/validator.py src/agent_foundations/tools/patch/applier.py
git diff --check
```

## 9. User Acceptance

- Confirmed at: 2026-09-08 +08:00.
- Exact user confirmation: `确认「Task 43 / phase-2d-task-27 用户验收通过」`.
- Result: Pre-3×3 gap Task 43 / `phase-2d-task-27` (`read_file` and structured patch share one UTF-8 line-text helper; apply preserves original `\r\n` or `\n`) is user-accepted for the current implementation. Independent reviewer re-ran the targeted contract (Target 31 passed; Affected 145 passed; ruff / mypy / `git diff --check` exit 0).
- Full suite note: this confirmation accepts **targeted verification passed**. It does not claim `full suite passed`, does not accept plan-body Task 25 as complete, does not accept paid 3×3, and does not mark user Phase 2 complete. Plan Task 25 Step 10 and Step 11 remain unchecked.
- TDD note: executor Red is internally consistent and marked complete (`read_lines` on CRLF/empty was already green; valid Red was structured `\r` mismatch and `PATCH_VALIDATION_ERROR`). This confirmation does not independently witness the original Red→Green sequence.
- Boundary: this confirmation records `phase-2d-task-27` acceptance only. The gap-remediation plan has **no Task 44**. Paid 3×3 still requires a separate explicit authorization and remains Task 25 Step 10. No commit, push, paid API rerun, Phase 2 complete checkbox, or Phase 3 is authorized by this confirmation. Reviewer P3 findings are retained and do not require immediate rework from this confirmation. Mixed newlines and legacy Mac `\r`-only files remain out of scope.
