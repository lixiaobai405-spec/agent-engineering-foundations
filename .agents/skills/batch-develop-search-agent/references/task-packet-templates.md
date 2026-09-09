# Task packet templates

All packets contain task-local facts only. Do not include full chat history, hidden reasoning, secrets, `.env` values, or unrelated Task logs.

## Intake-rejected report

```yaml
state: rejected
failure_class: invalid-input
invalid_fields: []
reason: ""
task_dispatched: false
recommended_next_action: "Submit a new current Prompt that explicitly invokes and authorizes the Skill with all four valid fields."
```

## Planner to Root

```yaml
task_id: <current-task-id>
authority_source: docs/agent-plans/<authority-plan>.md
required_branch: <required-existing-branch>
initial_head: <commit-sha>
prerequisites: []
allowed_files: []
non_scope: []
acceptance_criteria: []
verification_contract:
  tdd: required | not-applicable
  target_tests: []
  affected_regression_tests: []
  full_suite: required | not-required
  full_suite_reason: ""
  additional_gates: []
evidence_path: docs/task-evidence/<current-task-id>.md
parallelism: sequential | task-local-dag
risks: []
git_snapshot: "git status --short output recorded by Root during batch preflight"
task_start_scope_hashes: {}
task_end_scope_hashes: {}
changed_files: []
known_blockers: []
```

## Root to Executor

```yaml
task_id: <current-task-id>
authority_source: docs/agent-plans/<authority-plan>.md
required_branch: <required-existing-branch>
initial_head: <commit-sha>
prerequisites: []
allowed_files: []
non_scope: []
acceptance_criteria: []
verification_contract: {}
evidence_path: docs/task-evidence/<current-task-id>.md
git_snapshot: "git status --short output before Task"
task_start_scope_hashes: {}
changed_files: []
known_blockers: []
risks: []
```

## Root to Reviewer

```yaml
task_id: <current-task-id>
authority_source: docs/agent-plans/<authority-plan>.md
required_branch: <required-existing-branch>
initial_head: <commit-sha>
allowed_files: []
acceptance_criteria: []
verification_contract: {}
evidence_path: docs/task-evidence/<current-task-id>.md
git_snapshot: "git status --short output for review"
task_start_scope_hashes: {}
task_end_scope_hashes: {}
changed_files: []
risks: []
known_blockers: []
executor_evidence_summary: []
reviewer_focus: []
original_red_evidence: present | missing | unavailable | not-applicable
```

## Review result

```yaml
task_id: <current-task-id>
current_implementation: pass | partial | fail
tdd_process_evidence: complete | incomplete | unavailable | not-applicable
original_red_evidence: present | missing | unavailable | not-applicable
blocking: true | false
findings:
  - severity: blocking | non-blocking
    evidence: ""
    requested_action: ""
fresh_checks:
  - command: ""
    exit_code: 0
    result: ""
residual_risks: []
```

## Remediation request

```yaml
task_id: <current-task-id>
remediation_round: 1
findings: []
allowed_files: []
requested_action: "Fix only the listed confirmed findings and refresh the relevant checks."
```

## Blocked report

```yaml
blocked_task: <current-task-id-or-requested-start-task-id>
failure_class: acceptance-failure | regression | branch-mismatch | scope-conflict | invalid-task-range | dependency-missing | agent-capacity | safety-gate | environment | plan-ambiguity | file-ownership-conflict | unapproved-risky-action
reviewer_findings: []
remediation_attempts: 0
current_implementation: pass | partial | fail | not-assessed
tdd_process_evidence: complete | incomplete | unavailable | not-applicable
original_red_evidence: present | missing | unavailable | not-applicable
impact_on_remaining_tasks: []
recommended_next_action: ""
```
