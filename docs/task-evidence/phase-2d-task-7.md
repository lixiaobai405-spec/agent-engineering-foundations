# Task Evidence: phase-2d-task-7

## 1. Identity

- Task ID: `phase-2d-task-7`
- Authoritative plan or task spec: Task 23 in `docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md` plus the user-confirmed executor prompt for Task 23
- Evidence status: user-accepted / current implementation pass; TDD process evidence complete; full suite partial
- TDD required: yes; real compactor not authorized
- Started at: 2026-08-27 13:30:00 +08:00 (Asia/Shanghai)
- Dependency: Task 22 (`phase-2d-task-6`) user-accepted 2026-08-26; evidence `docs/task-evidence/phase-2d-task-6.md` (read-only). Reviewer P3 is not in this Task’s Files.

## 2. Pre-change Snapshot

- Branch: `codex/phase-2-next` (not `main`)
- Initial `git diff --check`: exit `0` (LF/CRLF working-copy warnings only)
- Existing user changes that must be preserved: all dirty Task 15–22 work, Chat hashed assets, `.agents/`, `.gate-backup/`. No reset/restore/clean/commit/push.
- Intended modification scope: Task 23 Create/Modify list only, optional `context/__init__.py` export, optional mechanical `test_builder.py` / `tests/unit/runtime` assertion updates, this evidence, Task 23 Step 1–8 checkboxes.
- Protected: Chat hashed assets, `.agents/`, `.gate-backup/`, real `.env`, `docs/eval-baselines/phase-1-v1.json`, `storage/migrations.py`, `chat/schema.py`, Dockerfiles, package.json
- Expected rollback: delete Task 23 created files; reverse Task 23 hunks in allowed Modify files.
- Docker: **not authorized / not-run**
- Real model / real compactor / paid API: **not authorized / not-run**
- Default production compact path: `FakeCompactor` only. `ModelCompactor` uses FakeProvider JSON only.

### Current Context Budget truncation (before this Task)

- `max_chars=32000`, `max_tool_result_chars=8000`, `max_source_chars=4000`
- System all kept; newest non-system always kept; older messages dropped to fit
- System or mandatory latest overflow → `ContextBudgetExceededError`
- Tool results truncated with `...`; source messages not mutated
- Task 22 sources are a droppable layer; `sources=()` preserves that behavior
- No `compaction_trigger_chars` yet

### SQLite `messages` invariants (must hold after this Task)

- Chat `messages` table stores user/assistant originals only (no tool rows)
- Compaction must not UPDATE/DELETE those rows with a summary
- Tool/system originals live on the current run `session.messages` / checkpoint, not Chat `messages`

### Compaction quality baseline plan

- Corpus: `tests/fixtures/context/compaction-cases-v1.json`
- Metric: every listed critical fact `value` is extracted and present in an accepted FakeCompactor summary (recall 100%)
- Invalid/malicious summaries are rejected; fallback is Task 22 truncation, not a lying summary

### Complete initial `git status --short --branch` (compact)

Command: `git status --short --branch`  
Exit code: `0`

```text
## codex/phase-2-next
 M docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md
 M src/agent_foundations/chat/*
 M src/agent_foundations/context/{__init__,budget,builder}.py
 M src/agent_foundations/runtime/loop.py
 M tests/integration/test_agent_loop.py
 M tests/unit/context/test_builder.py
 ... plus pre-existing Task 15–22 dirty/untracked paths, Chat hashed assets, .agents/, .gate-backup/
 ?? docs/task-evidence/phase-2d-task-6.md
 ?? src/agent_foundations/context/{cache,relevance,repo_map,sources}.py
```

Hashed Chat asset filenames omitted. Index/HEAD must not change.

## Verification contract (verbatim)

- Target tests: `conda run -n agent-foundations python -m pytest tests/unit/context/test_critical_facts.py tests/unit/context/test_compaction.py tests/unit/context/test_rehydration.py tests/unit/context/test_model_compactor.py tests/integration/test_context_compaction_flow.py -q`
- Affected regression tests: `conda run -n agent-foundations python -m pytest tests/unit/context tests/unit/runtime tests/unit/chat tests/integration/test_agent_loop.py tests/integration/test_command_feedback_agent_flow.py -q`
- Full suite: `required`
- Full suite reason: 本 Task 修改共享 ContextBuilder/AgentLoop 的模型输入语义，错误压缩可能造成跨模块事实丢失或权限判断漂移。
- Additional gates: FakeCompactor quality corpus、critical fact recall `100%`、rehydration fingerprint/range matrix、raw Artifact exclusion/leakage scan；自动测试不得调用真实模型。
- Docker: not-run / 未授权
- Real model / real compactor: not-run / 未授权

## 3. Red

### 3a. Compaction / critical facts (Step 3, before production-code changes)

- Recorded before production-code changes: yes
- Time: 2026-08-27 13:40:00 +08:00 (Asia/Shanghai)
- Test files: `tests/unit/context/test_critical_facts.py`, `tests/unit/context/test_compaction.py`
- Command: `D:\anaconda\envs\agent-foundations\python.exe -m pytest tests/unit/context/test_critical_facts.py tests/unit/context/test_compaction.py -q` (PYTHONIOENCODING=utf-8; conda run avoided due to Windows gbk)
- Exit code: `1`
- Relevant verbatim output:

```text
FFFFFFFFFFFFFFFF                                                         [100%]
AssertionError: missing module agent_foundations.context.critical_facts
AssertionError: missing module agent_foundations.context.compaction
16 failed in 0.56s
```

- Expected failure category: assertion failure from missing target behavior (extractor / FakeCompactor / CompactionRecord APIs)
- Why this failure demonstrates the missing behavior: `importlib.util.find_spec()` returned `None` for the Task 23 context modules; tests did not fail on syntax, environment, or unrelated imports.
- If unavailable, why it cannot be verified: n/a

### 3b. Rehydration / ModelCompactor / AgentLoop (Step 6, before those production files / loop wiring)

- Recorded before rehydration.py, model_compactor.py, repository.get_message, and loop wiring: yes
- Time: 2026-08-27 13:48:00 +08:00 (Asia/Shanghai)
- Test files: `tests/unit/context/test_rehydration.py`, `tests/unit/context/test_model_compactor.py`, `tests/integration/test_context_compaction_flow.py`
- Command: `D:\anaconda\envs\agent-foundations\python.exe -m pytest tests/unit/context/test_rehydration.py tests/unit/context/test_model_compactor.py tests/integration/test_context_compaction_flow.py -q`
- Exit code: `1`
- Relevant verbatim output:

```text
FFFFFFFFFFFFFF                                                           [100%]
AssertionError: missing module agent_foundations.context.rehydration
AssertionError: missing module agent_foundations.context.model_compactor
AssertionError: assert False  (hasattr ConversationRepository.get_message)
AssertionError: AgentLoop must accept optional compactor and conversation_repository
14 failed in 0.72s
```

- Expected failure category: assertion failure from missing rehydration / ModelCompactor / AgentLoop derived compact view
- Why this failure demonstrates the missing behavior: find_spec None for new modules; repository lacked get_message; AgentLoop lacked compactor kwargs. Failures were not syntax/import crashes of unrelated code.
- If unavailable, why it cannot be verified: n/a

## 4. Green

- Production files changed: `critical_facts.py`, `compaction.py`, `fake_compactor.py`, `rehydration.py`, `model_compactor.py`, `budget.py`, `builder.py`, `loop.py`, `repository.py` (`get_message`), `domain/messages.py` (`message_id`), `context/__init__.py`
- Compaction Green command: same as Step 3
- Exit code: `0`
- Output: `16 passed in 0.24s` (later `30 passed` after rehydration Green)
- Rehydration Green command: same as Step 6 Red
- Exit code: `0`
- Output: `30 passed in 0.60s` (combined with later target re-runs `30 passed in 0.57s`)

## 5. Regression and Quality Gates

Windows note: `conda run -n agent-foundations` can crash pytest with `UnicodeEncodeError: gbk`. Commands below used `D:\anaconda\envs\agent-foundations\python.exe` with `PYTHONIOENCODING=utf-8`. Equivalent interpreter, not a shrunk contract.

| Check | Command | Exit code | Result |
|---|---|---:|---|
| Target tests | `python -m pytest tests/unit/context/test_critical_facts.py tests/unit/context/test_compaction.py tests/unit/context/test_rehydration.py tests/unit/context/test_model_compactor.py tests/integration/test_context_compaction_flow.py -q` | 0 | 30 passed |
| Affected regression | `python -m pytest tests/unit/context tests/unit/runtime tests/unit/chat tests/integration/test_agent_loop.py tests/integration/test_command_feedback_agent_flow.py -q` | 0 | 401 passed, 6 warnings |
| Full pytest `-q` | `python -m pytest -q` | 1 | 8 failed, 1355 passed, 9 skipped. Failures: `test_controlled_patch_flow` / `test_patch_crash_recovery` with `PATCH_EFFECT_UNKNOWN` (7 marked `docker`; 1 untagged but uses DockerBackend). Not Task 23 files. Docker 未授权. |
| Full pytest `-m "not docker"` | extra probe | 1 | 1 failed (`test_cross_run_drift_and_capability_replay_are_rejected`, same PATCH_EFFECT_UNKNOWN), 1355 passed, 16 deselected |
| FakeCompactor quality corpus | `tests/fixtures/context/compaction-cases-v1.json` via target tests | 0 | critical fact recall 100% on listed values |
| Ruff | `python -m ruff check .` | 0 | All checks passed |
| mypy | `python -m mypy src tests` | 0 | Success: no issues found in 273 source files |
| pip check | `python -m pip check` | 0 | No broken requirements (invalid-distribution warning for `~gent-engineering-foundations`) |
| npm run test:viewer | | 0 | 12 pass |
| npm run typecheck:viewer | | 0 | pass |
| npm run test:chat | | 0 | 9 files / 74 tests pass |
| npm run typecheck:chat | | 0 | pass |
| npm run build:chat | | 0 | built in 612ms; regenerated hashed Chat assets (side effect; not Task 23 semantic change; git restore forbidden) |
| git diff --check | | 0 | LF/CRLF warnings only |
| git status --short | | 0 | dirty `codex/phase-2-next`; Task 23 files plus preserved pre-existing dirty tree |

Additional gates:
- critical fact recall: 100% on corpus `all-critical-kinds` and `cross-turn-decision`
- rehydration: same-conversation restore; cross-conversation / unknown ID / role mismatch / fingerprint drift / SQL / path rejected; tool rows not written to Chat `messages`
- leakage: `fixture-secret` and `.agent-foundations/command-output/...` absent from CompactionRequest and `context.compaction` / trace payloads
- malicious/missing-fact summaries rejected; AgentLoop falls back to Task 22 truncation (no lying summary in model input)
- automatic tests used FakeCompactor / FakeProvider only

## 6. Scope Audit

- Final Task 23 files: listed Create set; Modify `budget.py`, `builder.py`, `loop.py`, `chat/repository.py` (`get_message` only), `domain/messages.py` (`message_id`), `test_builder.py` (trigger default), `test_runner.py` (mechanical allow `[repository context]` in Chat runner history assertion — needed for Affected `tests/unit/chat`, does not drop history content checks), evidence, Task 23 Step checkboxes, `context/__init__.py` exports
- Unrelated changes introduced: `npm run build:chat` hashed asset churn; not reverted (no git restore). Pre-existing dirty Task 15–22 files preserved.
- Existing user changes preserved: yes
- Secrets or generated artifacts detected: no real `.env`/keys; fixtures use `coa_` placeholders and `sk-test-placeholder`
- Commit, push, deployment, paid API call, or next Task performed: no
- Files list exception: `tests/unit/chat/test_runner.py` updated because Affected includes `tests/unit/chat` and Task 22 repo-map injection made an exact message-list assertion fail. History contents still asserted.

## 7. Gaps and Limitations

- Checks not run: Docker image/build; real model; real/OpenAI compactor; paid API; commit
- Environment warnings: conda/gbk avoided; pip invalid distribution `~gent-engineering-foundations`; FastAPI Starlette httpx deprecation; sqlite3 datetime adapter deprecation
- Process evidence gaps: none for Red→Green of Task 23 modules. Full `pytest -q` docker/patch failures are pre-existing host/Docker apply_patch issues, not compaction regressions (Target/Affected did not include those files and passed).
- Remaining risks: Chat `runner.py` still does not copy SQLite `message_id` onto domain history (not in Files). Rehydration of Chat user/assistant works when IDs are supplied (loop/tests). Compaction is a derived `_request_model` view only.
- Real compactor: **not-run / 未授权**
- Docker: **not authorized**; docker-marked tests that executed during `pytest -q` failed with `PATCH_EFFECT_UNKNOWN`

### Metrics (FakeCompactor, automatic)

- critical recall: 100% on quality corpus expected values
- compression: accepted records satisfy `compacted_units < original_units` on the padded all-kinds case
- fallback count in tests: malicious unit path + AgentLoop malicious compactor path (rejected, not counted as successful compact)
- rehydration: pass for same conversation; reject for cross-conversation, unknown ID, role mismatch, fingerprint drift, SQL, filesystem path

## 8. Handoff Summary

- Evidence status: user-accepted
- Current verification status: **pass** (Task 23 target/affected/quality gates). Independently reviewed; user-accepted 2026-08-27.
- TDD process evidence: **complete** (two Red stages before corresponding production modules); user acceptance does not independently witness historical Red→Green
- Full suite: required; actual result **partial** due to Docker/`apply_patch` `PATCH_EFFECT_UNKNOWN`. Do not report as full suite passed.
- Docker: not-run / 未授权 for this Task; default `pytest -q` still collected docker-backed patch tests
- Real model / real compactor: not-run / 未授权
- User acceptance: recorded in §9
- Reviewer acceptance: pass (current implementation) in the reviewer session that preceded this confirmation
- Reviewer findings retained: P2 full-suite partial (unrelated patch/Docker); P3 Chat runner does not copy SQLite `message_id`; P3 label-based fact extraction; P3 ModelCompactor omits message bodies
- Recommended reviewer commands:
  - `python -m pytest tests/unit/context/test_critical_facts.py tests/unit/context/test_compaction.py tests/unit/context/test_rehydration.py tests/unit/context/test_model_compactor.py tests/integration/test_context_compaction_flow.py -q`
  - `python -m pytest tests/unit/context tests/unit/runtime tests/unit/chat tests/integration/test_agent_loop.py tests/integration/test_command_feedback_agent_flow.py -q`
  - inspect `context.compaction` payloads for absence of full summary
- Suggested commit (not executed): `feat: compact context without losing critical facts`

## 9. User Acceptance

- Confirmed at: 2026-08-27 14:03 +08:00.
- Exact user confirmation: `确认 Task 23 用户验收通过`.
- Result: Task 23 (`phase-2d-task-7`) is user-accepted for the current implementation; the `Task 23 accepted` dependency named by Task 24 is satisfied.
- Full suite note: this confirmation accepts Task 23 compaction/rehydration behavior after independent targeted review. It does not treat `pytest -q` Docker/`apply_patch` `PATCH_EFFECT_UNKNOWN` failures as a reconstructed green full suite.
- TDD note: executor Red is internally consistent and marked complete; this confirmation does not independently witness the original Red→Green sequence.
- Boundary: this confirmation records acceptance only. Task 24 has not been started and still requires its own explicit single-Task executor authorization. Real compactors remain forbidden until a separately authorized human acceptance. No commit, push, or next-Task implementation is authorized by this confirmation.

