# Task Evidence: phase-2d-task-2

## 1. Identity

- Task ID: `phase-2d-task-2`
- Authoritative plan or task spec: Task 18 in `docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md` plus the user-confirmed executor prompt for Task 18
- Evidence status: user-accepted / targeted verification, full suite, and authorized Docker lifecycle pass
- TDD required: yes
- Started at: 2026-08-26 13:10:31 +08:00 (Asia/Shanghai)
- Dependency: Task 17 (`phase-2d-task-1`) user-accepted 2026-08-26 12:45:34 +08:00; evidence `docs/task-evidence/phase-2d-task-1.md` §15

## 2. Pre-change Snapshot

- Branch: `codex/phase-2-next` (not `main`)
- Initial `git diff --check`: exit `0` (LF/CRLF working-copy warnings only; no whitespace errors)
- Existing user changes that must be preserved: all tracked and untracked Task 15–17 work, Chat hashed assets, `.agents/`, `.gate-backup/`, and every other dirty path present at start. No `git reset` / `restore` / `checkout --` / `clean` / stage / commit / push.
- Intended modification scope: only the Task 18 Create/Modify list, this evidence file, and Task 18 Step 1–9 checkboxes when actually satisfied. Documented exceptions if required:
  - `src/agent_foundations/execution/fake.py` if FakeBackend must stream / cancel / timeout for Target tests without Docker
  - shared `user_version == 8` pins in other tests if v9 makes Affected/Full suite fail (mechanical migration pin only)
- Protected files: Chat hashed assets, `.agents/`, `.gate-backup/`, real `.env`, Task 17 classifier/snapshot/image design, Policy matrix, Chat/API/UI, Parser, Git tools
- Expected rollback: delete only Task 18-created files; reverse only Task 18 hunks in allowed Modify files. Do not touch pre-existing user hunks.
- Artifact root strategy: production default `%LOCALAPPDATA%\AgentFoundations\command-output` (POSIX: user local application data / XDG data home equivalent). Tests always use an isolated tmp root. Reject project directory, Git worktree, relative paths, and symlink/reparse-point roots. Never write production data into the real user directory during this Task.
- Worktree decision: remain on existing dirty `codex/phase-2-next` because accepted Task 17 state exists only in this checkout.

### Docker / image read-only availability (Step 1)

Command: `docker version; docker image inspect agent-foundations-sandbox-python:phase2d agent-foundations-sandbox-node:phase2d agent-foundations-sandbox:phase2 --format "{{.RepoTags}} {{.Id}} {{.Config.User}}"`

Exit code: `0`

Key results:

- Docker Desktop 4.74.0; Engine 29.4.3; OS/Arch linux/amd64
- `agent-foundations-sandbox-python:phase2d` image ID `sha256:730aea0a2ba8ef2998bb0cc43b1f94641a9099f8a0d55b22a0605f384ad26e41` user `65532:65532`
- `agent-foundations-sandbox-node:phase2d` image ID `sha256:eb349e91bdf800e6065b700e315439dc443547b726cc3bd098e18cd952bb5f21` user `65532:65532`
- `agent-foundations-sandbox:phase2` (Patch) image ID `sha256:ae7d37eae541b4ead4f60614b25f3fe9f934298c332b2441f31d2ceec37a9569` user `65532:65532`

This Task's authorized Docker mutation scope:

- Allow: read-only inspect; Task 18 Docker command lifecycle / smoke including `-m docker` Target/integration; exact necessary `docker build --pull=false` only for existing Python/Node command-profile or retained Phase 2C Patch image if local image is missing or inconsistent with repo Dockerfiles/locks; exact cleanup of `af-*` containers created by this Task
- Forbid: `docker prune`; pull of unrecorded new bases; registry publish; mounting Docker socket / host home / conda / venv / host `node_modules` / `.env` / credentials; host subprocess fallback. Docker failure is recorded as fail, not retried on the host.

### Complete initial `git status --short --branch`

Command: `git status --short --branch`

Exit code: `0`

```text
## codex/phase-2-next
 M .dockerignore
 M docker/README.md
 M docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md
 M pyproject.toml
 M src/agent_foundations/chat/api.py
 M src/agent_foundations/chat/events.py
 M src/agent_foundations/chat/models.py
 M src/agent_foundations/chat/repository.py
 M src/agent_foundations/chat/runner.py
 M src/agent_foundations/chat/schema.py
 M src/agent_foundations/chat/tool_execution.py
 M src/agent_foundations/cli/main.py
 M src/agent_foundations/execution/container_runner.py
 M src/agent_foundations/execution/docker.py
 M src/agent_foundations/execution/models.py
 M src/agent_foundations/runtime/tool_execution.py
 M src/agent_foundations/storage/migrations.py
 M src/agent_foundations/viewer/static/chat/index.html
 M tests/chat/app.test.tsx
 M tests/chat/reducer.test.ts
 M tests/e2e/test_chat_ui.py
 M tests/integration/test_chat_api.py
 M tests/integration/test_chat_approval_flow.py
 M tests/integration/test_execution_backend.py
 M tests/unit/chat/test_repository.py
 M tests/unit/chat/test_tool_execution.py
 M tests/unit/durable/test_effects.py
 M tests/unit/durable/test_repository.py
 M tests/unit/security/test_repository.py
 M tests/unit/storage/test_database.py
 M tests/unit/tools/patch/test_repository.py
 M web/chat/App.tsx
 M web/chat/components/ApprovalCard.tsx
 M web/chat/components/ConversationList.tsx
 M web/chat/state/reducer.ts
 M web/chat/state/types.ts
 D/?? src/agent_foundations/viewer/static/chat/assets/*  (pre-existing Chat hashed asset churn; protected)
 ?? .agents/
 ?? .gate-backup/
 ?? docker/agent-sandbox-node.Dockerfile
 ?? docker/agent-sandbox-python.Dockerfile
 ?? docker/agent-sandbox-python.requirements.lock
 ?? docker/sandbox-entrypoint.sh
 ?? docs/task-evidence/phase-2c-task-4.md
 ?? docs/task-evidence/phase-2c-task-5.md
 ?? docs/task-evidence/phase-2d-task-1.md
 ?? src/agent_foundations/execution/sandbox_manifest.py
 ?? src/agent_foundations/execution/workspace.py
 ?? src/agent_foundations/tools/command/
 ?? src/agent_foundations/tools/patch/applier.py
 ?? src/agent_foundations/tools/patch/apply_patch.py
 ?? tests/chat/patch-preview.test.tsx
 ?? tests/chat/permission-profile.test.tsx
 ?? tests/fixtures/evals/phase-2c-permission-profiles-v1.json
 ?? tests/integration/test_controlled_patch_flow.py
 ?? tests/integration/test_patch_crash_recovery.py
 ?? tests/integration/test_phase2c_profile_eval.py
 ?? tests/integration/test_task16_production_wiring.py
 ?? tests/unit/execution/test_sandbox_manifest.py
 ?? tests/unit/execution/test_workspace.py
 ?? tests/unit/tools/command/
 ?? tests/unit/tools/patch/test_applier.py
 ?? tests/unit/tools/patch/test_apply_patch.py
 ?? web/chat/components/PatchPreviewCard.tsx
 ?? web/chat/components/PermissionProfileSelect.tsx
```

Chat hashed `D`/`??` asset paths are omitted here as a compact listing of the protected churn already present; they were not modified by this Task. Full `git status --short --branch` at start enumerated those hashed filenames individually.

## Verification contract (verbatim)

- Target tests: `conda run -n agent-foundations python -m pytest tests/unit/tools/command/test_run_command.py tests/unit/command_output tests/integration/test_run_command_flow.py tests/integration/test_run_command_cancellation.py tests/integration/test_command_artifact_lifecycle.py -q`
- Affected regression tests: `conda run -n agent-foundations python -m pytest tests/unit/security tests/unit/durable tests/unit/execution tests/unit/runtime/test_tool_execution.py tests/integration/test_idempotent_tool_execution.py -q`
- Full suite: `required`
- Full suite reason: 本 Task 首次扩大到命令副作用，并修改 shared migration、durable ledger、ExecutionBackend 和 Tool executor。
- Additional gates: 经授权 Docker command lifecycle；Artifact ACL/permission probe；容量、淘汰和 crash-point matrix；禁止真实模型、网络、包安装和 host fallback。

## 3. Red

### 3.1 Artifact / SQLite v9 Red (Step 3)

- Recorded before production-code changes: yes
- Time: 2026-08-26 13:15:18 +08:00
- Test file and test name: `tests/unit/command_output/*`, `tests/unit/storage/test_database.py::test_conversation_repository_constructor_remains_compatible`, `tests/integration/test_command_artifact_lifecycle.py`
- Command: `conda run -n agent-foundations python -m pytest tests/unit/command_output tests/unit/storage/test_database.py tests/integration/test_command_artifact_lifecycle.py -q --tb=line`
- Exit code: `1`
- Relevant verbatim output:

```text
FAILED tests/unit/command_output/test_models.py::test_retention_and_parser_status_contracts
  AssertionError: command output models are missing
FAILED tests/unit/command_output/test_store.py::test_atomic_write_persists_two_streams_hash_and_owner_permissions
  AssertionError: command output store is missing
FAILED tests/unit/command_output/test_repository.py::test_artifact_repository_persists_metadata_not_output
  AssertionError: command output store is missing
FAILED tests/unit/command_output/test_retention.py::test_quota_reservation_evicts_oldest_retained_not_active
  AssertionError: command output retention is missing
FAILED tests/unit/storage/test_database.py::test_conversation_repository_constructor_remains_compatible
  assert 8 == 9
FAILED tests/integration/test_command_artifact_lifecycle.py::test_lifecycle_persists_v9_metadata_without_raw_bytes
  AssertionError: command output store is missing
31 failed, 15 passed, 1 skipped in 0.55s
```

- Expected failure category: assertion failure from missing Artifact store / v9 metadata / quota-retention behavior
- Why this failure demonstrates the missing behavior: `find_spec` returns `None` for `command_output` modules so behavioral asserts fail; ConversationRepository still initializes at `user_version == 8` instead of v9. An earlier collect-time `ModuleNotFoundError` from uncaught `find_spec` was corrected in the tests (not production) and this run was recorded before any production-code change.
### 3.2 run_command Red (Step 6)

- Recorded before run_command production-code changes: yes
- Time: 2026-08-26 (immediately after Artifact Green; FakeBackend not yet extended)
- Command: `conda run -n agent-foundations python -m pytest tests/unit/tools/command/test_run_command.py tests/integration/test_run_command_flow.py tests/integration/test_run_command_cancellation.py -q --tb=line`
- Exit code: `1`
- Relevant verbatim output:

```text
FAILED tests/unit/tools/command/test_run_command.py::test_run_command_manifest_and_resource_contract
  AssertionError: run_command tool is missing
FAILED tests/integration/test_run_command_flow.py::test_run_command_discards_workspace_writes
  AssertionError: run_command tool is missing
FAILED tests/integration/test_run_command_cancellation.py::test_run_command_cancel_stops_active_execution
  AssertionError: run_command tool is missing
14 failed, 2 skipped
```

- Expected failure category: assertion failure from missing run_command / streaming Artifact / durable lifecycle
- Why this failure demonstrates the missing behavior: `find_spec("agent_foundations.tools.command.run_command")` is None. An earlier TypeError from constructing FakeBackend extras before the spec check was corrected in tests only; this recorded run is assertion-only.

## 4. Green

### 4.1 Artifact / SQLite v9 Green (Step 4)

- Production files changed: `src/agent_foundations/command_output/{__init__,models,schema,permissions,store,repository,retention}.py`, `src/agent_foundations/storage/migrations.py`
- Command: `conda run -n agent-foundations python -m pytest tests/unit/command_output tests/unit/storage/test_database.py tests/integration/test_command_artifact_lifecycle.py -q --tb=line`
- Exit code: `0`
- Relevant verbatim output:

```text
..............................................s
46 passed, 1 skipped in 0.86s
```

### 4.2 run_command Green (Step 7)

- Production files changed: `run_command.py`, `execution/{models,docker,fake,container_runner,backend}.py`, `runtime/tool_execution.py`, `cli/main.py`
- FakeBackend exception: added `result_factory`, `workspace_root`, `workspace_side_effect`, `honor_timeout`, and `output_sink` streaming so Target tests prove cancel/timeout/quota/crash without Docker.
- Command: env python pytest Target run_command files `-q --tb=line`
- Exit code: `0`
- Relevant verbatim output:

```text
14 passed, 2 skipped, 10 warnings in 3.17s
```

- Skipped items are Docker-marked tests reserved for the authorized `-m docker` gate.

## 5. Regression and Quality Gates

Interpreter note: `conda run -n agent-foundations python ...` on this Windows host previously crashed pytest output with `UnicodeEncodeError: gbk`. All Step 8 Python commands below used the same Anaconda env interpreter `D:\anaconda\envs\agent-foundations\python.exe` with `PYTHONIOENCODING=utf-8`. Equivalent env, not a host-subprocess fallback for sandbox commands.

| Check | Command | Exit code | Result |
|---|---|---:|---|
| Target tests | `python -m pytest tests/unit/tools/command/test_run_command.py tests/unit/command_output tests/integration/test_run_command_flow.py tests/integration/test_run_command_cancellation.py tests/integration/test_command_artifact_lifecycle.py -q` | 0 | `44 passed, 3 skipped` (3 Docker-marked tests reserved for `-m docker`) |
| Affected regression | `python -m pytest tests/unit/security tests/unit/durable tests/unit/execution tests/unit/runtime/test_tool_execution.py tests/integration/test_idempotent_tool_execution.py -q` | 0 | `280 passed` |
| Combined Target+Affected after Ruff/Patch sink fix | same Target + Affected files together `-q` | 0 | `324 passed, 3 skipped` |
| Full pytest | `python -m pytest -q` | 0 | `1265 passed, 8 skipped, 42 warnings in 160.14s` |
| Ruff | `python -m ruff check .` | 0 | `All checks passed!` |
| mypy | `python -m mypy src tests` | 0 | `Success: no issues found in 213 source files` |
| pip check | `python -m pip check` | 0 | `No broken requirements found.` (pre-existing invalid-distribution warning for `~gent-engineering-foundations`) |
| `npm run test:viewer` | `npm run test:viewer` | 0 | 12 tests pass |
| `npm run typecheck:viewer` | `npm run typecheck:viewer` | 0 | tsc `--noEmit` success |
| `npm run test:chat` | `npm run test:chat` | 0 | `8 passed` files, `73 passed` tests |
| `npm run typecheck:chat` | `npm run typecheck:chat` | 0 | tsc `--noEmit` success |
| `npm run build:chat` | `npm run build:chat` | 0 | vite build success (`built in 713ms`); regenerated Chat hashed assets as a required-gate side effect (not hand-edited) |
| `git diff --check` | `git diff --check` | 0 | no whitespace errors; LF/CRLF working-copy warnings only |
| `git status --short` | `git status --short --branch` | 0 | still on `codex/phase-2-next`; Task 18 files present; pre-existing dirty tree preserved |

### 5.1 Additional gates

#### Docker command lifecycle

Command: `python -m pytest tests/integration/test_run_command_flow.py tests/integration/test_run_command_cancellation.py tests/integration/test_command_artifact_lifecycle.py -m docker -q`

Final run after UUID/Ruff/ContainerRunner fixes: exit `0`

```text
3 passed, 13 deselected, 2 warnings in 5.74s
```

Covered: non-root `--user 65532:65532`, `--network none`, read-only `/project-ro`, ephemeral `/workspace` tmpfs, memory/pids limits, live pytest in Python profile image with no project writeback, real timeout cleanup, Artifact root not in project.

#### Patch Docker regression (required because command Docker tests do not cover apply_patch)

Command: `python -m pytest tests/integration/test_execution_backend.py tests/integration/test_controlled_patch_flow.py tests/integration/test_patch_crash_recovery.py -m docker -q`

Exit `0` after ContainerRunner only forwards `output_sink` when a sink is provided (Patch test doubles stay compatible):

```text
12 passed, 10 deselected, 7 warnings in 10.07s
```

#### Image IDs / provenance (no rebuild; `--pull=false` not used)

- `agent-foundations-sandbox-python:phase2d` `sha256:730aea0a2ba8ef2998bb0cc43b1f94641a9099f8a0d55b22a0605f384ad26e41` user `65532:65532`
- `agent-foundations-sandbox-node:phase2d` `sha256:eb349e91bdf800e6065b700e315439dc443547b726cc3bd098e18cd952bb5f21` user `65532:65532`
- `agent-foundations-sandbox:phase2` `sha256:ae7d37eae541b4ead4f60614b25f3fe9f934298c332b2441f31d2ceec37a9569` user `65532:65532`

`docker ps -a --filter name=af-` after Docker gates: `AF_RESIDUE=none` (`AF_RESIDUE_COUNT=0`).

#### FakeBackend ACL / quota / crash-point matrix

Covered by Target tests without Docker: owner-only permissions, 64 MiB / 1 GiB / 7 days, eviction of oldest retained not active, `ARTIFACT_CAPACITY_EXCEEDED` before sandbox start, `OUTPUT_LIMIT_EXCEEDED` + `output_truncated=true`, Artifact finalize failure → `OUTPUT_ARTIFACT_WRITE_FAILED` without rerun, CrashPoint `before_intent`/`after_intent`/`after_claim`/`after_execute`/`after_commit`.

No real model, network Tool, package install, or host subprocess fallback was used for command execution.

## 6. Scope Audit

Task 18 created:

- `src/agent_foundations/command_output/{__init__,models,schema,permissions,store,repository,retention}.py`
- `src/agent_foundations/tools/command/run_command.py`
- `tests/unit/command_output/*`
- `tests/unit/tools/command/test_run_command.py`
- `tests/integration/test_run_command_flow.py`
- `tests/integration/test_run_command_cancellation.py`
- `tests/integration/test_command_artifact_lifecycle.py`
- `docs/task-evidence/phase-2d-task-2.md`

Task 18 modified (allowed):

- `execution/{models,docker,container_runner}.py`
- `runtime/tool_execution.py`
- `cli/main.py` (`include_run_command` opt-in; `build_chat_services` does not register `run_command`)
- `storage/migrations.py` (v9)
- `tests/unit/storage/test_database.py` (`user_version == 9`)
- plan Task 18 Step 1–9 checkboxes only

Documented exceptions:

- `src/agent_foundations/execution/fake.py`: FakeBackend streaming / cancel / timeout / `result_factory` so Target Red/Green/crash/quota work without Docker.
- `src/agent_foundations/execution/backend.py`: Protocol `execute(..., output_sink=None)` so Docker/Fake/ContainerRunner share one signature. Patch path still omits the sink.
- `src/agent_foundations/durable/effects.py`: listed as Modify; **no production hunk required** — existing ledger already records PROCESS intents and terminal ToolResult without raw stdout.
- Shared migration pins only (not Chat product wiring): `tests/unit/durable/{test_repository,test_effects}.py`, `tests/unit/security/test_repository.py`, `tests/unit/chat/test_repository.py`, `tests/unit/tools/patch/test_repository.py`, `tests/integration/test_chat_api.py` — `user_version` 8→9, future-reject 9→10, v1 upgrade drops `command_output_artifacts`.

Required-gate side effect: `npm run build:chat` regenerated `src/agent_foundations/viewer/static/chat/assets/*` hashes. Executor did not hand-edit those files. Pre-existing dirty Chat assets, `.agents/`, `.gate-backup/`, and Task 15–17 files were preserved. No `git reset` / restore / commit / push.

- Unrelated product changes introduced: no (hashed-asset churn is the required build gate, not a Chat feature)
- Existing user changes preserved: yes
- Secrets or generated artifacts detected: no raw command logs in SQLite/ToolResult; tests use `fixture-secret` / `fixture-secret-output` placeholders
- Commit, push, deployment, paid API call, or next Task performed: no

## 7. Gaps and Limitations

- Checks not run: none of the contracted Step 8 commands. Docker image rebuild not needed.
- Environment warnings: sqlite3 datetime adapter DeprecationWarning; FastAPI/Starlette TestClient warning; pip invalid-distribution `~gent-engineering-foundations`; npm notice of a newer npm major.
- Process evidence gaps: none for Red→Green sequence of Artifact and run_command; original Reds were recorded before their production modules existed.
- Remaining risks: Chat production still does not expose `run_command` (Task 20). Parser/read APIs not implemented (Task 19). Reviewer must independently rerun current verification.

### Termination matrix

| Path | Command / Tool | Effect | Artifact | Notes |
|---|---|---|---|---|
| Classifier hard-deny | `success=False`, existing rule id | no ledger row | none | never Capability/Sandbox |
| Policy deny | `POLICY_DENIED` | no claim | none | existing Policy chain |
| Approval ask, no decider | `APPROVAL_REQUIRED` | no claim | none | existing Approval chain |
| Non-zero exit | `success=True`, `exit_code` scalar | COMMITTED | retained/active metadata, raw on disk | not an execution-chain failure |
| Timeout / cancel | `COMMAND_INTERRUPTED` | FAILED | metadata + files kept | FakeBackend + Docker timeout |
| 64 MiB | `OUTPUT_LIMIT_EXCEEDED`, `output_truncated=true` | FAILED | partial files kept | execution stopped |
| Capacity | `ARTIFACT_CAPACITY_EXCEEDED` | intent may exist, command not started | active not evicted | before Sandbox |
| Finalize fail | `OUTPUT_ARTIFACT_WRITE_FAILED` | FAILED with command outcome scalars | not durable / not rerun | restart does not re-execute |
| Crash before_intent | InjectedCrash | no effect | none | retry allowed |
| Crash after_intent | InjectedCrash then recover | INTENT_RECORDED then execute once | as success path | |
| Crash after_claim / after_execute | InjectedCrash | EXECUTING/UNKNOWN | no automatic rerun | `EffectResolutionRequiredError` |
| Crash after_commit | InjectedCrash | COMMITTED | existing result returned | no duplicate execute |
| Delete run | n/a | n/a | `pending_delete` → `deleted` / `delete_failed` | other runs untouched |

Migration: SQLite `PRAGMA user_version` v9 table `command_output_artifacts` metadata-only. v10 not occupied.

Leak scan: Target tests assert `fixture-secret` / `fixture-secret-output` are absent from SQLite bytes and from ToolResult content/metadata; Docker flow test asserts DB bytes do not contain stdout payload.

## 8. Handoff Summary

- Current verification status: pass (targeted + full suite; Docker lifecycle pass). Independently reviewed; user-accepted 2026-08-26.
- TDD process evidence: complete as executor-submitted material; reviewer did not independently witness the historical Red→Green sequence.
- Recommended reviewer commands: the verification contract Target, Affected, Full suite, and `pytest ... -m docker` commands above.

Suggested commit (not executed): `feat: persist sandbox command artifacts safely`

## 9. User Acceptance

- Confirmed at: 2026-08-26 14:29 +08:00.
- Exact user confirmation: `确认验收通过`.
- Result: Task 18 (`phase-2d-task-2`) is user-accepted; the `Task 18 accepted` dependency named by Task 19 is satisfied.
- Boundary: this confirmation records acceptance only. Task 19 has not been started and still requires its own explicit single-Task executor authorization. No commit, push, or next-Task implementation is authorized by this confirmation.
- Reviewer acknowledgment: 2026-08-26 reviewer session recorded the same user confirmation and updated plan §0 / Task 18 user-acceptance note.
