# Batch contract

## Authorization

The batch must receive `project_root`, `required_branch`, `start_task_id`, and a positive integer `authorized_task_count`. This first version accepts only `D:\codex-pj\search_agent` as `project_root`. A batch authorization exists only when the user's **current Prompt** (1) explicitly invokes `$batch-develop-search-agent`, (2) explicitly states `authorize` / `授权` for this invocation to execute the consecutive Task set, and (3) supplies all four valid fields above.

A bare YAML block, missing or invalid field, prior chat, an adjacent Task, Skill loading, or the static default prompt is not authorization. Reject such intake with `state: rejected` and `failure_class: invalid-input`, return the intake-rejected report, and do not create core Agents, plan, dispatch, or edit. Under the project's instruction priority, the qualifying current user instruction creates a bounded exception to the normal single-Task stopping rule only for the computed Task set on `required_branch`; it does not modify project rules or relax any other constraint.

Read the project's authority plan and calculate exactly `authorized_task_count` consecutive existing Tasks starting at `start_task_id`; count the start Task as one. A missing start Task or fewer remaining Tasks than requested is `invalid-task-range` and enters `blocked` before dispatch. An unresolved dependency or skipped prerequisite is `dependency-missing`; uncertain order is `plan-ambiguity`. Do not invent, reorder, skip, or append Tasks.

If the computed set crosses an intermediate Phase gate, the same invocation may continue only after the gate Task completes every required gate and its fresh Reviewer reports no blocking finding. The qualifying batch authorization supplies the user authorization to continue within the already-computed set; it does not pre-declare the gate successful. A failed or incomplete gate is `safety-gate` and blocks the batch.

## State machine

```text
intake -> rejected
intake -> batch-plan -> batch-preflight
-> task-execution -> task-review -> task-remediation
-> next-task | completed | blocked
```

`rejected` is terminal before a batch exists. For an authorized batch, `completed` and `blocked` are the only terminal states.

Only Root changes batch state. Keep the ledger only in the current conversation:

```yaml
batch_id: generated
project_root: D:\codex-pj\search_agent
required_branch: <required-existing-branch>
initial_head: ""
start_task_id: <required-existing-task-id>
authorized_task_count: <required-positive-integer>
authorized_tasks: []
current_task: null
completed_tasks: []
state: intake
stop_reason: null
initial_user_git_snapshot: ""
initial_user_dirty_files: []
initial_user_dirty_hashes: {}
authorized_task_allowed_files: {}
accepted_batch_changed_files: []
task_start_scope_hashes: {}
task_end_scope_hashes: {}
```

## Batch preflight

After Planner computes the complete authorized Task set and before Root accepts or dispatches any Task, Root verifies that the current branch exactly equals `required_branch`, records `git rev-parse HEAD` in `initial_head`, and records `git status --short --untracked-files=all` in `initial_user_git_snapshot`. Record every exact path as `initial_user_dirty_files`, hash each existing dirty file with SHA-256 in `initial_user_dirty_hashes`, and record each computed authorized Task's `allowed_files` separately in `authorized_task_allowed_files`.

Compare `initial_user_dirty_files` with every authorized Task's `allowed_files`, including declared directory or glob scope. Any real overlap is `scope-conflict`: Root enters `blocked`, returns the blocked report, and does not dispatch any Task or permit edits. This initial user dirty baseline is immutable for the invocation.

Before and after each Task, record SHA-256 for every existing file in that Task's allowed scope, using explicit `missing`, `created`, or `deleted` markers where applicable. Use these task-local scope hashes to distinguish the current Task's writes from prior accepted batch writes. A branch or `HEAD` change that the batch did not explicitly authorize is `scope-conflict`.

## Per-Task loop

1. Planner returns the current Task spec and exact verification contract.
2. Before every Task dispatch, Root compares immutable `initial_user_dirty_files` with that Task's `allowed_files`, including declared directory or glob scope. Any real overlap is `scope-conflict` and immediately enters `blocked`.
3. `accepted_batch_changed_files` contains only files changed by previously accepted batch Tasks; it is distinct from `initial_user_dirty_files` and must not be treated as a user dirty-worktree conflict. Root still checks its ownership and the current Task's scope before dispatch.
4. Executor rechecks the exact branch, `git status --short --untracked-files=all`, allowed files, dependencies, evidence path, and task-start scope hashes before edits.
5. Executor records valid original RED evidence before production edits when TDD applies, implements minimum GREEN behavior, runs its specified gates, and returns evidence.
6. Root checks completion, dependency order, file ownership, scope, and evidence without editing code.
7. Root creates a fresh Reviewer for the Task and sends a review packet.
8. Reviewer runs fresh minimum-sufficient checks and reports `current_implementation`, `tdd_process_evidence`, `original_red_evidence`, findings, and `blocking`.
9. On no blocking finding, record the Task completed, append its accepted changes to `accepted_batch_changed_files`, and enter `next-task` or `completed`. At an intermediate Phase gate, continue to `next-task` only when every required gate passed and the fresh Reviewer reported no blocking finding.
10. In `next-task`, Root immediately selects the next entry already present in `authorized_tasks` and repeats this loop without requesting another user message. Ordinary progress reporting, one Task completing, context length, or crossing a passed Phase gate is not a stop condition. Enter `completed` only when `completed_tasks` exactly equals `authorized_tasks` in order.

## Remediation and terminal failures

For a blocking review finding, send only the confirmed finding to the same Executor. It fixes only that Task, refreshes the relevant checks, and sends the result to the same Task Reviewer. Allow at most two remediation rounds. After the second blocking re-verification, enter `blocked`; do not start another Task.

Enter `blocked` immediately for these failure classes:

```text
acceptance-failure | regression | branch-mismatch | scope-conflict | invalid-task-range | dependency-missing |
agent-capacity | safety-gate | environment | plan-ambiguity |
file-ownership-conflict | unapproved-risky-action
```

Use these mappings: a syntactically valid authorization whose start Task does not exist or whose count exceeds the remaining consecutive Tasks -> `invalid-task-range`; current branch differs from `required_branch` -> `branch-mismatch`; unresolved dependency or skipped prerequisite -> `dependency-missing`; ambiguous or uncertain Task plan/order -> `plan-ambiguity`; overlap with immutable initial user dirty baseline -> `scope-conflict`; conflicting batch writer ownership -> `file-ownership-conflict`; loss of a required core role after one safe retry -> `agent-capacity`; failed required safety control or incomplete Phase gate -> `safety-gate`; unavailable or failed validation environment -> `environment`; action requiring separate confirmation -> `unapproved-risky-action`; failed acceptance or exhausted blocking remediation -> `acceptance-failure`; and a confirmed regression -> `regression`.

`blocked` is terminal for this invocation. The user must issue a new explicit authorization to resume any remaining Task.
