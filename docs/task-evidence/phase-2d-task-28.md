# Task Evidence: phase-2d-task-28

## 1. Identity

- Task ID: `phase-2d-task-28` (user-visible Task 44)
- Authoritative plan or task spec: `docs/agent-plans/2026-09-08-phase-2-node-sandbox-modules-overlay-plan.md`
- Evidence status: user-accepted / current implementation pass; TDD process evidence complete
- TDD required: yes
- Started at: 2026-09-08 (Asia/Shanghai)

## 2. Pre-change Snapshot

- Branch or revision: `codex/phase-2-next` @ `14ece4e`
- `git status --short`: dirty tree preserved (~372 `M` / `D` / `??` entries from prior Phase 2 work). Captured 2026-09-08 before production-code edits; not reset/restored/cleaned.
- Existing user changes that must be preserved: entire pre-existing dirty tree on `codex/phase-2-next`
- Intended modification scope: `docker/sandbox-entrypoint.sh`; Node `final_image_id` / `final_repo_digest` in `docker/sandbox-manifest.phase2d.json`; `_PINNED_NODE_IMAGE_ID`; `docker/README.md`; new unit/integration tests and Node fixture; this evidence; Task 44 plan checkboxes. Not Policy, Chat, Python pin, Node Dockerfile, or Task 25 Step 10/11.
- Expected rollback: restore this Task's files. If the Node image was rebuilt, record old vs new Id; do not `docker prune`. Do not restore the unrelated dirty tree.

## 3. Red

- Recorded before production-code changes: yes (entrypoint still root-symlinked the store)
- Time: 2026-09-08 (Asia/Shanghai), this session, before editing `docker/sandbox-entrypoint.sh`

### 3a. Unit Red

- Test file and test name: `tests/unit/execution/test_sandbox_entrypoint.py` (`test_entrypoint_does_not_root_symlink_node_modules_store`, `test_entrypoint_makes_writable_node_modules_dir_and_links_store_entries`)
- Command: `D:\anaconda\envs\agent-foundations\python.exe -m pytest tests/unit/execution/test_sandbox_entrypoint.py -q`
- Exit code: 1
- Relevant verbatim output:

```text
.FF                                                                      [100%]
FAILED tests/unit/execution/test_sandbox_entrypoint.py::test_entrypoint_does_not_root_symlink_node_modules_store
FAILED tests/unit/execution/test_sandbox_entrypoint.py::test_entrypoint_makes_writable_node_modules_dir_and_links_store_entries
2 failed, 1 passed in 0.15s
```

- Expected failure category: missing overlay behavior (root `ln -s "$SANDBOX_NODE_MODULES" /workspace/node_modules`; no `mkdir` of a real `/workspace/node_modules`)
- Why this failure demonstrates the missing behavior: assertions failed on the current script text, not on import/syntax. The remaining test (`exec` / no `eval` / no `sh -c` / no store `cp -a`) passed.

### 3b. Docker behavior Red (old pinned Node image, this session)

- Test file and test name: repaired fixture `tests/fixtures/phase2_node_sandbox_project` + old image `sha256:eb349e91bdf800e6065b700e315439dc443547b726cc3bd098e18cd952bb5f21` / `npm run test:chat`
- Command: `docker run --rm --pull never --network none --read-only --user 65532:65532 --tmpfs /workspace:rw,nosuid,nodev,size=536870912,mode=0755,uid=65532,gid=65532 --mount type=bind,source=<fixture>,target=/project-ro,readonly sha256:eb349e91… npm run test:chat`
- Exit code: 1
- Relevant verbatim output:

```text
failed to load config from /workspace/vitest.config.ts
Error: ENOENT: no such file or directory, mkdir '/workspace/node_modules/.vite-temp'
code: 'ENOENT'
syscall: 'mkdir'
path: '/workspace/node_modules/.vite-temp'
DOCKER_RED_EXIT=1
```

- Expected failure category: read-only store reached through a root `node_modules` symlink; Vite cannot create `.vite-temp`
- Why this failure demonstrates the missing behavior: the fixture is already repaired (`left + right`, expect `2`); failure is harness, not source. This output was captured in this session; it is not copied from `phase-2d-task-9-step-10.md`.

## 4. Green

- Production files changed:
  - `docker/sandbox-entrypoint.sh` (real `/workspace/node_modules` + per-entry `ln -s` including `.[!.]*` / `.bin`; Node-only `TMPDIR=/workspace/.sandbox-tmp`; still `exec "$@"`)
  - `docker/sandbox-manifest.phase2d.json` (Node `final_image_id` / `final_repo_digest` only)
  - `docker/README.md` (overlay + TMPDIR note; rebuild Node then update pin)
- Tests / pin helper: `tests/unit/execution/test_sandbox_entrypoint.py`; `tests/unit/execution/test_docker.py` (`test_entrypoint_and_build_context`); `tests/unit/execution/test_sandbox_manifest.py` (`_PINNED_NODE_IMAGE_ID`); `tests/integration/test_node_sandbox_gates.py`; `tests/fixtures/phase2_node_sandbox_project/`
- Command: Target unit tests; `pytest -m docker tests/integration/test_node_sandbox_gates.py`
- Exit code: 0 / 0
- Relevant verbatim output:

```text
Target: 20 passed in 1.39s
Docker gates: .... 4 passed in 7.12s
Without -m docker: 4 skipped
```

After the overlay-only image, `test:chat` still failed with `mkdir '/tmp/.../ssr'` (read-only rootfs `/tmp`). Entrypoint then set `TMPDIR` onto the existing `/workspace` tmpfs (not `VITE_CACHE_DIR`, not fixture `cacheDir`, not a `/tmp` docker mount, not a store copy). Node image rebuilt again; pin updated to the final inspect Id.

Old Node Id: `sha256:eb349e91bdf800e6065b700e315439dc443547b726cc3bd098e18cd952bb5f21`
New Node Id: `sha256:12f2470f314aae00f8757a313d78da471472984f7d039bdfdf1c57a553cfc0e7`
Python Id unchanged: `sha256:730aea0a2ba8ef2998bb0cc43b1f94641a9099f8a0d55b22a0605f384ad26e41`

## 5. Regression and Quality Gates

Verification contract:

- Target tests: `pytest tests/unit/execution/test_sandbox_entrypoint.py tests/unit/execution/test_docker.py::test_entrypoint_and_build_context tests/unit/execution/test_sandbox_manifest.py -q`
- Affected regression tests: `pytest tests/unit/execution/test_docker.py tests/unit/execution/test_sandbox_manifest.py tests/unit/tools/command/test_gate_expand.py tests/unit/tools/command/test_classifier.py -q`
- Full suite: not-required
- Full suite reason: Node entrypoint + Node final pin only; complete baseline belongs to Task 25 Step 11
- Additional gates: authorized Node docker build (`--pull=false`); inspect=pin; python pin unchanged; `pytest -m docker tests/integration/test_node_sandbox_gates.py`; ruff + mypy; `git diff --check`

| Check | Command | Exit code | Result |
|---|---|---:|---|
| Target tests | `python -m pytest tests/unit/execution/test_sandbox_entrypoint.py tests/unit/execution/test_docker.py::test_entrypoint_and_build_context tests/unit/execution/test_sandbox_manifest.py -q` | 0 | 20 passed |
| Regression tests | `python -m pytest tests/unit/execution/test_docker.py tests/unit/execution/test_sandbox_manifest.py tests/unit/tools/command/test_gate_expand.py tests/unit/tools/command/test_classifier.py -q` | 0 | 86 passed |
| Node docker build | `docker build --pull=false -f docker/agent-sandbox-node.Dockerfile -t agent-foundations-sandbox-node:phase2d .` | 0 | pass (twice; final pin is the second image) |
| inspect vs pin | `docker image inspect agent-foundations-sandbox-node:phase2d --format '{{.Id}}'` | 0 | equals `sha256:12f2470f…`; not `eb349e91…` |
| python pin | JSON `python.final_image_id` | n/a | unchanged `730aea0a…` |
| node.lockfile_sha256 | compare to `package-lock.json` sha256 | n/a | match |
| Docker gates | `python -m pytest -m docker tests/integration/test_node_sandbox_gates.py -q` | 0 | 4 passed (three npm scripts exit 0; dir overlay; `.bin` symlink; store touch fails) |
| Docker skip | same file without `-m docker` | 0 | 4 skipped |
| Ruff | `python -m ruff check` on affected test files | 0 | All checks passed |
| mypy | `python -m mypy tests/unit/execution/test_sandbox_entrypoint.py`; `python -m mypy src` | 0 | no issues (1 file; 155 source files). No production Python changed. |
| Frontend test/typecheck/build | not-required | n/a | not-run |
| Package or dependency check | not-required | n/a | not-run |
| `git diff --check` | this Task's paths | 0 | pass (LF/CRLF working-copy warning only) |

## 6. Scope Audit

- Final changed files:
  - `docker/sandbox-entrypoint.sh`
  - `docker/sandbox-manifest.phase2d.json` (Node `final_*` only)
  - `docker/README.md`
  - `tests/unit/execution/test_sandbox_entrypoint.py` (new)
  - `tests/unit/execution/test_docker.py` (`test_entrypoint_and_build_context`)
  - `tests/unit/execution/test_sandbox_manifest.py` (`_PINNED_NODE_IMAGE_ID`)
  - `tests/integration/test_node_sandbox_gates.py` (new)
  - `tests/fixtures/phase2_node_sandbox_project/` (new, repaired, no `node_modules`)
  - `docs/task-evidence/phase-2d-task-28.md`
  - `docs/agent-plans/2026-09-08-phase-2-node-sandbox-modules-overlay-plan.md` (Task 44 steps ticked)
- Unrelated changes introduced: no
- Existing user changes preserved: yes
- Secrets or generated artifacts detected: no
- Commit, push, deployment, paid API call, or next Task performed: none. No Chat. No 3×3. Task 25 Step 10/11 not ticked. Not Phase 2 complete.

## 7. Gaps and Limitations

- Checks not run and reasons: Full suite belongs to Step 11. Frontend/pip not required. `mypy -p agent_foundations` fails closed (no `py.typed`); `mypy src` used instead, matching prior targeted Tasks.
- Environment warnings: `git diff --check` LF/CRLF working-copy notices on `docker/README.md` and `tests/unit/execution/test_docker.py`.
- Process evidence gaps: none for required Red/Green. Reviewer must re-run current tests independently.
- Remaining risks: old Node image `eb349e91…` may still exist locally; do not `docker prune`. Paid 3×3 still needs a separate Task 25 Step 10 authorization and must precheck against the **new** Node pin. `TMPDIR` is Node-entrypoint-only; Python image does not set `SANDBOX_NODE_MODULES`.

## 8. Handoff Summary

- Current verification status: **pass** (targeted verification; not full suite). Reviewer-fresh: Target 20 passed; Affected 86 passed; `pytest -m docker` 4 passed; inspect Id equals pin `sha256:12f2470f314aae00f8757a313d78da471472984f7d039bdfdf1c57a553cfc0e7`; python pin unchanged; ruff / `git diff --check` exit 0. Reviewer did not rebuild the Node image.
- TDD process evidence: **complete**. Reviewer fresh checks prove current green, not the historical Red→Green sequence
- User acceptance: recorded in §9
- Reviewer acceptance: pass (current implementation, targeted) in the reviewer session that preceded this confirmation
- Reviewer findings retained: P3 overlay-plan Status still said “waiting for executor” until this confirmation; unit tests read shell text rather than executing it; old Node image `eb349e91…` may remain locally (do not prune); `TMPDIR` on `/workspace` tmpfs can consume the 512 MiB budget
- Recommended reviewer commands (already run for this Task):

```powershell
$env:PYTHONIOENCODING = 'utf-8'
D:\anaconda\envs\agent-foundations\python.exe -m pytest tests/unit/execution/test_sandbox_entrypoint.py tests/unit/execution/test_docker.py::test_entrypoint_and_build_context tests/unit/execution/test_sandbox_manifest.py -q
D:\anaconda\envs\agent-foundations\python.exe -m pytest -m docker tests/integration/test_node_sandbox_gates.py -q
docker image inspect agent-foundations-sandbox-node:phase2d --format "{{.Id}}"
```

## 9. User Acceptance

- Confirmed at: 2026-09-08 +08:00.
- Exact user confirmation: `确认「Task 44 / phase-2d-task-28 用户验收通过」`.
- Result: Node sandbox overlay Task 44 / `phase-2d-task-28` (writable `/workspace/node_modules` directory with per-store-entry symlinks, plus Node-only `TMPDIR` on the workspace tmpfs) is user-accepted for the current implementation. Independent reviewer re-ran the targeted contract (Target 20 passed; Affected 86 passed; docker gates 4 passed; inspect matches pin `sha256:12f2470f…`; python pin `730aea0a…` unchanged).
- Full suite note: this confirmation accepts **targeted verification passed**. It does not claim `full suite passed`, does not accept plan-body Task 25 as complete, does not accept paid 3×3, and does not mark user Phase 2 complete. Plan Task 25 Step 10 and Step 11 remain unchecked.
- TDD note: executor Red is internally consistent and marked complete (unit overlay assertions plus this-session Docker Red on old `eb349e91…` with `.vite-temp` ENOENT). This confirmation does not independently witness the original Red→Green sequence.
- Boundary: this confirmation records `phase-2d-task-28` acceptance only. The overlay plan has **no Task 45**. Paid 3×3 still requires a separate explicit authorization and remains Task 25 Step 10; any later pretest must use the **new** Node pin, not `eb349e91…`. No commit, push, paid API rerun, Phase 2 complete checkbox, or Phase 3 is authorized by this confirmation. Reviewer P3 findings are retained and do not require immediate rework from this confirmation.
