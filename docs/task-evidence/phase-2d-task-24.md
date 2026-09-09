# Task Evidence: phase-2d-task-24

## 1. Identity

- Task ID: `phase-2d-task-24`
- Authoritative plan or task spec: `docs/agent-plans/2026-09-04-phase-2-product-hardening-plan.md` Task 40 plus the user-confirmed executor prompt
- Evidence status: user-accepted 2026-09-05 (targeted verification); Task 25 Step 10/11 **not claimed**; Phase 2 complete **not claimed**
- TDD required: yes
- Started at: 2026-09-05 (Asia/Shanghai)

## 2. Pre-change Snapshot

- Branch or revision: `codex/phase-2-next` at `14ece4e` (not `main`)
- `git status --short` (this Task files before production edits): `M src/agent_foundations/chat/api.py`, `M src/agent_foundations/cli/main.py`, `M src/agent_foundations/viewer/app.py`, `?? src/agent_foundations/command_output/retention.py`, `?? src/agent_foundations/command_output/store.py`, `?? tests/integration/test_command_output_api.py`, `?? tests/unit/command_output/test_retention.py`. Broader dirty tree (Phase 2A–2D, evidence, Task 30–39) already present.
- Existing user changes that must be preserved: all pre-existing modified and untracked files at Task start. Do not `restore`/`reset`/`clean`.
- Intended modification scope: 512 MiB canonical capacity; Chat lifespan sweep; local usage/sweep/purge HTTP. Do not change Policy, gate_id, Git, data-root, pages/raw, sanitizer, 64 MiB, 7-day retention, reserve(), uvicorn host, Chat UI, Task 41 logging, Phase 2 Task 18 historical 1 GiB text, or Task 35–39 P3.
- Expected rollback: revert only this Task’s files; do not revert the pre-existing dirty tree.
- Interpreter: Windows `conda run` can crash pytest with GBK. Commands use `$env:PYTHONIOENCODING='utf-8'`. This does not shrink the verification contract.

## 3. Red

- Recorded before production-code changes: yes
- Time: 2026-09-05 (Asia/Shanghai)
- Test file and test name: `tests/unit/command_output/test_retention.py`, `tests/unit/chat/test_artifact_sweep.py`, `tests/integration/test_command_output_api.py` (new usage/sweep/purge)
- Command: `$env:PYTHONIOENCODING='utf-8'; conda run -n agent-foundations python -m pytest tests/unit/command_output/test_retention.py tests/unit/chat/test_artifact_sweep.py tests/integration/test_command_output_api.py -q --tb=line`
- Exit code: 1
- Relevant verbatim output:

```text
assert 1073741824 == ((512 * 1024) * 1024)
assert None == ((512 * 1024) * 1024)  # no global_capacity_bytes accessor
assert 'missing' is None  # ChatServices has no retention
assert 'retention' in {'broker', ...}
assert 'retention=retention' in 'return ChatServices(... durable_repository=...)'
9 failed, 10 passed
```

AttributeError on missing accessors was converted to `getattr` assertions **before production edits**. `test_build_chat_services_passes_sweeper` originally matched `ControlledCommandExecutor(retention=retention)` (false green); narrowed to the `return ChatServices(` block and re-run (exit 1) before production edits.

- Expected failure category: assertion failure from 1 GiB default, missing ChatServices.retention, missing lifespan sweep, missing HTTP routes/fields
- Why this failure demonstrates the missing behavior: capacity is still 1 GiB; ChatServices has no sweeper field so lifespan cannot sweep; ChatServices() does not receive the existing sweeper. Not syntax/import errors.
- If unavailable, why it cannot be verified: n/a

## 4. Green

- Production files changed:
  - `src/agent_foundations/command_output/retention.py` — `DEFAULT_GLOBAL_CAPACITY_BYTES = 512 * 1024 * 1024`; readonly `global_capacity_bytes` / `retention_period`
  - `src/agent_foundations/command_output/store.py` — import `DEFAULT_GLOBAL_CAPACITY_BYTES` and `EXECUTION_OUTPUT_LIMIT_BYTES` from `retention.py` (no local copies)
  - `src/agent_foundations/chat/api.py` — `ChatServices.retention` / `artifact_sweep_interval_seconds`; usage / sweep / purge endpoints
  - `src/agent_foundations/viewer/app.py` — lifespan startup sweep + periodic sleep-then-sweep; cancel before coordinator→supervisor shutdown
  - `src/agent_foundations/cli/main.py` — `build_chat_services()` passes `retention=retention`
- Command: `$env:PYTHONIOENCODING='utf-8'; conda run -n agent-foundations python -m pytest tests/unit/command_output/test_retention.py tests/unit/chat/test_artifact_sweep.py tests/integration/test_chat_approval_flow.py::test_chat_lifespan_shuts_down_coordinator_before_supervisor tests/integration/test_command_output_api.py -q --tb=short`
- Exit code: 0
- Relevant verbatim output:

```text
....................                                                     [100%]
20 passed, 1 warning in 2.99s
```

First Green attempt of `test_artifact_usage_sweep_and_origin_gates` failed because `_seed_artifact` writes `created_at` from wall clock, so advancing the sweeper clock by 8 days from fixture `NOW` did not expire it. Production sweep path was unchanged; the test was corrected to `store.write(..., created_at=NOW)` then re-run. Not a weakened assertion: still requires POST sweep to evict a retained artifact past the 7-day window.

## 5. Regression and Quality Gates

| Check | Command | Exit code | Result |
|---|---|---:|---|
| Target tests | `$env:PYTHONIOENCODING='utf-8'; conda run -n agent-foundations python -m pytest tests/unit/command_output/test_retention.py tests/unit/chat/test_artifact_sweep.py tests/integration/test_chat_approval_flow.py::test_chat_lifespan_shuts_down_coordinator_before_supervisor tests/integration/test_command_output_api.py -q --tb=short` | 0 | 20 passed, 1 warning |
| Regression tests | `$env:PYTHONIOENCODING='utf-8'; conda run -n agent-foundations python -m pytest tests/unit/command_output/test_retention.py tests/unit/command_output/test_store.py tests/integration/test_command_artifact_lifecycle.py tests/integration/test_command_output_api.py tests/integration/test_chat_approval_flow.py tests/unit/chat/test_artifact_sweep.py -q` | 0 | 42 passed, 1 skipped, 1 warning |
| Ruff | `$env:PYTHONIOENCODING='utf-8'; conda run -n agent-foundations python -m ruff check src/agent_foundations/command_output/retention.py src/agent_foundations/command_output/store.py src/agent_foundations/chat/api.py src/agent_foundations/viewer/app.py src/agent_foundations/cli/main.py tests/unit/command_output/test_retention.py tests/unit/chat/test_artifact_sweep.py tests/integration/test_command_output_api.py` | 0 | All checks passed (after removing one extra blank line after `api.py` imports; I001) |
| mypy | `$env:PYTHONIOENCODING='utf-8'; conda run -n agent-foundations python -m mypy src/agent_foundations/command_output/retention.py src/agent_foundations/command_output/store.py src/agent_foundations/chat/api.py src/agent_foundations/viewer/app.py src/agent_foundations/cli/main.py` | 0 | Success: no issues found in 5 source files |
| Frontend test, typecheck or build | not in contract | | not-run |
| Package or dependency check | not in contract | | not-run |
| `git diff --check` | `git diff --check` | 0 | pass (CRLF working-copy warnings only; no whitespace errors) |

Targeted verification passed. Full suite not-required and not run.

## 6. Scope Audit

- Final changed files (this Task):
  - Modify: `src/agent_foundations/command_output/retention.py` (512 MiB canonical constant; readonly accessors)
  - Modify: `src/agent_foundations/command_output/store.py` (import capacity/limit constants; no second assignment)
  - Modify: `src/agent_foundations/chat/api.py` (ChatServices fields + usage/sweep/purge)
  - Modify: `src/agent_foundations/viewer/app.py` (lifespan sweep)
  - Modify: `src/agent_foundations/cli/main.py` (`return ChatServices(..., retention=retention)`)
  - Modify: `tests/unit/command_output/test_retention.py` (512 MiB; import identity; accessors)
  - Create: `tests/unit/chat/test_artifact_sweep.py`
  - Modify: `tests/integration/test_command_output_api.py` (usage/sweep/purge/origin/404)
  - Create: `docs/task-evidence/phase-2d-task-24.md`
  - Modify: `docs/agent-plans/2026-09-04-phase-2-product-hardening-plan.md` (status only; Task 40 contract text not rewritten)
- Unrelated changes introduced: no. Pre-existing dirty tree from Tasks 30–39 preserved. Policy, gate_id, Git, data-root, pages/raw, sanitizer, 64 MiB, 7-day retention, `reserve()`, uvicorn `127.0.0.1`, Chat UI, Task 41 logging, Phase 2 Task 18 historical 1 GiB sentence untouched.
- Existing user changes preserved: yes
- Secrets or generated artifacts detected: no
- Commit, push, deployment, paid API call, or next Task performed: no

## 7. Gaps and Limitations

- Checks not run and reasons: full suite, Docker, Playwright e2e, npm, paid API — not in contract / not authorized.
- Environment warnings: Starlette/`httpx` TestClient deprecation; `git diff --check` CRLF warnings on many pre-existing files.
- Process evidence gaps: first Green of the usage/sweep integration test used wall-clock `created_at`; test was fixed to seed `created_at=NOW` then re-run. Original Red for missing 512 MiB / ChatServices.retention / HTTP routes was recorded before production edits.
- Remaining risks: periodic sweep is best-effort in-process; `retention is None` ChatServices (most unit tests) still 404 the three endpoints. Reviewer should re-run the verification contract; this evidence does not prove reviewer-witnessed history.

## 8. Handoff Summary

- Current verification status: **pass** (targeted verification; not full suite). Reviewer-fresh: Target 20 passed; Affected 42 passed / 1 skipped; ruff / mypy / `git diff --check` exit 0
- TDD process evidence: **complete**. Reviewer fresh checks prove current green, not the historical Red→Green sequence
- User acceptance: recorded in §9
- Reviewer acceptance: pass (current implementation, targeted) in the reviewer session that preceded this confirmation
- Reviewer findings retained: P3 periodic sweep is in-process best-effort; `ChatServices` without retention still 404s the three endpoints by contract; no Chat UI occupancy/cleanup surface
- Recommended reviewer commands (already run for this Task):

```text
$env:PYTHONIOENCODING='utf-8'
conda run -n agent-foundations python -m pytest tests/unit/command_output/test_retention.py tests/unit/chat/test_artifact_sweep.py tests/integration/test_chat_approval_flow.py::test_chat_lifespan_shuts_down_coordinator_before_supervisor tests/integration/test_command_output_api.py -q
conda run -n agent-foundations python -m pytest tests/unit/command_output/test_retention.py tests/unit/command_output/test_store.py tests/integration/test_command_artifact_lifecycle.py tests/integration/test_command_output_api.py tests/integration/test_chat_approval_flow.py tests/unit/chat/test_artifact_sweep.py -q
conda run -n agent-foundations python -m ruff check src/agent_foundations/command_output/retention.py src/agent_foundations/command_output/store.py src/agent_foundations/chat/api.py src/agent_foundations/viewer/app.py src/agent_foundations/cli/main.py tests/unit/command_output/test_retention.py tests/unit/chat/test_artifact_sweep.py tests/integration/test_command_output_api.py
conda run -n agent-foundations python -m mypy src/agent_foundations/command_output/retention.py src/agent_foundations/command_output/store.py src/agent_foundations/chat/api.py src/agent_foundations/viewer/app.py src/agent_foundations/cli/main.py
git diff --check
```

## 9. User Acceptance

- Confirmed at: 2026-09-05 +08:00.
- Exact user confirmation: `确认「Task 40 / phase-2d-task-24 用户验收通过」`.
- Result: Product-hardening Task 40 / `phase-2d-task-24` (Chat lifespan sweep and 512 MiB capacity) is user-accepted for the current implementation. This is **not** plan body Task 24. Independent reviewer re-ran the targeted contract (Target 20 passed; Affected 42 passed / 1 skipped; ruff / mypy / `git diff --check` exit 0).
- Full suite note: this confirmation accepts **targeted verification passed**. It does not claim `full suite passed`, does not accept Task 25 as complete, does not accept paid 3×3, and does not mark user Phase 2 complete. Plan Task 25 Step 10 and Step 11 remain unchecked.
- TDD note: executor Red is internally consistent and marked complete; this confirmation does not independently witness the original Red→Green sequence.
- Boundary: this confirmation records `phase-2d-task-24` acceptance only. Task 41 / `phase-2d-task-25` still requires its own explicit single-Task executor authorization. No commit, push, paid API rerun, Phase 2 complete checkbox, or Phase 3 is authorized by this confirmation. Reviewer P3 findings are retained and do not require immediate rework from this confirmation.
