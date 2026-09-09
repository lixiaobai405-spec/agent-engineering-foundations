from __future__ import annotations

import inspect
import time
from dataclasses import fields, replace
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from agent_foundations.chat.api import ChatServices
from agent_foundations.chat.approvals import ApprovalCoordinator
from agent_foundations.chat.events import ChatEventBroker
from agent_foundations.chat.repository import ConversationRepository
from agent_foundations.chat.runner import ConversationRunner, direct_executor_factory
from agent_foundations.chat.supervisor import RunSupervisor
from agent_foundations.context.budget import ContextBudget
from agent_foundations.context.builder import ContextBuilder
from agent_foundations.domain.model import ModelResponse
from agent_foundations.providers.fake import FakeModelProvider
from agent_foundations.runtime.agent import AgentConfig
from agent_foundations.runtime.loop import AgentLoop
from agent_foundations.runtime.redaction import Redactor
from agent_foundations.runtime.tool_execution import ToolCallExecutor
from agent_foundations.runtime.trace import EventSink
from agent_foundations.viewer.app import create_app
from tests.unit.tools.registry_helpers import readonly_tool_registry


class RecordingSweeper:
    def __init__(self) -> None:
        self.expired_calls = 0
        self.pending_calls = 0

    def sweep_expired(self) -> None:
        self.expired_calls += 1

    def sweep_pending_delete(self) -> None:
        self.pending_calls += 1


def _runtime_factory(provider: FakeModelProvider) -> Any:
    def factory(
        conversation: Any,
        event_sink: EventSink,
        tool_executor: ToolCallExecutor,
    ) -> AgentLoop:
        return AgentLoop(
            provider=provider,
            registry=readonly_tool_registry(Path(conversation.project_root)),
            context_builder=ContextBuilder(ContextBudget()),
            event_sink=event_sink,
            config=AgentConfig(max_steps=5),
            tool_executor=tool_executor,
        )

    return factory


def _require_sweep_fields() -> None:
    names = {item.name for item in fields(ChatServices)}
    assert "retention" in names
    assert "artifact_sweep_interval_seconds" in names


def _services(tmp_path: Path, **overrides: Any) -> ChatServices:
    repository = ConversationRepository(tmp_path / "chat.sqlite3")
    broker = ChatEventBroker()
    provider = FakeModelProvider([ModelResponse(content="ok")])
    runner = ConversationRunner(
        repository=repository,
        broker=broker,
        runtime_factory=_runtime_factory(provider),
        trace_dir=tmp_path / "traces",
        redactor_factory=lambda conversation: Redactor(Path(conversation.project_root)),
        tool_executor_factory=direct_executor_factory,
    )
    services = ChatServices(
        repository=repository,
        broker=broker,
        runner=runner,
        supervisor=RunSupervisor(),
        coordinator=ApprovalCoordinator(repository, broker),
    )
    if overrides:
        services = replace(services, **overrides)
    return services


def test_chat_services_sweep_fields_have_safe_defaults(tmp_path: Path) -> None:
    from agent_foundations.chat import api as chat_api

    services = _services(tmp_path)
    assert getattr(services, "retention", "missing") is None
    assert getattr(services, "artifact_sweep_interval_seconds", None) == 3600.0
    assert getattr(chat_api, "ARTIFACT_SWEEP_INTERVAL_SECONDS", None) == 3600.0


def test_lifespan_sweeps_once_on_startup(tmp_path: Path) -> None:
    _require_sweep_fields()
    sweeper = RecordingSweeper()
    services = _services(
        tmp_path,
        retention=sweeper,
        artifact_sweep_interval_seconds=0.0,
    )
    with TestClient(create_app(tmp_path / "traces", chat_services=services)):
        assert sweeper.expired_calls >= 1
        assert sweeper.pending_calls >= 1
    startup_expired = sweeper.expired_calls
    time.sleep(0.08)
    assert sweeper.expired_calls == startup_expired


def test_lifespan_does_not_sweep_when_retention_is_none(tmp_path: Path) -> None:
    services = _services(tmp_path)
    assert getattr(services, "retention", "missing") is None
    with TestClient(create_app(tmp_path / "traces", chat_services=services)) as client:
        assert client.get("/api/chat/conversations").status_code == 200
        missing = client.get("/api/chat/artifacts/usage")
        assert missing.status_code == 404
        assert str(missing.json().get("detail", "")).lower() == "not found"


def test_periodic_sweep_runs_after_interval_and_stops_on_exit(tmp_path: Path) -> None:
    _require_sweep_fields()
    sweeper = RecordingSweeper()
    services = _services(
        tmp_path,
        retention=sweeper,
        artifact_sweep_interval_seconds=0.05,
    )
    with TestClient(create_app(tmp_path / "traces", chat_services=services)):
        deadline = time.monotonic() + 1.0
        while sweeper.expired_calls < 2 and time.monotonic() < deadline:
            time.sleep(0.02)
        assert sweeper.expired_calls >= 2
    stopped = sweeper.expired_calls
    time.sleep(0.12)
    assert sweeper.expired_calls == stopped


def test_build_chat_services_passes_sweeper() -> None:
    from agent_foundations.cli import main as cli_main

    source = inspect.getsource(cli_main.build_chat_services)
    block = source[source.index("return ChatServices(") :]
    assert "retention=retention" in block
