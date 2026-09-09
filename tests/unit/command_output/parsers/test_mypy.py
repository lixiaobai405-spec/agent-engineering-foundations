from __future__ import annotations

import importlib.util
from typing import Any

from tests.unit.command_output.parsers import FIXTURE_ROOT


def _parser() -> Any:
    try:
        spec = importlib.util.find_spec("agent_foundations.command_output.parsers.mypy")
    except ModuleNotFoundError:
        spec = None
    assert spec is not None, "mypy output parser is missing"
    from agent_foundations.command_output.parsers.mypy import MypyOutputParser

    return MypyOutputParser()


def test_mypy_text_and_json_capture_error_code() -> None:
    parser = _parser()
    text = parser.parse(
        (FIXTURE_ROOT / "mypy" / "text-fail.txt").read_text(encoding="utf-8"),
        "",
        exit_code=1,
    )
    json_outcome = parser.parse(
        (FIXTURE_ROOT / "mypy" / "json-fail.json").read_text(encoding="utf-8"),
        "",
        exit_code=1,
    )
    assert text.diagnostics[0].error_code == "assignment"
    assert json_outcome.diagnostics[0].file == "src/a.py"
    passed = parser.parse(
        (FIXTURE_ROOT / "mypy" / "text-pass.txt").read_text(encoding="utf-8"),
        "",
        exit_code=0,
    )
    assert passed.parser_status == "complete"


def test_mypy_no_summary_and_exit_mismatch_are_not_complete() -> None:
    parser = _parser()
    missing = parser.parse(
        (FIXTURE_ROOT / "mypy" / "text-no-summary.txt").read_text(encoding="utf-8"),
        "",
        exit_code=1,
    )
    assert missing.parser_status in {"partial", "failed"}
    mismatch = parser.parse(
        (FIXTURE_ROOT / "mypy" / "text-exit-mismatch.txt").read_text(encoding="utf-8"),
        "",
        exit_code=1,
    )
    assert mismatch.parser_status in {"partial", "failed"}
    assert mismatch.unparsed_reason is not None
