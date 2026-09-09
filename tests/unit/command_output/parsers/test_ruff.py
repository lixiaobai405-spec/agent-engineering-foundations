from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from tests.unit.command_output.parsers import FIXTURE_ROOT


def _parser() -> Any:
    try:
        spec = importlib.util.find_spec("agent_foundations.command_output.parsers.ruff")
    except ModuleNotFoundError:
        spec = None
    assert spec is not None, "ruff output parser is missing"
    from agent_foundations.command_output.parsers.ruff import RuffOutputParser

    return RuffOutputParser()


def test_ruff_json_and_text_report_file_and_code() -> None:
    parser = _parser()
    json_outcome = parser.parse(
        (FIXTURE_ROOT / "ruff" / "json-fail.json").read_text(encoding="utf-8"),
        "",
        exit_code=1,
    )
    text_outcome = parser.parse(
        (FIXTURE_ROOT / "ruff" / "text-fail.txt").read_text(encoding="utf-8"),
        "",
        exit_code=1,
    )
    assert json_outcome.diagnostics[0].file == "src/a.py"
    assert json_outcome.diagnostics[0].error_code == "F401"
    assert text_outcome.diagnostics[0].error_code == "F401"
    passed = parser.parse(
        (FIXTURE_ROOT / "ruff" / "text-pass.txt").read_text(encoding="utf-8"),
        "",
        exit_code=0,
    )
    assert passed.parser_status == "complete"
    assert passed.failed in {0, None}


def test_ruff_truncated_json_is_partial_or_failed() -> None:
    outcome = _parser().parse(
        (FIXTURE_ROOT / "ruff" / "json-truncated.json").read_text(encoding="utf-8"),
        "",
        exit_code=1,
    )
    assert outcome.parser_status in {"partial", "failed"}
    assert outcome.unparsed_bytes > 0


def test_ruff_unknown_version_extra_braces_and_ansi_in_json() -> None:
    parser = _parser()
    unknown = parser.parse('{"version": 99, "diagnostics": []}', "", exit_code=1)
    assert unknown.parser_status in {"partial", "failed"}
    extra = parser.parse('[{"filename":"src/a.py","code":"F401","message":"x"}]]', "", exit_code=1)
    assert extra.parser_status in {"partial", "failed"}
    from agent_foundations.command_output.sanitize import sanitize_streams

    colored, _stderr = sanitize_streams(
        stdout=(
            b'\x1b[31m[{"filename":"src/a.py","code":"F401",'
            b'"message":"unused","location":{"row":1,"column":1}}]\x1b[0m'
        ),
        stderr=b"",
        project_root=Path("."),
    )
    ansi = parser.parse(colored, "", exit_code=1)
    assert ansi.parser_status == "complete"
    assert ansi.diagnostics[0].error_code == "F401"
