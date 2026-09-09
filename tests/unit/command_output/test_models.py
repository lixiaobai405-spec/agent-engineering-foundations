from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError


def _models() -> Any:
    try:
        spec = importlib.util.find_spec("agent_foundations.command_output.models")
    except ModuleNotFoundError:
        spec = None
    assert spec is not None, "command output models are missing"
    from agent_foundations.command_output.models import (
        ARTIFACT_ID_PATTERN,
        CommandArtifactMetadata,
        ParserStatus,
        RetentionStatus,
        RunCommandRequest,
        compute_artifact_sha256,
        generate_artifact_id,
    )

    return (
        CommandArtifactMetadata,
        ParserStatus,
        RetentionStatus,
        RunCommandRequest,
        ARTIFACT_ID_PATTERN,
        compute_artifact_sha256,
        generate_artifact_id,
    )


def test_retention_and_parser_status_contracts() -> None:
    _metadata, parser_status, retention_status, *_rest = _models()
    assert tuple(status.value for status in retention_status) == (
        "active",
        "retained",
        "pending_delete",
        "deleted",
        "delete_failed",
        "evicted",
    )
    assert tuple(status.value for status in parser_status) == (
        "pending",
        "complete",
        "partial",
        "failed",
    )


def test_artifact_id_is_opaque_coa_prefix_without_padding() -> None:
    *_rest, pattern, _digest, generate_artifact_id = _models()
    artifact_id = generate_artifact_id()
    assert pattern.fullmatch(artifact_id) is not None
    assert artifact_id.startswith("coa_")
    assert "=" not in artifact_id
    assert "/" not in artifact_id
    assert "+" not in artifact_id
    assert generate_artifact_id() != artifact_id


def test_run_command_request_bounds_timeout() -> None:
    _metadata, _parser, _retention, request_cls, *_rest = _models()
    request = request_cls(argv=("python", "-m", "pytest", "tests"))
    assert request.cwd == "."
    assert request.timeout_seconds == 120
    with pytest.raises(ValidationError):
        request_cls(argv=("python", "-m", "pytest"), timeout_seconds=0)
    with pytest.raises(ValidationError):
        request_cls(argv=("python", "-m", "pytest"), timeout_seconds=301)


def test_canonical_hash_frames_stdout_then_stderr() -> None:
    *_rest, compute_artifact_sha256, _generate = _models()
    stdout = b"fixture-secret"
    stderr = b"failure"
    digest = compute_artifact_sha256(stdout, stderr)
    assert len(digest) == 64
    assert digest != compute_artifact_sha256(stderr, stdout)
    assert digest != compute_artifact_sha256(b"fixture-secret", b"other")


def test_metadata_starts_parser_pending() -> None:
    (
        metadata_cls,
        parser_status,
        retention_status,
        _request,
        pattern,
        compute_artifact_sha256,
        generate_artifact_id,
    ) = _models()
    metadata = metadata_cls(
        artifact_id=generate_artifact_id(),
        run_id=uuid4(),
        effect_id=uuid4(),
        execution_id=uuid4(),
        stdout_bytes=3,
        stderr_bytes=0,
        sha256=compute_artifact_sha256(b"abc", b""),
        created_at=datetime(2026, 8, 26, 5, 0, tzinfo=UTC),
        retention_status=retention_status.ACTIVE,
        parser_status=parser_status.PENDING,
    )
    assert metadata.parser_status is parser_status.PENDING
    assert isinstance(metadata.run_id, UUID)
    assert pattern.fullmatch(metadata.artifact_id) is not None
