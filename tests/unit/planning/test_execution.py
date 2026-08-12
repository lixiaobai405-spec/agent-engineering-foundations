from __future__ import annotations

import importlib.util

import pytest
from pydantic import ValidationError

from agent_foundations.planning.execution import ExecutionFact

SESSION_A = "11111111-1111-4111-8111-111111111111"
SESSION_B = "22222222-2222-4222-8222-222222222222"


def _require_planning_module(module_name: str) -> None:
    package_spec = importlib.util.find_spec("agent_foundations.planning")
    assert package_spec is not None, "agent_foundations.planning package must exist"
    module_spec = importlib.util.find_spec(f"agent_foundations.planning.{module_name}")
    assert module_spec is not None, f"agent_foundations.planning.{module_name} must exist"


def _fact(
    *,
    session_id: str = SESSION_A,
    tool_call_id: str = "call-1",
    tool_name: str = "list_directory",
    success: bool = True,
    error_code: str | None = None,
) -> ExecutionFact:
    return ExecutionFact(
        session_id=session_id,
        tool_call_id=tool_call_id,
        tool_name=tool_name,
        success=success,
        error_code=error_code,
    )


def test_journal_records_successful_tool_fact() -> None:
    _require_planning_module("execution")
    from agent_foundations.planning.execution import ExecutionFactJournal

    journal = ExecutionFactJournal()
    journal.record(_fact(tool_call_id="call-1"))

    journal.validate_evidence_refs(SESSION_A, ("call-1",))


def test_journal_rejects_unknown_evidence_reference() -> None:
    _require_planning_module("execution")
    from agent_foundations.planning.execution import (
        ExecutionFactJournal,
        InvalidEvidenceReferenceError,
    )

    journal = ExecutionFactJournal()

    with pytest.raises(InvalidEvidenceReferenceError, match="unknown"):
        journal.validate_evidence_refs(SESSION_A, ("missing",))


def test_journal_rejects_failed_tool_call_as_evidence() -> None:
    _require_planning_module("execution")
    from agent_foundations.planning.execution import (
        ExecutionFactJournal,
        InvalidEvidenceReferenceError,
    )

    journal = ExecutionFactJournal()
    journal.record(
        _fact(
            tool_call_id="call-failed",
            success=False,
            error_code="InvalidToolArgumentsError",
        ),
    )

    with pytest.raises(InvalidEvidenceReferenceError, match="failed"):
        journal.validate_evidence_refs(SESSION_A, ("call-failed",))


def test_journal_rejects_duplicate_evidence_ids_in_one_request() -> None:
    _require_planning_module("execution")
    from agent_foundations.planning.execution import (
        ExecutionFactJournal,
        InvalidEvidenceReferenceError,
    )

    journal = ExecutionFactJournal()
    journal.record(_fact(tool_call_id="call-1"))

    with pytest.raises(InvalidEvidenceReferenceError, match="duplicate"):
        journal.validate_evidence_refs(SESSION_A, ("call-1", "call-1"))


def test_journal_rejects_duplicate_tool_call_id_on_record() -> None:
    _require_planning_module("execution")
    from agent_foundations.planning.execution import (
        DuplicateToolCallFactError,
        ExecutionFactJournal,
    )

    journal = ExecutionFactJournal()
    journal.record(_fact(tool_call_id="call-dup"))

    with pytest.raises(DuplicateToolCallFactError, match="duplicate"):
        journal.record(_fact(tool_call_id="call-dup"))


def test_journal_isolates_facts_by_session() -> None:
    _require_planning_module("execution")
    from agent_foundations.planning.execution import (
        ExecutionFactJournal,
        InvalidEvidenceReferenceError,
    )

    journal = ExecutionFactJournal()
    journal.record(_fact(session_id=SESSION_A, tool_call_id="call-a"))

    with pytest.raises(InvalidEvidenceReferenceError, match="unknown"):
        journal.validate_evidence_refs(SESSION_B, ("call-a",))


@pytest.mark.parametrize(
    "planning_tool_name",
    ["set_plan", "update_plan_step", "replan"],
)
def test_journal_rejects_planning_tool_call_as_evidence(
    planning_tool_name: str,
) -> None:
    _require_planning_module("execution")
    from agent_foundations.planning.execution import (
        ExecutionFactJournal,
        InvalidEvidenceReferenceError,
    )

    journal = ExecutionFactJournal()
    journal.record(
        _fact(tool_call_id="plan-call", tool_name=planning_tool_name),
    )

    with pytest.raises(InvalidEvidenceReferenceError, match="planning tool"):
        journal.validate_evidence_refs(SESSION_A, ("plan-call",))


def test_execution_fact_is_frozen() -> None:
    fact = _fact(success=False, error_code="oops")

    with pytest.raises((TypeError, ValidationError)):
        fact.success = True


def test_journal_rejects_evidence_when_failed_fact_reference_is_tampered() -> None:
    _require_planning_module("execution")
    from agent_foundations.planning.execution import (
        ExecutionFactJournal,
        InvalidEvidenceReferenceError,
    )

    journal = ExecutionFactJournal()
    fact = _fact(
        tool_call_id="call-tamper",
        success=False,
        error_code="RuntimeError",
    )
    journal.record(fact)

    with pytest.raises((TypeError, ValidationError)):
        fact.success = True

    with pytest.raises(InvalidEvidenceReferenceError, match="failed"):
        journal.validate_evidence_refs(SESSION_A, ("call-tamper",))


def test_journal_stored_fact_isolated_from_caller_model_copy() -> None:
    _require_planning_module("execution")
    from agent_foundations.planning.execution import (
        ExecutionFactJournal,
        InvalidEvidenceReferenceError,
    )

    journal = ExecutionFactJournal()
    fact = _fact(
        tool_call_id="call-copy",
        success=False,
        error_code="RuntimeError",
    )
    journal.record(fact)

    flipped = fact.model_copy(update={"success": True})
    assert flipped.success is True

    with pytest.raises(InvalidEvidenceReferenceError, match="failed"):
        journal.validate_evidence_refs(SESSION_A, ("call-copy",))


def test_journal_accepts_multiple_valid_evidence_refs() -> None:
    _require_planning_module("execution")
    from agent_foundations.planning.execution import ExecutionFactJournal

    journal = ExecutionFactJournal()
    journal.record(_fact(tool_call_id="call-1"))
    journal.record(_fact(tool_call_id="call-2", tool_name="read_file"))

    journal.validate_evidence_refs(SESSION_A, ("call-1", "call-2"))
