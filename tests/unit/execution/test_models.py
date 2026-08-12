from __future__ import annotations

import importlib.util
from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError


def _models() -> tuple[Any, ...]:
    assert importlib.util.find_spec("agent_foundations.execution") is not None, (
        "Task 14 execution package is missing"
    )
    assert importlib.util.find_spec("agent_foundations.execution.models") is not None, (
        "Task 14 execution models are missing"
    )
    from agent_foundations.execution.models import (
        MAX_OUTPUT_BYTES,
        MAX_STDIN_BYTES,
        MAX_TIMEOUT_SECONDS,
        ExecutionRequest,
        ExecutionResult,
    )

    return (
        ExecutionRequest,
        ExecutionResult,
        MAX_STDIN_BYTES,
        MAX_TIMEOUT_SECONDS,
        MAX_OUTPUT_BYTES,
    )


def _request(**changes: object) -> Any:
    ExecutionRequest, *_ = _models()
    values: dict[str, object] = {
        "execution_id": str(uuid4()),
        "run_id": str(uuid4()),
        "capability_id": str(uuid4()),
        "argv": ("python", "-c", "print('ok')"),
        "cwd": ".",
        "mount_mode": "read_only",
        "stdin": b"",
        "timeout_seconds": 30,
        "max_output_bytes": 4096,
    }
    values.update(changes)
    return ExecutionRequest.model_validate(values)


def test_execution_models_are_frozen_strict_and_copy_revalidates() -> None:
    _ExecutionRequest, ExecutionResult, *_ = _models()
    request = _request()
    result = ExecutionResult(
        execution_id=request.execution_id,
        exit_code=0,
        stdout=b"ok",
        stderr=b"",
        timed_out=False,
        cancelled=False,
        output_truncated=False,
    )

    with pytest.raises(ValidationError):
        request.argv = ("other",)
    with pytest.raises(ValidationError):
        request.model_copy(update={"cwd": "../outside"})
    with pytest.raises(ValidationError):
        ExecutionResult.model_validate(
            {**result.model_dump(), "stdout": "not-bytes"},
        )
    with pytest.raises(ValidationError):
        ExecutionResult.model_validate(
            {**result.model_dump(), "unknown": True},
        )


@pytest.mark.parametrize("field", ["execution_id", "run_id", "capability_id"])
@pytest.mark.parametrize("value", ["", "   ", "not-a-uuid"])
def test_request_rejects_invalid_identifiers(field: str, value: str) -> None:
    with pytest.raises(ValidationError):
        _request(**{field: value})


@pytest.mark.parametrize(
    "argv",
    [(), ("",), ("python", "bad\x00arg"), ("python", "bad\narg"), ("python", 3)],
)
def test_request_rejects_invalid_argv(argv: object) -> None:
    with pytest.raises(ValidationError):
        _request(argv=argv)


@pytest.mark.parametrize(
    "cwd",
    [
        "",
        "C:\\absolute",
        "C:relative",
        "\\\\server\\share",
        "\\\\?\\C:\\device",
        "\\\\.\\pipe\\docker_engine",
        "/absolute",
        "../outside",
        "src/../../outside",
        "src:stream",
        "bad\x00path",
        "bad\npath",
    ],
)
def test_request_rejects_unsafe_cwd(cwd: str) -> None:
    with pytest.raises(ValidationError):
        _request(cwd=cwd)


def test_request_rejects_invalid_mount_mode_and_resource_limits() -> None:
    _ExecutionRequest, _ExecutionResult, max_stdin, max_timeout, max_output = _models()
    invalid = (
        {"mount_mode": "host_write"},
        {"timeout_seconds": 0},
        {"timeout_seconds": max_timeout + 1},
        {"max_output_bytes": 0},
        {"max_output_bytes": max_output + 1},
        {"stdin": b"x" * (max_stdin + 1)},
    )
    for changes in invalid:
        with pytest.raises(ValidationError):
            _request(**changes)


def test_result_distinguishes_normal_timeout_and_cancel_states() -> None:
    _ExecutionRequest, ExecutionResult, *_ = _models()
    execution_id = str(uuid4())
    normal = ExecutionResult(
        execution_id=execution_id,
        exit_code=7,
        stdout=b"",
        stderr=b"failed",
        timed_out=False,
        cancelled=False,
        output_truncated=False,
    )
    assert normal.exit_code == 7

    for changes in (
        {"exit_code": 0, "timed_out": True},
        {"exit_code": 0, "cancelled": True},
        {"exit_code": None, "timed_out": False, "cancelled": False},
        {"exit_code": None, "timed_out": True, "cancelled": True},
    ):
        with pytest.raises(ValidationError):
            ExecutionResult(
                execution_id=execution_id,
                stdout=b"",
                stderr=b"",
                output_truncated=False,
                **changes,
            )
