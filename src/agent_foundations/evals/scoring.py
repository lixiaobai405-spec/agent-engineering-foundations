from agent_foundations.evals.models import EvalAssertion, EvalAssertionKind, EvalTask
from agent_foundations.evals.reporting import EvalAssertionResult, EvalTaskResult
from agent_foundations.evals.runner import EvalObservation


def score_assertion(assertion: EvalAssertion, observation: EvalObservation) -> bool:
    match assertion.kind:
        case EvalAssertionKind.ANSWER_CONTAINS:
            return assertion.value in observation.answer
        case EvalAssertionKind.ANSWER_EXCLUDES:
            return assertion.value not in observation.answer
        case EvalAssertionKind.TOOL_CALLED:
            return assertion.value in observation.tool_names
        case EvalAssertionKind.TOOL_NOT_CALLED:
            return assertion.value not in observation.tool_names
        case EvalAssertionKind.ERROR_CODE:
            return observation.error_code == assertion.value


def score_task(task: EvalTask, observation: EvalObservation) -> EvalTaskResult:
    assertion_results = tuple(
        EvalAssertionResult(
            kind=assertion.kind.value,
            value=assertion.value,
            passed=score_assertion(assertion, observation),
        )
        for assertion in task.assertions
    )
    return EvalTaskResult(
        task_id=task.task_id,
        passed=all(result.passed for result in assertion_results),
        assertion_results=assertion_results,
        observation=observation,
        error_kind=None,
    )


def build_failed_task_result(task: EvalTask, error_kind: str) -> EvalTaskResult:
    assertion_results = tuple(
        EvalAssertionResult(
            kind=assertion.kind.value,
            value=assertion.value,
            passed=False,
        )
        for assertion in task.assertions
    )
    return EvalTaskResult(
        task_id=task.task_id,
        passed=False,
        assertion_results=assertion_results,
        observation=None,
        error_kind=error_kind,
    )
