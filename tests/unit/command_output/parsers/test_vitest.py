from __future__ import annotations

import importlib.util
from typing import Any

from tests.unit.command_output.parsers import FIXTURE_ROOT


def _parser() -> Any:
    try:
        spec = importlib.util.find_spec("agent_foundations.command_output.parsers.vitest")
    except ModuleNotFoundError:
        spec = None
    assert spec is not None, "vitest output parser is missing"
    from agent_foundations.command_output.parsers.vitest import VitestOutputParser

    return VitestOutputParser()


def test_vitest_json_and_text_keep_failed_test_id() -> None:
    parser = _parser()
    json_outcome = parser.parse(
        (FIXTURE_ROOT / "vitest" / "json-fail-skip.json").read_text(encoding="utf-8"),
        "",
        exit_code=1,
    )
    text_outcome = parser.parse(
        (FIXTURE_ROOT / "vitest" / "text-fail-skip.txt").read_text(encoding="utf-8"),
        "",
        exit_code=1,
    )
    assert json_outcome.failed == 1
    assert json_outcome.passed == 1
    assert json_outcome.skipped == 1
    json_ids = {item.test_id for item in json_outcome.diagnostics if item.test_id}
    assert any("fails" in (item or "") for item in json_ids)
    assert text_outcome.failed == 1


def test_vitest_truncated_json_is_partial() -> None:
    outcome = _parser().parse(
        (FIXTURE_ROOT / "vitest" / "json-truncated.json").read_text(encoding="utf-8"),
        "",
        exit_code=1,
    )
    assert outcome.parser_status in {"partial", "failed"}
    assert outcome.unparsed_bytes > 0
