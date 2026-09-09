from __future__ import annotations

import importlib.util
from typing import Any

from tests.unit.command_output.parsers import FIXTURE_ROOT


def _parser() -> Any:
    try:
        spec = importlib.util.find_spec("agent_foundations.command_output.parsers.build")
    except ModuleNotFoundError:
        spec = None
    assert spec is not None, "build output parser is missing"
    from agent_foundations.command_output.parsers.build import BuildOutputParser

    return BuildOutputParser()


def test_vite_and_pip_check_pass_and_fail() -> None:
    parser = _parser()
    fail = parser.parse(
        (FIXTURE_ROOT / "build" / "vite-fail.txt").read_text(encoding="utf-8"),
        "",
        exit_code=1,
    )
    assert fail.parser_status in {"complete", "partial"}
    assert fail.diagnostics
    passed = parser.parse(
        (FIXTURE_ROOT / "build" / "vite-pass.txt").read_text(encoding="utf-8"),
        "",
        exit_code=0,
    )
    assert passed.parser_status == "complete"
    pip_fail = parser.parse(
        (FIXTURE_ROOT / "build" / "pip-check-fail.txt").read_text(encoding="utf-8"),
        "",
        exit_code=1,
    )
    assert "foo" in pip_fail.diagnostics[0].message
    pip_pass = parser.parse(
        (FIXTURE_ROOT / "build" / "pip-check-pass.txt").read_text(encoding="utf-8"),
        "",
        exit_code=0,
    )
    assert pip_pass.parser_status == "complete"


def test_build_truncated_json_is_failed_or_partial() -> None:
    outcome = _parser().parse(
        (FIXTURE_ROOT / "build" / "json-truncated.json").read_text(encoding="utf-8"),
        "",
        exit_code=1,
    )
    assert outcome.parser_status in {"partial", "failed"}
