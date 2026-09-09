from __future__ import annotations

import inspect
from pathlib import Path
from uuid import uuid4

import pytest

from agent_foundations.chat.models import PermissionMode
from agent_foundations.domain.model import ModelResponse
from agent_foundations.domain.tool import ToolCall
from agent_foundations.planning.tools import PlanningToolExecutor
from agent_foundations.providers.fake import FakeModelProvider
from agent_foundations.runtime.agent import PlanningMode
from agent_foundations.runtime.redaction import Redactor
from agent_foundations.runtime.sinks import JsonlEventSink
from agent_foundations.security.models import PermissionProfileName


@pytest.mark.asyncio
async def test_chat_runtime_registers_optional_planning_tools(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent_foundations.cli import main

    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "README.md").write_text("# fixture\n", encoding="utf-8")
    provider = FakeModelProvider(
        [
            ModelResponse(
                tool_calls=(
                    ToolCall(
                        id="plan-call",
                        name="set_plan",
                        arguments={
                            "goal": "inspect the fixture project",
                            "steps": [
                                {
                                    "step_id": "read",
                                    "description": "list project files",
                                },
                            ],
                        },
                    ),
                ),
            ),
            ModelResponse(content="Optional plan recorded. Ready to answer."),
        ],
    )
    monkeypatch.setenv("AGENT_API_KEY", "test-placeholder")
    monkeypatch.setenv("AGENT_MODEL", "test-model")
    monkeypatch.setattr(main, "build_provider", lambda: provider)

    services = main.build_chat_services(tmp_path)
    await services.repository.initialize()
    conversation = await services.repository.create_conversation(
        title="Optional planning",
        project_root=project_root,
        permission_profile=PermissionProfileName.ASK_ALWAYS,
        permission_mode=PermissionMode.ASK_FOR_ACCESS,
    )
    executor = services.runner._tool_executor_factory(
        conversation,
        str(uuid4()),
    )
    sink = JsonlEventSink(tmp_path / "traces", Redactor(project_root))
    loop = services.runner._runtime_factory(conversation, sink, executor)
    names = {definition.name for definition in loop._registry.definitions()}
    assert {"set_plan", "update_plan_step", "replan"} <= names
    assert loop._config.planning_mode is PlanningMode.DISABLED
    assert isinstance(loop._tool_executor, PlanningToolExecutor)
    factory_source = inspect.getsource(services.runner._runtime_factory)
    assert "PlanningMode.REQUIRED" not in factory_source
    assert "PlanController()" in factory_source


@pytest.mark.asyncio
async def test_chat_plan_survives_second_turn_and_blocks_second_set_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi.testclient import TestClient

    from agent_foundations.cli import main
    from agent_foundations.viewer.app import create_app

    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "README.md").write_text("# fixture\n", encoding="utf-8")
    provider = FakeModelProvider(
        [
            ModelResponse(
                tool_calls=(
                    ToolCall(
                        id="plan-call-1",
                        name="set_plan",
                        arguments={
                            "goal": "inspect the fixture project",
                            "steps": [
                                {
                                    "step_id": "read",
                                    "description": "list project files",
                                },
                            ],
                        },
                    ),
                ),
            ),
            ModelResponse(content="First turn kept the plan."),
            ModelResponse(
                tool_calls=(
                    ToolCall(
                        id="plan-call-2",
                        name="set_plan",
                        arguments={
                            "goal": "a second plan must not be created",
                            "steps": [
                                {
                                    "step_id": "other",
                                    "description": "should fail",
                                },
                            ],
                        },
                    ),
                ),
            ),
            ModelResponse(content="Second turn reused the existing plan."),
        ],
    )
    monkeypatch.setenv("AGENT_API_KEY", "test-placeholder")
    monkeypatch.setenv("AGENT_MODEL", "test-model")
    monkeypatch.setattr(main, "build_provider", lambda: provider)

    traces = tmp_path / "traces"
    services = main.build_chat_services(tmp_path)
    await services.repository.initialize()
    conversation = await services.repository.create_conversation(
        title="Persisted planning",
        project_root=project_root,
        permission_profile=PermissionProfileName.ASK_ALWAYS,
        permission_mode=PermissionMode.ASK_FOR_ACCESS,
    )

    first_session = str(uuid4())
    first_message, _run = await services.repository.begin_run(
        conversation.conversation_id,
        content="Create an optional plan.",
        session_id=first_session,
    )
    await services.runner.run_turn(
        conversation.conversation_id,
        first_session,
        first_message.message_id,
        first_message.content,
    )
    first_run = await services.repository.get_run(first_session)
    assert first_run.status.value == "completed"
    assert first_run.error_code is None

    with TestClient(create_app(traces, chat_services=services)) as client:
        state = client.get(
            f"/api/chat/conversations/{conversation.conversation_id}/state",
        )
    assert state.status_code == 200
    plan = state.json().get("plan")
    assert isinstance(plan, dict)
    plan_id = plan["plan_id"]
    assert plan["goal"] == "inspect the fixture project"
    assert plan["version"] == 1
    assert plan["replan_count"] == 0
    assert plan["max_replans"] == 2
    assert plan["steps"] == [
        {
            "step_id": "read",
            "status": "pending",
            "description": "list project files",
        },
    ]
    assert "evidence_refs" not in plan
    assert "evidence" not in str(plan).casefold()

    second_session = str(uuid4())
    second_message, _run = await services.repository.begin_run(
        conversation.conversation_id,
        content="Try to create another plan.",
        session_id=second_session,
    )
    await services.runner.run_turn(
        conversation.conversation_id,
        second_session,
        second_message.message_id,
        second_message.content,
    )
    second_run = await services.repository.get_run(second_session)
    assert second_run.status.value == "completed"

    failed = [
        message
        for request in provider.requests
        for message in request.messages
        if message.role.value == "tool" and message.name == "set_plan"
    ]
    assert failed
    payload = "\n".join(message.content or "" for message in failed)
    assert "already exists" in payload.casefold() or "PlanError" in payload

    with TestClient(create_app(traces, chat_services=services)) as client:
        again = client.get(
            f"/api/chat/conversations/{conversation.conversation_id}/state",
        )
    assert again.status_code == 200
    assert again.json()["plan"]["plan_id"] == plan_id
    assert again.json()["plan"]["goal"] == "inspect the fixture project"
