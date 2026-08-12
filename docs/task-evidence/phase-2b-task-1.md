# Task Evidence: phase-2b-task-1

## 1. Identity

- Task ID: phase-2b-task-1
- Authoritative plan: `docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md` — Task 6
- Evidence status: completed
- TDD required: yes
- Depends on: Phase 2A user-accepted (planner handoff; Task 5 implementation pass)
- Task 5 historical TDD evidence: incomplete (not modified)
- Started at: 2026-08-09

## 2. Pre-change Snapshot

- Branch or revision: `main` @ `7b6358478ba0a65db31fba49c7245c40524041ff`
- `_SCHEMA_VERSION == 2` in `chat/repository.py` (v1 tables + `chat_tool_activities` + `idx_chat_tool_activities_session_started`)
- Overlap: `chat/repository.py`, `tests/unit/chat/test_repository.py` modified (Chat v2 activity)
- `agent_foundations/storage/` and `chat/schema.py` absent at start
- Next Phase 2 migration version: `3` (constant only; no v3 DDL)
- Rollback: delete new storage/schema files; revert repository delegation (user-confirmed)

Scoped `git status --short` at start:

```text
 M src/agent_foundations/chat/repository.py
 M tests/unit/chat/test_repository.py
```

## 3. Red

- Recorded before production-code changes: yes
- Command:

```text
conda run -n agent-foundations python -m pytest tests/unit/storage tests/unit/chat/test_repository.py -q
```

- Exit code: 1
- Relevant verbatim output:

```text
FFFFFFFFFFFFF........................................................... [ 93%]
13 failed, 64 passed in 2.45s
AssertionError: assert None is not None  # agent_foundations.storage package must exist
```

- Expected failure category: assertion failure — storage package / schema module missing
- Repository baseline at Red: 64 passed

## 4. Green

- Production: `storage/migrations.py`, `storage/database.py`, `storage/__init__.py`, `chat/schema.py`
- Repository delegates `initialize()` and `_connect()` to `SqliteDatabase`; business SQL unchanged
- Command:

```text
conda run -n agent-foundations python -m pytest tests/unit/storage tests/unit/chat/test_repository.py -q
```

- Exit code: 0
- Result: **78 passed**

## 5. Regression and Quality Gates

| Check | Command | Exit code | Result |
|---|---|---:|---|
| Target + Repository | `pytest tests/unit/storage tests/unit/chat/test_repository.py -q` | 0 | 78 passed |
| Ruff (scoped) | `ruff check src/agent_foundations/storage ... tests/unit/storage ...` | 0 | pass |
| mypy | `mypy src tests` | 0 | 114 files |
| `git diff --check` | `git diff --check` | 0 | pass (CRLF warnings only) |

## 6. Scope Audit

Task 6 changed files:

```text
?? src/agent_foundations/storage/
?? src/agent_foundations/chat/schema.py
 M src/agent_foundations/chat/repository.py
 M tests/unit/chat/test_repository.py
?? tests/unit/storage/
?? docs/task-evidence/phase-2b-task-1.md
 M docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md (Task 6 steps only)
```

- No v3 migration or Durable tables
- No binary SQLite fixtures
- Chat business SQL unchanged (schema extracted verbatim)
- User Chat v2 activity code preserved

## 7. Data Preservation (Step 7)

### v1 → v2 upgrade (`test_existing_v1_database_upgrades_to_v2_without_data_loss`)

- Before: `user_version=1`, tables conversations/messages/runs/approval_requests with fixture rows
- After: `user_version=2`, `chat_tool_activities` created, core table rows byte-identical (ORDER BY rowid)

### v2 adoption (`test_existing_v2_database_is_adopted_without_reapplying_ddl`)

- Before/after: `user_version=2`
- All v1 core rows preserved
- `chat_tool_activities` row (session, tool_call_id, tool_name, status, summaries, timestamps, last_event_id) preserved
- Index set preserved including `idx_chat_tool_activities_session_started`

### Rollback

- Empty DB v1+v2 failure: `user_version=0`, no tables
- v1 data + failed v2: `user_version=1`, v1 rows preserved, no `chat_tool_activities`

### Future version

- `user_version=99` → `FutureSchemaVersionError` / repository `UnsupportedSchemaVersionError`

## 8. Reviewer Fix Round (P1 concurrent initialization)

- Trigger: independent acceptance blocked — `user_version` read before `BEGIN IMMEDIATE`
- Fix: `BEGIN IMMEDIATE` first; read `user_version` inside transaction; early commit when already at latest; `rollback()` on all exception paths
- Test: `test_concurrent_initialize_on_same_path_both_succeed` — two `SqliteDatabase` instances, `asyncio.gather` both `initialize()`, expect no exceptions and `user_version == 2`
- Command:

```text
conda run -n agent-foundations python -m pytest tests/unit/storage tests/unit/chat/test_repository.py -q
conda run -n agent-foundations python -m ruff check src/agent_foundations/storage src/agent_foundations/chat/schema.py src/agent_foundations/chat/repository.py tests/unit/storage tests/unit/chat/test_repository.py
conda run -n agent-foundations python -m mypy src tests
```

- Exit code: 0
- Result: **79 passed**; Ruff pass; mypy 114 files; `git diff --check` pass (CRLF warnings only)
- Evidence status: **completed** (awaiting re-acceptance)

## 9. Handoff Summary

- Current verification status: **pass**
- TDD process evidence: **complete**
- Recommended reviewer commands:

```powershell
conda run -n agent-foundations python -m pytest tests/unit/storage tests/unit/chat/test_repository.py -q
conda run -n agent-foundations python -m ruff check src/agent_foundations/storage src/agent_foundations/chat/schema.py src/agent_foundations/chat/repository.py tests/unit/storage tests/unit/chat/test_repository.py
conda run -n agent-foundations python -m mypy src tests
```
