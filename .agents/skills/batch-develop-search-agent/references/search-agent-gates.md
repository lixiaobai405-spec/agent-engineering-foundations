# search_agent gates

Project documents, not this reference, are authoritative. Before work read the project root `AGENTS.md`, the current authority plan, the relevant Task evidence/template, and prior accepted evidence needed for dependencies. Do not copy or relax their Phase, safety, dirty-worktree, sensitive-information, or learning rules.

For every implementation Task, Planner must state exact `Target tests`, `Affected regression tests`, `Full suite` (`required` or `not-required`), `Full suite reason`, and `Additional gates`. Executor records the original RED before production edits when TDD applies; a later fresh failure never substitutes for missing historical RED.

Use the project Conda environment and the Task's exact commands. Typical gates are:

```powershell
conda run -n agent-foundations python -m pytest <target>
conda run -n agent-foundations python -m ruff check <affected-files-or-directories>
conda run -n agent-foundations python -m mypy <affected-modules>
git diff --check
```

Use frontend commands only when the current Task's contract requires them. Preserve existing user changes, create/update only the Task's existing `docs/task-evidence/<task-id>.md` evidence as authorized by the Task, and treat any unexpected overlap as `scope-conflict`. Use `git status --short --untracked-files=all` for exact untracked paths and task-local allowed-scope SHA-256 snapshots to distinguish each Task's writes from prior accepted batch changes.

The batch invocation does not authorize dependency installation, real API/model calls, deletion, important overwrite, data migration, system changes, commit, push, PR, deployment, or publication. Stop for separate user direction when any appears.
