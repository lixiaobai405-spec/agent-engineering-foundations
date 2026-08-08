# Task Evidence: phase-1d-trace-navigation-scroll

## Metadata

- Task ID: `phase-1d-trace-navigation-scroll`
- Plan source: `docs/superpowers/plans/2026-08-08-trace-navigation-scroll.md`
- Design source: `docs/superpowers/specs/2026-08-08-trace-navigation-scroll-design.md`
- Role / executor: Codex side-conversation executor
- Started at: `2026-08-08`
- Evidence status: `complete`

## Scope

- Goal: make expanded Trace navigation groups scroll inside `#trace-navigation` while preserving native click-to-toggle behavior.
- Allowed files: Viewer CSS, focused Trace Viewer E2E, this evidence, and the implementation plan.
- Explicitly out of scope: new collapse controls, TypeScript interaction changes, backend/API/SQLite/JSONL changes, real model calls, commit, and push.
- TDD required: yes.

## Pre-change State

- Existing user changes: the worktree contains extensive pre-existing modified and untracked Phase 1 files. No reset, restore, clean, commit, or broad staging will be performed.
- Reproduction: at a 1405x1136 viewport, `#trace-navigation` had `clientHeight=520`, `scrollHeight=520`, and wheel scrolling left `scrollTop=0`; its expanded `.navigation-group` had `clientHeight=466` and `scrollHeight=823` with `overflowY=hidden`.

## Red Evidence

### Command

`conda run -n agent-foundations python -m pytest tests/e2e/test_trace_viewer.py -q`

### Exit Code

`1`

### Key Output

```text
assert dimensions["scrollHeight"] > dimensions["clientHeight"]
E assert 345 > 345
1 failed in 2.01s
```

### Why This Failure Is Expected

The expanded 12-run group was clipped to the navigation height, so the parent had no scrollable overflow. The failure is the target missing behavior, not an import, environment, or timing failure.

## Green Evidence

### Command

`conda run -n agent-foundations python -m pytest tests/e2e/test_trace_viewer.py -q`

### Exit Code

`0`

### Key Output

```text
.                                                                        [100%]
1 passed in 1.87s
```

### Live Data Verification

At `http://127.0.0.1:8765/trace` with the real 10-turn Conversation:

```text
before: clientHeight=520, scrollHeight=877, scrollTop=0, overflowY=auto
after wheel: scrollTop=357
native summary toggle closed: true
```

## Regression And Quality Gates

| Check | Command | Result | Exit Code |
|---|---|---|---:|
| Viewer tests/build | `npm run test:viewer` | 12 passed | 0 |
| Viewer typecheck | `npm run typecheck:viewer` | passed | 0 |
| Viewer API + E2E | `conda run -n agent-foundations python -m pytest tests/integration/test_viewer_api.py tests/e2e/test_trace_viewer.py -q` | 8 passed, 1 existing warning | 0 |
| Ruff | `conda run -n agent-foundations python -m ruff check tests/e2e/test_trace_viewer.py` | all checks passed | 0 |
| mypy | `conda run -n agent-foundations python -m mypy src tests` | no issues in 84 source files | 0 |
| diff check | `git diff --check` | passed; existing line-ending warnings only | 0 |

## Scope Audit

- Production change: `src/agent_foundations/viewer/static/styles.css` only.
- Test change: `tests/e2e/test_trace_viewer.py` only.
- Supporting records: design, implementation plan, and this evidence.
- No HTML, TypeScript, backend, API, SQLite, JSONL, credential, environment, or dependency changes.
- No real model or paid API call was made.

## Deviations And Limitations

- The design document was not committed because project rules require explicit commit authorization.
- A targeted `mypy tests/e2e/test_trace_viewer.py` diagnostic was not a valid project gate because it treated the local package as an untyped installed dependency. The required project command `mypy src tests` was rerun and passed.
- User visual acceptance after browser refresh remains pending.

## Reviewer Handoff

- Reviewer result: `not-reviewed`
- Recommended check: open the 10-turn Conversation, scroll inside `Trace sessions`, then click its heading to close and reopen it.
