# Task Evidence: phase-1d-task-6-exception-boundary-remediation

## 1. Identity

- Task ID: `phase-1d-task-6-exception-boundary-remediation`
- Authoritative plan or task spec: Phase 1D Task 6 exception-boundary remediation (user brief; parent Task 6 in `docs/agent-plans/2026-08-02-phase-1d-interactive-chat-ui-plan.md`)
- Evidence status: ready-for-review
- TDD required: yes
- Started at: 2026-08-04T21:04+08:00

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

- Existing user changes that must be preserved: all listed Phase 1B/1C/1D modified and untracked files
- Intended modification scope:
  - `src/agent_foundations/chat/runner.py`
  - `tests/unit/chat/test_runner.py`
  - `docs/task-evidence/phase-1d-task-6-exception-boundary-remediation.md`
- Expected rollback: revert only the three files above
- Parent Task 6 evidence: `docs/task-evidence/phase-1d-task-6.md` (TDD complete; current implementation partial due to this boundary gap)

## 3. Red

- Recorded before production-code changes: yes
- Time: 2026-08-04T21:05+08:00
- Test file and test name: `tests/unit/chat/test_runner.py::test_runner_runtime_factory_failure_marks_failed_safely`
- Command: `conda run -n agent-foundations python -m pytest tests/unit/chat/test_runner.py::test_runner_runtime_factory_failure_marks_failed_safely -q`
- Exit code: `1`
- Relevant verbatim output:

```text
F                                                                        [100%]
================================== FAILURES ===================================
___________ test_runner_runtime_factory_failure_marks_failed_safely ___________
...
>       await runner.run_turn(
...
src\agent_foundations\chat\runner.py:119: in run_turn
    loop = self._runtime_factory(conversation, event_sink, tool_executor)
...
>       raise RuntimeError("do-not-leak-secret")
E       RuntimeError: do-not-leak-secret
FAILED tests/unit/chat/test_runner.py::test_runner_runtime_factory_failure_marks_failed_safely
1 failed in 0.58s
```

- Expected failure category: missing exception boundary after `queued → running` (ordinary exception propagates; run left `running`; no safe `run.failed`)
- Why this failure demonstrates the missing behavior: `runtime_factory` raises outside `try`, so `run_turn` does not call `fail_run` / publish `RUN_FAILED` and does not return safely
- If unavailable, why it cannot be verified: n/a

## 4. Green

- Production files changed: `src/agent_foundations/chat/runner.py` — after successful `queued → running`, expand `try` to cover `run.started`, redactor/projector/sinks, `tool_executor_factory`, `runtime_factory`, and `AgentLoop.run()`; retain CancelledError → interrupt+re-raise and ordinary Exception → fail_run + safe `run.failed` + return
- Command: `conda run -n agent-foundations python -m pytest tests/unit/chat/test_runner.py::test_runner_runtime_factory_failure_marks_failed_safely -q`
- Exit code: `0`
- Relevant verbatim output:

```text
.                                                                        [100%]
1 passed in 1.03s
```

## 5. Regression and Quality Gates

| Check | Command | Exit code | Result |
|---|---|---:|---|
| Target test | `conda run -n agent-foundations python -m pytest tests/unit/chat/test_runner.py::test_runner_runtime_factory_failure_marks_failed_safely -q` | 0 | 1 passed |
| Target + supervisor + agent_loop | `conda run -n agent-foundations python -m pytest tests/unit/chat/test_runner.py tests/unit/chat/test_supervisor.py tests/integration/test_agent_loop.py -q` | 0 | 32 passed |
| Chat unit | `conda run -n agent-foundations python -m pytest tests/unit/chat -q` | 0 | 118 passed |
| Full pytest | `conda run -n agent-foundations python -m pytest -q` | 0 | 454 passed, 1 warning (Starlette/httpx deprecation) |
| Ruff | `conda run -n agent-foundations python -m ruff check src/agent_foundations/chat/runner.py tests/unit/chat/test_runner.py` | 0 | All checks passed |
| mypy | `conda run -n agent-foundations python -m mypy src tests` | 0 | Success: no issues found in 75 source files |
| `git diff --check` | `git diff --check` | 0 | pass (LF/CRLF warnings only on pre-existing tracked files) |

## 6. Scope Audit

- Final changed files (this remediation only):
  - `src/agent_foundations/chat/runner.py`
  - `tests/unit/chat/test_runner.py`
  - `docs/task-evidence/phase-1d-task-6-exception-boundary-remediation.md`
- `git diff -- <allowed paths>`: empty because `src/agent_foundations/chat/`, `tests/unit/chat/`, and `docs/task-evidence/` remain entirely untracked (`??`); scope confirmed via intended-only edits + `git status --short` showing no new tracked modifications beyond pre-existing dirty tree
- Unrelated changes introduced: none
- Existing user changes preserved: yes — status set matches pre-change snapshot; no reset/restore/clean/stage/commit
- Secrets or generated artifacts detected: none (`do-not-leak-secret` appears only as a test assertion that it must not leak)
- Commit, push, deployment, paid API call, or next Task performed: none; Task 7 not started

## 7. Gaps and Limitations

- Checks not run and reasons: Chat frontend npm scripts not applicable; no real-model smoke
- Environment warnings: Starlette `httpx` TestClient deprecation warning on full pytest
- Process evidence gaps: none for this remediation (original Red recorded before production change)
- Remaining risks: reviewer must independently re-verify; parent Task 6 overall acceptance still pending reviewer

## 8. Handoff Summary

- Current verification status: pass (executor local gates)
- TDD process evidence: complete
- Recommended reviewer commands:

```powershell
conda run -n agent-foundations python -m pytest tests/unit/chat/test_runner.py::test_runner_runtime_factory_failure_marks_failed_safely -q
conda run -n agent-foundations python -m pytest tests/unit/chat/test_runner.py tests/unit/chat/test_supervisor.py -q
conda run -n agent-foundations python -m ruff check src/agent_foundations/chat/runner.py tests/unit/chat/test_runner.py
conda run -n agent-foundations python -m mypy src/agent_foundations/chat/runner.py tests/unit/chat/test_runner.py
```
