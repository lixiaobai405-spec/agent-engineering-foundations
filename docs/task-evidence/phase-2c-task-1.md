# Task Evidence: phase-2c-task-1

## 1. Identity

- Task ID: `phase-2c-task-1` (Plan Task 12)
- Task name: Tool Metadata、Policy 与版本化 Permission Profile
- Authoritative plan: `docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md` Task 12
- Evidence status: `accepted` (independent review passed and user acceptance confirmed 2026-08-12)
- Current implementation: `pass` after reviewer fix round 3 and independent reviewer verification
- TDD process evidence: `incomplete`
- Historical Red output for the reviewer fix round: `unavailable`
- Depends on: Phase 2B user acceptance, confirmed 2026-08-12; `phase-2b-task-6` Red remains `unavailable`

The five reviewer regression tests and their implementation were already present when this executor turn began. The prior evidence asserted a complete Red/Green history, but it did not preserve an exact pre-fix command, exit code, or verbatim failing output. No other local evidence containing that Red was found. This turn did not break the working implementation to manufacture a historical Red.

## 2. Pre-verification Snapshot (2026-08-11)

- Branch: `main`
- Staging area: empty (`git diff --cached --name-only` returned no paths)
- Working tree: heavily dirty from prior accepted/in-progress Tasks and generated Chat assets
- `git status --short` summary before this evidence correction: 416 entries (46 tracked modified, 3 tracked deleted, 367 untracked)
- Existing user/prior-Task changes preserved: `yes`
- Production code changed in this executor turn: `no`
- Evidence file changed in this executor turn: `yes`
- Rollback for this turn: revert only this evidence correction; do not reset, restore, clean, or alter the pre-existing working tree

## 3. Reviewer Findings and Current Implementation

| Finding | Current implementation | Regression coverage |
|---|---|---|
| P1: Profile has no explicit Tool set | `PermissionProfile.allowed_tools`; authorized `security/models.py` defines Phase 2C default allowlists; unknown future Tool is denied with `tool_not_in_profile_allowlist` | `test_future_write_denied_when_not_in_profile_allowlist` |
| P1: CUSTOM rules are too broad | `CustomPolicyRule` binds `tool_name`, `resource_kind`, `operation`, optional `side_effect`, `path_prefix`, and `command_category`; unmatched requests default deny | `test_custom_rule_requires_matching_tool_and_path_prefix` |
| P1: Process Tool does not require Sandbox | `PROCESS` with `sandbox_required=False` is hard denied with `process_tool_requires_sandbox` | `test_process_tool_without_sandbox_required_is_denied` |
| P2: Manifest and resolved resource can disagree | `manifest.resource_kind != resource.kind` is hard denied with `manifest_resource_kind_mismatch` | `test_manifest_resource_kind_mismatch_is_denied` |
| P2: Request is not bound to Profile version | `request.profile_version != profile.version` is hard denied with `profile_version_mismatch` | `test_profile_version_mismatch_is_denied` |
| P2: Ruff failure | Current full-repository Ruff gate exits 0 | Full Ruff command in section 5 |

Hard-deny gates run before the built-in/CUSTOM decision matrix for Tool/profile mismatch, Profile version mismatch, manifest/resource mismatch, forbidden resource/side effects, and out-of-project writes. A process request additionally requires a `sandbox_command` resource and `sandbox_required=True`.

## 4. TDD Process Evidence

### 4.1 Historical Red

- Status: `unavailable`
- Reason: the previous evidence contained only a post-fix summary and test names. It did not contain the exact pre-fix command, exit code, or relevant failing output required by the project evidence contract.
- Classification: TDD process evidence is therefore `incomplete`, even though the current regression tests pass.
- Integrity rule: no post-fix code breakage or synthetic Red was run or presented as the original sequence.

### 4.2 Current Green (targeted)

Command:

```powershell
conda run -n agent-foundations python -m pytest tests/unit/security tests/unit/tools/test_registry.py tests/contract/test_protocols.py -q
```

Result:

```text
Exit code: 0
........................................................................ [ 90%]
........                                                                 [100%]
80 passed in 0.36s
```

This fresh run covers the five named reviewer regressions together with the Task 12 security, registry, and protocol contract suite.

## 5. Fresh Verification (2026-08-11)

### 5.1 Full pytest — first attempt

Command:

```powershell
conda run -n agent-foundations python -m pytest -q
```

Result:

```text
Exit code: 124
command timed out after 124087 milliseconds
```

Classification: command timeout, not a test assertion failure. `conda run` buffered the pytest output, so this attempt did not establish a pass/fail count.

### 5.2 Full pytest — completed rerun

Command:

```powershell
conda run --no-capture-output -n agent-foundations python -m pytest -q
```

Result:

```text
Exit code: 0
1001 passed, 20 warnings in 127.15s (0:02:07)
```

Warnings:

- 1 pre-existing Starlette/httpx deprecation warning from `fastapi.testclient`
- 19 Python 3.12 sqlite3 default datetime adapter deprecation warnings in durable tests

### 5.3 Ruff

Command:

```powershell
conda run --no-capture-output -n agent-foundations python -m ruff check .
```

Result:

```text
Exit code: 0
All checks passed!
```

### 5.4 mypy

Command:

```powershell
conda run --no-capture-output -n agent-foundations python -m mypy src tests
```

Result:

```text
Exit code: 0
Success: no issues found in 159 source files
```

### 5.5 Dependency check

Command:

```powershell
conda run --no-capture-output -n agent-foundations python -m pip check
```

Result:

```text
Exit code: 0
No broken requirements found.
```

Environment warning: conda emitted `Ignoring invalid distribution ~gent-engineering-foundations` twice. It did not change the exit code, but remains an environment hygiene warning.

### 5.6 Whitespace check

Command:

```powershell
git diff --check
```

Result:

```text
Exit code: 0
```

Git emitted LF-to-CRLF conversion warnings for existing working-tree files; no whitespace error was reported.

## 6. Scope Audit

Current Task 12 implementation paths include:

- `src/agent_foundations/security/models.py`
- `src/agent_foundations/security/policy.py`
- `src/agent_foundations/security/models.py`
- `tests/unit/security/test_policy.py`
- the Tool metadata/registry/resource resolver paths listed in Plan Task 12

This executor turn made no additional production or test-code edits because the requested fixes were already present and the fresh target/full gates passed. Only this evidence file was corrected to preserve the distinction between current correctness and historical TDD proof.

- Commit, push, PR, deployment, dependency installation, paid API, or real model call: `no`
- Task 13 started: `no`
- Existing user/prior-Task changes reset, restored, cleaned, or overwritten: `no`
- Independent reviewer verification: `pending`

## 7. Handoff

| Item | Status |
|---|---|
| Current Task 12 implementation | `pass` based on fresh executor verification; independent review pending |
| Reviewer regression behaviors | `pass` in the 82-test target suite |
| Full pytest | `pass` — 1003 tests on completed rerun; one unrelated durable flake recorded |
| Ruff / mypy / pip check / diff check | `pass` with warnings recorded above |
| Historical reviewer-fix round 1 Red | `unavailable` |
| Reviewer-fix round 2 Red/Green | `complete` |
| Overall TDD process evidence | `incomplete` because round 1 Red remains unavailable |
| Independent reviewer conclusion | `pending` |

Stop after this Task. Do not start Task 13 until reviewer/user acceptance.

## 8. Reviewer Fix Round 2 (2026-08-11)

### 8.1 Scope and pre-change state

- Finding P1: `path_prefix="src"` incorrectly allows `src_evil/payload.py` because `_custom_outcome` uses raw string `startswith` without a path-segment boundary.
- Finding P2: `RegisteredTool.manifest` is annotated as `Any`, and `ToolRegistry` accepts any object exposing a matching `.name` attribute.
- Authorized files: `src/agent_foundations/security/policy.py`, `src/agent_foundations/domain/tool.py`, `src/agent_foundations/tools/registry.py`, their two unit-test files, and this evidence file.
- Existing dirty-worktree changes are preserved; Task 13 remains out of scope.
- Production code changed before Red: `no`

### 8.2 Red tests added

- `tests/unit/security/test_policy.py::test_custom_path_prefix_requires_segment_boundary`
- `tests/unit/tools/test_registry.py::test_registry_rejects_name_only_pseudo_manifest`

### 8.3 Red — conda wrapper run

Command:

```powershell
conda run --no-capture-output -n agent-foundations python -m pytest tests/unit/security/test_policy.py::test_custom_path_prefix_requires_segment_boundary tests/unit/tools/test_registry.py::test_registry_rejects_name_only_pseudo_manifest -q
```

Key output:

```text
FF                                                                       [100%]
FAILED tests/unit/security/test_policy.py::test_custom_path_prefix_requires_segment_boundary
E AssertionError: assert PolicyDecision.ALLOW is PolicyDecision.DENY
FAILED tests/unit/tools/test_registry.py::test_registry_rejects_name_only_pseudo_manifest
E Failed: DID NOT RAISE <class 'TypeError'>
2 failed in 0.38s
ERROR conda.cli.main_run:execute(142): `conda run python -m pytest ...` failed.
```

Exit-code note: pytest and conda both reported failure, but the shell tool surfaced exit code 0 for this `conda run --no-capture-output` invocation. A direct invocation of the confirmed `agent-foundations` environment Python follows to capture the trustworthy pytest exit code before any production change.

### 8.4 Red — authoritative environment Python rerun

Command:

```powershell
& 'D:\anaconda\envs\agent-foundations\python.exe' -m pytest tests/unit/security/test_policy.py::test_custom_path_prefix_requires_segment_boundary tests/unit/tools/test_registry.py::test_registry_rejects_name_only_pseudo_manifest -q
```

Result:

```text
Exit code: 1
FF                                                                       [100%]
FAILED tests/unit/security/test_policy.py::test_custom_path_prefix_requires_segment_boundary
E AssertionError: assert PolicyDecision.ALLOW is PolicyDecision.DENY
FAILED tests/unit/tools/test_registry.py::test_registry_rejects_name_only_pseudo_manifest
E Failed: DID NOT RAISE <class 'TypeError'>
2 failed in 0.35s
```

Red validity: both failures are caused by the two missing target protections, tests collected normally, and no production file had been modified in this round.

### 8.5 Minimal implementation

- `security/policy.py`: replace raw `startswith` with `_matches_path_prefix`, which normalizes `\\` to `/` and only matches an exact path or a descendant separated by `/`.
- `domain/tool.py`: change `RegisteredTool.manifest` from `Any` to the `ToolManifest` type annotation.
- `tools/registry.py`: reject non-`ToolManifest` values before reading manifest fields.

### 8.6 Focused Green

Command:

```powershell
& 'D:\anaconda\envs\agent-foundations\python.exe' -m pytest tests/unit/security/test_policy.py::test_custom_path_prefix_requires_segment_boundary tests/unit/tools/test_registry.py::test_registry_rejects_name_only_pseudo_manifest -q
```

Result:

```text
Exit code: 0
..                                                                       [100%]
2 passed in 0.31s
```

Reviewer fix round 2 Red/Green evidence: `complete`.

### 8.7 Target suite Green

Command:

```powershell
conda run -n agent-foundations python -m pytest tests/unit/security tests/unit/tools/test_registry.py tests/contract/test_protocols.py -q
```

Result:

```text
Exit code: 0
........................................................................ [ 87%]
..........                                                               [100%]
82 passed in 0.31s
```

### 8.8 Full pytest — first post-fix run

Command:

```powershell
& 'D:\anaconda\envs\agent-foundations\python.exe' -m pytest -q
```

Result:

```text
Exit code: 1
FAILED tests/unit/durable/test_controller.py::test_cancel_stops_before_next_provider_call
E agent_foundations.durable.controller.ControllerRejectedError: cannot resume status cancelled
1 failed, 1002 passed, 20 warnings in 128.11s (0:02:08)
```

Classification: unrelated durable-controller scheduling race outside this Task 12 remediation. The failure occurred after the cancellation won before `resume()` read the run, while the test expected the alternate `RunCancelledError` path. No durable production/test file is authorized for modification in this round. The failing test will be rerun in isolation to determine reproducibility before deciding the final gate status.

### 8.9 Unrelated durable failure isolation

Command: run `tests/unit/durable/test_controller.py::test_cancel_stops_before_next_provider_call` 10 times with the confirmed `agent-foundations` environment Python.

Result:

```text
Exit code: 0
Iterations 1-10: 1 passed each
FAILED_ITERATIONS=
```

Classification: non-reproduced scheduling flake; no out-of-scope durable code or test was changed.

### 8.10 Full pytest — completed rerun

Command:

```powershell
& 'D:\anaconda\envs\agent-foundations\python.exe' -m pytest -q
```

Result:

```text
Exit code: 0
1003 passed, 20 warnings in 126.71s (0:02:06)
```

Warnings remain the pre-existing Starlette/httpx warning and 19 Python 3.12 sqlite3 datetime adapter warnings.

### 8.11 Quality gates

Ruff:

```powershell
conda run --no-capture-output -n agent-foundations python -m ruff check .
```

```text
Exit code: 0
All checks passed!
```

mypy:

```powershell
conda run --no-capture-output -n agent-foundations python -m mypy src tests
```

```text
Exit code: 0
Success: no issues found in 159 source files
```

Dependency check:

```powershell
conda run --no-capture-output -n agent-foundations python -m pip check
```

```text
Exit code: 0
No broken requirements found.
```

The pre-existing `Ignoring invalid distribution ~gent-engineering-foundations` environment warning appeared twice.

Whitespace check:

```powershell
git diff --check
```

```text
Exit code: 0
```

Existing LF-to-CRLF warnings were emitted; no whitespace error was reported.

### 8.12 Round 2 handoff

| Item | Status |
|---|---|
| CUSTOM exact/descendant boundary | `pass` — `src` allows `src/main.py`, denies `src_evil/payload.py` |
| Registry non-`ToolManifest` rejection | `pass` — name-only pseudo manifest raises `TypeError` |
| Focused Red/Green | `complete` — 2 failed before production changes, then 2 passed |
| Task 12 target suite | `pass` — 82 tests |
| Full pytest | `pass` — 1003 tests on completed rerun |
| Ruff / mypy / pip check / diff check | `pass` |
| Independent reviewer conclusion | `pending` |
| Task 13 | `not started` |

## 9. Reviewer Fix Round 3 (2026-08-12)

### 9.1 Pre-change findings and authorization boundary

- P1 security defect: `ResourceScope.UNKNOWN + SideEffectKind.PROJECT_WRITE` reaches the `PROJECT_FULL_ACCESS` matrix and returns `allow`; all non-`PROJECT_INTERNAL` writes must hard deny.
- P1 prerequisite gap: Phase 2B Plan Step 7 remains unchecked and `phase-2b-task-6.md` records user sign-off as pending. The current user request authorizes this Task 12 remediation only; it is not recorded as retroactive Phase 2B acceptance.
- P2 suppression: `tests/unit/tools/test_registry.py` contains a prohibited `# type: ignore[list-item]` in a negative runtime test.
- P2 scope: `src/agent_foundations/security/profiles.py` is not in the Plan Task 12 file list. Its constants/helper will be moved without behavior change into authorized `security/models.py`, all imports updated, then `profiles.py` removed.
- Task 13 remains out of scope and is not started.
- Production code changed before this round's Red: `no`.

### 9.2 Red test added

- `tests/unit/security/test_policy.py::test_unknown_scope_project_write_is_hard_denied`

### 9.3 Red

Command:

```powershell
& 'D:\anaconda\envs\agent-foundations\python.exe' -m pytest tests/unit/security/test_policy.py::test_unknown_scope_project_write_is_hard_denied -q
```

Result:

```text
Exit code: 1
F                                                                        [100%]
E AssertionError: assert PolicyDecision.ALLOW is PolicyDecision.DENY
E PolicyOutcome(decision=ALLOW, rule_id='builtin.project_write.allow', reason_code='project_write_allow')
FAILED tests/unit/security/test_policy.py::test_unknown_scope_project_write_is_hard_denied
1 failed in 0.32s
```

Red validity: the test collected normally and failed solely because the target hard-deny behavior was missing. No production file had been changed in this round.

### 9.4 Minimal implementation and scope remediation

- `security/policy.py`: hard deny every `PROJECT_WRITE` whose resource scope is not `PROJECT_INTERNAL`, with reason code `non_project_internal_write_forbidden`.
- `tests/unit/tools/test_registry.py`: replace the negative test's prohibited `# type: ignore[list-item]` with `cast(Any, EchoTool())`.
- `security/models.py`: receive the unchanged Phase 2C Tool allowlist constants and `default_allowed_tools` helper.
- `security/__init__.py` and security tests: import those symbols from `security.models`.
- `security/profiles.py`: removed after the equivalent move because it was outside Plan Task 12's authorized file list.

### 9.5 Focused Green

Command:

```powershell
& 'D:\anaconda\envs\agent-foundations\python.exe' -m pytest tests/unit/security/test_policy.py::test_unknown_scope_project_write_is_hard_denied tests/unit/tools/test_registry.py::test_registry_rejects_tool_without_manifest -q
```

Result:

```text
Exit code: 0
..                                                                       [100%]
2 passed in 0.33s
```

Reviewer fix round 3 security Red/Green: `complete`.

### 9.6 Post-fix verification before import-format remediation

| Check | Command | Result |
|---|---|---|
| Task 12 target | `conda run -n agent-foundations python -m pytest tests/unit/security tests/unit/tools/test_registry.py tests/contract/test_protocols.py -q` | exit 0; `83 passed in 0.55s` |
| Tool/AgentLoop regression | `conda run -n agent-foundations python -m pytest tests/unit/tools tests/integration/test_agent_loop.py -q` | exit 0; `149 passed in 1.12s` |
| Full pytest | `D:\anaconda\envs\agent-foundations\python.exe -m pytest -q` | exit 0; `1004 passed, 20 warnings in 131.13s` |
| mypy | `conda run --no-capture-output -n agent-foundations python -m mypy src tests` | exit 0; `Success: no issues found in 158 source files` |
| pip check | `conda run --no-capture-output -n agent-foundations python -m pip check` | exit 0; no broken requirements; existing invalid-distribution warning |
| git diff --check | `git diff --check` | exit 0; existing LF/CRLF warnings only |

Ruff command:

```powershell
conda run --no-capture-output -n agent-foundations python -m ruff check .
```

Ruff result:

```text
Found 6 errors.
6 x I001 Import block is un-sorted or un-formatted
```

All six findings are local import consolidation issues introduced when `default_allowed_tools` moved from `security.profiles` to `security.models`. The conda wrapper surfaced outer exit code 0 despite Ruff and conda reporting failure; this gate is classified as `fail` until a clean rerun.

### 9.7 Ruff import remediation

- Consolidated only the local `security.models` imports reported by Ruff in `test_models.py` and `test_policy.py`.
- No production behavior changed.

Fresh command:

```powershell
& 'D:\anaconda\envs\agent-foundations\python.exe' -m ruff check .
```

Result:

```text
Exit code: 0
All checks passed!
```

### 9.8 Phase 2B prerequisite correction

- `docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md` Task 12 Step 1 was changed from `[x]` back to `[ ]` because Phase 2B user acceptance is not recorded.
- Phase 2B Step 7 remains `[ ]`; `docs/task-evidence/phase-2b-task-6.md` continues to state user sign-off `pending`.
- No historical acceptance, date, quote, or checkbox was fabricated.
- Current Task 12 code correctness can be tested, but Task 12 acceptance remains prerequisite-blocked until the user explicitly confirms Phase 2B.

### 9.9 Final fresh verification after all round 3 edits

| Check | Command | Exit code | Result |
|---|---|---:|---|
| Focused security/typing Green | `D:\anaconda\envs\agent-foundations\python.exe -m pytest tests/unit/security/test_policy.py::test_unknown_scope_project_write_is_hard_denied tests/unit/tools/test_registry.py::test_registry_rejects_tool_without_manifest -q` | 0 | 2 passed |
| Task 12 target | `conda run -n agent-foundations python -m pytest tests/unit/security tests/unit/tools/test_registry.py tests/contract/test_protocols.py -q` | 0 | 83 passed in 0.35s |
| Tool/AgentLoop regression | `conda run -n agent-foundations python -m pytest tests/unit/tools tests/integration/test_agent_loop.py -q` | 0 | 149 passed in 0.93s |
| Full pytest | `D:\anaconda\envs\agent-foundations\python.exe -m pytest -q` | 0 | 1004 passed, 20 warnings in 125.57s |
| Ruff | `D:\anaconda\envs\agent-foundations\python.exe -m ruff check .` | 0 | All checks passed |
| mypy | `D:\anaconda\envs\agent-foundations\python.exe -m mypy src tests` | 0 | no issues in 158 source files |
| pip check | `D:\anaconda\envs\agent-foundations\python.exe -m pip check` | 0 | no broken requirements; existing invalid-distribution warning |
| git diff --check | `git diff --check` | 0 | pass; existing LF/CRLF warnings only |

The 20 pytest warnings remain the pre-existing Starlette/httpx warning plus 19 Python 3.12 sqlite3 datetime-adapter warnings.

### 9.10 Final scope audit and handoff

- `ResourceScope.UNKNOWN + PROJECT_WRITE` under `PROJECT_FULL_ACCESS`: hard denied with `non_project_internal_write_forbidden`.
- `tests/unit/tools/test_registry.py` contains no `type: ignore`.
- `src/agent_foundations/security/profiles.py`: absent.
- `security.profiles` imports under `src` and `tests`: none.
- Default allowlist symbols now live in authorized `src/agent_foundations/security/models.py`.
- Phase 2B Plan Step 7: `[x]`.
- Task 12 Step 1 (record Phase 2B acceptance): `[x]`.
- `phase-2b-task-6.md` user sign-off: `accepted` on 2026-08-12.
- Staging area: empty.
- Working tree remains heavily dirty: 416 entries (46 tracked modified, 3 tracked deleted, 367 untracked); all existing changes preserved.
- Commit, push, PR, dependency installation, real model/API call, or Task 13 work: none.

| Assessment | Status |
|---|---|
| Current implementation | `pass`; independently verified and accepted on 2026-08-12 |
| Reviewer fix round 3 Red/Green | `complete` |
| Overall historical TDD process | `incomplete` because original Task/round 1 Red remains unavailable |
| Task 12 prerequisite | `resolved` by explicit Phase 2B user acceptance on 2026-08-12 |
| Task 12 final acceptance | `accepted` on 2026-08-12; see §11 |
| Task 13 | `not started` |

## 10. Phase 2B User Acceptance Recorded (2026-08-12)

- User statement in the current executor conversation: `确认 Phase 2B 验收`.
- Phase 2B Plan Step 7 changed from `[ ]` to `[x]`.
- `docs/task-evidence/phase-2b-task-6.md` user sign-off changed from `pending` to `accepted`.
- Task 12 Step 1 changed from `[ ]` to `[x]` because its Phase 2B acceptance prerequisite is now recorded.
- This documentation-only update does not change production code, tests, historical Red availability, or the overall `incomplete` TDD-process assessment.
- At the time of this Phase 2B prerequisite update, Task 12 remained `completed-awaiting-review`; §11 records the later independent reviewer and user acceptance.
- Task 13 remains not started.

## 11. Independent Reviewer and User Acceptance Recorded (2026-08-12)

- Independent reviewer conclusion: current implementation `pass`.
- Fresh reviewer verification: security boundary probe exit `0`; Task target `83 passed`; Tool/AgentLoop regression `149 passed`; full pytest `1004 passed, 20 warnings`; Ruff, mypy, pip check, and `git diff --check` exit `0`.
- User statement in the reviewer conversation: `验收通过，你改一下状态`.
- Task 12 final acceptance: `accepted`.
- Overall historical TDD process remains `incomplete` because the original Task/round 1 Red is unavailable; this acceptance does not reconstruct or upgrade that historical evidence.
- This status-only update does not authorize or start Task 13.
