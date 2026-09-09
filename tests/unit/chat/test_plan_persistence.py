from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from agent_foundations.chat.models import PermissionMode
from agent_foundations.domain.messages import Role
from agent_foundations.domain.model import ModelResponse
from agent_foundations.domain.tool import ToolCall
from agent_foundations.providers.fake import FakeModelProvider
from agent_foundations.security.models import PermissionProfileName
from agent_foundations.viewer.app import create_app


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    (root / "README.md").write_text("# fixture\n", encoding="utf-8")
    return root


def _set_plan_call(call_id: str, goal: str, step_id: str, description: str) -> ToolCall:
    return ToolCall(
        id=call_id,
        name="set_plan",
        arguments={
            "goal": goal,
            "steps": [{"step_id": step_id, "description": description}],
        },
    )


def _replan_call(call_id: str, version: int, step_id: str) -> ToolCall:
    return ToolCall(
        id=call_id,
        name="replan",
        arguments={
            "plan_version": version,
            "reason": "adjust remaining work",
            "replacement_pending_steps": [
                {"step_id": step_id, "description": f"replacement {step_id}"},
            ],
        },
    )


@pytest.mark.asyncio
async def test_conversation_b_does_not_load_conversation_a_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent_foundations.cli import main

    project_root = _project(tmp_path)
    provider = FakeModelProvider(
        [
            ModelResponse(
                tool_calls=(_set_plan_call("a1", "plan for A", "read", "read A"),),
            ),
            ModelResponse(content="A planned."),
            ModelResponse(
                tool_calls=(_set_plan_call("b1", "plan for B", "read", "read B"),),
            ),
            ModelResponse(content="B planned."),
        ],
    )
    monkeypatch.setenv("AGENT_API_KEY", "test-placeholder")
    monkeypatch.setenv("AGENT_MODEL", "test-model")
    monkeypatch.setattr(main, "build_provider", lambda: provider)

    traces = tmp_path / "traces"
    services = main.build_chat_services(tmp_path)
    await services.repository.initialize()
    conversation_a = await services.repository.create_conversation(
        title="Conversation A",
        project_root=project_root,
        permission_profile=PermissionProfileName.PROJECT_READ_ONLY,
        permission_mode=PermissionMode.PROJECT_READ_ONLY,
    )
    conversation_b = await services.repository.create_conversation(
        title="Conversation B",
        project_root=project_root,
        permission_profile=PermissionProfileName.PROJECT_READ_ONLY,
        permission_mode=PermissionMode.PROJECT_READ_ONLY,
    )

    session_a = str(uuid4())
    message_a, _ = await services.repository.begin_run(
        conversation_a.conversation_id,
        content="plan A",
        session_id=session_a,
    )
    await services.runner.run_turn(
        conversation_a.conversation_id,
        session_a,
        message_a.message_id,
        message_a.content,
    )
    session_b = str(uuid4())
    message_b, _ = await services.repository.begin_run(
        conversation_b.conversation_id,
        content="plan B",
        session_id=session_b,
    )
    await services.runner.run_turn(
        conversation_b.conversation_id,
        session_b,
        message_b.message_id,
        message_b.content,
    )

    with TestClient(create_app(traces, chat_services=services)) as client:
        state_a = client.get(
            f"/api/chat/conversations/{conversation_a.conversation_id}/state",
        ).json()["plan"]
        state_b = client.get(
            f"/api/chat/conversations/{conversation_b.conversation_id}/state",
        ).json()["plan"]
    assert state_a["goal"] == "plan for A"
    assert state_b["goal"] == "plan for B"
    assert state_a["plan_id"] != state_b["plan_id"]


@pytest.mark.asyncio
async def test_replan_count_survives_turn_and_still_enforces_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent_foundations.cli import main

    project_root = _project(tmp_path)
    provider = FakeModelProvider(
        [
            ModelResponse(
                tool_calls=(
                    _set_plan_call("p1", "bounded replan", "one", "first step"),
                ),
            ),
            ModelResponse(tool_calls=(_replan_call("r1", 1, "two"),)),
            ModelResponse(content="Turn one replanned once."),
            ModelResponse(tool_calls=(_replan_call("r2", 2, "three"),)),
            ModelResponse(tool_calls=(_replan_call("r3", 3, "four"),)),
            ModelResponse(content="Turn two hit the replan limit."),
        ],
    )
    monkeypatch.setenv("AGENT_API_KEY", "test-placeholder")
    monkeypatch.setenv("AGENT_MODEL", "test-model")
    monkeypatch.setattr(main, "build_provider", lambda: provider)

    traces = tmp_path / "traces"
    services = main.build_chat_services(tmp_path)
    await services.repository.initialize()
    conversation = await services.repository.create_conversation(
        title="Replan persistence",
        project_root=project_root,
        permission_profile=PermissionProfileName.PROJECT_READ_ONLY,
        permission_mode=PermissionMode.PROJECT_READ_ONLY,
    )

    session_one = str(uuid4())
    message_one, _ = await services.repository.begin_run(
        conversation.conversation_id,
        content="plan then replan",
        session_id=session_one,
    )
    await services.runner.run_turn(
        conversation.conversation_id,
        session_one,
        message_one.message_id,
        message_one.content,
    )
    with TestClient(create_app(traces, chat_services=services)) as client:
        after_one = client.get(
            f"/api/chat/conversations/{conversation.conversation_id}/state",
        ).json()["plan"]
    assert after_one["replan_count"] == 1
    assert after_one["max_replans"] == 2

    session_two = str(uuid4())
    message_two, _ = await services.repository.begin_run(
        conversation.conversation_id,
        content="replan again",
        session_id=session_two,
    )
    await services.runner.run_turn(
        conversation.conversation_id,
        session_two,
        message_two.message_id,
        message_two.content,
    )
    with TestClient(create_app(traces, chat_services=services)) as client:
        after_two = client.get(
            f"/api/chat/conversations/{conversation.conversation_id}/state",
        ).json()["plan"]
    assert after_two["plan_id"] == after_one["plan_id"]
    assert after_two["replan_count"] == 2

    limit_messages = [
        message
        for request in provider.requests
        for message in request.messages
        if message.role is Role.TOOL and message.name == "replan"
    ]
    assert any(
        "PlanReplanLimitError" in (message.content or "")
        or "replan limit" in (message.content or "").casefold()
        for message in limit_messages
    )
