# Task Evidence: phase-2c-task-4

## 1. Identity

- Task ID: `phase-2c-task-4` (Plan Task 15)
- Task name: 受控 `apply_patch`、回滚与恢复
- Authoritative plan: `docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md` Task 15
- Evidence status: `completed` (executor implementation and gates pass; independent reviewer remains pending)
- TDD required: `yes`
- Started at: `2026-08-12T13:32:16+08:00`
- Authorization: only Task 15 implementation, target/affected/full gates, and Docker build/run/safety probes against temporary fixture copies are authorized. Paid API calls, deployment, Git writes, deletion/cleanup of existing data, Task 16, and edits outside the explicit allowlist remain unauthorized.

## 2. Pre-change Snapshot

- Required branch: `codex/phase-2-next`; observed: `codex/phase-2-next`.
- Required initial HEAD: `14ece4ec30948c01433c57aa95f0da791060a478`; observed exact match.
- `git status --short --untracked-files=all`: 318 existing untracked paths, all under `.agents/` or `.gate-backup/`; staging and tracked diff are empty.
- Existing user changes that must be preserved: every path under `.agents/` and `.gate-backup/`.
- Intended modification scope: create the six Task 15 production/test files and this evidence; modify only `container_runner.py`, `runtime/tool_execution.py`, `cli/main.py`, and Task 15 plan checkboxes when supported by real evidence.
- Expected rollback: remove only Task 15-created files and reverse only Task 15 hunks in the four authorized existing files; never reset, restore, clean, or alter the two protected dirty roots.

### Task-start hashes

```text
src/agent_foundations/tools/patch/apply_patch.py MISSING
src/agent_foundations/tools/patch/applier.py MISSING
tests/unit/tools/patch/test_applier.py MISSING
tests/unit/tools/patch/test_apply_patch.py MISSING
tests/integration/test_controlled_patch_flow.py MISSING
tests/integration/test_patch_crash_recovery.py MISSING
docs/task-evidence/phase-2c-task-4.md MISSING
src/agent_foundations/execution/container_runner.py 60AD0F81920B24D4C69106F64CDB23696BA142928414E4177520B686515EE922
src/agent_foundations/runtime/tool_execution.py 1680E2559C6F7BB9C02C8098F6DEF04FAC5C273A9B503316C69AE713718B274A
src/agent_foundations/cli/main.py 4622E50545D3C6CCCFBBDD324CB897585A93FB75B434D4E8C4B6743AC7963E6F
docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md 0EE691D46EB2E9B1EF80449CF520ABD08296AED3D3DA90A67911F28463ED8D77
```

### Docker preflight

```text
docker version exit 0: client/server 29.4.3, Docker Desktop 4.74.0, linux/amd64.
docker image inspect agent-foundations-sandbox:phase2 exit 0:
sha256:3b692a84c818d01499182604da38379fe36a5ee73792c87ebef60a078effcf42
```

## 3. Red

- Recorded before production-code changes: `yes`.
- Production files changed before Red: `no`.
- Time: `2026-08-12T13:37+08:00`.
- Command:

```powershell
conda run -n agent-foundations python -m pytest tests/unit/tools/patch tests/integration/test_controlled_patch_flow.py tests/integration/test_patch_crash_recovery.py -q
```

- Pytest/PowerShell exit code: `1` (captured explicitly as `POWERSHELL_EXIT=1`; the outer orchestration wrapper itself reported exit 0 because the command intentionally printed the exit code after pytest).
- Relevant verbatim output:

```text
FFFFFFFF...............................FFFFFFFF                          [100%]
E       AssertionError: Task 15 atomic patch applier is missing
E       AssertionError: Task 15 controlled apply_patch Tool is missing
E       AssertionError: Task 15 controlled apply_patch flow is missing
E       AssertionError: Task 15 patch crash recovery is missing
16 failed, 31 passed in 0.87s
POWERSHELL_EXIT=1
ERROR conda.cli.main_run:execute(142): `conda run python -m pytest tests/unit/tools/patch tests/integration/test_controlled_patch_flow.py tests/integration/test_patch_crash_recovery.py -q` failed. (See above for error)
```

- Expected failure category: assertion failures for the missing Task 15 atomic applier, controlled Tool/executor, authorization flow, and crash recovery behavior.
- Why this demonstrates the missing behavior: pytest collected the complete target suite successfully; 31 existing Patch tests passed, while every new Task 15 case failed through explicit behavioral precondition assertions. There were no syntax, import, collection, environment, or Docker failures.
- Red validity: `valid`.

### Refinement Red: explicit ledger `ROLLED_BACK`

Before implementing the controlled executor, an explicit backend-rollback/ledger assertion was added and run:

```powershell
conda run -n agent-foundations python -m pytest tests/integration/test_controlled_patch_flow.py::test_backend_rollback_result_sets_ledger_rolled_back_and_keeps_fixture -q
```

```text
E       AssertionError: Task 15 controlled apply_patch flow is missing
1 failed in 0.34s
PYTEST_EXIT=1
```

Validity: `valid`; normal collection reached the missing controlled executor assertion before any runtime/controlled executor production implementation existed.

## 4. Green

- Production files changed: `src/agent_foundations/tools/patch/applier.py`, `src/agent_foundations/tools/patch/apply_patch.py`, `src/agent_foundations/execution/container_runner.py`, `src/agent_foundations/runtime/tool_execution.py`, `src/agent_foundations/cli/main.py`.
- Target command:

```powershell
conda run -n agent-foundations python -m pytest tests/unit/tools/patch tests/integration/test_controlled_patch_flow.py tests/integration/test_patch_crash_recovery.py -q
```

```text
................................................                         [100%]
54 passed, 10 warnings in 6.87s
PYTEST_EXIT=0
```

The ten warnings are the existing Python 3.12 sqlite3 default datetime-adapter deprecation emitted at `durable/repository.py:1031` during ledger transitions. The target suite used only pytest temporary fixture projects. Its Docker-marked success, conflict rollback, symlink-swap, and crash tests launched the fixed sandbox image with `project_write`; no product repository file was a patch target. A separate exact second-`replace` failure probe passed and proved reverse rollback restores the complete snapshot and records ledger `ROLLED_BACK`.

## 5. Regression and Quality Gates

| Check | Command | Exit code | Result |
|---|---|---:|---|
| Target tests | plan target command | 0 | 54 passed, 10 warnings |
| Affected regressions | security/authorization/execution/durable/runtime/registry/patch-preview/CLI | 0 | 311 passed, 1 intentional skip, 19 warnings |
| Docker integration | Task 14 smoke plus Task 15 live Docker cases with `-m docker` | 0 | 8 passed, 9 deselected, 7 warnings; no residual `af-` containers |
| Full pytest | `conda run -n agent-foundations python -m pytest -q` | 0 | 1112 passed, 1 skipped, 29 warnings |
| Ruff | `conda run -n agent-foundations python -m ruff check .` | 0 | All checks passed |
| mypy | `conda run -n agent-foundations python -m mypy src tests` | 0 | no issues in 183 files |
| Frontend tests/typechecks/build | viewer test/typecheck; chat test/typecheck/build | 0 | viewer 12/12; chat 68/68; both typechecks and build pass |
| pip check | `conda run -n agent-foundations python -m pip check` | 0 | no broken requirements; existing invalid-distribution warnings |
| `git diff --check` | `git diff --check` | 0 | pass; existing LF-to-CRLF warnings only |

### First affected static-gate run

```text
Ruff exit 1: 6 findings (unused imports, one import-format issue, two long lines,
and ASYNC240 for a synchronous tmp_path.resolve() inside an async test).
mypy exit 0: Success: no issues found in 9 source files.
```

The Ruff findings are confined to Task 15 files and will be corrected without suppressions or behavior changes, then rerun. This failed gate is not hidden or counted as a pass.

Fresh affected regression command:

```powershell
conda run -n agent-foundations python -m pytest tests/unit/security tests/integration/test_authorization_flow.py tests/unit/execution tests/integration/test_execution_backend.py tests/unit/durable tests/integration/test_idempotent_tool_execution.py tests/unit/runtime/test_tool_execution.py tests/unit/tools/test_registry.py tests/integration/test_patch_preview_flow.py tests/e2e/test_cli.py -q
```

```text
311 passed, 1 skipped, 19 warnings in 6.01s
REGRESSION_EXIT=0
```

The skip is the pre-existing Task 14 real-Docker smoke that intentionally requires the exact `-m docker` expression; Task 15 live Docker cases ran in the target suite.

Fresh direct security probes:

```text
3 passed, 2 warnings in 2.57s
PROBE_EXIT=0
```

These probes verify explicit registry opt-in, a second-file conflict after preparation rolling back the already-replaced first file with ledger `ROLLED_BACK`, and a symlink swap inside the execution window being rejected by the Docker applier without modifying the outside target.

Fresh affected static gates after correction:

```text
Ruff exit 0: All checks passed.
mypy exit 0: Success: no issues found in 9 source files.
```

### Invalid full-suite launch attempt

The first full pytest orchestration call was mistakenly configured with a 1-second wrapper timeout. It was terminated before pytest output and returned wrapper exit `124`; a process check found no remaining Python/Conda/pytest process. This is an invalid environment/orchestration attempt, not a product test result, and is not counted as a gate. The exact command is rerun below with a sufficient timeout.

Fresh full and frontend gates:

```text
full pytest exit 0: 1112 passed, 1 skipped, 29 warnings in 136.26s.
Ruff exit 0: All checks passed.
mypy exit 0: Success: no issues found in 183 source files.
pip check exit 0: No broken requirements found; existing invalid-distribution warnings remain.
viewer test exit 0: 12 passed; viewer typecheck exit 0.
chat test exit 0: 6 files / 68 tests passed; chat typecheck and build exit 0.
git diff --check exit 0; existing LF-to-CRLF warnings only.
```

Explicit Docker gate:

```text
8 passed, 9 deselected, 7 warnings in 5.79s; exit 0.
docker ps -a --filter 'name=af-' returned no rows.
```

## 6. Scope Audit

- Final changed files: exactly the five Task 15 production files, four Task 15 test files, this evidence, and the Task 15 checkbox hunk in the authoritative plan.
- Unrelated changes introduced: `no`.
- Existing user changes preserved: `yes`; all 318 pre-existing `.agents/` and `.gate-backup/` paths remain untouched.
- Secrets or generated artifacts detected: `no`; source/tests contain no suppression markers and no real credentials.
- Commit, push, deployment, paid API call, or next Task performed: `no`.

## 7. Gaps and Limitations

- Checks not run and reasons: none required by the contract.
- Environment warnings: existing sqlite3 datetime-adapter, Starlette/httpx, pip invalid-distribution, Vite chunk-size, and Git line-ending warnings remain; all affected commands exit 0.
- Process evidence gaps: independent reviewer verification is not part of this executor run.
- Remaining risks: private durable repository internals are used by the allowed runtime adapter to persist `ROLLED_BACK` because the pre-existing public ledger API has no rollback transition. This is contained and atomically tested but is a reviewer concern; no out-of-scope durable file was modified.

## 8. Handoff Summary

- Current verification status: `pass` (executor gates)
- TDD process evidence: `complete`
- Recommended reviewer commands: target suite, affected security/authorization/execution regressions, full Ruff/mypy, explicit Docker gate, `git diff --check`, and direct inspection of capability consumption plus ledger rollback transition.

## 9. Final Scope Hashes

```text
src/agent_foundations/tools/patch/apply_patch.py 32F7B2DCCD6ACD2AD1C1225D625C10FBDD879F7024ED30BE9109C8226DEBA11B
src/agent_foundations/tools/patch/applier.py A2394B1B56494A654A759E89D31688CBC143207F446BD6A8FB25FE4A08BC18EA
tests/unit/tools/patch/test_applier.py 49AB9776B89746D130F3DD4193D396523701AB9DC36797F3E02241147EC18A39
tests/unit/tools/patch/test_apply_patch.py 82D104FF13646B192037256BF876A03EE975C93BA5CCFDCDEAA0F262FC9AD1E0
tests/integration/test_controlled_patch_flow.py 1971BE552FCF8AC85B1842ED19B7F8B965FD0C163424EE61547673290BB790E1
tests/integration/test_patch_crash_recovery.py 5B32C64B88DE3E3CE454611B9B0B5FCF89A955A840B8E0822BF29239320C307D
src/agent_foundations/execution/container_runner.py 8381F80516BC571DF9D6BAB8470019C8B1CBA89F8CF271C3EC5D16671235F800
src/agent_foundations/runtime/tool_execution.py D5C6C4014C3543937FB19CE9C06D5F42AB795EECF80F9E8C08C6ACD405C5E7AC
src/agent_foundations/cli/main.py 173753F82F598B81B3E1429EC9BA080473331BF60198BCF0937A07FB6DA6BDE7
docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md 793CC0015ACD4BC92F4AD3F70317A12C26D2C654A34B180F812164E4657CE980
```

The evidence file hash is intentionally omitted from its own body because adding it would change the hash recursively. Final external hash at handoff is reported separately.
