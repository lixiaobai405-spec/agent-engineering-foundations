from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from agent_foundations.command_output.models import ParserStatus
from agent_foundations.command_output.store import CommandArtifactStore
from agent_foundations.durable.models import DurableRun, DurableRunStatus
from agent_foundations.durable.repository import DurableRunRepository

PLACEHOLDER = "sk-test_placeholder_not_real"
RUN_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
RUN_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


def _require_access() -> Any:
    try:
        spec = importlib.util.find_spec("agent_foundations.command_output.access")
    except ModuleNotFoundError:
        spec = None
    assert spec is not None, "command output access is missing"
    from agent_foundations.command_output.access import (
        CommandOutputAccessService,
        parse_selector,
    )

    return CommandOutputAccessService, parse_selector


def _require_audit() -> Any:
    try:
        spec = importlib.util.find_spec("agent_foundations.command_output.audit")
    except ModuleNotFoundError:
        spec = None
    assert spec is not None, "command output audit is missing"
    from agent_foundations.command_output.audit import CommandOutputAuditRepository

    return CommandOutputAuditRepository


def test_parse_selector_accepts_three_exclusive_shapes_and_rejects_paths() -> None:
    _service_cls, parse_selector = _require_access()
    from agent_foundations.command_output.access import AccessError

    start = parse_selector({"stream": "stdout", "start_line": 1, "line_count": 10})
    around = parse_selector({"diagnostic_id": "abc123def4567890"})
    tail = parse_selector({"stream": "stderr", "tail_lines": 20})
    assert start.__class__.__name__ == "StartLineSelector"
    assert around.__class__.__name__ == "AroundDiagnosticSelector"
    assert tail.__class__.__name__ == "TailSelector"
    with pytest.raises(AccessError) as mixed:
        parse_selector(
            {
                "stream": "stdout",
                "start_line": 1,
                "line_count": 10,
                "tail_lines": 5,
            }
        )
    assert mixed.value.code == "SELECTOR_INVALID"
    for payload in (
        {"path": "stdout"},
        {"byte_offset": 0, "stream": "stdout", "tail_lines": 2},
        {"glob": "*.log", "stream": "stdout", "tail_lines": 2},
        {"regex": "secret", "query": "x"},
        {"sql": "SELECT 1"},
        {"stream": "stdout", "start_line": 1, "line_count": 201},
    ):
        with pytest.raises(AccessError):
            parse_selector(payload)


def test_parse_selector_defaults_missing_line_count_to_forty() -> None:
    _service_cls, parse_selector = _require_access()
    from agent_foundations.command_output.access import StartLineSelector

    parsed = parse_selector({"stream": "stdout", "start_line": 1})
    assert isinstance(parsed, StartLineSelector)
    assert parsed.line_count == 40
    assert parsed.start_line == 1
    assert parsed.stream == "stdout"


def test_parse_selector_drops_safe_extra_keys() -> None:
    _service_cls, parse_selector = _require_access()
    from agent_foundations.command_output.access import TailSelector

    parsed = parse_selector(
        {"stream": "stdout", "tail_lines": 5, "max_lines": 100},
    )
    assert isinstance(parsed, TailSelector)
    assert parsed.tail_lines == 5
    assert parsed.stream == "stdout"


def test_parse_selector_shape_error_lists_legal_shapes() -> None:
    _service_cls, parse_selector = _require_access()
    from agent_foundations.command_output.access import AccessError

    with pytest.raises(AccessError) as exc:
        parse_selector({"max_lines": 100})
    assert exc.value.code == "SELECTOR_INVALID"
    message = str(exc.value)
    assert "diagnostic_id" in message
    assert "tail_lines" in message
    assert "start_line" in message
    assert "line_count" in message
    assert len(message) <= 240


def test_reason_is_required_and_artifact_id_rejects_malformed() -> None:
    service_cls, _parse_selector = _require_access()
    from agent_foundations.command_output.access import AccessError

    service = object.__new__(service_cls)
    for artifact_id in (
        "coa_short",
        "../coa_AAAAAAAAAAAAAAAAAAAAAA",
        "coa_AAAA:BBBBBBBBBBBBBBBBBB",
        "coa_AAAA\x00BBBBBBBBBBBBBBBB",
        "C:\\temp\\coa_AAAAAAAAAAAAAAAAAAAAAA",
    ):
        with pytest.raises(AccessError) as exc:
            service.validate_artifact_id(artifact_id)
        assert exc.value.code in {
            "SELECTOR_INVALID",
            "ARTIFACT_SCOPE_DENIED",
            "ARTIFACT_NOT_READABLE",
        }
    with pytest.raises(AccessError) as blank:
        service.require_reason("")
    assert blank.value.code == "REASON_REQUIRED"


@pytest.mark.asyncio
async def test_read_re_redacts_and_budget_and_partial_warning(
    tmp_path: Path,
) -> None:
    service_cls, parse_selector = _require_access()
    from agent_foundations.command_output.access import AccessError

    store, service = await _service_stack(tmp_path, service_cls)
    secret = f"Authorization: Bearer {PLACEHOLDER}\nline-two\n"
    artifact = store.write(
        stdout=secret.encode("utf-8") * 20,
        stderr=b"fixture-secret-output\n",
        run_id=UUID(RUN_A),
    )
    page = service.read(
        current_run_id=RUN_A,
        artifact_id=artifact.artifact_id,
        selector=parse_selector({"stream": "stdout", "start_line": 1, "line_count": 8}),
        reason="inspect parser gap",
        project_root=tmp_path,
        parser_status=ParserStatus.PARTIAL,
    )
    text = "\n".join(page.lines)
    assert PLACEHOLDER not in text
    assert "[REDACTED]" in text
    assert page.parser_warning is not None
    assert page.byte_count <= 64 * 1024
    assert len(page.lines) <= 200
    over = service.read
    with pytest.raises(AccessError) as budget:
        # accumulate past 1000 lines
        for _ in range(80):
            over(
                current_run_id=RUN_A,
                artifact_id=artifact.artifact_id,
                selector=parse_selector(
                    {"stream": "stdout", "start_line": 1, "line_count": 200}
                ),
                reason="inspect parser gap",
                project_root=tmp_path,
            )
    assert getattr(budget.value, "code", "") == "OUTPUT_BUDGET_EXCEEDED"


@pytest.mark.asyncio
async def test_deleted_artifact_is_not_readable(tmp_path: Path) -> None:
    service_cls, parse_selector = _require_access()
    from agent_foundations.command_output.access import AccessError

    store, service = await _service_stack(tmp_path, service_cls)
    artifact = store.write(stdout=b"gone\n", stderr=b"", run_id=UUID(RUN_A))
    store._repository.mark_pending_delete(artifact.artifact_id)
    with pytest.raises(AccessError) as exc:
        service.read(
            current_run_id=RUN_A,
            artifact_id=artifact.artifact_id,
            selector=parse_selector({"stream": "stdout", "tail_lines": 4}),
            reason="inspect parser gap",
            project_root=tmp_path,
        )
    assert getattr(exc.value, "code", "") == "ARTIFACT_NOT_READABLE"


@pytest.mark.asyncio
async def test_audit_rows_omit_content(tmp_path: Path) -> None:
    service_cls, parse_selector = _require_access()
    audit_cls = _require_audit()
    store, service = await _service_stack(tmp_path, service_cls)
    artifact = store.write(stdout=b"fixture-secret-output\n", stderr=b"", run_id=UUID(RUN_A))
    service.read(
        current_run_id=RUN_A,
        artifact_id=artifact.artifact_id,
        selector=parse_selector({"stream": "stdout", "start_line": 1, "line_count": 2}),
        reason="inspect parser gap",
        project_root=tmp_path,
    )
    db_bytes = store._repository.path.read_bytes()
    assert b"fixture-secret-output" not in db_bytes
    rows = audit_cls(store._repository._database).list_for_run(RUN_A)
    assert rows
    dumped = str(rows)
    assert "fixture-secret-output" not in dumped
    assert "content" not in dumped.lower() or all(
        "fixture-secret" not in str(item) for item in rows
    )


async def _service_stack(tmp_path: Path, service_cls: Any) -> tuple[Any, Any]:
    db_path = tmp_path / "state.sqlite3"
    durable = DurableRunRepository(db_path)
    await durable.initialize()
    await durable.create_run(
        DurableRun(
            run_id=RUN_A,
            project_root=str(tmp_path / "project-a"),
            status=DurableRunStatus.CREATED,
            schema_version=1,
            state_version=0,
            attempt=1,
            created_at=datetime(2026, 8, 26, tzinfo=UTC),
            updated_at=datetime(2026, 8, 26, tzinfo=UTC),
        )
    )
    from agent_foundations.command_output.repository import CommandArtifactRepository

    artifacts = CommandArtifactRepository.from_path(db_path)
    await artifacts.initialize()
    store = CommandArtifactStore(tmp_path / "artifacts", repository=artifacts)
    return store, service_cls(store=store, repository=artifacts)
