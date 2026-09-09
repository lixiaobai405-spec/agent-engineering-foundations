# Task Evidence: phase-2d-task-26

## 1. Identity

- Task ID: `phase-2d-task-26`
- Authoritative plan or task spec: `docs/agent-plans/2026-09-08-phase-2-pre-3x3-gap-remediation-plan.md` Task 42 plus the user-confirmed executor prompt
- Evidence status: user-accepted / current implementation pass; TDD process evidence complete
- TDD required: yes
- Started at: 2026-09-08 (Asia/Shanghai)

## 2. Pre-change Snapshot

- Branch or revision: `codex/phase-2-next` at `14ece4e` (not `main`)
- `git status --short` (this Task files before build): `M src/agent_foundations/viewer/static/chat/index.html`, `?? src/agent_foundations/viewer/static/chat/assets/index-k5D9Loaj.js`, `?? docs/agent-plans/2026-09-08-phase-2-pre-3x3-gap-remediation-plan.md`. Broader dirty tree (Phase 2A–2D, Task 30–41, `.gate-backup`) already present and must be preserved.
- Existing user changes that must be preserved: all pre-existing modified and untracked files at Task start. Do not `restore`/`reset`/`clean`. Do not touch `.gate-backup`.
- Intended modification scope: `npm run build:chat` only for `src/agent_foundations/viewer/static/chat/**`; new probe test + this evidence. Do not change `web/chat/**`, `vite.config.ts`, Policy, gate_id, pages/raw, Python API.
- Expected rollback: restore only this Task’s starting `static/chat` tree and delete this Task’s new test/evidence. Do not revert the rest of the dirty tree.
- Interpreter: Windows. Pytest uses `D:\anaconda\envs\agent-foundations\python.exe` with `$env:PYTHONIOENCODING='utf-8'`. Do not use bare `conda run` as the primary path.
- **index.html script src before build (must record):** `/chat-static/assets/index-k5D9Loaj.js`
- Stylesheet href before build: `/chat-static/assets/index-DnJ-tWSu.css`

## 3. Red

- Recorded before production-code changes: yes (before `npm run build:chat`)
- Time: 2026-09-08 (Asia/Shanghai)
- Test file and test name: `tests/unit/viewer/test_chat_static_bundle.py::test_served_chat_bundle_includes_accepted_command_ui`
- Command: `$env:PYTHONIOENCODING='utf-8'; D:\anaconda\envs\agent-foundations\python.exe -m pytest tests/unit/viewer/test_chat_static_bundle.py -q --tb=short`
- Exit code: 1
- Relevant verbatim output:

```text
E   AssertionError: assert ['Controlled ...r', 'tablist'] == []
E     
E     Left contains 5 more items, first extra item: 'Controlled command approval'
FAILED tests/unit/viewer/test_chat_static_bundle.py::test_served_chat_bundle_includes_accepted_command_ui
1 failed in 0.80s
```

Missing markers in the JS currently referenced by index.html (`index-k5D9Loaj.js`): `Controlled command approval`, `sandbox_command`, `No stdout`, `No stderr`, `tablist`. Probe resolved the script via `CHAT_BUILD_DIR/index.html`, not a hardcoded filename.

- Expected failure category: assertion failure from stale served bundle missing Task 37/38 UI strings
- Why this failure demonstrates the missing behavior: the served hashed JS does not contain the already-accepted command approval title, empty-state copy, or tablist. Not a syntax/import error.
- If unavailable, why it cannot be verified: n/a

## 4. Green

- Production files changed: `src/agent_foundations/viewer/static/chat/**` via `npm run build:chat` only (Vite `emptyOutDir: true`). Entry script became `/chat-static/assets/index-HPZQEFX1.js`. No hand edits of hashed assets. `web/chat/**` and `vite.config.ts` unchanged.
- Command: `$env:PYTHONIOENCODING='utf-8'; D:\anaconda\envs\agent-foundations\python.exe -m pytest tests/unit/viewer/test_chat_static_bundle.py -q`
- Exit code: 0
- Relevant verbatim output:

```text
.                                                                        [100%]
1 passed in 0.46s
```

New script src: `/chat-static/assets/index-HPZQEFX1.js` (not `index-k5D9Loaj.js`). Marker snippets from that JS (not the whole bundle):

```text
e.resource_kind===`sandbox_command`?`Controlled command approval`:
u===`stdout`?`No stdout`:`No stderr`
role:`tablist`,"aria-label":`Comm
```

## 5. Regression and Quality Gates

| Check | Command | Exit code | Result |
|---|---|---:|---|
| Target tests (Red, before build) | `$env:PYTHONIOENCODING='utf-8'; D:\anaconda\envs\agent-foundations\python.exe -m pytest tests/unit/viewer/test_chat_static_bundle.py -q --tb=short` | 1 | 1 failed (5 markers missing) |
| Target tests (Green, after build) | `$env:PYTHONIOENCODING='utf-8'; D:\anaconda\envs\agent-foundations\python.exe -m pytest tests/unit/viewer/test_chat_static_bundle.py -q` | 0 | 1 passed |
| Regression tests | `$env:PYTHONIOENCODING='utf-8'; D:\anaconda\envs\agent-foundations\python.exe -m pytest tests/unit/viewer/test_chat_static_bundle.py tests/unit/viewer/test_stream.py tests/integration/test_chat_api.py::test_chat_enabled_routes_with_present_build_200 -q` | 0 | 20 passed, 1 warning |
| Ruff | not in contract | | not-run |
| mypy | not in contract | | not-run |
| Frontend typecheck | `npm run typecheck:chat` | 0 | `tsc --project tsconfig.chat.json --noEmit` |
| Chat build | `npm run build:chat` | 0 | Vite built in 480ms; 660 modules; chunk-size warning only |
| Package or dependency check | not in contract | | not-run |
| `git diff --check` | `git diff --check` | 0 | pass (CRLF working-copy warnings only; no whitespace errors) |

Targeted verification passed. Full suite not-required and not run.

## 6. Scope Audit

- Final changed files (this Task):
  - Create: `tests/unit/viewer/test_chat_static_bundle.py`
  - Create: `docs/task-evidence/phase-2d-task-26.md`
  - Modify: `docs/agent-plans/2026-09-08-phase-2-pre-3x3-gap-remediation-plan.md` (status only; Task 42 contract body not rewritten)
  - Rebuild: `src/agent_foundations/viewer/static/chat/index.html` + `assets/*` via `npm run build:chat` only
- Unrelated changes introduced: no. Pre-existing dirty tree from Tasks 30–41 preserved. `.gate-backup` untouched. `web/chat/**`, `vite.config.ts`, Policy, gate_id, pages/raw, Python API untouched.
- Existing user changes preserved: yes
- Secrets or generated artifacts detected: hashed Chat assets from `build:chat` only; no `.env` or credentials
- Commit, push, deployment, paid API call, or next Task performed: no

## 7. Gaps and Limitations

- Checks not run and reasons: full suite, Docker, Playwright, `npm run test:chat`, paid API / 3×3 — not in contract / not authorized.
- Environment warnings: Vite chunk-size warning (>500 kB Shiki/wasm chunks); Starlette/`httpx` TestClient deprecation on affected pytest; `git diff --check` CRLF warnings on pre-existing files.
- Process evidence gaps: none for this Task’s Red→Green. Probe failed on missing markers before build; same probe passed after official `npm run build:chat`.
- Remaining risks: hashed filenames will change on the next `build:chat`. Probe follows `index.html` and must not be rewritten to pin `index-HPZQEFX1.js`. Reviewer should re-run the verification contract.

## 8. Handoff Summary

- Current verification status: **pass** (targeted verification; not full suite). Reviewer-fresh: Target 1 passed; Affected 20 passed; `npm run typecheck:chat` exit 0; `git diff --check` exit 0. Reviewer did not re-run `npm run build:chat` (would rewrite hashed assets).
- TDD process evidence: **complete**. Reviewer fresh checks prove current green, not the historical Red→Green sequence
- User acceptance: recorded in §9
- Reviewer acceptance: pass (current implementation, targeted) in the reviewer session that preceded this confirmation
- Reviewer findings retained: P3 parent-plan appendix still said Task 42 was unauthorized until this confirmation; string probe is not a real browser; next `build:chat` will change the hash and the probe must keep following `index.html`
- Recommended reviewer commands (already run for this Task):

```text
$env:PYTHONIOENCODING='utf-8'
D:\anaconda\envs\agent-foundations\python.exe -m pytest tests/unit/viewer/test_chat_static_bundle.py -q
D:\anaconda\envs\agent-foundations\python.exe -m pytest tests/unit/viewer/test_chat_static_bundle.py tests/unit/viewer/test_stream.py tests/integration/test_chat_api.py::test_chat_enabled_routes_with_present_build_200 -q
npm run typecheck:chat
git diff --check
```

## 9. User Acceptance

- Confirmed at: 2026-09-08 +08:00.
- Exact user confirmation: `确认「Task 42 / phase-2d-task-26 用户验收通过」`.
- Result: Pre-3×3 gap Task 42 / `phase-2d-task-26` (serve the already-accepted Chat UI via official `npm run build:chat`) is user-accepted for the current implementation. Independent reviewer re-ran the targeted contract (Target 1 passed; Affected 20 passed; `npm run typecheck:chat` / `git diff --check` exit 0). Served entry is `/chat-static/assets/index-HPZQEFX1.js`; `index-k5D9Loaj.js` is no longer referenced.
- Full suite note: this confirmation accepts **targeted verification passed**. It does not claim `full suite passed`, does not accept plan-body Task 25 as complete, does not accept paid 3×3, and does not mark user Phase 2 complete. Plan Task 25 Step 10 and Step 11 remain unchecked.
- TDD note: executor Red is internally consistent and marked complete; this confirmation does not independently witness the original Red→Green sequence.
- Boundary: this confirmation records `phase-2d-task-26` acceptance only. It is not the product-hardening plan (that plan has no Task 42). Task 43 / `phase-2d-task-27` still requires a separate explicit authorization. Paid 3×3 still requires a separate explicit authorization and remains Task 25 Step 10. No commit, push, paid API rerun, Phase 2 complete checkbox, or Phase 3 is authorized by this confirmation. Reviewer P3 findings are retained and do not require immediate rework from this confirmation.
