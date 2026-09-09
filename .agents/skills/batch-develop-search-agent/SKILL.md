---
name: batch-develop-search-agent
description: Use when the user explicitly authorizes a bounded consecutive Task batch for D:/codex-pj/search_agent with a required branch, start Task, and positive Task count.
---

# Batch Develop Search Agent

Run one explicitly authorized consecutive Task batch for `D:\codex-pj\search_agent` in the current conversation. This is an external development workflow, not a Runtime feature: do not add Skills, Sub-Agent, MCP, A2A, or other future-Phase capabilities to the product merely by using this Skill.

## Required input

Require exactly these fields before any planning or edits:

```yaml
project_root: D:\codex-pj\search_agent
required_branch: <required-existing-branch>
start_task_id: <required-existing-task-id>
authorized_task_count: <required-positive-integer>
```

`authorized_task_count` includes `start_task_id`. A batch authorization exists only when the user's **current Prompt** (1) explicitly invokes `$batch-develop-search-agent`, (2) explicitly states `authorize` / `授权` for this invocation to execute the consecutive Task set, and (3) supplies all four valid fields above.

The qualifying current user instruction is a bounded, invocation-local exception to the project's normal single-Task stopping rule. It authorizes only the computed consecutive Task set on `required_branch`; it does not modify the project rules on disk or relax any safety, evidence, TDD, review, validation, Git, or scope rule. When this invocation ends, the default single-Task rule applies again.

When the computed set crosses an intermediate Phase gate, complete every gate test, evidence requirement, and fresh independent review first. A no-blocking Reviewer result permits this invocation to continue directly to the next already-authorized Task without another user message. This continuation never waives a failed gate and never extends the authorized Task set.

A bare YAML block, missing or invalid field, prior chat, an adjacent Task, Skill loading, or the static default prompt is not authorization. Do not plan or edit until the current Prompt satisfies all three conditions above; do not execute a Task outside the computed authorized set, even if it is adjacent.

Reject an invalid authorization deterministically as `state: rejected` with `failure_class: invalid-input`; do not create core Agents, plan, or edit. If the four fields are valid but the requested consecutive Task range cannot be computed exactly from the authority plan, block with `failure_class: invalid-task-range` before any Task dispatch.

## Required reading order

1. Read `references/role-contracts.md` before creating any core Agent.
2. Read `references/batch-contract.md` before batch preflight and every Task transition.
3. Read `references/search-agent-gates.md` before planning the first Task and any Task at a Phase boundary.
4. Read `references/task-packet-templates.md` before every Planner, Executor, Reviewer, remediation, or blocked handoff.

## Core contract

- Root is the sole coordinator, temporary batch-state owner, and user-facing synthesizer.
- Create one independent, read-only Planner and one independent Executor for the batch; reuse each only within this batch.
- Create a fresh, independent, read-only Reviewer for every Task. Reuse that Reviewer only to re-verify remediation for its own Task.
- Root and Reviewer never edit production code or tests. Do not relabel an Agent into another core role.
- Use Root-mediated communication and task-local packets; never forward full conversation history or hidden reasoning.
- Preserve the project's dirty-worktree, TDD evidence, Phase, safety, and validation rules. Project documents remain authoritative; this Skill recognizes only a current Prompt that satisfies every authorization condition above.

## Workflow

1. Validate the input fields, exact current branch, current `HEAD`, and Agent capacity.
2. Have Planner compute and return the consecutive authorized Task set from the authority plan, including dependencies, write scopes, and verification contracts.
3. Root accepts the plan only if its computed set equals the authorized count and has no missing prerequisite, scope conflict, or unapproved action.
4. For each authorized Task, execute the Task loop in `batch-contract.md`. After every accepted Task, immediately continue to the next Task already listed in `authorized_tasks`; do not wait for another user message or stop merely because one Task completed.
5. Mark `completed` only after every Task in `authorized_tasks` completed in order. Stop immediately when the batch reaches `completed` or `blocked`; never select a Task outside that list.

Use only dependency-ready, non-overlapping writes for any Task-internal parallelism. Otherwise serialize writes. A Task cannot advance until its fresh Reviewer reports no blocking finding.

## Stop conditions

Mark the whole batch `blocked` rather than improvising when there is a branch mismatch, missing dependency, dirty-worktree overlap, plan ambiguity, core-role loss after one safe retry, file ownership conflict, validation-environment failure, unapproved risky action, failed Phase gate, or a blocking finding after two remediation rounds. Use the failure-class mapping in `batch-contract.md` and return the structured blocked report from `task-packet-templates.md`.

Never treat batch authorization as permission for dependency installation, real/paid model calls, deletion, important overwrite, real-data migration, system configuration, commit, push, PR, deployment, or publication. Request separate user confirmation for those actions.

## Completion report

Report the computed authorization, actual Agent topology, completed Tasks, each fresh review result, changed files and scope audit, validation evidence, historical TDD-evidence status, and any remaining risk. Confirm that no project rules were modified and that no unperformed high-risk action was taken.
