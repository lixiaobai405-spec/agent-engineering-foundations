# Task Evidence: phase-2b-task-6

## 1. Identity

- Task ID: phase-2b-task-6 (Plan Task 11)
- Authoritative plan or task spec: `docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md` — Task 11
- Evidence status: gate-complete — implementation accepted; awaiting user Phase 2B sign-off (Plan Step 7)
- TDD required: yes
- TDD process evidence: **unavailable** (tests and minimal implementation were iterated in one session before a dedicated pre-implementation Red run was recorded; see §3)
- Depends on: phase-2b-task-5 user-accepted
- Started at: 2026-08-11
- Completed at: 2026-08-11

## 2. Pre-change Snapshot

- Branch: `main` (dirty worktree; large pre-existing user changes preserved)
- Intended scope: patch parser/validator/repository/v6 migration, `ValidatePatchTool`, `PatchProposalExecutor`, Trace redaction for `validate_patch`
- Rollback: remove `src/agent_foundations/tools/patch/`, patch tests, v6 migration wiring in `migrations.py`, loop Trace redaction only; do not downgrade user databases

Pre-existing user modifications preserved (not reverted). Task-scoped additions are isolated under `src/agent_foundations/tools/patch/` and `tests/unit/tools/patch/`.

## 3. Red

**Status: unavailable**

Reason: Module scaffolding and tests were written alongside minimal implementation in the same executor session. A formal Red run before any production code was not captured in evidence. Re-running Red after implementation yields 21 passed; artificially removing modules would produce import/collection failures rather than contract assertion failures.

Recommended reviewer note: treat Green + integration/trace tests as primary behavioral proof; historical Red→Green order cannot be independently verified.

## 4. Green

**Command:**

```powershell
conda run -n agent-foundations python -m pytest tests/unit/tools/patch tests/integration/test_patch_preview_flow.py -q
```

- Exit code: 0
- Result: **25 passed** in ~0.48s (post reviewer-fix round)

## 5. Regression and Quality Gates

| Check | Command | Exit code | Result |
|---|---|---:|---|
| Phase 2B scoped pytest | `pytest tests/unit/durable tests/unit/storage tests/unit/tools/patch tests/integration/test_agent_loop.py tests/integration/test_idempotent_tool_execution.py tests/integration/test_patch_preview_flow.py tests/unit/chat/test_repository.py -q` | 0 | **253 passed** |
| Full pytest | `pytest -q` | 0 | **927 passed** |
| Ruff | `ruff check .` | 0 | All checks passed |
| mypy | `mypy src tests` | 0 | Success (150 files) |
| pip check | `pip check` | 0 | No broken requirements |
| npm test:viewer | `npm run test:viewer` | 0 | pass |
| npm typecheck:viewer | `npm run typecheck:viewer` | 0 | pass |
| npm test:chat | `npm run test:chat` | 0 | 68 passed |
| npm typecheck:chat | `npm run typecheck:chat` | 0 | pass |
| npm build:chat | `npm run build:chat` | 0 | **pass** (built in ~603ms; chunk size warnings only) |
| git diff --check | `git diff --check` | 0 | pass (CRLF warnings only) |

**Pre-build backup:** `.gate-backup/phase-2b-task-6-chat-static/` (313 files copied from `src/agent_foundations/viewer/static/chat` before `emptyOutDir` rebuild).

**Post-build regression (2026-08-11):** Phase 2B scoped **253 passed**; full **927 passed**; pip check pass.

## 6. Scope Audit

### Task-scoped production files (created)

- `src/agent_foundations/tools/patch/__init__.py`
- `src/agent_foundations/tools/patch/models.py`
- `src/agent_foundations/tools/patch/parser.py`
- `src/agent_foundations/tools/patch/validator.py`
- `src/agent_foundations/tools/patch/repository.py`
- `src/agent_foundations/tools/patch/execution.py`
- `src/agent_foundations/tools/patch/validate_patch.py`
- `src/agent_foundations/tools/patch/schema.py` (v6 migration isolation)

### Task-scoped production files (modified)

- `src/agent_foundations/storage/migrations.py` — wire v6 `patch_proposals`
- `src/agent_foundations/runtime/loop.py` — Trace redaction for `validate_patch` on requested/completed/model context paths

### Task-scoped test files (created)

- `tests/unit/tools/patch/__init__.py`
- `tests/unit/tools/patch/test_parser.py`
- `tests/unit/tools/patch/test_validator.py`
- `tests/unit/tools/patch/test_repository.py`
- `tests/unit/tools/patch/test_execution.py`
- `tests/unit/tools/patch/test_validate_patch.py`
- `tests/integration/test_patch_preview_flow.py`
- `tests/unit/tools/patch_test_helpers.py`
- `tests/__init__.py`, `tests/unit/__init__.py`, `tests/unit/tools/__init__.py` (mypy package layout)

### Task-scoped test files (modified for v6)

- `tests/unit/chat/test_repository.py`
- `tests/unit/durable/test_repository.py`
- `tests/unit/durable/test_effects.py`
- `tests/unit/storage/test_database.py`

### Out of scope / not modified

- No `apply_patch`, write/delete/move Tools, `run_command`, Git write Tools
- No Phase 2C Policy/Capability/Sandbox
- No commit, push, PR

## 7. Gaps and Limitations

1. **TDD Red evidence unavailable** — see §3.
2. **Pre-build static backup** — user untracked chat static assets preserved at `.gate-backup/phase-2b-task-6-chat-static/`; live `viewer/static/chat` rebuilt by gate `build:chat`.

## 7f. Phase 2B Gate Completion (2026-08-11)

Executor ran remaining gate after backup:

```powershell
# backup → .gate-backup/phase-2b-task-6-chat-static/ (313 files)
npm run build:chat   # exit 0
pytest (scoped + full) # 253 + 927 passed
pip check            # pass
git diff --check     # pass
```

All required automated gates **pass**. TDD Red remains unavailable (process evidence gap, not behavioral).

## 7b. Reviewer Fix Round (2026-08-11)

| Issue | Fix |
|---|---|
| P1 reparse resolved before check | `joinpath` without `resolve()`; `_is_reparse_point` on path before follow |
| P1 ValidationError on bad sha256 | `ValidationError` → failed `ToolResult` (`PATCH_BASELINE_MISMATCH`) |
| P1 NUL in patch hunk lines | `_reject_binary_patch_content` on all hunk lines |
| P2 Git EOF marker on separate line | `_parse_hunk` consumes standalone marker line |

Post-fix: patch tests **25 passed**; Phase 2B scoped **246 passed**; full **920 passed**; ruff/mypy pass.

## 7c. Reviewer Fix Round 2 (2026-08-11)

| Issue | Fix |
|---|---|
| P1 duplicate target path in patch | Reject when canonical key already seen (unconditional) |
| P1 hunk topology | `_validate_create_hunks`: `old_start/old_count` must be 0, only ADD lines |
| P1 modify hunk overlap/order | `_validate_modify_hunk_topology`: non-decreasing `old_start`, no overlapping old ranges |

Post-fix: patch tests **28 passed**; Phase 2B scoped **249 passed**; full **923 passed**; ruff/mypy pass.

## 7d. Reviewer Fix Round 3 (2026-08-11)

| Issue | Fix |
|---|---|
| P1 zero-length insertion bounds | `_validate_zero_length_insertion_position`: empty file `old_start=0`; else `1 <= old_start <= len(file_lines)` |
| P1 duplicate insertion slot | Track `insertion_positions` set for `old_count=0` hunks |
| Overlap with covered region | Insertion conflicts only when `covered_end > 0` and `old_start <= covered_end` |

Post-fix: patch tests **31 passed**; Phase 2B scoped **252 passed**; full **926 passed**.

## 7e. Reviewer Fix Round 4 (2026-08-11)

| Issue | Fix |
|---|---|
| P1 `old_start=0` on non-empty file | Zero-length insertion bound unified to `0 <= old_start <= file_line_count` (Git header insert before line 1) |

Post-fix: patch tests **32 passed**.

## 8. Handoff Summary

### Delivered behavior

- Hand-written unified diff parser (CREATE/MODIFY only) with strict limits and path rules
- Filesystem + caller baseline validation (read-only; symlink/reparse checks)
- Deterministic `patch_id` and `project_root_fingerprint`
- v6 `patch_proposals` table with `(run_id, patch_id)` identity, idempotent save, conflict detection
- `ValidatePatchTool` fail-closed without context (`PATCH_CONTEXT_REQUIRED`)
- `PatchProposalExecutor` binds `session_id`→`run_id`, validates root fingerprint, saves proposal, returns bounded summary
- Trace redaction: no raw diff/source in JSONL events; Checkpoint retains full facts for resume
- Fixture project bytes unchanged after preview flow

### Reviewer recommended commands

```powershell
conda run -n agent-foundations python -m pytest tests/unit/tools/patch tests/integration/test_patch_preview_flow.py -q
conda run -n agent-foundations python -m pytest tests/unit/durable tests/unit/storage tests/unit/tools/patch tests/integration/test_agent_loop.py tests/integration/test_idempotent_tool_execution.py tests/integration/test_patch_preview_flow.py tests/unit/chat/test_repository.py -q
conda run -n agent-foundations python -m pytest -q
conda run -n agent-foundations python -m ruff check .
conda run -n agent-foundations python -m mypy src tests
```

Optional after user confirms static asset backup: `npm run build:chat`

### Step 7

- **Implementation:** reviewer accepted (2026-08-11).
- **Automated Phase 2B Gate:** all required commands pass including `build:chat` (see §5, §7f).
- **User Phase 2B sign-off:** accepted on 2026-08-12 — user explicitly confirmed `确认 Phase 2B 验收` in the current executor conversation; Plan Step 7 is checked.
