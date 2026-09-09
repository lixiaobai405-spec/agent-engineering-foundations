"""Expand run_command gate_id arguments into classified argv."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from agent_foundations.tools.command.models import CommandGate, ProjectCommandManifest

COMMAND_ARGV_REJECTED = "COMMAND_ARGV_REJECTED"
COMMAND_UNKNOWN_GATE = "COMMAND_UNKNOWN_GATE"
COMMAND_GATE_ARGUMENTS_REJECTED = "COMMAND_GATE_ARGUMENTS_REJECTED"


class GateExpandError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def expand_gate_argv(
    arguments: Mapping[str, Any],
    manifest: ProjectCommandManifest,
) -> tuple[str, ...]:
    if "argv" in arguments:
        raise GateExpandError(
            COMMAND_ARGV_REJECTED,
            "run_command does not accept argv",
        )
    gate_id = arguments.get("gate_id")
    if not isinstance(gate_id, str) or not gate_id:
        raise GateExpandError(COMMAND_UNKNOWN_GATE, "unknown gate_id")
    gate = _gate_by_id(manifest, gate_id)
    if gate is None:
        raise GateExpandError(COMMAND_UNKNOWN_GATE, f"unknown gate_id: {gate_id}")
    target = arguments.get("target")
    flags = arguments.get("flags")
    has_target = isinstance(target, str) and bool(target)
    has_flags = isinstance(flags, (list, tuple)) and len(flags) > 0
    if gate.exact:
        if has_target or has_flags:
            raise GateExpandError(
                COMMAND_GATE_ARGUMENTS_REJECTED,
                "exact gate does not accept target or flags",
            )
        return gate.argv_prefix
    if not has_target:
        raise GateExpandError(
            COMMAND_GATE_ARGUMENTS_REJECTED,
            "parameterized gate requires target",
        )
    flag_tokens = _normalized_flags(flags)
    return (*gate.argv_prefix, *flag_tokens, str(target))


def _gate_by_id(manifest: ProjectCommandManifest, gate_id: str) -> CommandGate | None:
    for gate in manifest.gates:
        if gate.rule_id == gate_id:
            return gate
    return None


def _normalized_flags(flags: object) -> tuple[str, ...]:
    if flags is None:
        return ()
    if not isinstance(flags, (list, tuple)):
        raise GateExpandError(
            COMMAND_GATE_ARGUMENTS_REJECTED,
            "flags must be a list of strings",
        )
    return tuple(str(item) for item in flags)
