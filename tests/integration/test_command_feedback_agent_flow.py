from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from agent_foundations.chat.models import ChatEventType
from agent_foundations.domain.messages import Role
from agent_foundations.domain.model import ModelRequest, ModelResponse
from agent_foundations.domain.tool import ToolCall
from agent_foundations.execution.fake import FakeBackend
from agent_foundations.execution.models import ByteStreamSink, ExecutionRequest, ExecutionResult
from agent_foundations.providers.fake import FakeModelProvider
from agent_foundations.security.models import PermissionProfileName
from agent_foundations.tools.patch.applier import (
    apply_prepared_patch_atomically,
    prepare_patch,
)
from agent_foundations.tools.patch.models import BaselineEntry
from agent_foundations.tools.patch.validator import parse_and_validate_patch
from agent_foundations.viewer.app import create_app
from tests.unit.tools.patch_test_helpers import sha256_bytes

SECRET = "fixture-secret-raw-output-task20"
FAILING_TEST = 'def test_boom() -> None:\n    assert False\n'
FIXED_TEST = 'def test_boom() -> None:\n    assert True\n'
NODE_ID = "tests/test_fail.py::test_boom"

_FAIL_JUNIT = f"""<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" tests="2" failures="1" errors="0" skipped="0">
    <!-- {SECRET} -->
    <testcase classname="tests.test_fail" name="test_boom" time="0.01">
      <failure message="assert False">AssertionError</failure>
    </testcase>
    <testcase classname="tests.test_ok" name="test_ok" time="0.01"/>
  </testsuite>
</testsuites>
"""

_PASS_JUNIT = f"""<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" tests="2" failures="0" errors="0" skipped="0">
    <!-- {SECRET} -->
    <testcase classname="tests.test_fail" name="test_boom" time="0.01"/>
    <testcase classname="tests.test_ok" name="test_ok" time="0.01"/>
  </testsuite>
</testsuites>
"""


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "fixture-project"
    tests = root / "tests"
    tests.mkdir(parents=True)
    (tests / "test_fail.py").write_text(FAILING_TEST, encoding="utf-8", newline="\n")
    (tests / "test_ok.py").write_text(
        "def test_ok() -> None:\n    assert True\n",
        encoding="utf-8",
        newline="\n",
    )
    (root / "pyproject.toml").write_text("[project]\nname='fixture'\n", encoding="utf-8")
    return root.resolve()


def _diff() -> str:
    return """diff --git a/tests/test_fail.py b/tests/test_fail.py
--- a/tests/test_fail.py
+++ b/tests/test_fail.py
@@ -1,2 +1,2 @@
 def test_boom() -> None:
-    assert False
+    assert True
"""


def _feedback_artifact_id(messages: tuple[Any, ...]) -> str | None:
    for message in reversed(messages):
        if message.role is not Role.TOOL:
            continue
        if message.name != "run_command":
            return None
        try:
            payload = json.loads(message.content or "{}")
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        artifact_id = payload.get("artifact_id")
        exit_code = payload.get("exit_code")
        timed_out = bool(payload.get("timed_out"))
        failed = payload.get("failed")
        failed_count = failed if isinstance(failed, int) else 0
        if not isinstance(artifact_id, str) or not artifact_id:
            return None
        if exit_code not in {0, None} or timed_out or failed_count > 0:
            return artifact_id
        return None
    return None


class FeedbackThenScriptProvider:
    """Scripted model that reads command artifacts before retrying the same argv."""

    def __init__(self, responses: list[ModelResponse]) -> None:
        self._script = FakeModelProvider(responses)
        self.requests = self._script.requests

    async def complete(self, request: ModelRequest) -> ModelResponse:
        artifact_id = _feedback_artifact_id(request.messages)
        if artifact_id is not None:
            self.requests.append(request)
            return ModelResponse(
                tool_calls=(
                    ToolCall(
                        id=f"call-read-feedback-{artifact_id}",
                        name="read_command_output",
                        arguments={
                            "artifact_id": artifact_id,
                            "selector": {
                                "stream": "stdout",
                                "start_line": 1,
                                "line_count": 40,
                            },
                            "reason": "read failing diagnostics before retry",
                        },
                    ),
                ),
            )
        return await self._script.complete(request)


def _serialize_model_input(provider: FakeModelProvider | FeedbackThenScriptProvider) -> str:
    chunks: list[str] = []
    for request in provider.requests:
        chunks.append(request.model_dump_json())
        for message in request.messages:
            chunks.append(message.content or "")
        for tool in request.tools:
            chunks.append(tool.name)
    return "\n".join(chunks)


def _scan_path(path: Path) -> str:
    parts: list[str] = []
    if path.is_file():
        return path.read_text(encoding="utf-8", errors="replace")
    for child in path.rglob("*"):
        if child.is_file():
            parts.append(child.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(parts)


@pytest.mark.asyncio
async def test_fakemodel_correction_uses_feedback_without_raw_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent_foundations.cli import main

    project_root = _project(tmp_path)
    fail_path = project_root / "tests" / "test_fail.py"
    baseline = sha256_bytes(fail_path.read_bytes())
    diff = _diff()
    patch = parse_and_validate_patch(
        diff,
        (BaselineEntry(path="tests/test_fail.py", sha256=baseline),),
        project_root,
    )

    class DualBackend:
        argv_log: list[tuple[str, ...]] = []

        def __init__(self, workspace: Path) -> None:
            self._workspace = workspace

        def _pytest_result(self, request: ExecutionRequest) -> ExecutionResult:
            fail_file = self._workspace / "tests" / "test_fail.py"
            failing = True
            if fail_file.is_file():
                failing = "assert False" in fail_file.read_text(encoding="utf-8")
            stdout = (_FAIL_JUNIT if failing else _PASS_JUNIT).encode("utf-8")
            return ExecutionResult(
                execution_id=request.execution_id,
                exit_code=1 if failing else 0,
                stdout=stdout,
                stderr=b"",
                timed_out=False,
                cancelled=False,
                output_truncated=False,
            )

        async def execute(
            self,
            request: object,
            *,
            output_sink: ByteStreamSink | None = None,
        ) -> ExecutionResult:
            assert isinstance(request, ExecutionRequest)
            type(self).argv_log.append(request.argv)
            if request.mount_mode == "project_write":
                prepared = prepare_patch(patch, self._workspace)
                apply_prepared_patch_atomically(prepared, self._workspace)
                return ExecutionResult(
                    execution_id=request.execution_id,
                    exit_code=0,
                    stdout=b'{"status":"applied"}\n',
                    stderr=b"",
                    timed_out=False,
                    cancelled=False,
                    output_truncated=False,
                )
            return await FakeBackend(result_factory=self._pytest_result).execute(
                request,
                output_sink=output_sink,
            )

        async def cancel(self, execution_id: str) -> None:
            del execution_id

    DualBackend.argv_log = []
    provider = FeedbackThenScriptProvider(
        [
            ModelResponse(
                tool_calls=(
                    ToolCall(
                        id="call-full-gate",
                        name="run_command",
                        arguments={
                            "gate_id": "manifest.python.pytest",
                            "target": "tests",
                            "flags": ["-q"],
                            "cwd": ".",
                            "timeout_seconds": 30,
                        },
                    ),
                ),
            ),
            ModelResponse(
                tool_calls=(
                    ToolCall(
                        id="call-failed-node",
                        name="run_command",
                        arguments={
                            "gate_id": "manifest.python.pytest",
                            "target": NODE_ID,
                            "flags": ["-q"],
                            "cwd": ".",
                            "timeout_seconds": 30,
                        },
                    ),
                ),
            ),
            ModelResponse(
                tool_calls=(
                    ToolCall(
                        id="call-validate",
                        name="validate_patch",
                        arguments={
                            "diff": diff,
                            "baselines": [
                                {"path": "tests/test_fail.py", "sha256": baseline},
                            ],
                        },
                    ),
                ),
            ),
            ModelResponse(
                tool_calls=(
                    ToolCall(
                        id="call-apply",
                        name="apply_patch",
                        arguments={"patch_id": patch.patch_id},
                    ),
                ),
            ),
            ModelResponse(
                tool_calls=(
                    ToolCall(
                        id="call-targeted-green",
                        name="run_command",
                        arguments={
                            "gate_id": "manifest.python.pytest",
                            "target": NODE_ID,
                            "flags": ["-q"],
                            "cwd": ".",
                            "timeout_seconds": 30,
                        },
                    ),
                ),
            ),
            ModelResponse(
                tool_calls=(
                    ToolCall(
                        id="call-affected-regression",
                        name="run_command",
                        arguments={
                            "gate_id": "manifest.python.pytest",
                            "target": "tests",
                            "flags": ["-q"],
                            "cwd": ".",
                            "timeout_seconds": 30,
                        },
                    ),
                ),
            ),
            ModelResponse(content="Targeted green and affected regression passed."),
        ],
    )
    monkeypatch.setenv("AGENT_API_KEY", "test-placeholder")
    monkeypatch.setenv("AGENT_MODEL", "test-model")
    monkeypatch.setattr(main, "build_provider", lambda: provider)
    monkeypatch.setattr(main, "DockerBackend", DualBackend)

    traces = tmp_path / "traces"
    database_path = tmp_path / "chat.sqlite3"
    services = main.build_chat_services(tmp_path)
    await services.repository.initialize()
    conversation = await services.repository.create_conversation(
        title="Command feedback correction",
        project_root=project_root,
        permission_profile=PermissionProfileName.PROJECT_FULL_ACCESS,
    )
    session_id = str(uuid4())
    message, _run = await services.repository.begin_run(
        conversation.conversation_id,
        content="Fix the failing gate using CommandFeedback",
        session_id=session_id,
    )

    sse_text: list[str] = []

    async def collect_sse() -> None:
        async for event in services.broker.subscribe(conversation.conversation_id):
            sse_text.append(event.model_dump_json())
            if event.type in {ChatEventType.RUN_COMPLETED, ChatEventType.RUN_FAILED}:
                return

    collector = asyncio.create_task(collect_sse())
    await asyncio.sleep(0)
    await services.runner.run_turn(
        conversation.conversation_id,
        session_id,
        message.message_id,
        message.content,
    )
    await asyncio.wait_for(collector, timeout=30)

    exposed = {tool.name for tool in provider.requests[0].tools}
    assert {
        "run_command",
        "read_command_output",
        "search_command_output",
        "apply_patch",
        "validate_patch",
    } <= exposed

    pytest_argv = [" ".join(argv) for argv in DualBackend.argv_log if "pytest" in argv]
    assert len(pytest_argv) == 4
    assert "pytest -q tests" in pytest_argv[0]
    assert NODE_ID in pytest_argv[1]
    assert NODE_ID in pytest_argv[2]
    assert "pytest -q tests" in pytest_argv[3]
    assert NODE_ID not in pytest_argv[3]

    first_tool = next(
        message
        for message in provider.requests[1].messages
        if message.role is Role.TOOL
    )
    feedback = json.loads(first_tool.content or "{}")
    assert feedback.get("failed") == 1
    diagnostics = feedback.get("diagnostics") or []
    assert any(item.get("test_id") == NODE_ID for item in diagnostics)
    assert SECRET not in (first_tool.content or "")

    assert fail_path.read_text(encoding="utf-8") == FIXED_TEST

    model_blob = _serialize_model_input(provider)
    sqlite_blob = database_path.read_bytes()
    trace_blob = _scan_path(traces)
    assert SECRET not in model_blob
    assert SECRET.encode() not in sqlite_blob
    assert SECRET not in trace_blob
    assert SECRET not in "\n".join(sse_text)

    with sqlite3.connect(database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'",
            )
        }
        assert "command_output_reads" in tables
        for table in sorted(tables):
            rows = connection.execute(f"SELECT * FROM {table}").fetchall()
            dumped = json.dumps([tuple(row) for row in rows], default=str)
            assert SECRET not in dumped

    app = create_app(traces, chat_services=services)
    with TestClient(app) as client:
        activities = client.get(
            f"/api/chat/conversations/{conversation.conversation_id}/activities",
        )
        messages = client.get(
            f"/api/chat/conversations/{conversation.conversation_id}/messages",
        )
        assert activities.status_code == 200
        assert messages.status_code == 200
        chat_json = activities.text + messages.text
        assert SECRET not in chat_json
        summaries = " ".join(
            str(item.get("result_summary") or "") for item in activities.json()
        )
        assert "run_command" in str(activities.json())
        assert "parser=" in summaries
        assert "artifact=coa_" in summaries
        assert "stdout" not in summaries
        assert SECRET not in summaries
