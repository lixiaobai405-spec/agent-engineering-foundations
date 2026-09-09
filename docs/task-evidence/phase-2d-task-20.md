# Task Evidence: phase-2d-task-20

## 1. Identity

- Task ID: `phase-2d-task-20`
- Authoritative plan or task spec: `docs/agent-plans/2026-09-04-phase-2-product-hardening-plan.md` Task 36 plus the user-confirmed executor prompt
- Evidence status: user-accepted 2026-09-04 (targeted verification); Task 25 Step 10/11 **not claimed**; Phase 2 complete **not claimed**
- TDD required: yes
- Started at: 2026-09-04 (Asia/Shanghai)

## 2. Pre-change Snapshot

- Branch or revision: `codex/phase-2-next` at `14ece4e` (not `main`)
- `git status --short`: dirty working tree already present (Phase 2A–2D, Chat hashed assets, Dockerfiles, evidence, Task 30–35 files). Exact listing is long.
- Existing user changes that must be preserved: all pre-existing modified and untracked files at Task start. Do not `restore`/`reset`/`clean`.
- Intended modification scope: Git version probe + L0/L1 fallback in `GitReadService`; unit tests; Docker status/diff/log on existing `agent-foundations-sandbox:phase2`. Do not change Policy, gate_id, Chat, Artifact paths, `max_steps`, Dockerfiles, Task 35 P3, Tasks 37–41.
- Expected rollback: revert only this Task’s files; do not revert the pre-existing dirty tree.
- Interpreter: Windows `conda run` can crash pytest with GBK. Commands use `$env:PYTHONIOENCODING='utf-8'`. This does not shrink the verification contract.

## 3. Red

- Recorded before production-code changes: yes
- Time: 2026-09-04 (Asia/Shanghai), after `tests/unit/tools/git/test_probe.py` and updated `test_unknown_option_and_timeout_are_not_missing_repository`, before `probe.py` / `GitReadService` probe cache / L0→L1
- Test file and test name:
  - `tests/unit/tools/git/test_probe.py` (parse, L0→L1 once, not-a-repo no L1, probe once, old git skips L0, unparseable still L0, version fail/timeout skip ops)
  - `tests/unit/tools/git/test_service.py::test_unknown_option_and_timeout_are_not_missing_repository`
- Command: `$env:PYTHONIOENCODING='utf-8'; conda run -n agent-foundations python -m pytest tests/unit/tools/git -q --tb=short`
- Exit code: 1
- Relevant verbatim output:

```text
ERROR conda.cli.main_run:execute(142): `conda run python -m pytest tests/unit/tools/git -q --tb=short` failed. (See above for error)
..FFFFFFF....F...                                                        [100%]
================================== FAILURES ===================================
____________________ test_parse_git_version_locked_shapes _____________________
tests\unit\tools\git\test_probe.py:73: in test_parse_git_version_locked_shapes
    module = _probe_module()
tests\unit\tools\git\test_probe.py:23: in _probe_module
    assert spec is not None
E   assert None is not None
_____________________ test_l0_usage_falls_back_to_l1_once _____________________
E   agent_foundations.tools.git.service.GitReadError: unknown option `no-optional-locks'
___________________ test_not_a_repository_does_not_send_l1 ____________________
E   AssertionError: assert [('git', '--n...', '-z', ...)] == [('git', '--v...', '-z', ...)]
E     At index 0 diff: ('git', '--no-pager', '--no-optional-locks', 'status', ...) != ('git', '--version')
________________ test_git_version_is_probed_once_per_instance _________________
E   assert 0 == 1
______________________ test_old_git_skips_l0_and_uses_l1 ______________________
E   AssertionError: L0 must be skipped for old git: ('git', '--no-pager', '--no-optional-locks', 'status', ...)
___________________ test_unparseable_version_still_tries_l0 ___________________
E   AssertionError: assert [('git', '--n...', '-z', ...)] == [('git', '--v...', '-z', ...)]
________________ test_version_nonzero_or_timeout_skips_git_ops ________________
E   AssertionError: ops must not run: ('git', '--no-pager', '--no-optional-locks', 'status', ...)
_________ test_unknown_option_and_timeout_are_not_missing_repository __________
E   AssertionError: assert [('git', '--n...xtconv', ...)] == [('git', '--v...'--no-color')]
E     At index 0 diff: ('git', '--no-pager', '--no-optional-locks', 'diff', ...) != ('git', '--version')
8 failed, 9 passed in 0.65s
```

- Expected failure category: missing `agent_foundations.tools.git.probe`; `GitReadService` still ran L0 only (no `--version`, no L1). Tests collected and ran (not syntax/import collection errors).
- Why this failure demonstrates the missing behavior: no version probe, no L0→L1 usage fallback, old git still sent `--no-optional-locks`, version failure still ran status.
- If unavailable, why it cannot be verified:

## 4. Green

- Production files changed:
  - `src/agent_foundations/tools/git/probe.py` (new: `VERSION_ARGV`, `parse_git_version`, L1 builders, `should_use_legacy_argv`)
  - `src/agent_foundations/tools/git/service.py` (per-instance probe cache; `_run_with_fallback`; probe uses exit 0 only)
- Command: `$env:PYTHONIOENCODING='utf-8'; conda run -n agent-foundations python -m pytest tests/unit/tools/git -q --tb=short`
- Exit code: 0
- Relevant verbatim output:

```text
.................                                                        [100%]
17 passed in 0.35s
```

After the first Green attempt, `test_version_nonzero_or_timeout_skips_git_ops` hit `FileExistsError` because `_service_with` called `project.mkdir()` twice on the same `tmp_path / "repo"`. Production probe/fallback already behaved; the test helper was changed to `mkdir(exist_ok=True)`. Re-run is the 17 passed output above.

## 5. Regression and Quality Gates

| Check | Command | Exit code | Result |
|---|---|---:|---|
| Target tests | `$env:PYTHONIOENCODING='utf-8'; conda run -n agent-foundations python -m pytest tests/unit/tools/git -q` | 0 | 17 passed (**targeted verification**, not full suite) |
| Regression tests | `$env:PYTHONIOENCODING='utf-8'; conda run -n agent-foundations python -m pytest tests/unit/tools/git tests/integration/test_git_read_tools.py -q` | 0 | 20 passed, 1 skipped (`-m` was not `docker`; existing skip kept) |
| Docker additional | `$env:PYTHONIOENCODING='utf-8'; conda run -n agent-foundations python -m pytest tests/integration/test_git_read_tools.py -m docker -q` | 0 | 1 passed, 3 deselected. Local image `agent-foundations-sandbox:phase2` (`sha256:250e993fbf4c…`) already present; no pull/build. After the test, `docker ps -a --filter name=af-` listed no leftover containers. |
| Ruff | `$env:PYTHONIOENCODING='utf-8'; conda run -n agent-foundations python -m ruff check src/agent_foundations/tools/git tests/unit/tools/git tests/integration/test_git_read_tools.py` | 0 | All checks passed |
| mypy | `$env:PYTHONIOENCODING='utf-8'; conda run -n agent-foundations python -m mypy src/agent_foundations/tools/git tests/unit/tools/git` | 0 | Success: no issues found in 12 source files |
| Frontend test, typecheck or build | not in contract | | not-run |
| Package or dependency check | not in contract | | not-run |
| `git diff --check` | `git diff --check` | 0 | no whitespace errors (LF/CRLF working-copy warnings only) |

## 6. Scope Audit

- Final changed files (this Task):
  - `src/agent_foundations/tools/git/probe.py` (new)
  - `src/agent_foundations/tools/git/service.py` (probe + fallback)
  - `tests/unit/tools/git/test_probe.py` (new)
  - `tests/unit/tools/git/test_service.py` (usage/timeout argv sequence; `--version` in FakeBackend factories; request indices)
  - `tests/unit/tools/git/test_tools.py` (schema property sets)
  - `tests/integration/test_git_read_tools.py` (Docker status + diff + log)
  - `docs/task-evidence/phase-2d-task-20.md`
  - `docs/agent-plans/2026-09-04-phase-2-product-hardening-plan.md` (status / 现状对照 / executor note only; Task 36 contract text unchanged)
- Unrelated changes introduced: no
- Existing user changes preserved: yes
- Secrets or generated artifacts detected: no
- Commit, push, deployment, paid API call, or next Task performed: no
- Not done: Task 35 reviewer P3; Policy matrix; gate_id; Chat; Artifact paths; `max_steps`; Dockerfiles; docker pull/build/prune; Task 37–41; Task 25 Step 10/11

## 7. Gaps and Limitations

- Checks not run and reasons: Phase 1 full baseline not-required by contract. Frontend / pip check not in contract.
- Environment warnings: Windows conda pytest uses `PYTHONIOENCODING=utf-8`. `git diff --check` prints LF/CRLF working-copy warnings on the pre-existing dirty tree.
- Process evidence gaps: none for Red→Green of probe/fallback. The `mkdir(exist_ok=True)` helper fix happened after the first Green run of the new tests (16 passed, 1 `FileExistsError`).
- Remaining risks: L1 isolation is weaker than L0 by design (no `--no-optional-locks` / `--no-ext-diff`). Probe errors are cached per instance so a failed `--version` is not retried. Docker gate used the already-local `agent-foundations-sandbox:phase2` image only.

## 8. Handoff Summary

- Current verification status: **pass** (targeted verification; not full suite). Reviewer-fresh: Target 17 passed; Affected 20 passed / 1 skipped; Docker Additional 1 passed / 3 deselected; ruff/mypy 12 files passed; `git diff --check` exit 0. Local image `agent-foundations-sandbox:phase2` (`sha256:250e993fbf4c…`); no pull/build; no leftover `af-*` containers
- TDD process evidence: **complete**. Reviewer fresh checks prove current green, not the historical Red→Green sequence
- User acceptance: recorded in §9
- Reviewer acceptance: pass (current implementation, targeted) in the reviewer session that preceded this confirmation
- Reviewer findings retained: P3 L1 isolation is weaker than L0 by design; probe failures are cached per `GitReadService` instance
- Recommended reviewer commands (already run for this Task):

```text
$env:PYTHONIOENCODING='utf-8'
conda run -n agent-foundations python -m pytest tests/unit/tools/git -q
conda run -n agent-foundations python -m pytest tests/unit/tools/git tests/integration/test_git_read_tools.py -q
conda run -n agent-foundations python -m pytest tests/integration/test_git_read_tools.py -m docker -q
conda run -n agent-foundations python -m ruff check src/agent_foundations/tools/git tests/unit/tools/git tests/integration/test_git_read_tools.py
conda run -n agent-foundations python -m mypy src/agent_foundations/tools/git tests/unit/tools/git
git diff --check
```

## 9. User Acceptance

- Confirmed at: 2026-09-04 +08:00.
- Exact user confirmation: `确认「Task 36 / phase-2d-task-20 用户验收通过」`.
- Result: Product-hardening Task 36 / `phase-2d-task-20` (Git probe and predefined fallback) is user-accepted for the current implementation. This is **not** plan body Task 20. Independent reviewer re-ran the targeted contract (17 passed on Target; 20 passed / 1 skipped on affected regression; Docker Additional 1 passed / 3 deselected).
- Full suite note: this confirmation accepts **targeted verification passed**. It does not claim `full suite passed`, does not accept Task 25 as complete, does not accept paid 3×3, and does not mark user Phase 2 complete. Plan Task 25 Step 10 and Step 11 remain unchecked.
- TDD note: executor Red is internally consistent and marked complete; this confirmation does not independently witness the original Red→Green sequence.
- Boundary: this confirmation records `phase-2d-task-20` acceptance only. Task 37 / `phase-2d-task-21` still requires its own explicit single-Task executor authorization. No commit, push, paid API rerun, Phase 2 complete checkbox, or Phase 3 is authorized by this confirmation. Reviewer P3 findings are retained and do not require immediate rework from this confirmation.

