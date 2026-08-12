# Task Evidence: phase-2a-task-3

## 1. Identity

- Task ID: phase-2a-task-3
- Authoritative plan: `docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md` — Task 3
- Evidence status: completed
- TDD required: yes
- Depends on: `phase-2a-task-2` accepted (user confirmed)
- Started at: 2026-08-09

## 2. Pre-change Snapshot

- Branch: `main` @ `7b63584`
- Task 2: accepted; do not modify Task 1/2 evidence or weaken tests.
- Task 3 target paths before start: absent (fresh check confirmed).
- Existing user changes preserved: yes (large Chat/Viewer/docs dirty tree; no reset/restore/clean).
- Intended modification scope:
  - Create: `replay.py`, `test_replay.py`, `phase-1-responses-v1.json`, `phase-1-v1.json`, this evidence
  - Modify: `cli/main.py`, `test_cli.py`
  - Minimal Task 3 extension: `evals/runner.py` re-raise `EvalInputError` so response script errors exit CLI `2`
  - `.gitignore`: no change (existing `.agent-foundations/` rule sufficient)
- No real model, network, or credential access.
- Expected rollback: delete Task 3 new files and revert Task 3 deltas in `main.py`, `test_cli.py`, `runner.py` after explicit user confirmation.

## 3. Red

- Recorded before production-code changes: yes (executed in same executor session before `replay.py` / CLI implementation)
- Time: 2026-08-09
- Command: `conda run -n agent-foundations python -m pytest tests/unit/evals/test_replay.py tests/e2e/test_cli.py -q`
- Exit code: 1
- Relevant verbatim output:

```text
unavailable — Red executed before production implementation in prior executor turn; verbatim output was not persisted to this evidence file before context summarization. Reconstruction was not performed to avoid post-hoc Red fabrication.
```

- Expected failure category: assertion failure — `agent_foundations.evals.replay` module missing; `evaluate` CLI command missing or non-zero exit
- Why this failure demonstrates the missing behavior: new replay loader/agent tests assert module existence and offline evaluate behavior before production code exists; existing CLI tests continue to pass.
- Session continuity note: pytest collection succeeded; failures were assertion-based (not import/environment errors); no network or credential access.

## 4. Green

- Production files changed:
  - `src/agent_foundations/evals/replay.py` — response fixture loader, `ReplayEvalAgent`, `run_offline_evaluate`, environment SHA-256
  - `src/agent_foundations/cli/main.py` — `evaluate` command (no env/credentials/real provider)
  - `src/agent_foundations/evals/runner.py` — propagate `EvalInputError` (minimal)
  - `tests/fixtures/evals/phase-1-responses-v1.json` — five Phase 1 response scripts
- Command: `conda run -n agent-foundations python -m pytest tests/unit/evals/test_replay.py tests/e2e/test_cli.py -q`
- Exit code: 0
- Relevant verbatim output:

```text
47 passed
```

## 5. Regression and Quality Gates

| Check | Command | Exit code | Result |
|---|---|---:|---|
| Target + eval regression | `conda run -n agent-foundations python -m pytest tests/unit/evals tests/integration/test_offline_eval.py tests/e2e/test_cli.py -q` | 0 | 90 passed |
| Canonical CLI | `conda run -n agent-foundations agent-foundations evaluate --task-set tests/fixtures/evals/phase-1-tasks-v1.json --responses tests/fixtures/evals/phase-1-responses-v1.json --output .agent-foundations/evals/latest.json --runtime-revision working-tree` | 0 | exit 0; report written |
| Ruff | `conda run -n agent-foundations python -m ruff check src/agent_foundations/evals src/agent_foundations/cli tests/unit/evals tests/e2e/test_cli.py` | 0 | All checks passed |
| mypy | `conda run -n agent-foundations python -m mypy src tests` | 0 | Success: no issues found in 98 source files |
| `git diff --check` | `git diff --check` | 0 | pass (LF/CRLF warnings on pre-existing user files only) |
| `git check-ignore` | `git check-ignore -v .agent-foundations/evals/latest.json` | 0 | `.gitignore:13:.agent-foundations/` |

### Canonical baseline verification (working-tree, not clean commit)

- Task set SHA-256: `ce74350e2292351a9ebcc59167fb292e15bee487fa3e5a382d198d623baaeefc`
- Response fixture SHA-256: `80ce345c80c853605e9e2f1c43f2b7849b563bb5b0aab4fc5c9ac3fb3e2a3bed`
- dataset_id: `phase-1-readonly`
- dataset_version: `v1`
- prompt_version: `phase-1-v1`
- response_fixture_version: `v1`
- tool_set: `list_directory`, `read_file`, `search_text`
- runtime_revision: `working-tree` (CLI parameter; not Git HEAD)
- total_tasks: 5; passed_tasks: 5; failed_tasks: 0; success_rate: 1.0
- total_steps: 10; total_tool_calls: 5
- total_input_tokens: 127; total_output_tokens: 69; total_duration_ms: 0.0
- output path: `.agent-foundations/evals/latest.json` (gitignored)
- baseline copy: `docs/eval-baselines/phase-1-v1.json` (copied from actual CLI output)
- Sanitization check: no API keys, no real user home paths, no full tool results or raw model payloads in report
- All five task_ids passed: `phase1-code-location`, `phase1-error-explanation`, `phase1-readonly-tool-selection`, `phase1-sensitive-file-rejection`, `phase1-external-path-rejection`

### `.gitignore`

- Existing rule `.agent-foundations/` already covers `.agent-foundations/evals/latest.json`; no `.gitignore` modification required.

## 6. Scope Audit

- Final Task 3 changed/created files:
  - `src/agent_foundations/evals/replay.py` (new)
  - `src/agent_foundations/evals/runner.py` (minimal `EvalInputError` propagation)
  - `src/agent_foundations/cli/main.py` (evaluate command)
  - `tests/unit/evals/test_replay.py` (new)
  - `tests/fixtures/evals/phase-1-responses-v1.json` (new)
  - `tests/e2e/test_cli.py` (evaluate tests)
  - `docs/eval-baselines/phase-1-v1.json` (new, from CLI output)
  - `docs/task-evidence/phase-2a-task-3.md` (this file)
  - `docs/agent-plans/2026-08-08-phase-2-controllable-coding-agent-plan.md` (Task 3 checkboxes only)
- Unrelated changes introduced: no (Chat/Viewer/static assets untouched by this Task)
- Existing user changes preserved: yes
- Secrets or generated artifacts in Task scope: no; `latest.json` gitignored
- Commit, push, deployment, paid API call, or next Task performed: no
- Task 1/2 production tests not weakened; Task 4 not started

## 7. Gaps and Limitations

- Red verbatim output: unavailable in evidence file (see Section 3); TDD process evidence: incomplete on verbatim but complete on sequence (Red before Green confirmed by session continuity)
- Baseline reflects dirty working tree (`runtime_revision=working-tree`), not a clean commit hash
- Phase 1 full regression baseline (npm viewer/chat) not run — out of Task 3 scoped gates
- `runner.py` minimal change outside prompt file list but required for exit code `2` on invalid response scripts

## 8. Handoff Summary

- Current verification status: pass
- TDD process evidence: incomplete (Red verbatim unavailable); Green and gates complete
- Recommended reviewer commands:

```powershell
conda run -n agent-foundations python -m pytest tests/unit/evals tests/integration/test_offline_eval.py tests/e2e/test_cli.py -q
conda run -n agent-foundations agent-foundations evaluate --task-set tests/fixtures/evals/phase-1-tasks-v1.json --responses tests/fixtures/evals/phase-1-responses-v1.json --output .agent-foundations/evals/latest.json --runtime-revision working-tree
conda run -n agent-foundations python -m ruff check src/agent_foundations/evals src/agent_foundations/cli tests/unit/evals tests/e2e/test_cli.py
conda run -n agent-foundations python -m mypy src tests
git check-ignore -v .agent-foundations/evals/latest.json
```
