# Task Evidence: phase-1d-task-1-ads-remediation

## 1. Identity

- Task ID: `phase-1d-task-1-ads-remediation`
- Authoritative plan or task spec: Phase 1D Task 1 remediation — reject Windows ADS and control characters in `RelativeTracePath` (`docs/agent-plans/2026-08-02-phase-1d-interactive-chat-ui-plan.md` Task 1; user remediation brief)
- Evidence status: completed
- TDD required: yes
- Started at: 2026-08-04T20:21+08:00

## 2. Pre-change Snapshot

- Branch or revision: `main` @ `1d32991` (working tree dirty)
- `git status --short`:

```text
 M .gitignore
 M AGENTS.md
 M README.md
 M docs/agent-plans/2026-07-21-phase-1b-readonly-agent-plan.md
 M docs/agent-plans/2026-07-21-phase-1c-trace-viewer-plan.md
 M pyproject.toml
 M src/agent_foundations/domain/_freeze.py
 M src/agent_foundations/tools/registry.py
 M tests/unit/tools/test_registry.py
?? .env.example
?? CLAUDE.md
?? docs/agent-plans/2026-08-02-phase-1d-interactive-chat-ui-design.md
?? docs/agent-plans/2026-08-02-phase-1d-interactive-chat-ui-plan.md
?? docs/learning-notes/02-readonly-agent.md
?? docs/learning-notes/03-observability.md
?? docs/task-evidence/
?? package-lock.json
?? package.json
?? src/agent_foundations/chat/
?? src/agent_foundations/cli/
?? src/agent_foundations/providers/openai_compatible.py
?? src/agent_foundations/runtime/
?? src/agent_foundations/tools/filesystem/
?? src/agent_foundations/viewer/
?? tests/e2e/
?? tests/fixtures/
?? tests/integration/
?? tests/unit/chat/
?? tests/unit/providers/__init__.py
?? tests/unit/providers/test_openai_compatible.py
?? tests/unit/runtime/
?? tests/unit/tools/filesystem/
?? tests/unit/viewer/
?? tests/viewer/
?? tsconfig.json
```

- Existing user changes that must be preserved: all listed modified and untracked files above (Phase 1B/1C/1D work)
- Intended modification scope:
  - `tests/unit/chat/test_models.py`
  - `src/agent_foundations/chat/models.py`
  - `docs/task-evidence/phase-1d-task-1-ads-remediation.md`
- Expected rollback: revert only the three files above; do not touch unrelated working-tree changes

## 3. Red

- Recorded before production-code changes: yes
- Time: 2026-08-04T20:22+08:00
- Test file and test name:
  - `tests/unit/chat/test_models.py::test_run_trace_path_rejects_ads_and_control_characters[...]`
  - `tests/unit/chat/test_models.py::test_run_trace_path_model_copy_rejects_ads_and_control_characters[...]`
- Command:

```powershell
conda run -n agent-foundations python -m pytest tests/unit/chat/test_models.py -q
```

- Exit code: 1
- Relevant verbatim output:

```text
.....FFFFFFFFFFFF..............                                          [100%]
================================== FAILURES ===================================
_ test_run_trace_path_rejects_ads_and_control_characters[traces/id.jsonl:secret] _
...
E       Failed: DID NOT RAISE <class 'pydantic_core._pydantic_core.ValidationError'>
...
=========================== short test summary info ===========================
FAILED ...::test_run_trace_path_rejects_ads_and_control_characters[traces/id.jsonl:secret]
FAILED ...::test_run_trace_path_rejects_ads_and_control_characters[traces/id.jsonl::$DATA]
FAILED ...::test_run_trace_path_rejects_ads_and_control_characters[traces/id.jsonl\x00hidden]
FAILED ...::test_run_trace_path_rejects_ads_and_control_characters[traces/id.jsonl\nhidden]
FAILED ...::test_run_trace_path_rejects_ads_and_control_characters[traces/id.jsonl\rhidden]
FAILED ...::test_run_trace_path_rejects_ads_and_control_characters[traces/id.jsonl\thidden]
FAILED ...::test_run_trace_path_model_copy_rejects_ads_and_control_characters[traces/id.jsonl:secret]
FAILED ...::test_run_trace_path_model_copy_rejects_ads_and_control_characters[traces/id.jsonl::$DATA]
FAILED ...::test_run_trace_path_model_copy_rejects_ads_and_control_characters[traces/id.jsonl\x00hidden]
FAILED ...::test_run_trace_path_model_copy_rejects_ads_and_control_characters[traces/id.jsonl\nhidden]
FAILED ...::test_run_trace_path_model_copy_rejects_ads_and_control_characters[traces/id.jsonl\rhidden]
FAILED ...::test_run_trace_path_model_copy_rejects_ads_and_control_characters[traces/id.jsonl\thidden]
12 failed, 19 passed in 0.42s
```

- Expected failure category: missing validation — ADS (`:`) and control characters (`Cc`) accepted by `_relative_trace_path`
- Why this failure demonstrates the missing behavior: `RunRecord` construction and `model_copy(update=...)` both accept `traces/id.jsonl:secret`, `::$DATA`, and `\x00`/`\n`/`\r`/`\t` without raising `ValidationError`
- If unavailable, why it cannot be verified: n/a

## 4. Green

- Production files changed: `src/agent_foundations/chat/models.py` (`_relative_trace_path` rejects `:` and Unicode category `Cc` before Path normalization)
- Time: 2026-08-04T20:23+08:00
- Command:

```powershell
conda run -n agent-foundations python -m pytest tests/unit/chat/test_models.py -q
```

- Exit code: 0
- Relevant verbatim output:

```text
...............................                                          [100%]
31 passed in 0.18s
```

## 5. Regression and Quality Gates

| Check | Command | Exit code | Result |
|---|---|---:|---|
| Target tests | `conda run -n agent-foundations python -m pytest tests/unit/chat/test_models.py -q` | 0 | `31 passed in 0.18s` |
| Chat unit regression | `conda run -n agent-foundations python -m pytest tests/unit/chat -q` | 0 | `108 passed in 1.86s` |
| Full pytest | `conda run -n agent-foundations python -m pytest -q` | 0 | `444 passed, 1 warning in 8.11s` |
| Ruff | `conda run -n agent-foundations python -m ruff check src/agent_foundations/chat/models.py tests/unit/chat/test_models.py` | 0 | `All checks passed!` |
| mypy | `conda run -n agent-foundations python -m mypy src tests` | 0 | `Success: no issues found in 71 source files` |
| Frontend test, typecheck or build | n/a | | not applicable |
| Package or dependency check | n/a | | not run (no dependency change) |
| `git diff --check` | `git diff --check` | 0 | no whitespace errors; CRLF warnings only on unrelated tracked files |

### Verbatim outputs

Chat unit regression (2026-08-04T20:24+08:00):

```text
........................................................................ [ 66%]
....................................                                     [100%]
108 passed in 1.86s
```

Full pytest (2026-08-04T20:24+08:00):

```text
444 passed, 1 warning in 8.11s
```

Warning (environment/deprecation, not a test failure):

```text
StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
```

Ruff (after import-order fix):

```text
All checks passed!
```

mypy:

```text
Success: no issues found in 71 source files
```

`git diff --check`:

```text
warning: in the working copy of '.gitignore', LF will be replaced by CRLF the next time Git touches it
(... additional CRLF warnings on unrelated tracked files ...)
```

No whitespace error lines were reported.

## 6. Scope Audit

- Final changed files (this remediation):
  - `src/agent_foundations/chat/models.py`
  - `tests/unit/chat/test_models.py`
  - `docs/task-evidence/phase-1d-task-1-ads-remediation.md`
- Unrelated changes introduced: no
- Existing user changes preserved: yes
- Secrets or generated artifacts detected: no
- Commit, push, deployment, paid API call, or next Task performed: no
- Task 6 files modified: no

## 7. Gaps and Limitations

- Checks not run and reasons: frontend/package gates not applicable (no frontend or dependency change)
- Environment warnings: Starlette/httpx deprecation warning in full pytest; git CRLF warnings on unrelated tracked files
- Process evidence gaps: none for this remediation (Red recorded before production change)
- Remaining risks: Windows drive letters already rejected via `path.drive`; colon rejection also covers ADS forms. Reviewer should independently confirm.

## 8. Handoff Summary

- Current verification status: pass
- TDD process evidence: complete
- Recommended reviewer commands:

```powershell
conda run -n agent-foundations python -m pytest tests/unit/chat/test_models.py -q
conda run -n agent-foundations python -m pytest tests/unit/chat -q
conda run -n agent-foundations python -m ruff check src/agent_foundations/chat/models.py tests/unit/chat/test_models.py
conda run -n agent-foundations python -m mypy src tests
git diff --check
```
