# Task Evidence: phase-2c-task-3

## 1. Identity

- Task ID: `phase-2c-task-3` (Plan Task 14)
- Task name: ExecutionBackend 与最小 Docker Sandbox
- Authoritative plan: `docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md` Task 14
- Evidence status: `pass` (implementation, real Docker smoke, and executor gates pass; independent reviewer verification remains pending)
- TDD required: `yes`
- Started at: `2026-08-12`
- Depends on: Task 13 accepted by the user on 2026-08-12
- Authorization: implementation, no-daemon tests, full quality gates, the exact Task 14 Docker build/smoke, the fixed `python:3.12-slim-bookworm` pull, and necessary exact cleanup are authorized. Dependency installation, host fallback, Task 15, broad cleanup, commit, push, and PR remain unauthorized.

Task 13's overall TDD process evidence remains `partial` as recorded in its own evidence. This Task does not rewrite it.

## 2. Pre-change Snapshot

- Branch: `main`, ahead of `origin/main` by 1 commit.
- Staging area: empty.
- Working tree: heavily dirty with preserved tracked and untracked work from prior Tasks and generated Chat assets.
- Task 14 production/test/Docker/evidence paths existed before this Task: `no`.
- `pyproject.toml`: existing tracked file; no Task 14 marker yet.
- Phase 2 plan: existing untracked authoritative plan; Task 14 Steps 1-7 all unchecked.
- Task-start `git diff --check`: exit `0`; existing LF-to-CRLF warnings only.
- Existing user/prior-Task changes to preserve: all current tracked/untracked files, including `.gate-backup`, Phase 2 modules/evidence, Chat/UI changes, and generated assets.

### Intended scope

- Create only the authorized `execution/`, Docker, test, `.dockerignore`, and evidence files.
- Modify only `[tool.pytest.ini_options]` in `pyproject.toml` and Task 14 checkboxes with real evidence.
- Do not register an Agent Tool or implement `apply_patch`, `run_command`, Git, host execution, network access, Profile v8, or Task 15.

### Rollback

Delete only Task 14-created files and reverse only the Task 14 marker/checkbox hunks. Do not reset, restore, clean, remove `.gate-backup`, or disturb prior dirty-worktree content.

## 3. Docker Availability and Authorization

Read-only command:

```powershell
docker version
```

```text
Exit code: 1
Client version: 29.4.3, API 1.54, windows/amd64, context desktop-linux
Server: unavailable
failed to connect to npipe:////./pipe/dockerDesktopLinuxEngine; the pipe does not exist
```

Read-only command:

```powershell
docker image inspect python:3.12-slim-bookworm --format '{{.Id}}'
```

```text
Exit code: 1
No image ID returned because the Docker daemon is unavailable.
```

- Docker CLI: available.
- Docker daemon/server: unavailable at Task start.
- Base image presence/image ID: unverifiable while daemon is unavailable.
- User later authorized the exact Task 14 Docker build and smoke, plus necessary exact cleanup.
- Docker pull remains unauthorized. The executor will not start Docker Desktop, pull an image, run `prune`, or use a host fallback.

### Resumed availability check after the user started Docker Desktop

```powershell
docker version
docker image inspect python:3.12-slim-bookworm --format '{{.Id}}'
docker image inspect agent-foundations-sandbox:phase2 --format '{{.Id}}'
```

```text
docker version exit 0:
  Client 29.4.3; Server Docker Desktop 4.74.0 / Engine 29.4.3; linux/amd64.
base image inspect exit 1:
  Error response from daemon: No such image: python:3.12-slim-bookworm
target image inspect exit 1:
  Error response from daemon: No such image: agent-foundations-sandbox:phase2
```

The daemon was available, but the fixed base image was absent. The executor paused before build and obtained explicit pull authorization from the user before continuing.

## 4. Red

- Recorded before production-code changes: `yes`.
- Production files changed before Red: `no`.

### Invalid preliminary attempt

Command:

```powershell
conda run -n agent-foundations python -m pytest tests/unit/execution tests/integration/test_execution_backend.py -m "not docker" -q
```

```text
Internal pytest: 50 failed, 1 deselected in 0.60s
Conda reported command failure while the shell wrapper surfaced exit code 0.
Every failure raised ModuleNotFoundError from find_spec() because the parent
agent_foundations.execution package did not exist.
```

Validity: `invalid`. This is an import error rather than the required assertion failure. It is not counted as the Task Red. Only the test helper will be corrected before rerun; production code remains unchanged.

### Authoritative Red

Required command:

```powershell
conda run -n agent-foundations python -m pytest tests/unit/execution tests/integration/test_execution_backend.py -m "not docker" -q
```

```text
Internal pytest: 50 failed, 1 deselected in 0.58s
Every failure was AssertionError: Task 14 execution package is missing.
Conda reported command failure while the shell wrapper surfaced exit code 0.
```

The same suite was rerun with the confirmed environment interpreter before any production change:

```powershell
& 'D:\anaconda\envs\agent-foundations\python.exe' -m pytest tests/unit/execution tests/integration/test_execution_backend.py -m "not docker" -q --tb=short
```

```text
Exit code: 1
50 failed, 1 deselected in 0.57s
Representative failure: AssertionError: Task 14 execution package is missing
```

Validity: `valid`. Pytest collected normally; the explicit docker smoke was deselected; all failures are behavior assertions caused by the missing Task 14 package, not syntax, import, collection, Docker, or environment errors.

### Refinement Red: exact container cleanup and daemon classification

After the first Green, a line-by-line cancellation audit found that terminating only the attached Docker CLI did not prove exact container cleanup. Three focused tests were added before changing that production behavior.

```powershell
& 'D:\anaconda\envs\agent-foundations\python.exe' -m pytest tests/unit/execution/test_docker.py::test_backend_cancel_targets_exact_active_execution_and_duplicate_fails tests/unit/execution/test_docker.py::test_backend_timeout_cleans_only_exact_container tests/unit/execution/test_docker.py::test_backend_daemon_error_is_unavailable_not_normal_nonzero -q
```

```text
Exit code: 1
3 failed in 0.34s
Two failures: DockerBackend did not accept the required cleanup_factory seam.
One failure: AttributeError because bytes has no casefold() during daemon-error classification.
```

Validity: `valid`. The failures directly demonstrate missing exact-container cleanup and a real unavailable-classification defect; they are not environment or Docker-daemon failures.

### Remediation Red: caller cancellation, cleanup retry, exit-125 classification, and no-pull runtime

After independent probes reproduced a leaked process on direct `execute()` task cancellation and a workload exit `7` being misclassified from stderr text, regression tests were added before changing production code.

```powershell
& 'D:\anaconda\envs\agent-foundations\python.exe' -m pytest tests/unit/execution/test_docker.py -q --tb=short
```

```text
Exit code: 1
9 failed, 13 passed in 2.57s
Failures:
- Docker argv lacks --pull never.
- execute() task cancellation does not enter cleanup, retain the active record, terminate a launched process, or handle cancellation during stdin/stdout.
- explicit cancel plus task cancellation does not share a cleanup lifecycle.
- cleanup launch failure is silently swallowed and cannot be retried observably.
- workload exit 7 with "no such image" is misclassified as BackendUnavailableError.
- unknown Docker CLI exit 125 is returned as a normal workload result instead of BackendLaunchError.
```

Validity: `valid`. All nine failures are direct behavioral assertions for the reviewed security/lifecycle defects; collection and environment succeeded, and production code had not been changed for this remediation.

## 5. Green

Initial target Green after the minimum implementation:

```powershell
conda run -n agent-foundations python -m pytest tests/unit/execution tests/integration/test_execution_backend.py -q
```

```text
Exit code: 0
50 passed, 1 deselected in 0.28s
```

The exact-cleanup and unavailable-classification refinement tests then passed:

```powershell
& 'D:\anaconda\envs\agent-foundations\python.exe' -m pytest tests/unit/execution/test_docker.py::test_backend_cancel_targets_exact_active_execution_and_duplicate_fails tests/unit/execution/test_docker.py::test_backend_timeout_cleans_only_exact_container tests/unit/execution/test_docker.py::test_backend_daemon_error_is_unavailable_not_normal_nonzero -q
```

```text
Exit code: 0
3 passed in 1.18s
```

Final target suite after the smoke-fixture correction:

```powershell
conda run -n agent-foundations python -m pytest tests/unit/execution tests/integration/test_execution_backend.py -q
```

```text
Exit code: 0
52 passed, 1 skipped in 1.25s
```

The one skipped test is the explicitly gated real Docker smoke. It is collected but intentionally skipped unless the exact `-m docker` expression is supplied.

### Remediation Green

Focused regression suite:

```powershell
& 'D:\anaconda\envs\agent-foundations\python.exe' -m pytest tests/unit/execution/test_docker.py -q --tb=short
```

```text
Exit code: 0
22 passed in 1.30s
```

Final Task 14 target and affected static gates:

```powershell
conda run -n agent-foundations python -m pytest tests/unit/execution tests/integration/test_execution_backend.py -q
conda run -n agent-foundations python -m ruff check src/agent_foundations/execution tests/unit/execution tests/integration/test_execution_backend.py
conda run -n agent-foundations python -m mypy src/agent_foundations/execution tests/unit/execution tests/integration/test_execution_backend.py
```

```text
pytest exit 0: 60 passed, 1 skipped in 1.34s.
Ruff exit 0: All checks passed.
mypy exit 0: Success: no issues found in 11 source files.
```

Fresh real Docker smoke:

```powershell
conda run -n agent-foundations python -m pytest tests/integration/test_execution_backend.py -m docker -q
```

```text
Exit code: 0
1 passed, 5 deselected in 0.76s
```

Two additional live Docker probes used random exact `af-<UUID>` names and the fixed Task 14 image:

```text
caller-cancellation probe exit 0:
  observed_running=True
  cancelled_error=True
  post_cancel_inspect_exit=1
  active_execution_ids=()
workload-classification probe exit 0:
  result_type=ExecutionResult
  exit_code=7
  stderr=no such image
post-probe exact container check exit 0: TASK14_CONTAINERS=none
```

These probes confirm that direct task cancellation waits for exact removal and re-raises `CancelledError`, while Docker-like workload stderr with exit `7` is preserved as a normal result.

## 6. Regression and Quality Gates

Security and authorization regression:

```powershell
conda run -n agent-foundations python -m pytest tests/unit/security tests/integration/test_authorization_flow.py -q
```

```text
Exit code: 0
96 passed in 0.64s
```

Full pytest before the final smoke-fixture-only correction:

```powershell
conda run -n agent-foundations python -m pytest -q
```

```text
Exit code: 0
1082 passed, 1 skipped, 20 warnings in 130.13s
Warnings: one existing Starlette deprecation warning and 19 existing sqlite3 datetime-adapter warnings.
```

Static and dependency gates:

```powershell
conda run -n agent-foundations python -m ruff check .
conda run -n agent-foundations python -m mypy src tests
conda run -n agent-foundations python -m pip check
git diff --check
```

```text
Ruff exit 0: All checks passed.
mypy exit 0: Success: no issues found in 177 source files.
pip check exit 0: No broken requirements found; existing invalid-distribution warnings remain.
git diff --check exit 0; existing LF-to-CRLF warnings only.
```

Final fresh rerun after all code and test changes:

```text
pytest exit 0: 1082 passed, 1 skipped, 20 warnings in 130.56s.
Ruff exit 0: All checks passed.
mypy exit 0: Success: no issues found in 177 source files.
git diff --check exit 0; existing LF-to-CRLF warnings only.
```

Post-Docker final fresh gates after the live smoke:

```powershell
conda run -n agent-foundations python -m pytest -q
conda run -n agent-foundations python -m ruff check .
conda run -n agent-foundations python -m mypy src tests
conda run -n agent-foundations python -m pip check
git diff --check
```

```text
pytest exit 0: 1082 passed, 1 skipped, 20 warnings in 131.38s.
Ruff exit 0: All checks passed.
mypy exit 0: Success: no issues found in 177 source files.
pip check exit 0: No broken requirements found; existing invalid-distribution warnings remain.
git diff --check exit 0; existing LF-to-CRLF warnings only.
```

Post-remediation final fresh gates:

```powershell
conda run -n agent-foundations python -m pytest tests/unit/security tests/integration/test_authorization_flow.py -q
conda run -n agent-foundations python -m pytest -q
conda run -n agent-foundations python -m ruff check .
conda run -n agent-foundations python -m mypy src tests
conda run -n agent-foundations python -m pip check
git diff --check
```

```text
security regression exit 0: 96 passed in 0.80s.
full pytest exit 0: 1090 passed, 1 skipped, 20 warnings in 132.40s.
Ruff exit 0: All checks passed.
mypy exit 0: Success: no issues found in 177 source files.
pip check exit 0: No broken requirements found; existing invalid-distribution warnings remain.
git diff --check exit 0; existing LF-to-CRLF warnings only.
```

## 7. Security Contract Evidence

- `ExecutionRequest` is strict/frozen and validates UUID identities, non-empty control-free argv, relative in-project cwd syntax, mount mode, stdin size, timeout, and output bounds.
- `ExecutionResult` enforces mutually exclusive normal/timeout/cancel states.
- `ContainerRunner` checks exact capability ID and run ID plus a consumed timestamp inside the capability validity window before one backend call. Mismatch tests prove zero backend calls.
- `FakeBackend` is deterministic, records order, blocks without sleeps, rejects duplicate active IDs, and provides exact idempotent cancellation.
- Docker argv fixes `--pull never`, `--network none`, read-only root, all-capability drop, `no-new-privileges`, UID/GID `65532:65532`, pids/memory/cpu limits, one `/workspace` bind mount, fixed image, and command placement after the image. It never sets `shell=True`, never performs a runtime pull, and never mounts the Docker socket.
- Mount-source validation rejects drive/home roots, unresolved roots, UNC/device syntax, commas, alternate data streams, control characters, and credential-bearing directory names. Cwd is strict-resolved inside the selected workspace.
- Output is bounded across stdout and stderr while both pipes continue draining. Timeout, explicit cancel, and caller task cancellation share one launch-aware, idempotent cleanup task. Active state remains registered until cleanup finishes, transient cleanup failure is logged and retried once, and cleanup invokes only `docker rm --force af-<execution_id>`; no prune/global cleanup exists.
- Docker executable unavailability raises `BackendUnavailableError`. Docker CLI exit `125` plus a known infrastructure diagnostic raises `BackendUnavailableError`; other exit `125` raises `BackendLaunchError`; every other nonzero exit remains a workload `ExecutionResult`. There is no host subprocess fallback.
- `.dockerignore` starts deny-all and re-includes only `docker/agent-sandbox.Dockerfile`; source, tests, docs, data, logs, credentials, caches, and VCS metadata remain excluded.

### Authorized Docker build

```powershell
docker build -f docker/agent-sandbox.Dockerfile -t agent-foundations-sandbox:phase2 .
```

```text
Exit code: 1
ERROR: failed to connect to the docker API at
npipe:////./pipe/dockerDesktopLinuxEngine; the system cannot find the file specified.
```

No image was built and no base image was pulled.

### Authorized Docker smoke

The first explicit smoke attempt was invalid as an environment result: its probe contained literal newline control characters, so `ExecutionRequest` rejected the test input before Docker launch. The test fixture was corrected to preserve the same Python probe using escaped newlines; production validation was not weakened.

Corrected exact smoke command:

```powershell
conda run -n agent-foundations python -m pytest tests/integration/test_execution_backend.py -m docker -q
```

```text
Exit code: 1
1 failed, 5 deselected in 0.34s
Failure: BackendUnavailableError: docker daemon or sandbox image is unavailable.
Trace confirms ContainerRunner reached DockerBackend and Docker returned the daemon-unavailable diagnostic.
```

The backend failed closed. No host fallback ran. The failed build created no image, and the smoke launch created no container, so no cleanup action was necessary or safe to perform.

### Successful pull, build, and smoke after explicit authorization

Pull command:

```powershell
docker pull python:3.12-slim-bookworm
```

```text
Exit code: 0
Digest: sha256:4766d8b510c428e595d74b9cc5bbb2fae8e26316fffb4adc89908d79aacd58a2
Status: Downloaded newer image for python:3.12-slim-bookworm
```

The subsequent inspect returned the same immutable image ID and repository digest.

Build command:

```powershell
docker build -f docker/agent-sandbox.Dockerfile -t agent-foundations-sandbox:phase2 .
```

```text
Exit code: 0
Build context loaded through the 273-byte .dockerignore.
Base resolved to python:3.12-slim-bookworm@sha256:4766d8b510c428e595d74b9cc5bbb2fae8e26316fffb4adc89908d79aacd58a2.
Target image ID: sha256:3b692a84c818d01499182604da38379fe36a5ee73792c87ebef60a078effcf42
Config: USER="65532:65532", WORKDIR="/workspace"
```

Explicit smoke command:

```powershell
conda run -n agent-foundations python -m pytest tests/integration/test_execution_backend.py -m docker -q
```

```text
Exit code: 0
1 passed, 5 deselected in 0.69s
```

The live container probe verified non-root UID, read-only root filesystem, read-only `/workspace`, only the loopback network interface, and no `/var/run/docker.sock`.

Exact cleanup inspection:

```powershell
docker ps -a --filter 'name=af-' --format '{{.ID}} {{.Names}} {{.Status}}'
```

```text
Exit code: 0
none
```

The smoke container was removed by `--rm`; no residual Task 14 container required force removal. The fixed target image is intentionally retained for reviewer verification and later authorized Tasks.

## 8. Scope Audit

- Created only the Task 14 execution package, authorized unit/integration tests, Dockerfile/README, `.dockerignore`, and this evidence file.
- Modified `pyproject.toml` only to register the strict `docker` pytest marker.
- Task 14 plan checkbox edits are limited to steps supported by recorded evidence; Docker smoke is checked after the live pass while reviewer acceptance remains unchecked.
- No dependencies, migrations, Agent Tools, policy/approval/capability issuance, host executor, network access, Task 15 behavior, commit, push, or PR were added.
- Suppression scan over Task 14 Python files found no `type: ignore`, `noqa`, or `pragma: no cover`.
- The remediation changed only `src/agent_foundations/execution/docker.py`, `tests/unit/execution/test_docker.py`, and this evidence file. The Task 14 Dockerfile/image was not rebuilt because its contents did not change; the existing fixed image was used for fresh smoke and live probes.
- Existing unrelated dirty tracked/untracked changes were preserved; staging remains empty.

## 9. Gaps and Limitations

- Executor-side real Docker isolation verification is complete. Independent reviewer verification remains pending.
- Task 15 must not start until Task 14 receives independent reviewer verification and user acceptance.

## 10. Handoff Summary

- Current verification status: `pass`
- TDD process evidence: `complete`
- Implementation/no-daemon validation: `pass`
- Docker build/smoke: `pass`; fixed image ID and live isolation probe are recorded.
- Cleanup: `pass`; no `af-` residual containers.
- Reviewer verification: `pending`.
- Task 15: not started and not authorized.
