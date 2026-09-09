# Task Evidence: phase-2d-task-12

## 1. Identity

- Task ID: `phase-2d-task-12`
- Authoritative plan or task spec: user prompt 2026-08-27; `docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md` Appendix Task 28
- Evidence status: user-accepted 2026-08-27 (targeted verification); Task 25 overall **not complete**; user Phase 2 complete **not claimed**
- TDD required: yes
- Started at: 2026-08-27 (Asia/Shanghai)

## 2. Pre-change Snapshot

- Branch or revision: `codex/phase-2-next` (not `main`)
- `git status --short`: dirty working tree. `tests/integration/test_phase2_coding_agent.py` is untracked in this dirty tree and must be preserved except for appending the sibling case.
- Existing user changes that must be preserved: entire dirty tree; DualBackend E2E, `_DIFF`, and `test_phase2_agent_recovers_from_structured_command_feedback` stay unchanged.
- Intended modification scope: append `@pytest.mark.docker` sibling + helper; this evidence. No production runtime, no DualBackend deletion, no `_DIFF` edit.
- Expected rollback: revert only this Task’s additions.
- Interpreter: `$env:PYTHONIOENCODING='utf-8'; D:\anaconda\envs\agent-foundations\python.exe`
- Depends on: `phase-2d-task-10` user-accepted. Production pin must be used, not `sha256:{'c'*64}`.

## 3. Red

- Recorded before production-code changes: yes (docker helper still DualBackend stub)
- Time: 2026-08-27 (Asia/Shanghai)
- Test file and test name: `tests/integration/test_phase2_coding_agent.py::test_phase2_agent_recovers_from_structured_command_feedback_in_docker`
- Command: `$env:PYTHONIOENCODING='utf-8'; D:\anaconda\envs\agent-foundations\python.exe -m pytest tests/integration/test_phase2_coding_agent.py::test_phase2_agent_recovers_from_structured_command_feedback_in_docker -m docker -q`
- Exit code: 1
- Relevant verbatim output:

```text
F                                                                        [100%]
>       assert snapshot_argvs, "scripted correction must launch docker run, not DualBackend"
E       AssertionError: scripted correction must launch docker run, not DualBackend
E       assert []
FAILED tests/integration/test_phase2_coding_agent.py::test_phase2_agent_recovers_from_structured_command_feedback_in_docker
1 failed, 5 warnings in 3.35s
```

- Expected failure category: sibling still used DualBackend host apply; no `docker run` argv
- Why this failure demonstrates the missing behavior: scripted FakeModel correction had not been wired to real DockerBackend + production pin. Not an import error.
- If unavailable, why it cannot be verified:

## 4. Green

- Production files changed: none (test-only)
- Command: `$env:PYTHONIOENCODING='utf-8'; D:\anaconda\envs\agent-foundations\python.exe -m pytest tests/integration/test_phase2_coding_agent.py::test_phase2_agent_recovers_from_structured_command_feedback_in_docker -m docker -q`
- Exit code: 0
- Relevant verbatim output:

```text
.                                                                        [100%]
1 passed, 5 warnings in 7.92s
```

## 5. Regression and Quality Gates

| Check | Command | Exit code | Result |
|---|---|---:|---|
| Target tests | `pytest tests/integration/test_phase2_coding_agent.py -q` | 0 | 5 passed, 1 skipped (docker sibling skipped without `-m docker`) |
| Target tests | `pytest tests/integration/test_phase2_coding_agent.py -m docker -q` | 0 | 1 passed, 5 deselected |
| Regression tests | `pytest -m docker -q` | 0 | 17 passed, 1395 deselected |
| Additional: readonly inspect | `docker image inspect agent-foundations-sandbox-python:phase2d --format "{{.Id}}"` / node tag | 0 | python `sha256:730aea0a2ba8ef2998bb0cc43b1f94641a9099f8a0d55b22a0605f384ad26e41`; node `sha256:eb349e91bdf800e6065b700e315439dc443547b726cc3bd098e18cd952bb5f21`; matches pin |
| Ruff | `ruff check tests/integration/test_phase2_coding_agent.py` | 0 | All checks passed |
| mypy | `python -m mypy src tests` | 0 | Success: no issues found in 287 source files |
| Frontend test, typecheck or build | not-required | | |
| Package or dependency check | not-required | | |
| `git diff --check` | Task files | 0 | pass |

## 6. Scope Audit

- Final changed files:
  - Modify: `tests/integration/test_phase2_coding_agent.py` (append docker sibling + helper; DualBackend and `_DIFF` kept; original test function unchanged)
  - Create: `docs/task-evidence/phase-2d-task-12.md`
- Unrelated changes introduced: no
- Existing user changes preserved: yes
- Secrets or generated artifacts detected: no
- Commit, push, deployment, paid API call, or next Task performed: none

## 7. Gaps and Limitations

- Checks not run and reasons: Full suite not-required. Paid 3×3 not run. Phase 2 Step 10/11 not ticked.
- Environment warnings: sqlite3 datetime adapter DeprecationWarning; Starlette/httpx TestClient deprecation in docker matrix.
- Process evidence gaps: original DualBackend test is unchanged; docker sibling removes fixture `conftest.py` `collect_ignore` only in the copied temp project so real pytest collects tests.
- Remaining risks: Git/apply `read_only`/`project_write` still use whatever image the wrapped DockerBackend receives; the wrapper supplies the production pin when Chat omits it. This Task does not replace the DualBackend locked contract.

## 8. Handoff Summary

- Current verification status: **pass** (targeted verification passed; not full suite). Reviewer-fresh: no `-m docker` 5 passed / 1 skipped; file `-m docker` 1 passed / 5 deselected; `pytest -m docker -q` 17 passed / 1395 deselected; inspect matches pin; ruff on the test file passed; `mypy src tests` 287 files passed
- TDD process evidence: **complete**. Reviewer fresh checks prove current green, not the historical Red→Green sequence
- User acceptance: recorded in §9
- Reviewer acceptance: pass (current implementation, targeted) in the reviewer session that preceded this confirmation
- Reviewer findings retained: P3 test wrapper falls back to production pin if Chat omits `sandbox_manifest`; temp copy unlinks fixture `conftest.py` so in-container pytest collects tests; DualBackend locked contract and `_DIFF` unchanged
- Recommended reviewer commands (already run for this Task):

```powershell
$env:PYTHONIOENCODING='utf-8'
D:\anaconda\envs\agent-foundations\python.exe -m pytest tests/integration/test_phase2_coding_agent.py -q
D:\anaconda\envs\agent-foundations\python.exe -m pytest tests/integration/test_phase2_coding_agent.py -m docker -q
D:\anaconda\envs\agent-foundations\python.exe -m pytest -m docker -q
docker image inspect agent-foundations-sandbox-python:phase2d --format "{{.Id}}"
docker image inspect agent-foundations-sandbox-node:phase2d --format "{{.Id}}"
D:\anaconda\envs\agent-foundations\python.exe -m ruff check tests/integration/test_phase2_coding_agent.py
D:\anaconda\envs\agent-foundations\python.exe -m mypy src tests
git diff --check -- tests/integration/test_phase2_coding_agent.py docs/task-evidence/phase-2d-task-12.md
```

## 9. User Acceptance

- Confirmed at: 2026-08-27 +08:00.
- Exact user confirmation: `确认「Task 12 / phase-2d-task-12 用户验收通过」`.
- Result: Appendix Task 28 / `phase-2d-task-12` (FakeModel correction-flow Docker sibling E2E) is user-accepted for the current implementation. This is **not** plan body Task 12 (Approval/Policy). Independent reviewer re-ran the targeted contract (5 passed / 1 skipped without `-m docker`; 1 passed / 5 deselected with file `-m docker`; full docker marker 17 passed / 1395 deselected; inspect IDs match pin).
- Full suite note: this confirmation accepts **targeted verification passed**. It does not claim `full suite passed`, does not accept Task 25 as complete, does not accept paid 3×3, and does not mark user Phase 2 complete. Plan Task 25 Step 10 and Step 11 remain unchecked. The DualBackend locked FakeModel E2E remains the default no-Docker contract.
- TDD note: executor Red is internally consistent and marked complete; this confirmation does not independently witness the original Red→Green sequence.
- Boundary: this confirmation records `phase-2d-task-12` acceptance only. The P1 `_DIFF` alignment and `phase-2d-task-10` / `phase-2d-task-11` remain separately accepted. No commit, push, paid API rerun, Phase 2 complete checkbox, or Phase 3 is authorized by this confirmation.
