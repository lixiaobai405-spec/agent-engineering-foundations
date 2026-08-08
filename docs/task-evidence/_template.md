# Task Evidence Template

由 `executor` 在当前 Task 执行过程中维护。默认复制为 `docs/task-evidence/<task-id>.md`；不要直接覆盖本模板。

不得事后重构未保存的 Red。生产代码修改前没有保存真实失败输出时，填写 `unavailable` 并说明原因。

````markdown
# Task Evidence: <task-id>

## 1. Identity

- Task ID:
- Authoritative plan or task spec:
- Evidence status: in-progress / completed / blocked
- TDD required: yes / no
- Started at:

## 2. Pre-change Snapshot

- Branch or revision:
- `git status --short`:
- Existing user changes that must be preserved:
- Intended modification scope:
- Expected rollback:

## 3. Red

- Recorded before production-code changes: yes / no / unavailable
- Time:
- Test file and test name:
- Command:
- Exit code:
- Relevant verbatim output:

```text
<failure output, or unavailable>
```

- Expected failure category:
- Why this failure demonstrates the missing behavior:
- If unavailable, why it cannot be verified:

## 4. Green

- Production files changed:
- Command:
- Exit code:
- Relevant verbatim output:

```text
<passing output>
```

## 5. Regression and Quality Gates

| Check | Command | Exit code | Result |
|---|---|---:|---|
| Target tests | | | |
| Regression tests | | | |
| Ruff | | | |
| mypy | | | |
| Frontend test, typecheck or build | | | |
| Package or dependency check | | | |
| `git diff --check` | | | |

## 6. Scope Audit

- Final changed files:
- Unrelated changes introduced: yes / no
- Existing user changes preserved: yes / no
- Secrets or generated artifacts detected: yes / no
- Commit, push, deployment, paid API call, or next Task performed:

## 7. Gaps and Limitations

- Checks not run and reasons:
- Environment warnings:
- Process evidence gaps:
- Remaining risks:

## 8. Handoff Summary

- Current verification status: pass / partial / fail
- TDD process evidence: complete / incomplete / not-applicable
- Recommended reviewer commands:
````

最低要求：

- 命令运行后立即记录，包括非零退出码和未经改写的关键输出。
- 实现完成后制造的失败不是原始 TDD Red。
- 不推断或编造缺失的命令、时间、退出码或输出。
- 不记录真实 `.env` 值、密钥、Token、Cookie、密码、私钥或敏感载荷。
- reviewer 必须独立检查当前实现并重跑当前验证；evidence 不能证明 reviewer 没有亲历的历史顺序。
