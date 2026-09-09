# Task Evidence: phase-2d-task-8

## 1. Identity

- Task ID: `phase-2d-task-8`
- Authoritative plan or task spec: Task 24 in `docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md` plus the user-confirmed executor prompt for Task 24
- Evidence status: user-accepted / current implementation pass; TDD process evidence complete; full suite partial
- TDD required: yes
- Started at: 2026-08-27 14:20:00 +08:00 (Asia/Shanghai)
- Dependency: Task 23 (`phase-2d-task-7`) user-accepted 2026-08-27; evidence `docs/task-evidence/phase-2d-task-7.md` (read-only). Compaction/P3 is not in this Task’s Files.
- Role: reviewer recorded user acceptance; executor did not claim it.

## 2. Pre-change Snapshot

- Branch: `codex/phase-2-next` (not `main`)
- Initial `git diff --check`: exit `0` (LF/CRLF working-copy warnings only)
- Existing user changes that must be preserved: all dirty Task 15–23 work, Chat hashed assets, `.agents/`, `.gate-backup/`. No reset/restore/clean/commit/push.
- Intended modification scope: Task 24 Create/Modify list only, planner-allowed extras (`domain/errors.py`, `domain/model.py`, `runtime/state_machine.py`, `providers/__init__.py`, mechanical `test_state_machine.py` / `tests/unit/durable` / `tests/e2e/test_cli.py`), this evidence, Task 24 Step 1–8 checkboxes.
- Protected: Chat hashed assets, `.agents/`, `.gate-backup/`, real `.env`, `docs/eval-baselines/phase-1-v1.json`, `storage/migrations.py`, `durable/schema.py`, `durable/controller.py`, `chat/runner.py`, Dockerfiles, package.json
- Expected rollback: delete Task 24 created files; reverse Task 24 hunks in allowed Modify files.
- Docker: **not authorized / not-run**
- Real Provider / paid API / real HTTP: **not authorized / not-run**
- New SQLite `PRAGMA user_version` / v11: **not authorized**

### Current Provider retry (before this Task)

- CLI `build_provider()`: `AsyncOpenAI(..., timeout=60.0, max_retries=2)` returning bare `OpenAICompatibleProvider`
- Adapter `openai_compatible.py` has no owned retry loop; maps SDK errors only
- `tests/e2e/test_cli.py` asserts `captured["max_retries"] == 2`
- `ProviderRateLimitError` has no `retry_after_seconds`
- No `ProviderTemporaryError`; connection/500 map to `ProviderError`
- `AgentRunState` has no `provider_attempts`; `CheckpointReason` ends at `RETRY_STARTED`
- `DurableRun.attempt` is run-level `begin_retry` only; checkpoint `state_json` is serialized `AgentRunState` (`schema_version` Literal[1])
- No `ResilientModelProvider`, `TokenBucketRateLimiter`, or `ProviderAttemptBudget` modules

### Verification contract (verbatim)

Target tests:
```text
conda run -n agent-foundations python -m pytest tests/unit/providers/test_resilient.py tests/unit/runtime/test_rate_limit.py tests/unit/runtime/test_provider_attempt_budget.py tests/integration/test_provider_retry_recovery.py -q
```

Affected regression tests:
```text
conda run -n agent-foundations python -m pytest tests/unit/providers tests/unit/durable tests/unit/runtime tests/integration/test_agent_loop.py -q
```

- Full suite: required
- Full suite reason: 本 Task 修改 Provider/AgentLoop/Durable checkpoint 的共享请求语义，重复重试可能产生费用和不可恢复状态漂移。
- Additional gates: injected clock/sleeper（自动测试不得 `asyncio.sleep` 真实等待）、restart/crash matrix、SDK retry disabled assertion、no response-cache assertion；自动测试不得调用真实 Provider。

Windows note: `conda run` may crash pytest with `UnicodeEncodeError: gbk`. Commands are executed with the same interpreter:

```powershell
$env:PYTHONIOENCODING='utf-8'
D:\anaconda\envs\agent-foundations\python.exe -m pytest ...
```

This is not a shrunk contract.

### Complete initial `git status --short --branch` (compact)

Command: `git status --short --branch`  
Exit code: `0`

```text
## codex/phase-2-next
 M docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md
 M src/agent_foundations/cli/main.py
 M src/agent_foundations/runtime/loop.py
 M tests/integration/test_agent_loop.py
 ... plus pre-existing Task 15–23 dirty/untracked paths, Chat hashed assets, .agents/, .gate-backup/
 ?? docs/task-evidence/phase-2d-task-7.md
```

Hashed Chat asset filenames omitted. Index/HEAD must not change.

## 3. Red

- Recorded before production-code changes: yes
- Time: 2026-08-27 14:28:00 +08:00 (Asia/Shanghai)
- Test file and test name: `tests/unit/providers/test_resilient.py`, `tests/unit/runtime/test_rate_limit.py`, `tests/unit/runtime/test_provider_attempt_budget.py`, `tests/integration/test_provider_retry_recovery.py` (27 tests)
- Command: `D:\anaconda\envs\agent-foundations\python.exe -m pytest tests/unit/providers/test_resilient.py tests/unit/runtime/test_rate_limit.py tests/unit/runtime/test_provider_attempt_budget.py tests/integration/test_provider_retry_recovery.py -q` with `$env:PYTHONIOENCODING='utf-8'` (same `agent-foundations` interpreter as `conda run`)
- Exit code: `1`
- Relevant verbatim output:

```text
FFFFFFFFFFFFFFFFFFFFFFFFFFF                                              [100%]
AssertionError: agent_foundations.providers.resilient must exist
AssertionError: agent_foundations.runtime.rate_limit must exist
AssertionError: agent_foundations.runtime.provider_attempt_budget must exist
FAILED ... 27 failed in 0.60s
```

- Expected failure category: assertion failure from missing wrapper / limiter / durable attempt budget modules (`find_spec` is `None`)
- Why this failure demonstrates the missing behavior: production modules and contracts (`ResilientModelProvider`, `TokenBucketRateLimiter`, `ProviderAttemptBudget`, `reserve_provider_attempt`) do not exist yet. One earlier `TypeError` on `ProviderRateLimitError(..., retry_after_seconds=)` was rewritten so `_require_resilient()` runs first; the saved Red is assertion-only.

## 4. Green

- Production files changed:
  - Create: `providers/resilient.py`, `runtime/rate_limit.py`, `runtime/provider_attempt_budget.py`, four target test files
  - Modify: `openai_compatible.py`, `durable/repository.py`, `runtime/loop.py`, `cli/main.py`, `domain/errors.py`, `domain/model.py`, `runtime/state_machine.py`, `providers/__init__.py`, `test_openai_compatible.py`, `test_agent_loop.py`, `test_cli.py`, `test_state_machine.py`, this evidence, Task 24 Step checkboxes
  - `durable/models.py` unchanged (checkpoint already stores `AgentRunState`; no table/schema change)
- Command: same Target tests command as Red
- Time: 2026-08-27 14:33:00 +08:00 (Asia/Shanghai)
- Exit code: `0`
- Relevant verbatim output:

```text
...........................                                              [100%]
27 passed in 1.54s
```

## 5. Regression and Quality Gates

Interpreter: `D:\anaconda\envs\agent-foundations\python.exe` with `PYTHONIOENCODING=utf-8` (same env as `conda run -n agent-foundations`).

| Check | Command | Exit code | Result |
|---|---|---:|---|
| Target tests | `python -m pytest tests/unit/providers/test_resilient.py tests/unit/runtime/test_rate_limit.py tests/unit/runtime/test_provider_attempt_budget.py tests/integration/test_provider_retry_recovery.py -q` | 0 | 27 passed |
| Regression tests | `python -m pytest tests/unit/providers tests/unit/durable tests/unit/runtime tests/integration/test_agent_loop.py -q` | 0 | 276 passed, 6 warnings |
| Full suite pytest | `python -m pytest -q` | 1 | **partial**: 8 failed, 1383 passed, 9 skipped, 47 warnings in 173.27s. Failures are Docker/`apply_patch` `PATCH_EFFECT_UNKNOWN` / crash-recovery (same class as Task 23). No new Provider retry, attempt budget, checkpoint version, AgentLoop, or FakeModel failures. |
| Ruff | `python -m ruff check .` | 0 | All checks passed |
| mypy | `python -m mypy src tests` | 0 | Success: no issues found in 280 source files |
| pip check | `python -m pip check` | 0 | No broken requirements found (env warning: ignoring invalid distribution `~gent-engineering-foundations`) |
| Frontend | `npm run test:viewer`; `npm run typecheck:viewer`; `npm run test:chat`; `npm run typecheck:chat`; `npm run build:chat` | 0 | viewer 12 pass; chat 74 pass; typecheck pass; vite build pass. `build:chat` regenerated hashed Chat assets (required gate side effect; not restored). |
| `git diff --check` | `git diff --check` | 0 | LF/CRLF working-copy warnings only |
| `git status --short` | `git status --short --branch` | 0 | Still `codex/phase-2-next`; pre-existing dirty tree preserved; Task 24 new files untracked |

### Full suite pytest exact failure nodes (not “full suite passed”)

1. `tests/integration/test_controlled_patch_flow.py::test_controlled_patch_applies_modify_create_and_multifile_in_docker` — `PATCH_EFFECT_UNKNOWN`
2. `tests/integration/test_controlled_patch_flow.py::test_cross_run_drift_and_capability_replay_are_rejected` — `PATCH_EFFECT_UNKNOWN`
3. `tests/integration/test_controlled_patch_flow.py::test_second_file_conflict_rolls_back_first_file_and_ledger` — `PATCH_EFFECT_UNKNOWN` vs `PATCH_ROLLED_BACK`
4. `tests/integration/test_controlled_patch_flow.py::test_symlink_swap_is_rejected_inside_sandbox_without_touching_outside` — `PATCH_EFFECT_UNKNOWN` vs `PATCH_ROLLED_BACK`
5. `tests/integration/test_patch_crash_recovery.py::test_four_crash_points_recover_without_duplicate_write[before_intent-1]` — `PATCH_EFFECT_UNKNOWN`
6. `...[after_intent-1]` — `PATCH_EFFECT_UNKNOWN`
7. `...[after_execute-1]` — `PATCH_VERIFY_FAILED` / applied hunk mismatch
8. `...[after_commit-1]` — DID NOT RAISE `InjectedCrash`

### Additional gates

- Injected clock/sleeper: FakeClock/FakeSleeper; `real_sleeps == 0` on retry, rate-limit wait, and durable wrapper tests.
- Restart/crash matrix: crash-before-reserve (count unchanged, `DurableRun.attempt` still 1); crash-after-reserve (consumed=1 after new repository instance); restart remaining budget (3rd of max 3); concurrent same request serializes to 1 then 2; exhausted budget does not call inner provider.
- SDK retry disabled: `AsyncOpenAI(..., max_retries=0)` and `build_provider()` returns `ResilientModelProvider`.
- No response cache: second `complete` returns second inner `tool_calls`/`content`.
- Automatic tests did not call a real Provider.

### Error classification (implemented)

- Retryable: `ProviderRateLimitError`, `ProviderTimeoutError`, `ProviderTemporaryError` (connection + HTTP 500/502/503/504).
- Not retryable (single attempt): auth, invalid response, non-429 4xx `ProviderError`, `FakeModelExhaustedError`, cancellation, Policy/Tool/PathPolicy, context/compaction (loop fails before/without retry wrapper on FakeModel path).

### Attempt state transitions

- `AgentRunState.provider_attempts` is the Provider attempt fact source (`request_id` → consumed count).
- `DurableRun.attempt` is unchanged by `reserve_provider_attempt`; only `begin_retry` increments it and resets `provider_attempts` to `{}`.
- Crash resume (same `DurableRun.attempt`) continues from checkpoint counts; does not zero them.

## 6. Scope Audit

- Final Task 24 files: listed in §4; `durable/models.py` not modified.
- Unrelated changes introduced: no intentional unrelated edits. `npm run build:chat` regenerated hashed Chat assets as a required gate side effect (same class as prior Tasks).
- Existing user changes preserved: yes
- Secrets or generated artifacts detected: hashed Chat assets from required `build:chat` only; no `.env`/keys
- Commit, push, deployment, paid API call, or next Task performed: none / not authorized

## 7. Gaps and Limitations

- Checks not run: Docker / image operations (未授权); real Provider / paid API / real HTTP (未授权); Chat runner checkpoint_sink wiring (existing gap; in-memory budget covers that path)
- Environment warnings: sqlite3 datetime adapter deprecation; Starlette/httpx TestClient deprecation; pip invalid distribution name `~gent-engineering-foundations`
- Process evidence gaps: none for Red→Green of the four target files; Red recorded before production modules existed
- Remaining risks: Chat `loop.run()` without `CheckpointSink` still only accumulates attempts in-process; host Docker/`apply_patch` `PATCH_EFFECT_UNKNOWN` remains from Task 23

## 8. Handoff Summary

- Evidence status: user-accepted
- Current verification status: **pass** (Task 24 target/affected/quality gates). Independently reviewed; user-accepted 2026-08-27.
- TDD process evidence: **complete** (Red saved before production modules); user acceptance does not independently witness historical Red→Green
- Full suite: required; actual result **partial** due to Docker/`apply_patch` `PATCH_EFFECT_UNKNOWN`. Do not report as full suite passed.
- Docker: not-run / 未授权
- Real Provider / paid API: not-run / 未授权
- SDK `max_retries`: independently asserted `== 0`
- Crash/restart matrix: pass (in Target)
- User acceptance: recorded in §9
- Reviewer acceptance: pass (current implementation) in the reviewer session that preceded this confirmation
- Reviewer findings retained: P2 full-suite partial (unrelated patch/Docker); P3 Chat path has no `CheckpointSink` so attempts are in-process only; P3 `durable/models.py` unchanged and CLI uses in-memory budget with checkpoint persistence when a sink exists
- Recommended reviewer commands: Target tests; `tests/e2e/test_cli.py::test_build_runtime_passes_sdk_config`; crash/restart tests in `tests/integration/test_provider_retry_recovery.py`
- Suggested commit (not executed): `feat: make provider retries durable and bounded`

## 9. User Acceptance

- Confirmed at: 2026-08-27 15:22 +08:00.
- Exact user confirmation: `确认 Task 24 用户验收通过`.
- Result: Task 24 (`phase-2d-task-8`) is user-accepted for the current implementation; the `Task 24 accepted` dependency named by Task 25 is satisfied.
- Full suite note: this confirmation accepts Task 24 provider retry / rate limit / durable attempt-budget behavior after independent targeted review. It does not treat `pytest -q` Docker/`apply_patch` `PATCH_EFFECT_UNKNOWN` failures as a reconstructed green full suite.
- TDD note: executor Red is internally consistent and marked complete; this confirmation does not independently witness the original Red→Green sequence.
- Boundary: this confirmation records acceptance only. Task 25 has not been started and still requires its own explicit single-Task executor authorization. No commit, push, paid API, Docker, or next-Task implementation is authorized by this confirmation.
