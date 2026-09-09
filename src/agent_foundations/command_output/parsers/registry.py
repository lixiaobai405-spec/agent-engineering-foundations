from __future__ import annotations

from agent_foundations.command_output.parsers.base import OutputParser
from agent_foundations.command_output.parsers.build import BuildOutputParser
from agent_foundations.command_output.parsers.mypy import MypyOutputParser
from agent_foundations.command_output.parsers.pytest import PytestOutputParser
from agent_foundations.command_output.parsers.ruff import RuffOutputParser
from agent_foundations.command_output.parsers.typescript import TypeScriptOutputParser
from agent_foundations.command_output.parsers.vitest import VitestOutputParser

_RULE_PARSERS: dict[str, type[OutputParser]] = {
    "manifest.python.pytest": PytestOutputParser,
    "manifest.python.ruff-check": RuffOutputParser,
    "manifest.python.mypy": MypyOutputParser,
    "manifest.node.test-viewer": VitestOutputParser,
    "manifest.node.test-chat": VitestOutputParser,
    "manifest.node.typecheck-viewer": TypeScriptOutputParser,
    "manifest.node.typecheck-chat": TypeScriptOutputParser,
    "manifest.node.build-chat": BuildOutputParser,
    "manifest.python.pip-check": BuildOutputParser,
}


def parser_for(rule_id: str) -> OutputParser:
    try:
        parser_type = _RULE_PARSERS[rule_id]
    except KeyError as exc:
        raise LookupError(f"no command-output parser for rule_id={rule_id}") from exc
    return parser_type()
