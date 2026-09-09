"""Layered stop conditions derived from the transcript, not AgentRunState."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from agent_foundations.domain.messages import Message
from agent_foundations.runtime.recovery import (
    _RECOVERY_ERROR_CODES,
    _argv,
    _iter_turns,
    _patch_paths,
    _Turn,
)

BUDGET_PATCH_REPAIRS_EXCEEDED = "BUDGET_PATCH_REPAIRS_EXCEEDED"
BUDGET_COMMAND_RETRIES_EXCEEDED = "BUDGET_COMMAND_RETRIES_EXCEEDED"
BUDGET_ARTIFACT_READS_EXCEEDED = "BUDGET_ARTIFACT_READS_EXCEEDED"

CHAT_MAX_STEPS = 24
CHAT_MAX_PATCH_REPAIRS = 4
CHAT_MAX_SAME_ARGV_COMMAND_RUNS = 3
CHAT_MAX_ARTIFACT_READS = 8

_PATCH_WRITE_TOOLS = frozenset({"validate_patch", "apply_patch"})
_ARTIFACT_READ_TOOLS = frozenset({"read_command_output", "search_command_output"})
_BUDGET_ERROR_CODES = frozenset({
    BUDGET_PATCH_REPAIRS_EXCEEDED,
    BUDGET_COMMAND_RETRIES_EXCEEDED,
    BUDGET_ARTIFACT_READS_EXCEEDED,
})
_NON_EXECUTED_ERROR_CODES = _RECOVERY_ERROR_CODES | _BUDGET_ERROR_CODES


@dataclass(frozen=True)
class CodingBudgetLimits:
    max_patch_repairs: int
    max_same_argv_command_runs: int
    max_artifact_reads: int

    def __post_init__(self) -> None:
        for label, value in (
            ("max_patch_repairs", self.max_patch_repairs),
            ("max_same_argv_command_runs", self.max_same_argv_command_runs),
            ("max_artifact_reads", self.max_artifact_reads),
        ):
            if value < 1:
                raise ValueError(f"{label} must be positive")


CHAT_CODING_BUDGET = CodingBudgetLimits(
    max_patch_repairs=CHAT_MAX_PATCH_REPAIRS,
    max_same_argv_command_runs=CHAT_MAX_SAME_ARGV_COMMAND_RUNS,
    max_artifact_reads=CHAT_MAX_ARTIFACT_READS,
)


@dataclass(frozen=True)
class BudgetDecision:
    allowed: bool
    error_code: str | None = None
    message: str = ""


def evaluate_budget(
    messages: Sequence[Message],
    tool_name: str,
    arguments: Mapping[str, Any],
    limits: CodingBudgetLimits,
) -> BudgetDecision:
    executed = [
        turn for turn in _iter_turns(messages) if _was_executed(turn)
    ]
    if tool_name in _PATCH_WRITE_TOOLS:
        candidate_paths = _paths_of(tool_name, arguments, {})
        repairs = sum(
            1
            for turn in executed
            if turn.name in _PATCH_WRITE_TOOLS
            and not turn.success
            and _same_path_bucket(
                _paths_of(turn.name, turn.arguments, turn.metadata),
                candidate_paths,
            )
        )
        if repairs >= limits.max_patch_repairs:
            return BudgetDecision(
                allowed=False,
                error_code=BUDGET_PATCH_REPAIRS_EXCEEDED,
                message="same-path patch repair budget exceeded",
            )
        return BudgetDecision(allowed=True)
    if tool_name == "run_command":
        argv = _argv(arguments)
        runs = sum(
            1
            for turn in executed
            if turn.name == "run_command" and _argv(turn.arguments) == argv
        )
        if argv is not None and runs >= limits.max_same_argv_command_runs:
            return BudgetDecision(
                allowed=False,
                error_code=BUDGET_COMMAND_RETRIES_EXCEEDED,
                message="same argv command run budget exceeded",
            )
        return BudgetDecision(allowed=True)
    if tool_name in _ARTIFACT_READ_TOOLS:
        reads = sum(1 for turn in executed if turn.name in _ARTIFACT_READ_TOOLS)
        if reads >= limits.max_artifact_reads:
            return BudgetDecision(
                allowed=False,
                error_code=BUDGET_ARTIFACT_READS_EXCEEDED,
                message="artifact read budget exceeded",
            )
    return BudgetDecision(allowed=True)


def _was_executed(turn: _Turn) -> bool:
    return turn.error_code not in _NON_EXECUTED_ERROR_CODES


def _paths_of(
    name: str,
    arguments: Mapping[str, Any],
    metadata: Mapping[str, Any],
) -> frozenset[str]:
    return _patch_paths(
        _Turn(
            name=name,
            arguments=arguments,
            error_code=None,
            metadata=metadata,
            success=True,
        ),
    )


def _same_path_bucket(left: frozenset[str], right: frozenset[str]) -> bool:
    if not left and not right:
        return True
    return bool(left & right)
