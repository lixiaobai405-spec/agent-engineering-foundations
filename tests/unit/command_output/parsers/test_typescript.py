from __future__ import annotations

import importlib.util
from typing import Any

from tests.unit.command_output.parsers import FIXTURE_ROOT


def _parser() -> Any:
    try:
        spec = importlib.util.find_spec("agent_foundations.command_output.parsers.typescript")
    except ModuleNotFoundError:
        spec = None
    assert spec is not None, "typescript output parser is missing"
    from agent_foundations.command_output.parsers.typescript import TypeScriptOutputParser

    return TypeScriptOutputParser()


def test_typescript_keeps_all_errors_including_missing_module() -> None:
    outcome = _parser().parse(
        (FIXTURE_ROOT / "typescript" / "text-fail.txt").read_text(encoding="utf-8"),
        "",
        exit_code=2,
    )
    codes = {item.error_code for item in outcome.diagnostics}
    assert "TS2322" in codes
    assert "TS2307" in codes
    assert outcome.failed == 2
    passed = _parser().parse(
        (FIXTURE_ROOT / "typescript" / "text-pass.txt").read_text(encoding="utf-8"),
        "",
        exit_code=0,
    )
    assert passed.parser_status == "complete"


def test_typescript_no_summary_is_partial() -> None:
    outcome = _parser().parse(
        (FIXTURE_ROOT / "typescript" / "text-no-summary.txt").read_text(encoding="utf-8"),
        "",
        exit_code=2,
    )
    assert outcome.parser_status in {"partial", "failed"}
    assert outcome.diagnostics[0].error_code == "TS2322"
