from __future__ import annotations

from pydantic import ConfigDict

from agent_foundations.domain._model import ValidatedCopyModel

PLANNING_TOOL_NAMES = frozenset({"set_plan", "update_plan_step", "replan"})


class ExecutionFactError(ValueError):
    """Base execution fact journal error."""


class InvalidEvidenceReferenceError(ExecutionFactError):
    """Evidence reference does not point to a valid successful tool fact."""


class DuplicateToolCallFactError(ExecutionFactError):
    """Tool call ID was already recorded for this session."""


class PlanningRequiredError(ExecutionFactError):
    """Final answer blocked because planning requirements are not satisfied."""


class ExecutionFact(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True)

    session_id: str
    tool_call_id: str
    tool_name: str
    success: bool
    error_code: str | None = None


class ExecutionFactJournal:
    def __init__(self) -> None:
        self._facts: dict[tuple[str, str], ExecutionFact] = {}

    def record(self, fact: ExecutionFact) -> None:
        key = (fact.session_id, fact.tool_call_id)
        if key in self._facts:
            raise DuplicateToolCallFactError(
                f"duplicate tool_call_id for session: {fact.tool_call_id}",
            )
        self._facts[key] = fact.model_copy()

    def validate_evidence_refs(
        self,
        session_id: str,
        evidence_refs: tuple[str, ...],
    ) -> None:
        seen: set[str] = set()
        for ref in evidence_refs:
            if ref in seen:
                raise InvalidEvidenceReferenceError("duplicate evidence_tool_call_id")
            seen.add(ref)
            fact = self._facts.get((session_id, ref))
            if fact is None:
                raise InvalidEvidenceReferenceError("unknown evidence_tool_call_id")
            if not fact.success:
                raise InvalidEvidenceReferenceError(
                    "failed tool call cannot be evidence",
                )
            if fact.tool_name in PLANNING_TOOL_NAMES:
                raise InvalidEvidenceReferenceError(
                    "planning tool call cannot be evidence",
                )
