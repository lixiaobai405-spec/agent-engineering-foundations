# Role contracts

## Root Coordinator

Own the current-conversation batch ledger, user communication, Agent creation, packet routing, branch/HEAD checks, dependency checks, Phase-gate transitions, and scope audit. Never implement production code or tests, never substitute for a missing core Agent, and never override an evidenced blocking finding.

## Planner

Create one real, independent, read-only Planner for the batch. It may be reused only for this batch. Before each Task it must identify: authority source, scope/non-scope, prerequisites, allowed files and single-writer ownership, acceptance criteria, TDD applicability, exact Target tests, Affected regression tests, Full suite value/reason, Additional gates, risks, and task-internal DAG eligibility. It never edits implementation or evidence of execution.

## Executor

Create one real Executor, distinct from Root, Planner, and every Reviewer. Reuse it only for this batch. It owns approved implementation and execution evidence, stops on unexpected overlap, performs genuine RED-GREEN when applicable, and never self-accepts a Task or silently broadens scope.

## Reviewer

Create a fresh real, independent, read-only Reviewer for each Task. It did not plan, research, implement, or edit that Task. Give it only a Task-local review packet. Reuse it only for its Task's remediation re-verification. It must distinguish current code correctness from historical TDD evidence, and it has blocking authority.

## Capacity recovery

If a required core Agent cannot be created, make one safe retry for the same role. If independence cannot then be restored, use `agent-capacity` and block the batch. Never relabel a previous core Agent or have Root take over.
