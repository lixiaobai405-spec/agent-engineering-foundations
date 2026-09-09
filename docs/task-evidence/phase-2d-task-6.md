# Task Evidence: phase-2d-task-6

## 1. Identity

- Task ID: `phase-2d-task-6`
- Authoritative plan or task spec: Task 22 in `docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md` plus the user-confirmed executor prompt for Task 22
- Evidence status: user-accepted / current implementation pass; TDD process evidence complete
- TDD required: yes
- Started at: 2026-08-26 21:55:00 +08:00 (Asia/Shanghai)
- Dependency: Task 21 (`phase-2d-task-5`) user-accepted 2026-08-26; evidence `docs/task-evidence/phase-2d-task-5.md` (read-only)

## 2. Pre-change Snapshot

- Branch: `codex/phase-2-next` (not `main`); HEAD `14ece4e`
- Initial `git diff --check`: exit `0` (LF/CRLF working-copy warnings only; no whitespace errors)
- Existing user changes that must be preserved: all tracked and untracked Task 15–21 work, Chat hashed assets, `.agents/`, `.gate-backup/`, and every other dirty path present at start. No `git reset` / `restore` / `checkout --` / `clean` / stage / commit / push.
- Intended modification scope: only the Task 22 Create/Modify list, optional minimal `context/__init__.py` export, this evidence file, and Task 22 Step 1–7 checkboxes when actually satisfied.
- Protected files: Chat hashed assets (no hand edits), `.agents/`, `.gate-backup/`, real `.env`, `docs/eval-baselines/phase-1-v1.json`, Classifier / Artifact / Git-read contracts, Dockerfiles, package.json
- Expected rollback: delete only Task 22-created files; reverse only Task 22 hunks in allowed Modify files.
- Docker: **not authorized / not-run**.
- Real model / real compactor: not-run.
- Offline Eval output: `.agent-foundations/evals/phase-2d-task-6.json` only; do not overwrite the authoritative baseline.

### Existing Context Budget behavior (before this Task)

- `ContextBudget.max_chars` default `32000`
- `ContextBudget.max_tool_result_chars` default `8000`
- System messages all kept; if they exceed `max_chars` → `ContextBudgetExceededError`
- Non-system messages filled from newest; the newest non-system message is always included (mandatory latest); leftover older messages dropped
- If system + mandatory latest exceed `max_chars` → `ContextBudgetExceededError`
- Tool messages truncated to `max_tool_result_chars` with `...` suffix; source messages are not mutated
- `ContextBuilder.build(messages)` has no `sources` parameter yet

### Authoritative Offline Eval baseline (`docs/eval-baselines/phase-1-v1.json`)

- dataset_id: `phase-1-readonly`
- dataset_version: `v1`
- prompt_version: `phase-1-v1`
- response_fixture_version: `v1`
- runtime_revision: `working-tree`
- summary: `total_tasks=5`, `passed_tasks=5`, `failed_tasks=0`, `success_rate=1.0`
- task_ids (all passed): `phase1-code-location`, `phase1-error-explanation`, `phase1-readonly-tool-selection`, `phase1-sensitive-file-rejection`, `phase1-external-path-rejection`

### Complete initial `git status --short --branch` (compact)

Command: `git status --short --branch`

Exit code: `0`

```text
## codex/phase-2-next
 M .dockerignore
 M docker/README.md
 M docker/agent-sandbox.Dockerfile
 M docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md
 M pyproject.toml
 M src/agent_foundations/chat/*
 M src/agent_foundations/cli/main.py
 M src/agent_foundations/execution/*
 M src/agent_foundations/runtime/loop.py
 M src/agent_foundations/runtime/tool_execution.py
 M src/agent_foundations/security/*
 M src/agent_foundations/storage/migrations.py
 M src/agent_foundations/tools/registry.py
 M src/agent_foundations/viewer/static/chat/index.html
 M tests/chat/*
 M tests/e2e/test_chat_ui.py
 M tests/integration/test_chat_*.py
 M tests/integration/test_execution_backend.py
 M tests/unit/chat/*
 M tests/unit/durable/*
 M tests/unit/execution/test_docker.py
 M tests/unit/execution/test_models.py
 M tests/unit/security/*
 M tests/unit/storage/test_database.py
 M tests/unit/tools/patch/test_repository.py
 M web/chat/*
 D src/agent_foundations/viewer/static/chat/assets/<pre-build hashed assets>
 ?? .agents/
 ?? .gate-backup/
 ?? docker/agent-sandbox-*.Dockerfile
 ?? docs/task-evidence/phase-2c-*.md
 ?? docs/task-evidence/phase-2d-task-1.md through phase-2d-task-5.md
 ?? src/agent_foundations/command_output/
 ?? src/agent_foundations/execution/sandbox_manifest.py
 ?? src/agent_foundations/execution/workspace.py
 ?? src/agent_foundations/tools/command/
 ?? src/agent_foundations/tools/git/
 ?? src/agent_foundations/tools/patch/applier.py
 ?? src/agent_foundations/tools/patch/apply_patch.py
 ?? src/agent_foundations/viewer/static/chat/assets/<post-build hashed assets>
 ?? tests/chat/*.test.tsx (command-feedback/patch-preview/permission-profile)
 ?? tests/fixtures/command-output/
 ?? tests/fixtures/evals/phase-2c-permission-profiles-v1.json
 ?? tests/integration/test_command_*.py
 ?? tests/integration/test_git_read_tools.py
 ?? tests/integration/test_controlled_patch_flow.py
 ?? tests/integration/test_patch_crash_recovery.py
 ?? tests/unit/command_output/
 ?? tests/unit/tools/command/
 ?? tests/unit/tools/git/
 ?? web/chat/components/CommandFeedbackCard.tsx
 ?? web/chat/components/PatchPreviewCard.tsx
 ?? web/chat/components/PermissionProfileSelect.tsx
```

Hashed Chat asset filenames omitted. Exact `git status --short --branch` from this session is the working-tree baseline. Index/HEAD must not change. `src/agent_foundations/context/budget.py` and `builder.py` were unmodified at start.

## Verification contract (verbatim)

- Target tests: `conda run -n agent-foundations python -m pytest tests/unit/context tests/integration/test_agent_loop.py -q`
- Affected regression tests: `conda run -n agent-foundations python -m pytest tests/unit/runtime tests/unit/tools tests/integration/test_command_feedback_agent_flow.py tests/integration/test_git_read_tools.py -q`
- Full suite: `not-required`
- Full suite reason: 本 Task 只增加只读、确定性的 context source selection，不增加 Tool、Capability、migration 或模型调用。
- Additional gates: PathPolicy/sensitive/symlink corpus、cache invalidation matrix、Context Budget before/after Offline Eval；不得调用真实 compactor/model。
- Docker: not-run / 未授权

## 3. Red

- Recorded before production-code changes: yes
- Time: 2026-08-26 22:05:00 +08:00
- Test file and test name: `tests/unit/context/test_*.py`, `tests/integration/test_agent_loop.py`
- Command: env python `pytest tests/unit/context tests/integration/test_agent_loop.py -q --tb=line`
- Exit code: `1`
- Relevant verbatim output:

```text
FAILED tests/unit/context/test_builder.py::test_budget_default_source_cap_does_not_change_legacy_limits
  AssertionError: assert None == 4000
FAILED tests/unit/context/test_cache.py::test_cache_hit_miss_invalidation_and_policy_recheck
  AssertionError: context cache is missing
FAILED tests/unit/context/test_relevance.py::test_term_overlap_score_is_deterministic_and_bounded
  AssertionError: RelevanceScorer is missing
FAILED tests/unit/context/test_sources.py::test_context_source_shape_fingerprint_and_stable_ids
  AssertionError: ContextSource module is missing
FAILED tests/unit/context/test_repo_map.py::test_python_and_ts_map_are_deterministic_and_skip_unsafe_paths
  AssertionError: RepoMapBuilder is missing
FAILED tests/integration/test_agent_loop.py::test_context_snapshot_records_selection_without_source_body
  AssertionError: context.snapshot event is missing
FAILED tests/integration/test_agent_loop.py::test_agent_executes_tool_then_returns_final_answer
  AssertionError: assert ['session.sta...lidated', ...] == ['session.sta...quested', ...]
12 failed, 42 passed in 0.63s
```

- Expected failure category: assertion failure from missing ContextSource / Repo Map / Relevance / cache / `sources` / `max_source_chars` / `context.snapshot`
- Why this failure demonstrates the missing behavior: existing `test_builder.py` budget tests still collected and passed (42 passed). New contracts failed with `AssertionError`, not import/syntax/environment errors. `find_spec` is None for the new modules.
- If unavailable, why it cannot be verified: n/a


## 4. Green

- Production files changed: `src/agent_foundations/context/{sources,repo_map,relevance,cache,budget,builder,__init__}.py`, `src/agent_foundations/runtime/loop.py`
- Command: env python `pytest tests/unit/context tests/integration/test_agent_loop.py -q`
- Exit code: `0`
- Relevant verbatim output:

```text
54 passed in 0.71s
```

No model, embedding, tsc, or semantic summary. Truncation is labeled truncated/dropped, not compaction.

## 5. Regression and Quality Gates

| Check | Command | Exit code | Result |
|---|---|---:|---|
| Target tests | env python `pytest tests/unit/context tests/integration/test_agent_loop.py -q` | 0 | 54 passed |
| Affected regression | env python `pytest tests/unit/runtime tests/unit/tools tests/integration/test_command_feedback_agent_flow.py tests/integration/test_git_read_tools.py -q` | 0 | 330 passed, 1 skipped |
| Ruff | env python `ruff check src/agent_foundations/context src/agent_foundations/runtime/loop.py tests/unit/context tests/integration/test_agent_loop.py` | 0 | All checks passed |
| mypy | env python `mypy src/agent_foundations/context src/agent_foundations/runtime/loop.py tests/unit/context tests/integration/test_agent_loop.py` | 0 | Success: no issues found in 14 source files |
| `git diff --check` | `git diff --check` | 0 | LF/CRLF warnings only |
| Offline Eval | env python `-m agent_foundations.cli.main evaluate --task-set tests/fixtures/evals/phase-1-tasks-v1.json --responses tests/fixtures/evals/phase-1-responses-v1.json --output .agent-foundations/evals/phase-2d-task-6.json --runtime-revision working-tree` | 0 | see §7 |
| Full suite | not-required | n/a | not-run; report is `targeted verification passed` |
| Frontend / pip check | not-required | n/a | not-run |
| Docker | not authorized | n/a | not-run |
| Real model / compactor | forbidden | n/a | not-run |

Windows note: `conda run` skipped (gbk pytest crash). Used `PYTHONIOENCODING=utf-8` and `D:\anaconda\envs\agent-foundations\python.exe`.

## 6. Scope Audit

- Final Task 22 files: Create list under `context/` and `tests/unit/context/test_{sources,repo_map,relevance,cache}.py`; Modify `budget.py`, `builder.py`, `loop.py`, `test_builder.py`, `test_agent_loop.py`, `context/__init__.py` (minimal export), this evidence, plan Step 1–7 checkboxes
- Unrelated changes introduced: no
- Existing user changes preserved: yes
- Secrets or generated artifacts: Offline Eval wrote `.agent-foundations/evals/phase-2d-task-6.json` (not the authoritative baseline). No `.env` values recorded.
- Commit, push, deployment, paid API, Docker, or next Task: no

## 7. Gaps and Limitations

- Checks not run: full Phase 1 suite (not-required); `conda run` wrapper; Docker; real model
- Environment warnings: Starlette/`httpx` deprecation; sqlite3 datetime adapter on command-feedback tests
- Process evidence gaps: none for Task 22 Red (saved before production modules existed)
- Remaining risks: snapshot currently marks ranked Repo Map sources as `selected` before builder budget drops; droppable-source tests cover builder dropping. Reviewer should re-run Target tests and Offline Eval independently.

### Context Budget before / after

- Defaults still `max_chars=32000`, `max_tool_result_chars=8000`. Added `max_source_chars=4000` (sources-only cap). `sources=()` preserves prior truncation/mandatory-overflow behavior.
- Offline Eval vs `docs/eval-baselines/phase-1-v1.json` (file **not** modified):
  - Baseline: dataset `phase-1-readonly` / `v1`; 5 tasks all passed; `total_input_tokens=127`
  - New report `.agent-foundations/evals/phase-2d-task-6.json`: same 5 `phase1-*` task_ids still all passed; their `input_tokens` unchanged (36/28/23/20/20). Fixture now also contains 3 `phase2a-*` tasks (not in the frozen 5-task baseline JSON); all 8 passed (`success_rate=1.0`, `total_input_tokens=297`).
- Assertion pass/fail for the five frozen baseline tasks is unchanged.

### Cache / PathPolicy matrix

- Skip: `.git`, `node_modules`, `.venv`/`venv`, `artifacts`, `.agent-foundations`, `.env`, `id_rsa`, NUL binary, symlink
- Cache key: project fingerprint + relative_path + size + mtime_ns + content sha256
- Hit still re-runs PathPolicy; `.env` poison lookup discarded; fingerprint drift and size/mtime change miss; LRU max 256 (test uses 2)

## 8. Handoff Summary

- Evidence status: user-accepted
- Current verification status: **pass** (targeted verification passed; full suite not-required). Independently reviewed; user-accepted 2026-08-26.
- TDD process evidence: **complete** (executor Red saved before production context modules); user acceptance does not independently witness historical Red→Green
- Full suite: not-required; do not report as full suite passed
- Docker: not-run / 未授权
- Real model / real compactor: not-run
- User acceptance: recorded in §9
- Reviewer acceptance: pass (current implementation) in the reviewer session that preceded this confirmation
- Reviewer P3 retained: snapshot `decision` is always `selected` before builder budget drops; text `.sql` may appear as path-only `file:` sources
- Recommended reviewer commands:

```text
$env:PYTHONIOENCODING='utf-8'
D:\anaconda\envs\agent-foundations\python.exe -m pytest tests/unit/context tests/integration/test_agent_loop.py -q
D:\anaconda\envs\agent-foundations\python.exe -m pytest tests/unit/runtime tests/unit/tools tests/integration/test_command_feedback_agent_flow.py tests/integration/test_git_read_tools.py -q
D:\anaconda\envs\agent-foundations\python.exe -m agent_foundations.cli.main evaluate --task-set tests/fixtures/evals/phase-1-tasks-v1.json --responses tests/fixtures/evals/phase-1-responses-v1.json --output .agent-foundations/evals/phase-2d-task-6-review.json --runtime-revision working-tree
```

Suggested commit (not executed): `feat: select observable repository context`

## 9. User Acceptance

- Confirmed at: 2026-08-26 22:24 +08:00.
- Exact user confirmation: `确认 Task 22 用户验收通过`.
- Result: Task 22 (`phase-2d-task-6`) is user-accepted for the current implementation; the `Task 22 accepted` dependency named by Task 23 is satisfied.
- TDD note: executor Red is internally consistent and marked complete; this confirmation accepts current behavior after independent targeted review, not a reconstructed witness of the original Red→Green sequence.
- Boundary: this confirmation records acceptance only. Task 23 has not been started and still requires its own explicit single-Task executor authorization. Real compactors remain forbidden until a separately authorized human acceptance. No commit, push, or next-Task implementation is authorized by this confirmation.
