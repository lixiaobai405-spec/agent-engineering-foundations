# Task Evidence: phase-2c-task-2

## 1. Identity

- Task ID: `phase-2c-task-2` (Plan Task 13)
- Task name: 通用 Approval 与一次性 Capability
- Authoritative plan: `docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md` Task 13
- Evidence status: `completed-awaiting-review`
- Current implementation: `pass` based on fresh executor verification
- TDD process evidence: `partial`
- Depends on: Task 12 accepted on 2026-08-12
- Authorization: user supplied the Task 13 executor prompt after confirming the prior acceptance; Task 14 is not authorized

Task 12's overall historical TDD evidence remains `incomplete` because its original first-round Red is unavailable. This Task does not alter that conclusion and must preserve its own fresh Red.

## 2. Pre-change Snapshot (2026-08-12)

- Branch: `main`, ahead of `origin/main` by 1 commit
- Staging area: empty
- Working tree: heavily dirty with preserved tracked and untracked work from prior accepted Tasks and generated Chat assets
- Task-start `git diff --check`: exit `0`; existing LF-to-CRLF warnings only
- Existing user/prior-Task changes preserved: `yes`
- Production code changed before Task 13 Red: `no`
- `.gate-backup` and generated assets preserved: `yes`
- Dependency install, real model/API/network call, commit, push, PR, or deployment: `no`

### Authorized production scope

- Create: `security/approvals.py`, `security/capabilities.py`, `security/repository.py`, `security/schema.py`
- Modify: `storage/migrations.py`, `chat/approvals.py`, `chat/tool_execution.py`
- No CLI, Chat schema/models/ConversationRepository, Runtime architecture, backend, Sandbox, write, command, Git, or network changes

### Authorized test/document scope

- Create Task 13 security unit tests and `tests/integration/test_authorization_flow.py`
- Extend `tests/integration/test_chat_approval_flow.py`
- Mechanically update only the authorized v6-to-v7 latest-schema assertions in the five listed existing test files
- Update only Task 13 checkboxes in the Phase 2 plan after evidence exists

### Rollback

Remove only Task 13-created files and reverse only Task 13 hunks in the authorized modified files. Do not reset, restore, clean, remove `.gate-backup`, or disturb prior dirty-worktree content.

## 3. Red

- Status: `valid`
- Production code changed before both Red runs: `no`

Required command:

```powershell
conda run -n agent-foundations python -m pytest tests/unit/security tests/integration/test_authorization_flow.py tests/integration/test_chat_approval_flow.py -q
```

Result:

```text
Internal pytest result: 15 failed, 75 passed, 1 warning in 1.54s
All 15 failures were AssertionError checks that the missing Task 13 approval,
capability, repository, and schema modules exist.
Conda reported the command failed, but the shell wrapper surfaced exit code 0.
```

Because the wrapper exit code was unreliable, the same suite was rerun with the confirmed environment interpreter before any production change:

```powershell
& 'D:\anaconda\envs\agent-foundations\python.exe' -m pytest tests/unit/security tests/integration/test_authorization_flow.py tests/integration/test_chat_approval_flow.py -q
```

```text
Exit code: 1
15 failed, 75 passed, 1 warning in 1.28s
```

Red validity: pytest collected normally; existing security and Chat approval regression tests passed; every failure was a deliberate assertion caused by missing Task 13 behavior, not an import, syntax, collection, or environment error.

## 4. Green and Verification

### 4.1 Target Green

Command:

```powershell
& 'D:\anaconda\envs\agent-foundations\python.exe' -m pytest tests/unit/security tests/integration/test_authorization_flow.py tests/integration/test_chat_approval_flow.py -q
```

Result:

```text
Exit code: 0
98 passed, 1 warning in 1.41s
```

The warning is the existing Starlette/httpx deprecation warning.

### 4.2 Affected regression

Command:

```powershell
& 'D:\anaconda\envs\agent-foundations\python.exe' -m pytest tests/unit/security tests/unit/storage tests/unit/durable tests/unit/tools/patch tests/unit/chat/test_approvals.py tests/unit/chat/test_repository.py tests/integration/test_authorization_flow.py tests/integration/test_chat_approval_flow.py tests/integration/test_chat_api.py tests/integration/test_idempotent_tool_execution.py tests/integration/test_patch_preview_flow.py -q
```

First run: `1 failed, 365 passed, 20 warnings`. The failure was an authorized migration fixture that reset `user_version` to 1 after starting from current schema but did not remove the newly added v7 tables. No production behavior failed. The fixture was mechanically updated to drop `capabilities` then `authorization_requests` before simulating v1.

Completed rerun:

```text
Exit code: 0
366 passed, 20 warnings in 8.18s
```

### 4.3 Full pytest

```powershell
& 'D:\anaconda\envs\agent-foundations\python.exe' -m pytest -q
```

```text
Exit code: 0
1027 passed, 20 warnings in 126.88s (0:02:06)
```

Warnings: one existing Starlette/httpx deprecation warning and 19 existing Python 3.12 sqlite default datetime-adapter warnings.

### 4.4 Quality gates

| Gate | Result |
|---|---|
| `python -m ruff check .` | exit 0; `All checks passed!` |
| `python -m mypy src tests` | exit 0; no issues in 166 source files |
| `python -m pip check` | exit 0; no broken requirements |
| `git diff --check` | exit 0; existing LF-to-CRLF warnings only |

`pip check` also emitted the pre-existing `Ignoring invalid distribution ~gent-engineering-foundations` warning twice.

## 5. Security Semantics Evidence

### allow / ask / deny to Capability

| Policy outcome | Human decision | Durable authorization | Capability |
|---|---|---|---|
| `allow` | must be `None` | `policy_allowed`, `decided_at=NULL` | issued directly; exact retry returns the same row |
| `ask` | missing or pending | remains pending | rejected |
| `ask` | exact approved | pending → approved in the same transaction as insert | one exact Capability |
| `ask` | denied | pending → denied | rejected; no Capability |
| `deny` | absent or forged approved | denied fact | always rejected; no Capability |

Approval types contain no Tool executor and cannot perform the operation. Policy continues to return only allow/ask/deny; Capability authorizes the later exact execution.

### Exact binding, TTL, atomicity, and legacy adapter

- Binding: `authorization_id`, `run_id`, `tool_call_id`, `tool_name`, full canonical `PolicyResource`, `operation`, `profile_version`, `issued_at`, `expires_at`, and `consumed_at`.
- Canonical JSON: sorted compact UTF-8 JSON with `kind`, `scope`, `identifier`, and optional `category`; maximum 2048 bytes; no manifest, raw arguments, diff, source, or credentials field is serialized.
- TTL: explicit positive duration, maximum 24 hours; production legacy Adapter uses five minutes. Tests inject timezone-aware UTC clocks and never sleep. `now >= expires_at` rejects without consumption.
- Atomic issue: `BEGIN IMMEDIATE`; authorization transition and Capability insert share one transaction. The injected insert-failure test leaves the exact human authorization `pending` and creates zero Capability rows.
- Idempotency: concurrent exact issue returns one persisted Capability; changed request conflicts; consumed Capability cannot be reissued.
- Atomic consume: a conditional `UPDATE ... WHERE consumed_at IS NULL` permits one of two concurrent consumers; the loser receives a stable consumed rejection. Every mismatch and expiry test verifies `consumed_at` stays null.
- Corruption: unknown authorization status, malformed canonical resource, or authorization/Capability join inconsistency fails closed.
- Migration: empty and real v1, v2, v3, v4, v5, and v6 databases migrate to v7; v1 Chat rows and the existing indexes remain; the broader authorized regression covers Durable, lease, ledger, and Patch preservation. A forced v7 SQL failure rolls the whole v1–v7 transaction back to version 0 with no probe table.
- Legacy Adapter: the existing constructor remains valid. External reads follow canonicalize → Policy ASK → legacy durable human Approval → exact Capability → strict re-resolve → atomic consume → scoped read. The legacy UUID is reused as `authorization_id`.
- Legacy integration: two approvals produce two distinct, consumed Capabilities; a third denial persists `denied` and produces no Capability. Existing bounded `access_denied` result, API response, and SSE event shapes pass unchanged; serialized Chat events contain neither `resource_json` nor `capability_id`.

## 6. Scope Audit and Handoff

### Production files

- Created `src/agent_foundations/security/approvals.py`: human decision models and pending-request service; no Tool execution.
- Created `src/agent_foundations/security/capabilities.py`: canonical resource serialization, Issuer, Consumer, TTL, and stable rejection types.
- Created `src/agent_foundations/security/repository.py`: v7 authorization fact persistence, exact idempotent issue, rollback, and atomic consume.
- Created `src/agent_foundations/security/schema.py`: only migration v7.
- Modified `src/agent_foundations/storage/migrations.py`: append v7 after Patch v6.
- Modified `src/agent_foundations/chat/approvals.py`: backward-compatible generic authorization Adapter using the same SQLite database.
- Modified `src/agent_foundations/chat/tool_execution.py`: legacy external reads request and consume exact Capability after strict re-resolution.

### Tests and documents

- Created the three Task 13 security unit files and `tests/integration/test_authorization_flow.py`.
- Extended `tests/integration/test_chat_approval_flow.py` with durable authorization/Capability and non-leakage assertions.
- Mechanically updated only latest/future schema expectations and the v1 simulation in the five authorized existing migration test files.
- Updated only Task 13 Steps 1–7 in the Phase 2 plan; no Task 14 checkbox changed.

### Protection and exclusions

- No modification to CLI wiring, Chat schema/models/ConversationRepository, Runtime architecture, ExecutionBackend, Docker/Sandbox, Patch application, command/Shell, Git, network, Profile v8, or host access.
- No `# type: ignore`, `# noqa`, rule disable, dependency install, real model/API call, commit, push, PR, deployment, staging, reset, restore, or clean.
- Existing dirty tracked/untracked changes, `.gate-backup`, and generated assets remain preserved.
- Staging area remains empty.

### Recommended independent reviewer commands

```powershell
conda run -n agent-foundations python -m pytest tests/unit/security tests/integration/test_authorization_flow.py tests/integration/test_chat_approval_flow.py -q
conda run -n agent-foundations python -m pytest tests/unit/security tests/unit/storage tests/unit/durable tests/unit/tools/patch tests/unit/chat/test_approvals.py tests/unit/chat/test_repository.py tests/integration/test_authorization_flow.py tests/integration/test_chat_approval_flow.py tests/integration/test_chat_api.py tests/integration/test_idempotent_tool_execution.py tests/integration/test_patch_preview_flow.py -q
conda run -n agent-foundations python -m pytest -q
conda run -n agent-foundations python -m ruff check .
conda run -n agent-foundations python -m mypy src tests
conda run -n agent-foundations python -m pip check
git diff --check
git status --short --branch
```

Stop after Task 13 and wait for independent reviewer. Task 14 is not started or authorized.

## 7. Reviewer Fix Round 1 (2026-08-12)

### 7.1 Findings and pre-change state

- P1: legacy approval commits `approved` before generic Capability issuance; an injected insert failure leaves generic `pending` and legacy `approved`, while retry attempts to create the legacy row again and conflicts.
- P2: consumption checks only `now >= expires_at`; `now < issued_at` is incorrectly accepted.
- P2 evidence gap: `profile_version` mismatch is covered, but `profile_name` mismatch lacks an independent test.
- Current Task 13 assessment from reviewer: implementation `fail`; TDD evidence `partial`.
- Existing dirty worktree remains preserved; Task 14 is not started.
- Production code changed before this remediation Red: `no`.

### 7.2 Remediation Red

First test run was not accepted as the P1 Red because the new integration fixture omitted the required `session_id` argument and failed with `TypeError`. P2 failed for the intended missing time-window behavior and the profile-name test passed. Only the test fixture was corrected; production code remained unchanged.

Authoritative remediation Red command:

```powershell
& 'D:\anaconda\envs\agent-foundations\python.exe' -m pytest tests/integration/test_chat_approval_flow.py::test_capability_insert_failure_can_resume_exact_approved_legacy_request tests/unit/security/test_capabilities.py::test_capability_rejects_consumption_before_issued_at_without_mutation tests/unit/security/test_capabilities.py::test_approved_decision_profile_name_must_match_issuer_profile -q
```

Result:

```text
Exit code: 1
FF.
P1: retry raised ChatConflictError: approval already exists for tool call
P2: Failed: DID NOT RAISE CapabilityError for now < issued_at
Profile-name mismatch: passed
2 failed, 1 passed, 1 warning in 0.83s
```

Red validity: P1 and P2 reproduce the two reviewer findings through real Repository/Adapter behavior. The third test independently proves the existing `profile_name` mismatch guard. No production file had been changed in this remediation round.

### 7.3 Minimal remediation implementation

- `chat/approvals.py`: before creating a legacy approval, resolve an existing row by the exact `approval_id` and verify the complete request binding (`conversation_id`, `session_id`, `tool_call_id`, `tool_name`, canonical path, and operation). An exact terminal `approved` or `denied` decision is reusable; missing rows follow the original request path; pending, invalidated, or mismatched rows fail closed. This lets an exact retry resume after Capability insertion rollback without republishing the human prompt or weakening one-time Capability rules.
- `security/capabilities.py`: add stable `CapabilityNotYetValidError` under `CapabilityError`.
- `security/repository.py`: enforce the complete validity window `issued_at <= consumed_at < expires_at` before the conditional consume update. A rejected early consume leaves `consumed_at` null.
- Tests: add the injected Capability-insert failure recovery, early-clock rejection, and independent `profile_name` mismatch cases requested by the reviewer.

### 7.4 Remediation Green and regressions

Focused Green command: same three-test command as section 7.2.

```text
Exit code: 0
3 passed, 1 warning in 0.61s
```

Task target suite:

```powershell
& 'D:\anaconda\envs\agent-foundations\python.exe' -m pytest tests/unit/security tests/integration/test_authorization_flow.py tests/integration/test_chat_approval_flow.py -q
```

```text
Exit code: 0
101 passed, 1 warning in 1.67s
```

Affected regression suite: same command as section 4.2.

```text
Exit code: 0
369 passed, 20 warnings in 7.76s
```

Full pytest:

```powershell
& 'D:\anaconda\envs\agent-foundations\python.exe' -m pytest -q
```

```text
Exit code: 0
1030 passed, 20 warnings in 127.23s (0:02:07)
```

### 7.5 Final quality and scope audit

| Gate | Fresh result after remediation |
|---|---|
| `python -m ruff check .` | exit 0; `All checks passed!` |
| `python -m mypy src tests` | exit 0; no issues in 166 source files |
| `python -m pip check` | exit 0; no broken requirements; existing invalid-distribution warning only |
| `git diff --check` | exit 0; existing LF-to-CRLF warnings only |
| suppression scan over remediation production/tests | no `# type: ignore` or `# noqa` matches |
| staging area | empty |

Final executor assessment: current implementation `pass`, awaiting independent reviewer verification. Overall TDD process evidence remains `partial`: the P1/P2 remediation has a valid Red-to-Green record, but the `profile_name` regression passed immediately because that guard already existed; a tests-after result cannot be rewritten as historical Red. Task 14 remains unstarted and unauthorized.

## 8. Duplicate Reviewer Snapshot Recheck (2026-08-12)

The same reviewer report was submitted again with the pre-remediation counts (`98` target, `366` affected, and `1027` full). Before making any further production change, the executor inspected the current workspace and confirmed that section 7's remediation is present:

- `ApprovalCoordinator.request_capability()` resolves an exact existing legacy approval through `_resolved_legacy_status()` before attempting `create_approval()` again.
- Capability consumption rejects `consumed_at < issued_at` with `CapabilityNotYetValidError` before mutation.
- The three requested regression tests exist, including the independent `profile_name` mismatch case.

Fresh focused recheck:

```text
Exit code: 0
3 passed, 1 warning in 0.55s
```

Fresh target, affected, and full verification:

```text
Target:   101 passed, 1 warning in 1.44s
Affected: 369 passed, 20 warnings in 7.88s
Full:     1030 passed, 20 warnings in 127.46s (0:02:07)
```

Fresh quality gates:

```text
Ruff:      exit 0; All checks passed!
mypy:      exit 0; no issues in 166 source files
pip check: exit 0; no broken requirements; existing invalid-distribution warning only
```

No production or test code was changed in this duplicate-review round because the reported behavior is not reproducible in the current workspace. No new Red is claimed. TDD process evidence remains `partial`, staging remains empty, and Task 14 remains unstarted.
