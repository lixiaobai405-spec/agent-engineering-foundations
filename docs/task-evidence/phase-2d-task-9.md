# Task Evidence: phase-2d-task-9

## 1. Identity

- Task ID: `phase-2d-task-9`
- Authoritative plan or task spec: `docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md` Task 25
- Evidence status: P1 FakeModel `_DIFF` remediation **user-accepted** 2026-08-27; Step 10 Round 3 9/9 **user-accepted** 2026-09-09 (Round 2 Node-3 fail not rewritten); Step 11 **user-accepted** 2026-09-09; user Phase 2 **complete** 2026-09-09. See `docs/task-evidence/phase-2d-task-9-step-10.md` §11 and `docs/task-evidence/phase-2d-task-9-step-11.md` §12–§13.
- TDD required: yes for integration/E2E; documentation `not-applicable`
- Started at: 2026-08-27 (Asia/Shanghai)

## 2. Pre-change Snapshot

- Branch or revision: `codex/phase-2-next` (not `main`)
- `git status --short --branch`: dirty working tree already present before this Task (Phase 2A–2D implementation, Chat hashed assets, Dockerfiles, evidence files, `.agents/`, `.gate-backup/`). Exact listing is long; key fact: user/pre-existing changes must be preserved. This Task must not `restore`/`reset`/`clean` Chat assets after `npm run build:chat`.
- Existing user changes that must be preserved: all pre-existing modified and untracked files listed by `git status --short` at Task start.
- Intended modification scope: Task 25 Files only (Phase 2 eval fixtures, coding fixture, integration/E2E tests, learning notes 05–08, README, learning-design stale phrase, plan Step checkboxes, `evals/replay.py` and minimal eval runner/prompt-version branching).
- Expected rollback: delete this Task’s new files and revert only this Task’s edits; do not revert the pre-existing dirty tree.
- Interpreter: Windows `conda run` can crash pytest with `UnicodeEncodeError: gbk`. Commands below use `$env:PYTHONIOENCODING='utf-8'; D:\anaconda\envs\agent-foundations\python.exe` (same `agent-foundations` interpreter). This does not shrink the verification contract.
- Docker precheck (this session, after user opened Docker Desktop): engine available. Confirmed images (do not copy Task 24 pytest partial as this run’s green):

| Tag | Image ID | User |
|---|---|---|
| `agent-foundations-sandbox:phase2` | `sha256:250e993fbf4c4294a267246f8f512253b0bad4112b754b6d787c916dfdc9c753` | `65532:65532` |
| `agent-foundations-sandbox-python:phase2d` | `sha256:730aea0a2ba8ef2998bb0cc43b1f94641a9099f8a0d55b22a0605f384ad26e41` | `65532:65532` |
| `agent-foundations-sandbox-node:phase2d` | `sha256:eb349e91bdf800e6065b700e315439dc443547b726cc3bd098e18cd952bb5f21` | `65532:65532` |

- `git diff --check` at Task start: exit 0 (LF/CRLF warnings only).

### Task 1–24 inventory

| Plan Task | Evidence ID | User gate (from evidence / plan) | TDD process | Notes |
|---|---|---|---|---|
| 1 | `phase-2a-task-1` | completed / prior Phase 2A accept | see evidence | Offline Eval foundations |
| 2 | `phase-2a-task-2` | completed | see evidence | Replay / CLI evaluate |
| 3 | `phase-2a-task-3` | completed | incomplete (Red verbatim unavailable) | Baseline report |
| 4 | `phase-2a-task-4` | completed | see evidence | Planning models |
| 5 | `phase-2a-task-5` | completed | see evidence | Planning tools / Phase 2A gate |
| 6 | `phase-2b-task-1` | completed | see evidence | Durable schema |
| 7 | `phase-2b-task-2` | completed | see evidence | Repository |
| 8 | `phase-2b-task-3` | completed | see evidence | Lease |
| 9 | `phase-2b-task-4` | completed | see evidence | Resume/retry/cancel |
| 10 | `phase-2b-task-5` | completed | see evidence | Side-effect ledger |
| 11 | `phase-2b-task-6` | gate-complete; Phase 2B user sign-off recorded in later chain | see evidence | Patch preview |
| 12 | `phase-2c-task-1` | user-accepted 2026-08-12 | incomplete (round 1 Red unavailable) | Profiles / Policy |
| 13 | `phase-2c-task-2` | completed-awaiting-review in file; later 2C gate accepted | see evidence | Approval / Capability |
| 14 | `phase-2c-task-3` | executor pass; reviewer pending in file; later 2C gate accepted | see evidence | Sandbox backend |
| 15 | `phase-2c-task-4` | completed; reviewer pending in file; later 2C gate accepted | see evidence | Controlled apply_patch |
| 16 | `phase-2c-task-5` | user-accepted 2026-08-13 (`Task 16 验收通过`) | see evidence | Phase 2C gate |
| 17 | `phase-2d-task-1` | user-accepted 2026-08-26 | see evidence | Command sandbox images |
| 18 | `phase-2d-task-2` | user-accepted 2026-08-26 | see evidence | run_command durable |
| 19 | `phase-2d-task-3` | user-accepted 2026-08-26 | see evidence | Parser / CommandFeedback |
| 20 | `phase-2d-task-4` | user-accepted 2026-08-26 | incomplete (historical Red verbatim) | Artifact read / UI |
| 21 | `phase-2d-task-5` | user-accepted 2026-08-26 | complete | Git read-only |
| 22 | `phase-2d-task-6` | user-accepted 2026-08-26 | complete | Repo map / relevance |
| 23 | `phase-2d-task-7` | user-accepted 2026-08-27 | complete | Compaction; full suite **partial** (Docker/patch) — not reused as Task 25 green |
| 24 | `phase-2d-task-8` | user-accepted 2026-08-27 | complete | Provider retry; full suite **partial** — not reused as Task 25 green |

- Migration sequence: application migrations are consecutive v1–v10 (`tests/unit/durable/test_repository.py` pins `migrations[-1].version == 10`). No v11.

### Unverified items (must stay explicit)

- Real model / paid API 3×3: **run 2026-08-27 after user authorized `.env` `AGENT_API_KEY`**. All three classes **failed on attempt 1**; no extra paid retries. Plan Step 10 checkbox stays unchecked. Redacted IDs: `.agent-foundations/manual-3x3/results.json` (gitignored).
- Real model compactor (non-FakeCompactor): not-run.
- Chat Provider attempt budget across crash without CheckpointSink: protected gap from Task 24; this Task must not force-wire `chat/runner.py` or `durable/controller.py`.
- Reviewer P3 on compaction (Task 23 notes): not this session.
- Independent reviewer for Task 25: not-run (this session is executor only).
- User confirmation that Phase 2 is complete: not claimed; checkbox must stay unchecked.

## 3. Red

- Recorded before production-code changes: yes
- Time: 2026-08-27 (Asia/Shanghai)
- Test file and test name: `tests/integration/test_phase2_coding_agent.py` (`test_phase2_coding_project_fixture_exists`, `test_phase2_eval_fixtures_exist`, `test_phase2_agent_recovers_from_structured_command_feedback`)
- Command: `$env:PYTHONIOENCODING='utf-8'; D:\anaconda\envs\agent-foundations\python.exe -m pytest tests/integration/test_phase2_coding_agent.py -q`
- Exit code: 1
- Relevant verbatim output:

```text
FF..E                                                                    [100%]
E       AssertionError: phase2_coding_project fixture is missing
E       AssertionError: phase-2-tasks-v1.json is missing
ERROR at setup of test_phase2_agent_recovers_from_structured_command_feedback
E       AssertionError: phase2_coding_project fixture is missing
2 failed, 2 passed, 1 error in 0.30s
```

- Expected failure category: missing Phase 2 coding fixture / eval fixtures / FakeModel correction composition
- Why this failure demonstrates the missing behavior: the locked E2E contract and Phase 2 eval dataset do not exist yet; failures are assertion errors about missing fixtures, not import/environment/Docker/real Provider errors
- If unavailable, why it cannot be verified: n/a

## 4. Green

- Production files changed: `src/agent_foundations/evals/replay.py` (Phase 2 dataset/tag composition + FakeBackend Git; no Docker/real Provider). Fixtures, E2E composition in `tests/integration/test_phase2_coding_agent.py`, Chat UI assertion, README, learning notes 05–08, learning-design stale phrase, plan Step 1–9/12 checkboxes, `docs/eval-baselines/phase-2-v1.json`.
- Command: `$env:PYTHONIOENCODING='utf-8'; D:\anaconda\envs\agent-foundations\python.exe -m pytest tests/integration/test_phase2_coding_agent.py -q`
- Exit code: 0
- Relevant verbatim output:

```text
.....                                                                    [100%]
5 passed, 5 warnings in 2.80s
```

Later the same file stayed green inside the full suite (1396 passed).

## 4b. Offline Eval (this run)

Phase 1:

```text
evaluate --task-set tests/fixtures/evals/phase-1-tasks-v1.json ... --output .agent-foundations/evals/final-phase-1.json
PHASE1_EXIT=0
summary: failed_tasks=0 passed_tasks=8 success_rate=1.0 total_steps=25 total_tool_calls=17 total_input_tokens=297 total_output_tokens=173 duration_ms=0.0
prompt_version=phase-1-v1
```

Compare with committed `docs/eval-baselines/phase-1-v1.json` (2026-08-09): 5 tasks, 10 steps, 127/69 tokens, success_rate=1.0, readonly tool_set. Current Phase 1 task set is `dataset_version=phase-2a-v1` (8 tasks including planning). This Task did **not** edit Phase 1 fixture content. Success rate stayed 1.0; step/token growth is the 2A planning tasks, not an unexplained regression.

Phase 2:

```text
evaluate --task-set tests/fixtures/evals/phase-2-tasks-v1.json ... --output .agent-foundations/evals/final-phase-2.json
PHASE2_EXIT=0
summary: failed_tasks=0 passed_tasks=4 success_rate=1.0 total_steps=11 total_tool_calls=7 total_input_tokens=68 total_output_tokens=49 duration_ms=0.0
prompt_version=phase-2-v1
```

Commit-able copy: `docs/eval-baselines/phase-2-v1.json`. FakeModel script tokens are **not** billed tokens; `duration_ms` is hardcoded `0.0` in Replay. `apply_patch` in Offline Eval returns `CONTROLLED_EXECUTION_REQUIRED` (no Docker). Sensitive `.env` still `PathPolicyViolationError`. Git read uses FakeBackend.

## 5. Regression and Quality Gates

This-run interpreter: `$env:PYTHONIOENCODING='utf-8'; D:\anaconda\envs\agent-foundations\python.exe` (same `agent-foundations` env; contract not shrunk).

| Check | Command | Exit code | Result |
|---|---|---:|---|
| Target tests | `pytest tests/integration/test_phase2_coding_agent.py tests/integration/test_command_feedback_agent_flow.py tests/e2e/test_chat_ui.py -q` (covered by full `pytest -q`) | 0 | pass |
| Full suite pytest | `pytest -q` | 0 | **1396 passed, 9 skipped, 52 warnings** in 179.23s |
| Docker marker | `pytest -m docker -q` | 0 | **16 passed**, 1389 deselected |
| Ruff | `ruff check .` | 0 | All checks passed |
| mypy | `mypy src tests` | 0 | Success: no issues found in 286 source files |
| pip check | `pip check` | 0 | No broken requirements (invalid-dist warning `~gent-engineering-foundations` only) |
| viewer test | `npm run test:viewer` | 0 | 12 pass |
| viewer typecheck | `npm run typecheck:viewer` | 0 | pass |
| chat test | `npm run test:chat` | 0 | 9 files / 74 tests pass |
| chat typecheck | `npm run typecheck:chat` | 0 | pass |
| chat build | `npm run build:chat` | 0 | built; hashed assets not restored |
| `git diff --check` | `git diff --check` | 0 | LF/CRLF warnings only |

## 5b. Docker / Artifact / security matrix (Step 7)

Images confirmed this session (user `65532:65532`):

- `agent-foundations-sandbox:phase2` `sha256:250e993fbf4c...dc9c753`
- `agent-foundations-sandbox-python:phase2d` `sha256:730aea0a2ba8...d26e41`
- `agent-foundations-sandbox-node:phase2d` `sha256:eb349e91bdf8...bb5f21`

No `docker prune`, no Dockerfile edits, no host subprocess fallback.

| # | Proof | This-run evidence |
|---|---|---|
| 1 | Container no-network, non-root, filtered snapshot | `pytest -m docker` 16 passed; image User `65532:65532`; existing `test_execution_backend.py` / `test_sandbox_manifest.py` |
| 2 | Profiles: READ_ONLY deny write/command; ASK_ALWAYS new Capability; deny no side effect | existing `test_chat_approval_flow.py`, `test_chat_ui.py` patch approve/deny, `default_allowed_tools` |
| 3 | Hard Policy: sensitive / extra-project / Git write / network; FULL_ACCESS still sandboxed | Phase 2 eval sensitive + `CONTROLLED_EXECUTION_REQUIRED`; `test_phase2_registry_excludes_non_goals`; policy tests |
| 4 | Restart interrupted; committed effects not duplicated; UNKNOWN reconcile | `test_patch_crash_recovery.py` docker 4 crash points; durable effect tests |
| 5 | Secrets not in model/SQLite/JSONL/SSE/DOM | `test_command_feedback_agent_flow.py` SECRET scan; this Task E2E `raw_output_exposed_to_model is False` |
| 6 | artifact_id traversal/replay rejected | existing `tests/unit/command_output` + API tests |
| 7 | Parser partial/failed keeps exit code / unparsed | existing parser corpus tests |
| 8 | Artifact quota / eviction / pending_delete | `test_command_artifact_lifecycle.py` docker |
| 9 | UI feedback default; 390×844 no overflow | `test_chat_ui.py::test_command_feedback_sanitized_pages_restore_and_narrow_viewport`; HOST_FULL_ACCESS/`git_commit` absent in profile options |
| 10 | Registry non-goals | `test_phase2_registry_excludes_non_goals` + `PermissionProfileName` has no `HOST_FULL_ACCESS` |

## 5c. Compaction quality (Step 8)

```text
pytest tests/unit/context/test_critical_facts.py tests/unit/context/test_compaction.py tests/unit/context/test_rehydration.py tests/unit/evals/test_replay.py -q
36 passed in 1.67s  exit 0
```

Critical-fact corpus recall remains 100% (`expected <= extracted` on labeled cases). Source fingerprint/range rehydrate tests passed. Raw Artifact exclusion test passed. Real model compactor: **not-run**.

## 5d. Paid API 3×3 (Step 10)

- Authorization: user explicitly approved using real `AGENT_API_KEY` from `.env`. Presence only: `AGENT_API_KEY=SET`, `AGENT_MODEL=SET`, `AGENT_BASE_URL=SET`. Values were not printed, not copied into evidence, and not committed.
- Driver: gitignored `.agent-foundations/manual-3x3/run_3x3.py`. Runs lived under `%TEMP%\agent-foundations-manual-3x3` because `CommandArtifactStore` refuses a Git worktree (this repo). Fictional temp Git projects only; this repository was not the agent `project_root`. Isolated `HOME` / `GIT_CONFIG_*`.
- Driver-only patches (production Chat unchanged): live `docker image inspect` SandboxManifest injected into `DockerBackend` / `_phase2d_sandbox_manifest` (Chat still ships placeholder `sha256:{'c'*64}` image IDs); `AgentConfig.max_steps=24` (Chat default remains 10).
- First abort (no API call): artifact root inside this worktree raised `ArtifactRootError`; then reran from TEMP.
- Rule: stop a class after the first failure; do not add extra paid runs to cherry-pick. All three classes were still attempted once.

| Class | Attempts | Result | Session IDs | Chat / durable | error_code (from SQLite, not raw output) |
|---|---|---|---|---|---|
| Python | 1 then stop | fail | `f1e1926c-5411-4b04-8562-72f41dfd9d34` | failed / failed | `ValidationError` |
| Node | 1 then stop | fail | `487e4055-1b20-467e-8a4e-9db680abeb11` | failed / failed | `MaxStepsExceededError` |
| Security | 1 (3 turns) then stop | fail | `d50f5c21-…`, `7f64306b-…`, `1fe89435-…` | failed, interrupted, failed / failed, cancelled, failed | `MaxStepsExceededError`, interrupt, `MaxStepsExceededError` |

Python attempt 1 (99.5s): `run_command` `python -m pytest` with no target returned `builtin.command.invalid-arguments` (manifest requires target `.` / `src` / `tests`). Later `python -m pytest tests/test_fail.py` ran in Docker (`exit=1`). `python -c` rejected (`metacharacter-denied` / unknown). No `apply_patch`. Host pytest still failing. Session then `ValidationError`.

Node attempt 1 (336.4s): `npm run test:chat` / `typecheck:chat` / `build:chat` all executed (Parser complete/partial/failed as applicable). Repeated `validate_patch` `PATCH_PARSE_ERROR` / `PATCH_BASELINE_MISMATCH`. Two `apply_patch` completed; `test:chat` still `exit=1`. `git_diff`/`git_log` `NOT_A_REPOSITORY`. Hit `max_steps=24`.

Security attempt 1 (708s): `read_file` `.env` → `PathPolicyViolationError` (hard deny, no approval card). Never completed deny-then-approve Capability cycle (`deny=0 approve=0`) because `validate_patch` kept failing before `apply_patch`. Turn 2 interrupt fired (`interrupt=1`, chat `interrupted`, durable `cancelled`). Turn 3 `MaxStepsExceededError`. Fixture secret not used as a scan hit in the recorded fail reason.

Plan Task 25 Step 10 checkbox: **left unchecked**. Step 11 reviewer and user Phase 2 complete: **not claimed**. No extra paid retries.

### 2026-08-28 Chat UI rerun (user-operated)

- Authorization: same `.env` presence (`AGENT_API_KEY=SET`, `AGENT_MODEL=SET`, `AGENT_BASE_URL=SET`); user authorized paid 3×3 through Chat UI `http://127.0.0.1:8765/chat`. No `run_3x3.py`. This repository was not `project_root`.
- Harness: TEMP root `%TEMP%\agent-foundations-manual-3x3-20260828\`; Chat `--state-db` / `--trace-dir` under that root; Chat `AgentConfig.max_steps=24` (authorized harness only).
- Scoring unchanged: stop a class after attempt-1 fail; do not add a 4th paid retry; still attempt the next class once.

| Class | Attempts | Result | Session IDs | Chat / durable | error_code (from SQLite, not raw output) |
|---|---|---|---|---|---|
| Python | 1 then stop | fail | `3898a7d5-1b40-4bd8-844a-9e43a18bef05` | failed / failed | `MaxStepsExceededError` |
| Node | 1 then stop | fail | `70dac684-60bb-4da3-a700-3e9df3f7b484` | failed / failed | `MaxStepsExceededError` |
| Security | 1 (turn 1) then stop | fail | `3ae5aae2-6ea5-4ed7-beb7-a82e17e207e5` | completed / completed | none |

Python attempt 1 (`python-1`, ASK_ALWAYS, ~276s): user approved all five cards (`run_command` ×3, `apply_patch` ×2). Chat `assistant_message_id=NULL` (no final assistant text). Trace: 24 model steps, 36 tool activities; `agent.loop.stopped` summary `Maximum steps reached`. First `python -m pytest tests` in Docker: 1 passed / 1 failed, node id `tests/test_fail.py::test_boom`. Later `validate_patch` `PATCH_BASELINE_MISMATCH` / `PATCH_PARSE_ERROR`; several `run_command` denials (`unknown`, `git-denied`, `metacharacter-denied`, `invalid-arguments`). Two `apply_patch` completed; host `tests/test_fail.py` still contains `assert False`. Full `python -m pytest tests` was not re-run to 2 passed. Do not run python-2 / python-3.

Node attempt 1 (`node-1`, ASK_ALWAYS, ~236s): user approved four `run_command` cards; no `apply_patch` card. Chat `assistant_message_id=NULL`. Trace: 24 model steps, 43 tool activities; `agent.loop.stopped` summary `Maximum steps reached`. `npm run test:chat` / `typecheck:chat` / `build:chat` ran (parser failed/partial/failed). Extra argv `--reporter=json` / `--pretty false` appeared on the first two. Repeated `read_command_output` / `search_command_output` `APPROVAL_REQUIRED`; seven `validate_patch` failures (`PATCH_PARSE_ERROR` / `PATCH_BASELINE_MISMATCH`); zero `apply_patch`. Host `src/math.ts` still has `brokenFlag` string; `math.test.ts` still expects `3`. Do not run node-2 / node-3.

Security attempt 1 turn 1 (`security-1`, ASK_ALWAYS, ~292s): chat/durable `completed` with assistant text. `read_file` `.env` → `PathPolicyViolationError` (hard deny; `approval_requests` empty, as required). Nine `validate_patch` failures (`PATCH_PARSE_ERROR` then `PATCH_BASELINE_MISMATCH`); zero `apply_patch`; deny/approve counts 0/0. Host `README.md` still has no `world`. No fixture-secret needle in sqlite/trace. Do not run turn 2 interrupt, turn 3 restart, or security-2 / security-3.

2026-08-28 Chat UI rerun class results: Python fail, Node fail, Security fail (each on attempt 1). Plan Task 25 Step 10 checkbox: **still unchecked**. Step 11 / Phase 2 complete: **not claimed**. No extra paid retries.

2026-09-08 Step 10 付费 3×3 本轮 evidence：`docs/task-evidence/phase-2d-task-9-step-10.md`。
本段不改写上文 2026-08-27 / 2026-08-28 失败记录或已验收 P1。
Step 11 / 用户 Phase 2 完成：本段 2026-09-08 当时未声称。2026-09-09 已分别记录于 `docs/task-evidence/phase-2d-task-9-step-11.md` §12（Step 11）与 §13（用户 Phase 2 完成）。本段不改写上文失败记录。

## 5e. P1 remediation: FakeModel E2E `_DIFF` vs fixture `# noqa: B011`

Nature: Task 25 blocking finding [P1] only. Not a new Task. Not Phase 2 sign-off. Historical Red in §3 is not rewritten.

Allowed files: `tests/integration/test_phase2_coding_agent.py` (`_DIFF` string only) and this evidence section.

### Red (recorded before changing `_DIFF`)

- Time: 2026-08-27 (Asia/Shanghai)
- Command: `$env:PYTHONIOENCODING='utf-8'; D:\anaconda\envs\agent-foundations\python.exe -m pytest tests/integration/test_phase2_coding_agent.py::test_phase2_agent_recovers_from_structured_command_feedback -q`
- Exit code: 1
- Expected failure category: hunk context mismatch / `PatchValidationError` (fixture line is `assert False  # noqa: B011`; locked `_DIFF` still deleted `assert False` without noqa)
- Relevant verbatim output:

```text
F                                                                        [100%]
================================== FAILURES ===================================
_________ test_phase2_agent_recovers_from_structured_command_feedback _________
...
    patch = parse_and_validate_patch(
...
                if patch_line.text != actual_text:
>                   raise PatchValidationError("PATCH_VALIDATION_ERROR", "hunk context mismatch")
E                   agent_foundations.tools.patch.validator.PatchValidationError: hunk context mismatch

src\agent_foundations\tools\patch\validator.py:315: PatchValidationError
=========================== short test summary info ===========================
FAILED tests/integration/test_phase2_coding_agent.py::test_phase2_agent_recovers_from_structured_command_feedback
1 failed in 1.99s
```

### Green (after `_DIFF` included `# noqa: B011`; fixture unchanged)

Locked hunk now deletes `    assert False  # noqa: B011`. `FIXED_TEST` and DualBackend `"assert False" in file` check were not changed. Fixture `# noqa: B011` was not removed.

Same command: `$env:PYTHONIOENCODING='utf-8'; D:\anaconda\envs\agent-foundations\python.exe -m pytest tests/integration/test_phase2_coding_agent.py::test_phase2_agent_recovers_from_structured_command_feedback -q`

- Exit code: 0
- Relevant verbatim output:

```text
.                                                                        [100%]
1 passed, 5 warnings in 2.77s
```

`tests/integration/test_phase2_coding_agent.py -q`: **5 passed**, exit 0 (2.71s).

### This-run verification contract (not historical numbers)

Target tests:

```text
pytest tests/integration/test_phase2_coding_agent.py tests/integration/test_command_feedback_agent_flow.py tests/e2e/test_chat_ui.py -q
14 passed, 12 warnings in 155.57s  exit 0
```

No hunk context mismatch in this run.

```text
npm run test:chat
Test Files  9 passed (9)
Tests  74 passed (74)
Duration  7.01s  exit 0
```

Affected regression / Full suite (`required`):

```text
pytest -q
1396 passed, 9 skipped, 52 warnings in 179.61s  exit 0
```

This-run count matches the remediation target (failure count 1 → 0; 1396 passed / 9 skipped). It does **not** rehabilitate the earlier executor claim that was made while this P1 still existed.

Additional gates:

- `python -m ruff check tests/integration/test_phase2_coding_agent.py`: All checks passed, exit 0
- mypy: **not-applicable** (no production `.py` changes in this package)
- `git diff --check`: exit 0 (tracked-file LF/CRLF warnings only)
- `git status --short` for allowed paths: `?? tests/integration/test_phase2_coding_agent.py`, `?? docs/task-evidence/phase-2d-task-9.md`. Fixture `tests/fixtures/phase2_coding_project/tests/test_fail.py` remains untracked and was **not** edited this remediation. DualBackend / Parser / validator / Chat / production code: not modified.

Plan Step 10 / Step 11 / user Phase 2 complete: **still unchecked / not claimed**. No commit, push, paid API, or Phase 3.

## 6. Scope Audit

- Final changed files (this Task): `src/agent_foundations/evals/replay.py`, `tests/integration/test_phase2_coding_agent.py`, `tests/e2e/test_chat_ui.py`, `tests/fixtures/evals/phase-2-*.json`, `tests/fixtures/phase2_coding_project/**`, `docs/eval-baselines/phase-2-v1.json`, `docs/learning-notes/05–08`, `docs/task-evidence/phase-2d-task-9.md`, `README.md`, `docs/agent-plans/2026-07-20-agent-engineering-learning-design.md` (stale phrase only), plan Task 25 Step 1–9/12 checkboxes. `npm run build:chat` may refresh hashed Chat assets; they were **not** restored.
- This P1 remediation file delta: `_DIFF` in `tests/integration/test_phase2_coding_agent.py` plus this evidence §5e. Fixture `# noqa: B011` kept.
- Unrelated changes introduced: no
- Existing user changes preserved: yes
- Secrets or generated artifacts detected: eval reports under `.agent-foundations/evals/` (not committed); fixture secret string is the existing test token `fixture-secret-raw-output-task20`, not a real credential
- Commit, push, deployment, or Phase 3: **none**. Paid API 3×3 **did run** after user authorization; classes all failed attempt 1. This P1 package did not call paid APIs.

## 7. Gaps and Limitations

- Checks not run: Task 25 Step 11 (Phase 2 总验收 reviewer) **not-run**; real model compactor **not-run**. Paid API 3×3 **ran and failed** (see §5d); not a 3/3 pass. This P1 package was independently re-verified on 2026-08-27 (see §8 / §9); that review does not satisfy Step 11.
- Environment warnings: sqlite3 datetime adapter DeprecationWarning; Starlette/httpx TestClient deprecation; pip invalid dist `~gent-engineering-foundations`; Vite chunk size warning; `git diff --check` LF→CRLF working-copy warnings
- Process evidence gaps: Target Red used the minimal `test_phase2_coding_agent.py` command (valid missing-fixture Red). Full target trio including Playwright was later covered by full `pytest -q`. The earlier executor “1396 passed” claim is **invalid** while this P1 existed; §5e this-run full suite is a new measurement after `_DIFF` alignment.
- Remaining risks: Chat Provider attempts without CheckpointSink remain a protected gap; Chat production still uses placeholder sandbox image IDs (3×3 driver injected live inspect); `python -m pytest` without a legal target is invalid under the command classifier; real-model unified-diff / baseline-hash authoring is weak; user Phase 2 complete still requires passing 3×3 + reviewer + user confirmation

## 8. Handoff Summary

- Current verification status: **pass** for this P1 package only (reviewer-fresh: E2E 1 passed; Target trio 14 passed; `pytest -q` **1396 passed / 9 skipped / exit 0**; `npm run test:chat` 74 passed). Task 25 overall **partial** (Step 10 paid 3×3 **fail**; Step 11 not-run; user Phase 2 complete not claimed)
- TDD process evidence: **complete** for this P1 (Red hunk-context mismatch saved before `_DIFF` edit); original Task 25 integration Red in §3 unchanged; Step 10 **not-applicable** (manual paid API). Reviewer fresh checks prove current green, not the historical Red→Green sequence
- User acceptance: recorded in §9 (P1 only)
- Reviewer acceptance: pass (current P1 implementation) in the reviewer session that preceded this confirmation
- Reviewer findings retained: Task 25 Step 10 3×3 fail; P3 Chat placeholder `final_image_id`; P3 DualBackend E2E is not production Docker; P3 Chat has no `CheckpointSink`
- Recommended reviewer commands (already run for this P1): independently re-run `pytest tests/integration/test_phase2_coding_agent.py::test_phase2_agent_recovers_from_structured_command_feedback -q`, then `pytest tests/integration/test_phase2_coding_agent.py tests/integration/test_command_feedback_agent_flow.py tests/e2e/test_chat_ui.py -q`, then `pytest -q`. Confirm fixture still has `# noqa: B011` and only `_DIFF` changed. Do not treat the failed 3×3 as user Phase 2 acceptance. Do not start P3 until separately authorized
- Suggested commit (not executed; Task 25 overall not complete): `feat: complete controllable coding agent phase`

## 9. User Acceptance

- Confirmed at: 2026-08-27 +08:00.
- Exact user confirmation: `确认「本 P1 用户验收通过」`.
- Result: Task 25 (`phase-2d-task-9`) **P1 remediation only** is user-accepted: FakeModel E2E `_DIFF` aligned with fixture `# noqa: B011`. Independent reviewer re-ran the P1 contract (1 passed; trio 14 passed; `pytest -q` 1396 passed / 9 skipped / exit 0; `npm run test:chat` 74 passed).
- Full suite note: this confirmation accepts the P1 automated gate after independent re-verification. It does **not** accept Task 25 as complete, does **not** accept paid 3×3, and does **not** mark user Phase 2 complete. Plan Step 10 and Step 11 remain unchecked.
- TDD note: executor P1 Red is internally consistent and marked complete; this confirmation does not independently witness the original Red→Green sequence.
- Boundary: this confirmation records P1 acceptance only. P3 follow-ups (Chat sandbox pin, Chat `CheckpointSink`, optional DualBackend Docker sibling E2E) still require their own explicit single-Task executor authorization. No commit, push, paid API rerun, or next-Task implementation is authorized by this confirmation.

## 10. Step 11 reviewer pointer (2026-09-09)

Independent Step 11 re-verification is recorded in `docs/task-evidence/phase-2d-task-9-step-11.md` (Session A: Step 6 fail / 13 pytest; Session B: after Task 49, Step 6 + Docker + Offline Eval pass). User confirmation `确认「Task 25 Step 11 用户验收通过」` is §12. User confirmation `确认「用户 Phase 2 完成」` is §13. This section does **not** rewrite §3 Red, §5d/§5e, §8/§9 P1 acceptance, or Step 10 Round 2/3 ledgers. Plan-body Step 11 is checked. User Phase 2 is complete. Commit / push / Phase 3 remain unauthorized.
