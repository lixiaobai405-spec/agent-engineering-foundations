# Task Evidence: structured-chat-rendering-task-9

## Identity / Scope
- Task: `structured-chat-rendering-task-9`; test/documentation/gate task; status complete.
- Branch: `main`; continuous execution authorized.
- Scope: fake-provider browser acceptance, README and learning-note updates, complete independent gates, security/scope audit.
- No real model, paid API, or `.env` read is permitted or used.

## E2E Red / Applicability
- TDD process evidence: `not-applicable` for this test/documentation/gate Task, as allowed by the plan when Tasks 1-8 already implement the asserted behavior.
- Initial command: `conda run -n agent-foundations python -m pytest tests/e2e/test_chat_ui.py -q`.
- The first attempt reached pytest but `conda run` could not encode the captured Unicode output with the Windows GBK console codec. The test was rerun with `PYTHONIOENCODING=utf-8`, `PYTHONUTF8=1`, and `--no-capture-output`; this was an environment-output issue, not product Red evidence.
- The first assertion run reported `1 failed, 5 passed` because a broad Testing Library selector matched both the outer transcript `<ol>` and the intended Markdown `<ul>`. A test-harness-only selector correction scoped it to `.message-markdown ul`.
- A later focused assertion expected obsolete visible text (`Run completed`) although the accepted design exposes terminal state through the collapsed activity group. The assertion was corrected to verify that the legacy `.activity-card` and raw event name are absent.
- Neither harness failure is claimed as a valid Red because neither demonstrated missing product behavior.
- Focused integrated scenario after harness corrections: `1 passed in 18.25s`.
- Final independent E2E: `6 passed in 116.38s`.

## Documentation / Gates / Audit
- `README.md` documents safe GFM rendering, Shiki-highlighted fenced code, one collapsible tool group per run, Trace Viewer ownership of full details, historical-run compatibility, recovery, and `127.0.0.1` binding.
- `docs/learning-notes/04-chat-control-plane.md` documents JSONL as the full record, SQLite as a redacted replaceable projection, projection-failure isolation, `(session_id, tool_call_id)` idempotency, HTTP/SSE/catch-up recovery, and AST/token rendering instead of raw HTML.

### Fresh complete gates

- `conda run -n agent-foundations python -m pytest -q`: PASS, `601 passed, 1 warning in 129.37s`. The warning is the existing Starlette/httpx `TestClient` deprecation warning. These 601 tests already include the 6 Chat UI E2E tests.
- `conda run -n agent-foundations python -m ruff check .`: PASS, `All checks passed!`.
- `conda run -n agent-foundations python -m mypy src tests`: PASS, `Success: no issues found in 84 source files`.
- `conda run -n agent-foundations python -m pip check`: PASS, `No broken requirements found`. Conda emitted an existing invalid-distribution warning for `~gent-engineering-foundations`.
- `npm run test:viewer`: PASS, 12 tests.
- `npm run typecheck:viewer`: PASS.
- `npm run test:chat`: PASS, 68 tests in 6 files.
- `npm run typecheck:chat`: PASS.
- `npm run build:chat`: PASS, 656 modules transformed. Vite reports a non-blocking chunk-size warning; Shiki's lazy language/theme modules produce 311 generated asset files totaling 10,299,599 bytes.
- `conda run -n agent-foundations python -m pytest tests/e2e/test_chat_ui.py -q`: PASS, 6 tests. This focused rerun is not added to the unique test total because it is included in the full pytest run.
- Unique automated test count: 681 (`601` Python including E2E + `12` Viewer + `68` Chat).
- `npm audit --omit=dev --registry=https://registry.npmjs.org`: PASS, 0 vulnerabilities. The configured package mirror had first returned HTTP 404 `NOT_IMPLEMENTED`, so the official npm registry was used for the audit only.
- `git diff --check`: PASS. Git only reports line-ending conversion notices for existing LF working-copy files.

### Security and scope audit

- The fake sentinel literal has 0 matches across repository source/generated artifacts when `.git`, `node_modules`, and `.env*` are excluded. The E2E also checks its absence from the temporary SQLite database, JSONL Trace, Chat API JSON, DOM text, and generated frontend assets.
- Source map count under the generated Chat bundle: 0.
- `dangerouslySetInnerHTML`, `rehype-raw`, and `rehypeRaw` matches under Chat source/tests: 0.
- Markdown blocks `img`, `iframe`, `object`, `embed`, `video`, and `audio`; no network-fetching Markdown plugin was added.
- Activity projection tests prove it stores counts/status/redacted project-relative path summaries rather than raw file content, match text, raw tool arguments/results, or external absolute paths.
- No write, Shell, Git, network tool, permanent approval, memory, skill, planning, or sub-agent capability was added.
- Legacy `ActivityCard` references: 0; the file was removed only after the integrated timeline had no callers.
- Pre-existing user changes listed before Task 1 remain present and were not reset, restored, cleaned, staged, committed, or pushed.

## Current Correctness / Manual Handoff

- Current implementation: PASS against the plan's automated acceptance criteria.
- TDD evidence: Tasks 1-8 have saved Red/Green evidence in their individual evidence files; Task 9 is `not-applicable` as described above.
- User acceptance is not claimed. A separately user-run real-model smoke test remains required for visual Markdown quality, active-to-terminal group behavior, exact approval nesting/approve/deny, reload/restart experience, exact Trace navigation, narrow-screen usability, and confirmation that real credentials do not appear in any user-visible or persisted artifact.
- Proposed commit after user acceptance/review: `feat: complete structured chat rendering`.
