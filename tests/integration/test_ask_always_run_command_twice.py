from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import uuid4

import pytest

from agent_foundations.chat.api import ChatServices
from agent_foundations.chat.models import (
    ApprovalDecision,
    ApprovalRequest,
    ChatEventType,
    PermissionMode,
)
from agent_foundations.domain.model import ModelResponse
from agent_foundations.domain.tool import ToolCall
from agent_foundations.execution.fake import FakeBackend
from agent_foundations.execution.models import ByteStreamSink, ExecutionRequest, ExecutionResult
from agent_foundations.providers.fake import FakeModelProvider
from agent_foundations.security.models import PermissionProfileName


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "fixture-project"
    tests = root / "tests"
    tests.mkdir(parents=True)
    (tests / "test_ok.py").write_text(
        "def test_ok() -> None:\n    assert True\n",
        encoding="utf-8",
        newline="\n",
    )
    (root / "pyproject.toml").write_text("[project]\nname='fixture'\n", encoding="utf-8")
    return root.resolve()


class CommandFakeBackend:
    def __init__(self, workspace: Path, sandbox_manifest: object = None) -> None:
        del sandbox_manifest
        self._inner = FakeBackend(
            result_factory=lambda request: ExecutionResult(
                execution_id=request.execution_id,
                exit_code=0,
                stdout=b"1 passed\n",
                stderr=b"",
                timed_out=False,
                cancelled=False,
                output_truncated=False,
            ),
        )
        self.workspace = workspace

    async def execute(
        self,
        request: object,
        *,
        output_sink: ByteStreamSink | None = None,
    ) -> ExecutionResult:
        assert isinstance(request, ExecutionRequest)
        return await self._inner.execute(request, output_sink=output_sink)

    async def cancel(self, execution_id: str) -> None:
        await self._inner.cancel(execution_id)


async def _wait_for_pending_approval(
    services: ChatServices,
    conversation_id: str,
) -> ApprovalRequest:
    approval = None
    for _ in range(400):
        _latest, approval = await services.repository.get_conversation_state(
            conversation_id,
        )
        if approval is not None:
            return approval
        await asyncio.sleep(0.01)
    raise AssertionError("expected a pending run_command approval")


@pytest.mark.asyncio
async def test_ask_always_run_command_asks_twice_in_same_conversation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent_foundations.cli import main

    project_root = _project(tmp_path)
    provider = FakeModelProvider(
        [
            ModelResponse(
                tool_calls=(
                    ToolCall(
                        id="cmd-call-1",
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
            ModelResponse(content="First command finished."),
            ModelResponse(
                tool_calls=(
                    ToolCall(
                        id="cmd-call-2",
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
            ModelResponse(content="Second command finished."),
        ],
    )
    monkeypatch.setenv("AGENT_API_KEY", "test-placeholder")
    monkeypatch.setenv("AGENT_MODEL", "test-model")
    monkeypatch.setattr(main, "build_provider", lambda: provider)
    monkeypatch.setattr(main, "DockerBackend", CommandFakeBackend)

    services = main.build_chat_services(tmp_path)
    await services.repository.initialize()
    conversation = await services.repository.create_conversation(
        title="ASK_ALWAYS commands",
        project_root=project_root,
        permission_profile=PermissionProfileName.ASK_ALWAYS,
        permission_mode=PermissionMode.ASK_FOR_ACCESS,
    )

    requested: list[str] = []

    async def collect_requested() -> None:
        async for event in services.broker.subscribe(conversation.conversation_id):
            if event.type is ChatEventType.APPROVAL_REQUESTED:
                requested.append(str(event.data.get("tool_call_id")))
            if event.type in {ChatEventType.RUN_COMPLETED, ChatEventType.RUN_FAILED}:
                if len(requested) >= 2:
                    return

    collector = asyncio.create_task(collect_requested())
    await asyncio.sleep(0)

    first_session = str(uuid4())
    first_message, _first_run = await services.repository.begin_run(
        conversation.conversation_id,
        content="Run the first pytest command",
        session_id=first_session,
    )
    first_task = asyncio.create_task(
        services.runner.run_turn(
            conversation.conversation_id,
            first_session,
            first_message.message_id,
            first_message.content,
        ),
    )
    first_approval = await _wait_for_pending_approval(
        services,
        conversation.conversation_id,
    )
    assert first_approval.tool_name == "run_command"
    assert first_approval.tool_call_id == "cmd-call-1"
    await services.coordinator.resolve(
        first_approval.approval_id,
        ApprovalDecision.APPROVE,
    )
    await asyncio.wait_for(first_task, timeout=30)

    second_session = str(uuid4())
    second_message, _second_run = await services.repository.begin_run(
        conversation.conversation_id,
        content="Run the second pytest command",
        session_id=second_session,
    )
    second_task = asyncio.create_task(
        services.runner.run_turn(
            conversation.conversation_id,
            second_session,
            second_message.message_id,
            second_message.content,
        ),
    )
    second_approval = await _wait_for_pending_approval(
        services,
        conversation.conversation_id,
    )
    assert second_approval.tool_name == "run_command"
    assert second_approval.tool_call_id == "cmd-call-2"
    assert second_approval.approval_id != first_approval.approval_id
    await services.coordinator.resolve(
        second_approval.approval_id,
        ApprovalDecision.APPROVE,
    )
    await asyncio.wait_for(second_task, timeout=30)
    await asyncio.wait_for(collector, timeout=5)

    assert requested == ["cmd-call-1", "cmd-call-2"]
    first_run = await services.repository.get_run(first_session)
    second_run = await services.repository.get_run(second_session)
    assert first_run.status.value == "completed"
    assert second_run.status.value == "completed"
