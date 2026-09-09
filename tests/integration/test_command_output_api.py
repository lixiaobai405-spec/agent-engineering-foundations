from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from agent_foundations.chat.approvals import ApprovalCoordinator
from agent_foundations.chat.events import ChatEventBroker
from agent_foundations.chat.models import ChatToolActivity, ToolActivityStatus
from agent_foundations.chat.repository import ConversationRepository
from agent_foundations.chat.runner import ConversationRunner, direct_executor_factory
from agent_foundations.chat.supervisor import RunSupervisor
from agent_foundations.command_output.store import CommandArtifactStore
from agent_foundations.context.budget import ContextBudget
from agent_foundations.context.builder import ContextBuilder
from agent_foundations.domain.model import ModelResponse
from agent_foundations.durable.models import DurableRun, DurableRunStatus
from agent_foundations.durable.repository import DurableRunRepository
from agent_foundations.providers.fake import FakeModelProvider
from agent_foundations.runtime.agent import AgentConfig
from agent_foundations.runtime.loop import AgentLoop
from agent_foundations.runtime.redaction import Redactor
from agent_foundations.runtime.tool_execution import ToolCallExecutor
from agent_foundations.runtime.trace import EventSink
from agent_foundations.security.models import PermissionProfileName
from agent_foundations.viewer.app import create_app
from agent_foundations.viewer.stream import EventBroker
from tests.unit.tools.registry_helpers import readonly_tool_registry

SECRET = "sk-test_placeholder_not_real"
NOW = datetime(2026, 8, 26, 8, 0, tzinfo=UTC)


def _require_chat_api() -> Any:
    from agent_foundations.chat.api import ChatServices, create_chat_router

    return ChatServices, create_chat_router


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


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    (root / "README.md").write_text("hello\n", encoding="utf-8")
    return root


@pytest.fixture
def api_stack(
    tmp_path: Path,
    project_root: Path,
) -> Iterator[tuple[Any, ConversationRepository, Path, Path]]:
    ChatServices, _ = _require_chat_api()
    database_path = tmp_path / "state.sqlite3"
    repository = ConversationRepository(database_path)
    asyncio.run(repository.initialize())
    broker = ChatEventBroker()
    supervisor = RunSupervisor()
    provider = FakeModelProvider([ModelResponse(content="ok")])
    runner = ConversationRunner(
        repository=repository,
        broker=broker,
        runtime_factory=_runtime_factory(provider),
        trace_dir=tmp_path / "traces",
        redactor_factory=lambda conversation: Redactor(Path(conversation.project_root)),
        tool_executor_factory=direct_executor_factory,
        durable_repository=DurableRunRepository(database_path),
    )
    from agent_foundations.command_output.access import CommandOutputDownloadTicketStore
    from agent_foundations.command_output.repository import CommandArtifactRepository

    artifacts = CommandArtifactRepository.from_path(database_path)
    asyncio.run(artifacts.initialize())
    store = CommandArtifactStore(tmp_path / "artifacts", repository=artifacts)
    tickets = CommandOutputDownloadTicketStore()
    services = ChatServices(
        repository=repository,
        broker=broker,
        runner=runner,
        supervisor=supervisor,
        coordinator=ApprovalCoordinator(repository, broker),
        command_artifact_store=store,
        command_artifact_repository=artifacts,
        command_output_tickets=tickets,
    )
    yield services, repository, database_path, project_root
    asyncio.run(supervisor.shutdown())


def _client(services: Any, tmp_path: Path) -> TestClient:
    app = create_app(tmp_path / "traces", EventBroker(), chat_services=services)
    return TestClient(app)


async def _seed_artifact(
    *,
    repository: ConversationRepository,
    database_path: Path,
    project_root: Path,
    tmp_path: Path,
    secret: str = SECRET,
) -> tuple[str, str, str]:
    conversation = await repository.create_conversation(
        title="Command feedback",
        project_root=project_root,
        permission_profile=PermissionProfileName.PROJECT_FULL_ACCESS,
    )
    _user, run = await repository.begin_run(
        conversation.conversation_id,
        content="inspect failing gate",
        session_id="cccccccc-cccc-4ccc-8ccc-cccccccccccc",
    )
    durable = DurableRunRepository(database_path)
    await durable.initialize()
    await durable.create_run(
        DurableRun(
            run_id=run.session_id,
            project_root=str(project_root),
            status=DurableRunStatus.COMPLETED,
            schema_version=1,
            state_version=0,
            attempt=1,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    from agent_foundations.command_output.repository import CommandArtifactRepository

    artifacts = CommandArtifactRepository.from_path(database_path)
    await artifacts.initialize()
    store = CommandArtifactStore(tmp_path / "artifacts", repository=artifacts)
    artifact = store.write(
        stdout=b"ok\n",
        stderr=f"Authorization: Bearer {secret}\n".encode(),
        run_id=UUID(run.session_id),
    )
    await repository.upsert_tool_activity(
        ChatToolActivity(
            conversation_id=conversation.conversation_id,
            session_id=run.session_id,
            tool_call_id="call-run-command",
            tool_name="run_command",
            status=ToolActivityStatus.COMPLETED,
            arguments_summary="python -m pytest tests",
            result_summary=f"exit=1 failed=1 parser=complete artifact={artifact.artifact_id}",
            started_at=NOW,
            finished_at=NOW,
            last_event_id="11111111-1111-4111-8111-111111111111",
        )
    )
    return conversation.conversation_id, run.session_id, artifact.artifact_id


def test_default_projection_hides_logs_and_pages_are_sanitized(
    tmp_path: Path,
    api_stack: tuple[Any, ConversationRepository, Path, Path],
) -> None:
    services, repository, database_path, project_root = api_stack
    conversation_id, session_id, artifact_id = asyncio.run(
        _seed_artifact(
            repository=repository,
            database_path=database_path,
            project_root=project_root,
            tmp_path=tmp_path,
        )
    )
    with _client(services, tmp_path) as client:
        activities = client.get(f"/api/chat/conversations/{conversation_id}/activities")
        assert activities.status_code == 200
        body = activities.json()
        dumped = json.dumps(body)
        assert SECRET not in dumped
        assert "sk-test_placeholder_not_real" not in dumped
        summary = body[0]["result_summary"]
        assert artifact_id in summary
        assert len(summary) <= 240

        page = client.get(
            f"/api/chat/conversations/{conversation_id}/runs/{session_id}"
            f"/command-artifacts/{artifact_id}/pages",
            params={"stream": "stderr", "start_line": 1, "line_count": 20},
        )
        assert page.status_code == 200
        payload = page.json()
        text = json.dumps(payload)
        assert SECRET not in text
        assert "sk-test_placeholder_not_real" not in text
        assert "[REDACTED]" in text
        assert payload["artifact_id"] == artifact_id
        before = client.get(f"/api/chat/conversations/{conversation_id}/activities")
        after_count = len(before.json())
        assert after_count == 1


def test_pages_require_explicit_stream_and_do_not_default_to_stderr(
    tmp_path: Path,
    api_stack: tuple[Any, ConversationRepository, Path, Path],
) -> None:
    services, repository, database_path, project_root = api_stack
    conversation_id, session_id, artifact_id = asyncio.run(
        _seed_artifact(
            repository=repository,
            database_path=database_path,
            project_root=project_root,
            tmp_path=tmp_path,
        )
    )
    pages_url = (
        f"/api/chat/conversations/{conversation_id}/runs/{session_id}"
        f"/command-artifacts/{artifact_id}/pages"
    )
    with _client(services, tmp_path) as client:
        missing = client.get(pages_url, params={"start_line": 1, "line_count": 20})
        assert missing.status_code == 422
        missing_text = missing.text
        assert SECRET not in missing_text
        assert "[REDACTED]" not in missing_text
        assert "Authorization" not in missing_text

        stdout = client.get(
            pages_url,
            params={"stream": "stdout", "start_line": 1, "line_count": 20},
        )
        assert stdout.status_code == 200
        stdout_lines = stdout.json()["lines"]
        assert "ok" in stdout_lines
        assert SECRET not in json.dumps(stdout.json())

        stderr = client.get(
            pages_url,
            params={"stream": "stderr", "start_line": 1, "line_count": 20},
        )
        assert stderr.status_code == 200
        stderr_text = json.dumps(stderr.json())
        assert SECRET not in stderr_text
        assert "[REDACTED]" in stderr_text

        illegal = client.get(
            pages_url,
            params={"stream": "both", "start_line": 1, "line_count": 20},
        )
        assert illegal.status_code == 400
        assert "SELECTOR_INVALID" in str(illegal.json().get("detail", illegal.json()))
        assert SECRET not in illegal.text


def test_raw_download_ticket_origin_expiry_replay_and_ownership(
    tmp_path: Path,
    api_stack: tuple[Any, ConversationRepository, Path, Path],
) -> None:
    services, repository, database_path, project_root = api_stack
    conversation_id, session_id, artifact_id = asyncio.run(
        _seed_artifact(
            repository=repository,
            database_path=database_path,
            project_root=project_root,
            tmp_path=tmp_path,
        )
    )
    ticket_url = (
        f"/api/chat/conversations/{conversation_id}/runs/{session_id}"
        f"/command-artifacts/{artifact_id}/download-tickets"
    )
    with _client(services, tmp_path) as client:
        missing_origin = client.post(ticket_url)
        assert missing_origin.status_code in {403, 400}
        assert "ticket" not in missing_origin.text.lower() or missing_origin.status_code >= 400

        evil = client.post(ticket_url, headers={"Origin": "https://evil.example"})
        assert evil.status_code == 403

        created = client.post(ticket_url, headers={"Origin": "http://127.0.0.1"})
        assert created.status_code == 201
        ticket = created.json()["ticket"]
        assert "artifact" not in ticket
        assert "\\" not in ticket
        assert "/" not in ticket or ticket.count("/") == 0

        download = client.get(
            f"/api/chat/conversations/{conversation_id}/runs/{session_id}"
            f"/command-artifacts/{artifact_id}/raw",
            params={"ticket": ticket},
            headers={"Origin": "http://127.0.0.1"},
        )
        assert download.status_code == 200
        raw = download.content
        assert SECRET.encode() in raw

        replay = client.get(
            f"/api/chat/conversations/{conversation_id}/runs/{session_id}"
            f"/command-artifacts/{artifact_id}/raw",
            params={"ticket": ticket},
            headers={"Origin": "http://127.0.0.1"},
        )
        assert replay.status_code in {403, 404, 410}

        other = client.post(
            "/api/chat/conversations",
            json={
                "title": "Other",
                "project_root": str(project_root),
                "permission_profile": "PROJECT_FULL_ACCESS",
            },
        )
        other_id = other.json()["conversation_id"]
        stolen = client.post(
            f"/api/chat/conversations/{other_id}/runs/{session_id}"
            f"/command-artifacts/{artifact_id}/download-tickets",
            headers={"Origin": "http://127.0.0.1"},
        )
        assert stolen.status_code in {403, 404}
        dumped = json.dumps(created.json())
        assert SECRET not in dumped
        assert "ticket" in created.json()


def test_cross_run_page_is_denied(
    tmp_path: Path,
    api_stack: tuple[Any, ConversationRepository, Path, Path],
) -> None:
    services, repository, database_path, project_root = api_stack
    conversation_id, session_id, artifact_id = asyncio.run(
        _seed_artifact(
            repository=repository,
            database_path=database_path,
            project_root=project_root,
            tmp_path=tmp_path,
        )
    )
    foreign_run = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
    with _client(services, tmp_path) as client:
        page = client.get(
            f"/api/chat/conversations/{conversation_id}/runs/{foreign_run}"
            f"/command-artifacts/{artifact_id}/pages",
            params={"stream": "stderr", "start_line": 1, "line_count": 8},
        )
        assert page.status_code in {403, 404}
        assert SECRET not in page.text
        detail = str(page.json().get("detail", page.json()))
        assert "ARTIFACT_SCOPE_DENIED" in detail


def _sweeper_services(
    tmp_path: Path,
    project_root: Path,
    *,
    clock: Any | None = None,
    interval: float = 0.0,
) -> tuple[Any, ConversationRepository, Path, Any]:
    from dataclasses import fields, replace
    from datetime import timedelta

    from agent_foundations.command_output.repository import CommandArtifactRepository
    from agent_foundations.command_output.retention import ArtifactRetentionSweeper

    names = {item.name for item in fields(_require_chat_api()[0])}
    assert "retention" in names
    ChatServices, _ = _require_chat_api()
    database_path = tmp_path / "state.sqlite3"
    repository = ConversationRepository(database_path)
    asyncio.run(repository.initialize())
    broker = ChatEventBroker()
    supervisor = RunSupervisor()
    provider = FakeModelProvider([ModelResponse(content="ok")])
    runner = ConversationRunner(
        repository=repository,
        broker=broker,
        runtime_factory=_runtime_factory(provider),
        trace_dir=tmp_path / "traces",
        redactor_factory=lambda conversation: Redactor(Path(conversation.project_root)),
        tool_executor_factory=direct_executor_factory,
        durable_repository=DurableRunRepository(database_path),
    )
    from agent_foundations.command_output.access import CommandOutputDownloadTicketStore

    artifacts = CommandArtifactRepository.from_path(database_path)
    asyncio.run(artifacts.initialize())
    store = CommandArtifactStore(tmp_path / "artifacts", repository=artifacts)
    tickets = CommandOutputDownloadTicketStore()
    services = ChatServices(
        repository=repository,
        broker=broker,
        runner=runner,
        supervisor=supervisor,
        coordinator=ApprovalCoordinator(repository, broker),
        command_artifact_store=store,
        command_artifact_repository=artifacts,
        command_output_tickets=tickets,
    )
    sweeper = ArtifactRetentionSweeper(
        store,
        artifacts,
        retention=timedelta(days=7),
        clock=clock or (lambda: NOW),
    )
    services = replace(
        services,
        retention=sweeper,
        artifact_sweep_interval_seconds=interval,
    )
    return services, repository, database_path, sweeper


def test_artifact_usage_sweep_and_origin_gates(
    tmp_path: Path,
    project_root: Path,
) -> None:
    from datetime import timedelta

    current = {"now": NOW}

    def clock() -> datetime:
        return current["now"]

    services, repository, database_path, _sweeper = _sweeper_services(
        tmp_path,
        project_root,
        clock=clock,
        interval=0.0,
    )
    _conversation_id, session_id, _seeded_id = asyncio.run(
        _seed_artifact(
            repository=repository,
            database_path=database_path,
            project_root=project_root,
            tmp_path=tmp_path,
        )
    )
    from agent_foundations.command_output.repository import CommandArtifactRepository
    from agent_foundations.command_output.store import CommandArtifactStore

    artifacts = services.command_artifact_repository
    store = services.command_artifact_store
    assert isinstance(artifacts, CommandArtifactRepository)
    assert isinstance(store, CommandArtifactStore)

    with _client(services, tmp_path) as client:
        usage = client.get("/api/chat/artifacts/usage")
        assert usage.status_code == 200
        body = usage.json()
        assert body["capacity_bytes"] == 512 * 1024 * 1024
        assert body["retention_seconds"] == 604800
        assert isinstance(body["used_bytes"], int)
        assert SECRET not in json.dumps(body)

        evil = client.get(
            "/api/chat/artifacts/usage",
            headers={"Origin": "https://evil.example"},
        )
        assert evil.status_code == 403
        assert evil.json()["detail"] == "ARTIFACT_SCOPE_DENIED"

        missing_origin = client.post("/api/chat/artifacts/sweep")
        assert missing_origin.status_code == 403
        assert missing_origin.json()["detail"] == "ARTIFACT_SCOPE_DENIED"

        evil_post = client.post(
            "/api/chat/artifacts/sweep",
            headers={"Origin": "https://evil.example"},
        )
        assert evil_post.status_code == 403
        assert evil_post.json()["detail"] == "ARTIFACT_SCOPE_DENIED"

        expired = store.write(
            stdout=b"old\n",
            stderr=b"",
            run_id=UUID(session_id),
            created_at=NOW,
        )
        artifacts.mark_retained(expired.artifact_id)
        assert artifacts.fetch_artifact(expired.artifact_id).retention_status.value == "retained"
        current["now"] = NOW + timedelta(days=8)
        swept = client.post(
            "/api/chat/artifacts/sweep",
            headers={"Origin": "http://127.0.0.1"},
        )
        assert swept.status_code == 200
        assert swept.json() == {"ok": True}
        assert artifacts.fetch_artifact(expired.artifact_id).retention_status.value == "evicted"


def test_artifact_purge_is_run_scoped_and_idempotent(
    tmp_path: Path,
    project_root: Path,
) -> None:
    from uuid import uuid4

    services, repository, database_path, _sweeper = _sweeper_services(
        tmp_path,
        project_root,
        interval=0.0,
    )
    _conversation_id, session_id, artifact_id = asyncio.run(
        _seed_artifact(
            repository=repository,
            database_path=database_path,
            project_root=project_root,
            tmp_path=tmp_path,
        )
    )
    other_run = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
    durable = DurableRunRepository(database_path)
    asyncio.run(durable.initialize())
    asyncio.run(
        durable.create_run(
            DurableRun(
                run_id=other_run,
                project_root=str(project_root),
                status=DurableRunStatus.COMPLETED,
                schema_version=1,
                state_version=0,
                attempt=1,
                created_at=NOW,
                updated_at=NOW,
            )
        )
    )
    store = services.command_artifact_store
    other = store.write(
        stdout=b"keep\n",
        stderr=b"",
        run_id=UUID(other_run),
        effect_id=uuid4(),
        execution_id=uuid4(),
        created_at=NOW,
    )
    from agent_foundations.command_output.repository import CommandArtifactRepository

    artifacts = services.command_artifact_repository
    assert isinstance(artifacts, CommandArtifactRepository)

    empty_run = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
    with _client(services, tmp_path) as client:
        purged = client.post(
            f"/api/chat/artifacts/runs/{session_id}/purge",
            headers={"Origin": "http://127.0.0.1"},
        )
        assert purged.status_code == 200
        payload = purged.json()
        assert payload["ok"] is True
        assert artifact_id in payload["purged_artifact_ids"]
        assert other.artifact_id not in payload["purged_artifact_ids"]
        assert artifacts.fetch_artifact(artifact_id).retention_status.value == "deleted"
        assert store.directory_for(other.artifact_id).exists()

        empty = client.post(
            f"/api/chat/artifacts/runs/{empty_run}/purge",
            headers={"Origin": "http://127.0.0.1"},
        )
        assert empty.status_code == 200
        assert empty.json() == {"ok": True, "purged_artifact_ids": []}

        bad = client.post(
            "/api/chat/artifacts/runs/not-a-uuid/purge",
            headers={"Origin": "http://127.0.0.1"},
        )
        assert bad.status_code == 422


def test_artifact_control_plane_404_without_sweeper(
    tmp_path: Path,
    api_stack: tuple[Any, ConversationRepository, Path, Path],
) -> None:
    services, _repository, _database_path, _project_root = api_stack
    with _client(services, tmp_path) as client:
        usage = client.get("/api/chat/artifacts/usage")
        assert usage.status_code == 404
        assert str(usage.json().get("detail", "")).lower() == "not found"
        sweep = client.post(
            "/api/chat/artifacts/sweep",
            headers={"Origin": "http://127.0.0.1"},
        )
        assert sweep.status_code == 404
        assert str(sweep.json().get("detail", "")).lower() == "not found"
        purge = client.post(
            "/api/chat/artifacts/runs/cccccccc-cccc-4ccc-8ccc-cccccccccccc/purge",
            headers={"Origin": "http://127.0.0.1"},
        )
        assert purge.status_code == 404
        assert str(purge.json().get("detail", "")).lower() == "not found"

