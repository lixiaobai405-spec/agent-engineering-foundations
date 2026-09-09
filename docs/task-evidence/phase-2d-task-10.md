# Task Evidence: phase-2d-task-10

## 1. Identity

- Task ID: `phase-2d-task-10`
- Authoritative plan or task spec: `docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md` Appendix Task 26; user prompt 2026-08-27
- Evidence status: user-accepted 2026-08-27 (targeted verification); Task 25 overall **not complete**; user Phase 2 complete **not claimed**
- TDD required: yes
- Started at: 2026-08-27 (Asia/Shanghai)

## 2. Pre-change Snapshot

- Branch or revision: `codex/phase-2-next` (not `main`)
- `git status --short`: dirty working tree already present (Phase 2A–2D, Chat hashed assets, Dockerfiles, evidence). Must preserve all pre-existing user changes. No `reset`/`restore`/`clean`.
- Existing user changes that must be preserved: entire pre-existing dirty tree.
- Intended modification scope: versioned Chat SandboxManifest pin file; `SandboxManifest.from_path`/`load_pinned`; Chat loader and two `DockerBackend(..., sandbox_manifest=)` factories; unit tests; this evidence; optional plan appendix locating this Task. Not Task 25 E2E `_DIFF`, CheckpointSink, Dockerfiles, lockfiles, paid API, Step 10/11 checkboxes.
- Expected rollback: revert only this Task’s files; do not revert the pre-existing dirty tree.
- Interpreter: `$env:PYTHONIOENCODING='utf-8'; D:\anaconda\envs\agent-foundations\python.exe`
- Pre-change readonly pin check (must match authorized values; do not rewrite pin):
  - `docker/agent-sandbox-python.requirements.lock` sha256 `54a48d9fe970cea3b27a5488b123660a0b6c73cd68e8462bdac231737b85c531`
  - `package-lock.json` sha256 `06c84831ab91e26c98c7ce32291c0e3aac95c97c0287203e5bb292687dbb8d98`
  - `docker image inspect agent-foundations-sandbox-python:phase2d` Id `sha256:730aea0a2ba8ef2998bb0cc43b1f94641a9099f8a0d55b22a0605f384ad26e41`
  - `docker image inspect agent-foundations-sandbox-node:phase2d` Id `sha256:eb349e91bdf800e6065b700e315439dc443547b726cc3bd098e18cd952bb5f21`
  - Match: yes. No STOP.

## 3. Red

- Recorded before production-code changes: yes
- Time: 2026-08-27 (Asia/Shanghai)
- Test file and test name: `tests/unit/execution/test_sandbox_manifest.py` (`test_phase2d_chat_loader_uses_pinned_final_image_ids`, `test_chat_services_pass_sandbox_manifest_into_docker_backends`)
- Command: `$env:PYTHONIOENCODING='utf-8'; D:\anaconda\envs\agent-foundations\python.exe -m pytest tests/unit/execution/test_sandbox_manifest.py::test_phase2d_chat_loader_uses_pinned_final_image_ids tests/unit/execution/test_sandbox_manifest.py::test_chat_services_pass_sandbox_manifest_into_docker_backends -q`
- Exit code: 1
- Relevant verbatim output:

```text
FF                                                                       [100%]
____________ test_phase2d_chat_loader_uses_pinned_final_image_ids _____________
>       assert manifest.python.final_image_id != _PLACEHOLDER_IMAGE_ID
E       AssertionError: assert 'sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc' != 'sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc'
________ test_chat_services_pass_sandbox_manifest_into_docker_backends ________
>       assert source.count("DockerBackend(workspace, sandbox_manifest=") == 2
E       AssertionError: assert 0 == 2
FAILED tests/unit/execution/test_sandbox_manifest.py::test_phase2d_chat_loader_uses_pinned_final_image_ids
FAILED tests/unit/execution/test_sandbox_manifest.py::test_chat_services_pass_sandbox_manifest_into_docker_backends
2 failed in 1.63s
```

- Expected failure category: production Chat loader still returns placeholder `sha256:{'c'*64}`; `build_chat_services` constructs `DockerBackend(workspace)` without `sandbox_manifest`
- Why this failure demonstrates the missing behavior: target pin IDs and Chat backend wiring are absent; not an import/environment error
- If unavailable, why it cannot be verified:

Green-stage note (not a reconstructed Red): after wrapping `DockerBackend(...)` for Ruff E501, `test_chat_services_pass_sandbox_manifest_into_docker_backends` was updated to assert `load_pinned` in the loader, absence of `'c' * 64`, two `backend_factory=lambda workspace: docker_backend_factory(workspace)` call sites, and `sandbox_manifest=sandbox_manifest` in the shared factory. The pin ID assertions were not weakened.

## 4. Green

- Production files changed:
  - `docker/sandbox-manifest.phase2d.json`
  - `src/agent_foundations/execution/sandbox_manifest.py` (`from_path`, `load_pinned`; `verify_runtime` unchanged)
  - `src/agent_foundations/cli/main.py` (`_phase2d_sandbox_manifest` → `load_pinned`; both Chat `backend_factory` paths pass the same pin)
  - `tests/unit/execution/test_sandbox_manifest.py`
- Command: `$env:PYTHONIOENCODING='utf-8'; D:\anaconda\envs\agent-foundations\python.exe -m pytest tests/unit/execution/test_sandbox_manifest.py -q`
- Exit code: 0
- Relevant verbatim output:

```text
................                                                         [100%]
16 passed in 1.37s
```

## 5. Regression and Quality Gates

| Check | Command | Exit code | Result |
|---|---|---:|---|
| Target tests | `$env:PYTHONIOENCODING='utf-8'; D:\anaconda\envs\agent-foundations\python.exe -m pytest tests/unit/execution/test_sandbox_manifest.py -q` | 0 | 16 passed |
| Regression tests | `$env:PYTHONIOENCODING='utf-8'; D:\anaconda\envs\agent-foundations\python.exe -m pytest tests/unit/tools/command/test_classifier.py tests/unit/tools/command/test_models.py tests/integration/test_run_command_flow.py tests/e2e/test_chat_ui.py -q` | 0 | 87 passed, 1 skipped |
| Additional: readonly inspect | `docker image inspect agent-foundations-sandbox-python:phase2d --format "{{.Id}}"` / `...-node:phase2d` | 0 | python `sha256:730aea0a2ba8ef2998bb0cc43b1f94641a9099f8a0d55b22a0605f384ad26e41`; node `sha256:eb349e91bdf800e6065b700e315439dc443547b726cc3bd098e18cd952bb5f21`; matches pin; no STOP |
| Additional: docker marker | `$env:PYTHONIOENCODING='utf-8'; D:\anaconda\envs\agent-foundations\python.exe -m pytest -m docker -q` | 0 | 16 passed, 1393 deselected |
| Ruff | `$env:PYTHONIOENCODING='utf-8'; D:\anaconda\envs\agent-foundations\python.exe -m ruff check src/agent_foundations/cli/main.py src/agent_foundations/execution/sandbox_manifest.py tests/unit/execution/test_sandbox_manifest.py` | 0 | All checks passed |
| mypy | `$env:PYTHONIOENCODING='utf-8'; D:\anaconda\envs\agent-foundations\python.exe -m mypy src/agent_foundations/cli/main.py src/agent_foundations/execution/sandbox_manifest.py tests/unit/execution/test_sandbox_manifest.py` | 0 | Success: no issues found in 3 source files |
| Frontend test, typecheck or build | not-required | | |
| Package or dependency check | not-required | | |
| `git diff --check` | `git diff --check --` Task files listed in §6 | 0 | pass after removing appendix markdown trailing spaces / extra EOF blank |

## 6. Scope Audit

- Final changed files:
  - Create: `docker/sandbox-manifest.phase2d.json`
  - Modify: `src/agent_foundations/execution/sandbox_manifest.py`
  - Modify: `src/agent_foundations/cli/main.py`
  - Modify: `tests/unit/execution/test_sandbox_manifest.py`
  - Create: `docs/task-evidence/phase-2d-task-10.md`
  - Modify: `docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md` (Appendix Task 26 only; Task 25 Step 10/11 remain unchecked)
- Unrelated changes introduced: no
- Existing user changes preserved: yes
- Secrets or generated artifacts detected: no
- Commit, push, deployment, paid API call, or next Task performed: none

## 7. Gaps and Limitations

- Checks not run and reasons: Full suite not-required; Phase 1 frontend/pip baseline not run. DualBackend E2E and CheckpointSink not in this Task.
- Environment warnings: sqlite3 datetime adapter DeprecationWarning in affected/docker runs; Starlette/httpx TestClient deprecation in docker marker run. `git diff --check` LF/CRLF warning from `core.autocrlf`.
- Process evidence gaps: Chat wiring Green assertion was adapted after Ruff wrapping; original Red still records the missing one-line `DockerBackend(workspace, sandbox_manifest=` count. Reviewer should treat that adaptation as Green-stage test maintenance, not a second historical Red.
- Remaining risks: Chat startup still does not live-inspect the daemon (pin + lockfile fingerprint only). Runtime `SandboxManifest.verify_runtime()` is unchanged and still requires inspect image ID == pin; mismatch hard-fails. Test doubles that monkeypatch `DockerBackend` without a `sandbox_manifest` parameter are constructed without the kwarg via `inspect.signature`; production `DockerBackend` always receives the pin. This is constructor compatibility for stubs, not a silent tag fallback.

## 8. Handoff Summary

- Current verification status: **pass** (targeted verification passed; not full suite). Reviewer-fresh: `test_sandbox_manifest.py` 16 passed; affected 87 passed / 1 skipped (includes `test_task16_browser_patch_profile_reload_approve_deny_and_no_duplicate_write`); readonly inspect matches pin; `pytest -m docker` 16 passed; ruff/mypy on the three Task files passed
- TDD process evidence: **complete**. Reviewer fresh checks prove current green, not the historical Red→Green sequence. Green-stage wiring assertion maintenance after Ruff wrap is disclosed in §3
- User acceptance: recorded in §9
- Reviewer acceptance: pass (current implementation, targeted) in the reviewer session that preceded this confirmation
- Reviewer findings retained: P3 Chat wiring unit test is largely source-string based; `inspect.signature` factory is stub compatibility, not a silent tag fallback. Delayed `TypeError` on the Task 16 Playwright stub is not a current failure
- Recommended reviewer commands (already run for this Task):

```powershell
$env:PYTHONIOENCODING='utf-8'
D:\anaconda\envs\agent-foundations\python.exe -m pytest tests/unit/execution/test_sandbox_manifest.py -q
D:\anaconda\envs\agent-foundations\python.exe -m pytest tests/unit/tools/command/test_classifier.py tests/unit/tools/command/test_models.py tests/integration/test_run_command_flow.py tests/e2e/test_chat_ui.py -q
docker image inspect agent-foundations-sandbox-python:phase2d --format "{{.Id}}"
docker image inspect agent-foundations-sandbox-node:phase2d --format "{{.Id}}"
D:\anaconda\envs\agent-foundations\python.exe -m pytest -m docker -q
D:\anaconda\envs\agent-foundations\python.exe -m ruff check src/agent_foundations/cli/main.py src/agent_foundations/execution/sandbox_manifest.py tests/unit/execution/test_sandbox_manifest.py
D:\anaconda\envs\agent-foundations\python.exe -m mypy src/agent_foundations/cli/main.py src/agent_foundations/execution/sandbox_manifest.py tests/unit/execution/test_sandbox_manifest.py
git diff --check -- docker/sandbox-manifest.phase2d.json src/agent_foundations/execution/sandbox_manifest.py src/agent_foundations/cli/main.py tests/unit/execution/test_sandbox_manifest.py docs/task-evidence/phase-2d-task-10.md docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md
```

## 9. User Acceptance

- Confirmed at: 2026-08-27 +08:00.
- Exact user confirmation: `确认「Task 10 / phase-2d-task-10 用户验收通过」`.
- Result: Appendix Task 26 / `phase-2d-task-10` (Chat production `SandboxManifest` pin) is user-accepted for the current implementation. This is **not** plan body Task 10 (Side-effect Ledger). Independent reviewer re-ran the targeted contract (16 passed; affected 87 passed / 1 skipped; inspect IDs match pin; docker marker 16 passed).
- Full suite note: this confirmation accepts **targeted verification passed**. It does not claim `full suite passed`, does not accept Task 25 as complete, does not accept paid 3×3, and does not mark user Phase 2 complete. Plan Task 25 Step 10 and Step 11 remain unchecked.
- TDD note: executor Red is internally consistent and marked complete; this confirmation does not independently witness the original Red→Green sequence.
- Delayed regression note: an earlier affected run failed `test_task16_browser_patch_profile_reload_approve_deny_and_no_duplicate_write` with `TypeError` after `sandbox_manifest` was passed into a root-only E2E stub. The signature-compatible factory fix was independently re-verified green; that old failure is not part of this acceptance.
- Boundary: this confirmation records `phase-2d-task-10` acceptance only. Chat `CheckpointSink` (`phase-2d-task-11`) and the optional DualBackend Docker sibling E2E still require their own explicit single-Task executor authorization. No commit, push, paid API rerun, or next-Task implementation is authorized by this confirmation.
