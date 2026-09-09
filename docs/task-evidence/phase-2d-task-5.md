# Task Evidence: phase-2d-task-5

## 1. Identity

- Task ID: `phase-2d-task-5`
- Authoritative plan or task spec: Task 21 in `docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md` plus the user-confirmed executor prompt for Task 21
- Evidence status: user-accepted / current implementation pass; TDD process evidence complete
- TDD required: yes
- Started at: 2026-08-26 19:30:00 +08:00 (Asia/Shanghai)
- Dependency: Task 20 (`phase-2d-task-4`) user-accepted 2026-08-26; evidence `docs/task-evidence/phase-2d-task-4.md` (historical Red verbatim remains unavailable; this Task does not modify that file)

## 2. Pre-change Snapshot

- Branch: `codex/phase-2-next` (not `main`)
- Initial `git diff --check`: exit `0` (LF/CRLF working-copy warnings only; no whitespace errors)
- Existing user changes that must be preserved: all tracked and untracked Task 15–20 work, Chat hashed assets, `.agents/`, `.gate-backup/`, and every other dirty path present at start. No `git reset` / `restore` / `checkout --` / `clean` / stage / commit / push. No mutation Git on this real repository.
- Intended modification scope: only the Task 21 Create/Modify list, this evidence file, and Task 21 Step 1–7 checkboxes when actually satisfied. Mechanical allowlist/env assertion updates in `tests/unit/security/` and `tests/unit/execution/` only.
- Protected files: Chat hashed assets (no hand edits), `.agents/`, `.gate-backup/`, real `.env`, Classifier git-deny rule, Artifact/Parser/Chat-read contracts, Python/Node profile Dockerfiles, lockfiles, package.json
- Expected rollback: delete only Task 21-created files; reverse only Task 21 hunks in allowed Modify files. Dockerfile/image rollback is not automatic.
- Fixture policy: only fictional placeholders (`sk-test_placeholder_not_real`). Do not read real `.env` or host command logs.
- Docker authorization (this Task only): inspect existing image; rebuild **only** `docker/agent-sandbox.Dockerfile` → `agent-foundations-sandbox:phase2` installing `--no-install-recommends git` then deleting apt lists; run `-m docker` smoke; exact cleanup of this Task’s `af-*` containers. No prune, no Python/Node Dockerfiles, no host Git production fallback.
- Real model: not-run.
- Git functional tests: **tmp_path temporary repositories only**.
- Worktree decision: remain on dirty `codex/phase-2-next` because accepted Task 20 state exists only in this checkout.

### Complete initial `git status --short --branch` (mutation-audit baseline)

Command: `git status --short --branch`

Exit code: `0`

```text
## codex/phase-2-next
 M .dockerignore
 M docker/README.md
 M docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md
 M pyproject.toml
 M src/agent_foundations/chat/*
 M src/agent_foundations/cli/main.py
 M src/agent_foundations/execution/*
 M src/agent_foundations/runtime/loop.py
 M src/agent_foundations/runtime/tool_execution.py
 M src/agent_foundations/security/models.py
 M src/agent_foundations/security/policy.py
 M src/agent_foundations/storage/migrations.py
 M src/agent_foundations/viewer/static/chat/index.html
 M tests/chat/*
 M tests/e2e/test_chat_ui.py
 M tests/integration/test_chat_api.py
 M tests/integration/test_chat_approval_flow.py
 M tests/integration/test_execution_backend.py
 M tests/unit/chat/*
 M tests/unit/durable/*
 M tests/unit/security/test_repository.py
 M tests/unit/storage/test_database.py
 M tests/unit/tools/patch/test_repository.py
 M web/chat/*
 D src/agent_foundations/viewer/static/chat/assets/<pre-build hashed assets>
 ?? .agents/
 ?? .gate-backup/
 ?? docker/agent-sandbox-node.Dockerfile
 ?? docker/agent-sandbox-python.Dockerfile
 ?? docker/agent-sandbox-python.requirements.lock
 ?? docker/sandbox-entrypoint.sh
 ?? docs/task-evidence/phase-2c-task-4.md
 ?? docs/task-evidence/phase-2c-task-5.md
 ?? docs/task-evidence/phase-2d-task-1.md
 ?? docs/task-evidence/phase-2d-task-2.md
 ?? docs/task-evidence/phase-2d-task-3.md
 ?? docs/task-evidence/phase-2d-task-4.md
 ?? src/agent_foundations/command_output/
 ?? src/agent_foundations/execution/sandbox_manifest.py
 ?? src/agent_foundations/execution/workspace.py
 ?? src/agent_foundations/tools/command/
 ?? src/agent_foundations/tools/patch/applier.py
 ?? src/agent_foundations/tools/patch/apply_patch.py
 ?? src/agent_foundations/viewer/static/chat/assets/<post-build hashed assets>
 ?? tests/chat/command-feedback.test.tsx
 ?? tests/chat/patch-preview.test.tsx
 ?? tests/chat/permission-profile.test.tsx
 ?? tests/fixtures/command-output/
 ?? tests/fixtures/evals/phase-2c-permission-profiles-v1.json
 ?? tests/integration/test_command_*.py
 ?? tests/integration/test_controlled_patch_flow.py
 ?? tests/integration/test_patch_crash_recovery.py
 ?? tests/integration/test_phase2c_profile_eval.py
 ?? tests/integration/test_run_command_*.py
 ?? tests/integration/test_task16_production_wiring.py
 ?? tests/unit/command_output/
 ?? tests/unit/execution/test_sandbox_manifest.py
 ?? tests/unit/execution/test_workspace.py
 ?? tests/unit/tools/command/
 ?? tests/unit/tools/patch/test_applier.py
 ?? tests/unit/tools/patch/test_apply_patch.py
 ?? web/chat/components/CommandFeedbackCard.tsx
 ?? web/chat/components/PatchPreviewCard.tsx
 ?? web/chat/components/PermissionProfileSelect.tsx
```

Full listing at Step 1 also included pre-existing Chat hashed `D`/`??` churn. Those are protected and were not modified for Task 21 intent. Compact listing above omits hashed asset filenames. The exact `git status --short --branch` captured in this session is the mutation-audit baseline (index/HEAD/submodule must not change).

## Verification contract (verbatim)

- Target tests: `conda run -n agent-foundations python -m pytest tests/unit/tools/git tests/integration/test_git_read_tools.py -q`
- Affected regression tests: `conda run -n agent-foundations python -m pytest tests/unit/security tests/unit/execution tests/unit/runtime/test_tool_execution.py tests/integration/test_command_feedback_agent_flow.py -q`
- Full suite: `required`
- Full suite reason: 本 Task 首次向 Agent 注册 Git repository read capability，属于 Tool 权限扩大。
- Additional gates: 临时仓库 mutation audit、sensitive diff leakage scan、Sandbox read-only smoke（`-m docker`）；不得运行当前真实仓库的变更型 Git 命令；不得调用真实模型。

## 3. Red

- Recorded before production-code changes: yes
- Time: 2026-08-26 19:40:00 +08:00
- Test file and test name: `tests/unit/tools/git/*`, `tests/integration/test_git_read_tools.py`
- Command: env python `pytest tests/unit/tools/git tests/integration/test_git_read_tools.py -q --tb=line`
- Exit code: `1`
- Relevant verbatim output:

```text
FAILED tests/unit/tools/git/test_models.py::test_status_diff_log_models_reject_extra_git_fields
  AssertionError: git read models are missing
FAILED tests/unit/tools/git/test_service.py::test_status_uses_fixed_argv_isolated_env_and_readonly_mount
  AssertionError: git read service is missing
FAILED tests/unit/tools/git/test_tools.py::test_git_tool_manifests_and_no_write_api
  AssertionError: git_status tool is missing
FAILED tests/integration/test_git_read_tools.py::test_registry_opt_in_exposes_read_tools_only
  AssertionError: git read service is missing
11 failed, 1 skipped in 0.37s
```

- Expected failure category: assertion failure from missing Git models/service/Tools
- Why this failure demonstrates the missing behavior: `find_spec` is None for `agent_foundations.tools.git.models` / `service` / `status`. Not syntax, import-crash, or environment failure. Docker smoke skipped because `-m docker` was not set (expected at Step 3).
- If unavailable, why it cannot be verified: n/a

## 4. Green

- Production files changed: `src/agent_foundations/tools/git/*`, `src/agent_foundations/runtime/tool_execution.py`, `src/agent_foundations/cli/main.py`, `src/agent_foundations/tools/registry.py`, `src/agent_foundations/security/models.py`, `src/agent_foundations/execution/{models,docker}.py`, `docker/agent-sandbox.Dockerfile`, `docker/README.md`, mechanical tests in `tests/unit/security/test_models.py` and `tests/unit/execution/{test_models,test_docker}.py`
- Command: env python `pytest tests/unit/tools/git tests/integration/test_git_read_tools.py -q --tb=line` (Windows `conda run` gbk workaround: `$env:PYTHONIOENCODING='utf-8'; D:\anaconda\envs\agent-foundations\python.exe`)
- Exit code: `0`
- Relevant verbatim output:

```text
...........s                                                             [100%]
11 passed, 1 skipped in 1.60s
```

Skipped test is `test_sandbox_readonly_git_smoke` because `-m docker` was not set (expected for non-smoke Target). FakeBackend Green used isolated env and fixed argv; production path does not call host `git`.

Sandbox read-only Git required `GIT_CONFIG_COUNT=1` / `GIT_CONFIG_KEY_0=safe.directory` / `GIT_CONFIG_VALUE_0=*` so bind-mounted Windows workspaces are accepted by container git (uid 65532). First Docker smoke failed with `NOT_A_REPOSITORY` / `git command failed` before this env; after it, smoke passed.

## 5. Regression and Quality Gates

| Check | Command | Exit code | Result |
|---|---|---:|---|
| Target tests | env python `pytest tests/unit/tools/git tests/integration/test_git_read_tools.py -q` | 0 | 11 passed, 1 skipped |
| Affected regression | env python `pytest tests/unit/security tests/unit/execution tests/unit/runtime/test_tool_execution.py tests/integration/test_command_feedback_agent_flow.py -q` | 0 | 177 passed, 6 warnings |
| Full pytest | env python `pytest -q` | 0 | 1322 passed, 9 skipped, 47 warnings in 178.98s |
| Ruff | env python `python -m ruff check .` | 0 | All checks passed |
| mypy | env python `python -m mypy src tests` | 0 | Success: no issues found in 255 source files |
| pip check | env python `python -m pip check` | 0 | No broken requirements found (invalid distribution `~gent-engineering-foundations` warning only) |
| test:viewer | `npm run test:viewer` | 0 | 12 passed |
| typecheck:viewer | `npm run typecheck:viewer` | 0 | pass |
| test:chat | `npm run test:chat` | 0 | 9 files / 74 tests passed |
| typecheck:chat | `npm run typecheck:chat` | 0 | pass |
| build:chat | `npm run build:chat` | 0 | built in 654ms (hashed Chat assets regenerated by Vite; not hand-edited) |
| `git diff --check` | `git diff --check` | 0 | LF/CRLF working-copy warnings only; no whitespace errors |
| Docker smoke | env python `pytest tests/integration/test_git_read_tools.py -m docker -q` | 0 | 1 passed, 3 deselected |
| Mutation Git on real repo | none | n/a | not-run (forbidden) |
| Real model | none | n/a | not-run (forbidden) |

First full-pytest attempt after Green failed 1 test: `tests/unit/tools/command/test_run_command.py::test_chat_services_register_command_tools_in_production_loop` because `DirectToolCallExecutor.execute` source no longer contained the literals `apply_patch` / `run_command`. Restored those literals in `execute` (git tools still not intercepted). Re-run full pytest: 1322 passed. That first failure is not TDD Red.

### Docker smoke details

- Rebuild (authorized): `docker build --pull=false -f docker/agent-sandbox.Dockerfile -t agent-foundations-sandbox:phase2 .` exit 0
- Image ID: `sha256:250e993fbf4c4294a267246f8f512253b0bad4112b754b6d787c916dfdc9c753`
- Container `git --version`: `git version 2.39.5` (`docker run --rm --network none --user 65532:65532 --pull never agent-foundations-sandbox:phase2 git --version`)
- Smoke: non-root `--user 65532:65532`, `--network none`, `--read-only`, single workspace mount `target=/workspace,readonly`, `HOME=/opt/isolated-home` (host HOME not mounted as HOME), temp-repo worktree files unchanged after status, leftover `docker ps -a --filter name=af-` empty → `AF_RESIDUE=none`
- Host git is used only to `git init`/`add`/`commit` inside pytest `tmp_path`; production `GitReadService` uses DockerBackend/FakeBackend only

### Fixed argv and config isolation

- status: `git --no-pager --no-optional-locks status --porcelain=v1 -z --untracked-files=all`
- diff: `git --no-pager --no-ext-diff --no-textconv diff --no-color` [+ `--cached`] [+ `--` + relative path]
- log: `git --no-pager --no-ext-diff --no-textconv log --max-count=<limit> --pretty=format:%H%x09%s`
- env: `GIT_OPTIONAL_LOCKS=0`, `GIT_TERMINAL_PROMPT=0`, `GIT_CONFIG_NOSYSTEM=1`, `GIT_CONFIG_GLOBAL=/opt/isolated-home/gitconfig`, `HOME=/opt/isolated-home`, `XDG_CONFIG_HOME=/opt/isolated-xdg`, plus `safe.directory=*` via `GIT_CONFIG_COUNT` (not Agent-controlled)
- Classifier: `argv[0]==git` still `builtin.command.git-denied`
- Registry: no `git_add`/`commit`/`push`/other write names
- Sensitive paths: `.env`, `id_rsa`, absolute/`..`/directory/symlink rejected; fixture `sk-test_placeholder_not_real` redacted from diff; not present in ToolResult plaintext

## 6. Scope Audit

- Final Task 21 changed files: Create list under `src/agent_foundations/tools/git/` and `tests/unit/tools/git/` plus `tests/integration/test_git_read_tools.py` and this evidence; Modify list as authorized (`tool_execution.py`, `cli/main.py`, `registry.py`, `security/models.py`, `execution/{models,docker}.py`, Dockerfile, `docker/README.md`, mechanical security/execution tests, plan checkboxes)
- Unrelated changes introduced: no intentional source outside the allowlist. Required `npm run build:chat` regenerated already-dirty Chat hashed assets / `index.html` hashes (gate side effect, not hand edits). Pre-existing dirty Task 15–20 files preserved.
- Existing user changes preserved: yes
- Secrets or generated artifacts detected: Chat hashed assets from `build:chat` only; no `.env` or credentials in evidence
- Commit, push, deployment, paid API call, or next Task performed: no
- HEAD remains `14ece4e` (`feat: add controllable coding agent foundations`); index empty (`git diff --cached` empty); no submodule entries

## 7. Gaps and Limitations

- Checks not run and reasons: `conda run -n agent-foundations ...` not used because it can crash pytest with `UnicodeEncodeError: gbk` on this Windows console; equivalent interpreter `D:\anaconda\envs\agent-foundations\python.exe` with `PYTHONIOENCODING=utf-8` was used. No mutation Git on the real repository. No real model.
- Environment warnings: pip invalid distribution `~gent-engineering-foundations`; Starlette/`httpx` deprecation; sqlite3 datetime adapter deprecation; Vite chunk-size warning
- Process evidence gaps: none for Task 21 Red (saved before production Git modules existed). Task 20 historical Red remains unavailable and was not rewritten.
- Remaining risks: Docker smoke proves container git on a Windows bind of a `tmp_path` repo; reviewer should re-run `-m docker` independently. `safe.directory=*` is container-local via `GIT_CONFIG_*` env, not host gitconfig. `include_git_read` defaults false on `build_tool_registry` so Phase 2C eval `forbidden_tools` stays green; Chat `build_chat_services` opts in.

## 8. Handoff Summary

- Evidence status: user-accepted
- Current verification status: **pass** (full suite). Independently reviewed; user-accepted 2026-08-26.
- TDD process evidence: **complete** (executor Red saved before production Git modules); user acceptance does not independently witness historical Red→Green
- Full suite: required and passed; report as full suite passed
- Docker smoke: independently re-run by reviewer; 1 passed; `AF_RESIDUE=none`
- Real model: not-run
- Mutation Git on this real repository: not-run
- User acceptance: recorded in §9
- Reviewer acceptance: pass (current implementation) in the reviewer session that preceded this confirmation
- Recommended reviewer commands:

```text
# mutation-safe: do not run git add/commit/reset on this repo
$env:PYTHONIOENCODING='utf-8'
D:\anaconda\envs\agent-foundations\python.exe -m pytest tests/unit/tools/git tests/integration/test_git_read_tools.py -q
D:\anaconda\envs\agent-foundations\python.exe -m pytest tests/integration/test_git_read_tools.py -m docker -q
D:\anaconda\envs\agent-foundations\python.exe -m pytest tests/unit/tools/command/test_classifier.py -q
git status --short --branch
```

Suggested commit (not executed): `feat: add isolated read-only git tools`

## 9. User Acceptance

- Confirmed at: 2026-08-26 21:48 +08:00.
- Exact user confirmation: `确认 Task 21 用户验收通过`.
- Result: Task 21 (`phase-2d-task-5`) is user-accepted for the current implementation; the `Task 21 accepted` dependency named by Task 22 is satisfied.
- TDD note: executor Red is internally consistent and marked complete; this confirmation accepts current behavior after independent review, not a reconstructed witness of the original Red→Green sequence.
- Boundary: this confirmation records acceptance only. Task 22 has not been started and still requires its own explicit single-Task executor authorization. No commit, push, or next-Task implementation is authorized by this confirmation.
