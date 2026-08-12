# Task Evidence: structured-chat-rendering-task-7

## Identity / Scope
- Task: `structured-chat-rendering-task-7`; TDD required; status complete.
- Branch: `main`; continuous execution and focused dependency installation explicitly authorized.
- Scope: safe GFM message rendering, token-based Shiki code highlighting, exact copy, focused dependencies and tests.

## Dependency Change
- Command: `npm install react-markdown remark-gfm shiki` -> exit `0`; 114 packages added to local `node_modules`.
- Installed: `react-markdown@10.1.0`, `remark-gfm@4.0.1`, `shiki@4.4.2`.
- License checks: `npm view <package> license` returned `MIT` for all three.

## Red
- Command: `npm run test:chat -- --run tests/chat/markdown-message.test.tsx --reporter=dot`.
- Exit code: `1`; suite failed before test collection because `CodeBlock` and `MarkdownMessage` did not exist.
- Expected cause: the safe Markdown boundary and token-based code renderer had not been implemented.

## Green / Gates / Audit
- Target Green: `npm run test:chat -- --run tests/chat/markdown-message.test.tsx --reporter=dot` -> exit `0`; `4 passed`.
- `npm run typecheck:chat` -> exit `0`.
- `npm run build:chat` -> exit `0`; Vite transformed 24 modules and emitted the configured Chat assets.
- Initial `npm audit --omit=dev` was unavailable on the configured `npmmirror` endpoint (`404 [NOT_IMPLEMENTED]`); rerun against the official registry with `npm audit --omit=dev --registry=https://registry.npmjs.org` -> exit `0`, `0 vulnerabilities`.
- `git diff --check` -> exit `0` (existing line-ending warnings only).
- Dependency audit: `package.json` adds only the three approved dependencies; no chat framework added. Lockfile growth reflects their transitive graph.
- Security scan: `dangerouslySetInnerHTML` / `rehype-raw` hits in Chat source and dependency manifests: `0`; raw HTML/media are blocked, unsafe URLs lose anchors, highlighting renders React token spans, and copy uses the original string.
- Current verification status: `pass`; TDD process evidence: `complete`.
