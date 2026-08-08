from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from agent_foundations.chat.events import ChatEventBroker
from agent_foundations.chat.models import (
    ChatEvent,
    ChatEventType,
    Conversation,
    MessageRole,
    PermissionMode,
    RunStatus,
)
from agent_foundations.chat.repository import ConversationRepository
from agent_foundations.context.budget import ContextBudget
from agent_foundations.context.builder import ContextBuilder
from agent_foundations.domain.messages import Role
from agent_foundations.domain.model import ModelResponse
from agent_foundations.providers.fake import FakeModelProvider
from agent_foundations.runtime.agent import AgentConfig
from agent_foundations.runtime.loop import AgentLoop
from agent_foundations.runtime.redaction import Redactor
from agent_foundations.runtime.tool_execution import ToolCallExecutor
from agent_foundations.runtime.trace import EventSink
from agent_foundations.tools.filesystem.list_directory import ListDirectoryTool
from agent_foundations.tools.filesystem.path_policy import PathPolicy
from agent_foundations.tools.registry import ToolRegistry

CONVERSATION_ID = "11111111-1111-4111-8111-111111111111"
SESSION_ID = "22222222-2222-4222-8222-222222222222"
SESSION_ID_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


def _require_runner_types() -> tuple[Any, Any]:
    try:
        from agent_foundations.chat.runner import (
            ConversationRunner,
            direct_executor_factory,
        )
    except ImportError as exc:
        raise AssertionError(
            f"ConversationRunner module missing: {exc}",
        ) from exc
    return ConversationRunner, direct_executor_factory


class RecordingBroker(ChatEventBroker):
    def __init__(self, repository: ConversationRepository, session_id: str) -> None:
        super().__init__()
        self.events: list[ChatEvent] = []
        self.assistant_committed_before_publish: list[bool] = []
        self._repository = repository
        self._session_id = session_id

    async def publish(self, event: ChatEvent) -> None:
        if event.type is ChatEventType.ASSISTANT_MESSAGE_COMPLETED:
            run = await self._repository.get_run(self._session_id)
            self.assistant_committed_before_publish.append(
                run.status is RunStatus.COMPLETED
                and run.assistant_message_id is not None,
            )
        self.events.append(event)
        await super().publish(event)


async def _prepare_conversation(
    tmp_path: Path,
    *,
    title: str = "Runtime study",
) -> tuple[ConversationRepository, Conversation, Path]:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "README.md").write_text("hello\n", encoding="utf-8")
    database_path = tmp_path / "state" / "chat.sqlite3"
    repository = ConversationRepository(database_path)
    await repository.initialize()
    conversation = await repository.create_conversation(
        title=title,
        project_root=project_root,
        permission_mode=PermissionMode.PROJECT_READ_ONLY,
    )
    return repository, conversation, project_root


def _build_runtime_factory(
    provider: FakeModelProvider,
) -> Any:
    def factory(
        conversation: Conversation,
        event_sink: EventSink,
        tool_executor: ToolCallExecutor,
    ) -> AgentLoop:
        return AgentLoop(
            provider=provider,
            registry=ToolRegistry(
                [ListDirectoryTool(PathPolicy(Path(conversation.project_root)))],
            ),
            context_builder=ContextBuilder(ContextBudget()),
            event_sink=event_sink,
            config=AgentConfig(max_steps=5),
            tool_executor=tool_executor,
        )

    return factory


@pytest.mark.asyncio
async def test_runner_completes_turn_with_history_and_fixed_session(
    tmp_path: Path,
) -> None:
    ConversationRunner, direct_executor_factory = _require_runner_types()
    repository, conversation, project_root = await _prepare_conversation(tmp_path)
    first_message, first_run = await repository.begin_run(
        conversation.conversation_id,
        content="old question",
        session_id=SESSION_ID_B,
    )
    await repository.transition_run(
        first_run.session_id,
        RunStatus.QUEUED,
        RunStatus.RUNNING,
    )
    await repository.complete_run(first_run.session_id, "old answer")

    user_message, run = await repository.begin_run(
        conversation.conversation_id,
        content="new question",
        session_id=SESSION_ID,
    )
    broker = RecordingBroker(repository, SESSION_ID)
    provider = FakeModelProvider([ModelResponse(content="continued answer")])
    runner = ConversationRunner(
        repository=repository,
        broker=broker,
        runtime_factory=_build_runtime_factory(provider),
        trace_dir=tmp_path / "traces",
        redactor_factory=lambda conversation: Redactor(
            Path(conversation.project_root),
        ),
        tool_executor_factory=direct_executor_factory,
    )

    await runner.run_turn(
        conversation.conversation_id,
        SESSION_ID,
        user_message.message_id,
        "new question",
    )

    completed = await repository.get_run(SESSION_ID)
    assert completed.status is RunStatus.COMPLETED
    assert completed.session_id == SESSION_ID
    assert completed.assistant_message_id is not None
    messages = await repository.list_messages(conversation.conversation_id)
    assistant = next(
        message for message in messages if message.message_id == completed.assistant_message_id
    )
    assert assistant.role is MessageRole.ASSISTANT
    assert assistant.content == "continued answer"
    assert assistant.sequence == user_message.sequence + 1

    assert [message.content for message in provider.requests[0].messages] == [
        AgentConfig().system_prompt,
        "old question",
        "old answer",
        "new question",
    ]
    assert provider.requests[0].messages[0].role is Role.SYSTEM
    assert all(
        message.role in {Role.USER, Role.ASSISTANT}
        for message in provider.requests[0].messages[1:]
    )

    event_types = [event.type for event in broker.events]
    assert ChatEventType.RUN_STARTED in event_types
    completed_index = event_types.index(ChatEventType.ASSISTANT_MESSAGE_COMPLETED)
    run_completed_index = event_types.index(ChatEventType.RUN_COMPLETED)
    assert completed_index < run_completed_index
    assert broker.assistant_committed_before_publish == [True]
    assert {event.session_id for event in broker.events} == {SESSION_ID}

    trace_path = tmp_path / "traces" / f"{SESSION_ID}.jsonl"
    assert trace_path.is_file()
    assert completed.trace_path == f"traces/{SESSION_ID}.jsonl"
    assert first_message.content == "old question"


@pytest.mark.asyncio
async def test_runner_provider_failure_marks_failed_without_exposing_text(
    tmp_path: Path,
) -> None:
    ConversationRunner, direct_executor_factory = _require_runner_types()
    repository, conversation, _ = await _prepare_conversation(tmp_path)
    user_message, _ = await repository.begin_run(
        conversation.conversation_id,
        content="will fail",
        session_id=SESSION_ID,
    )
    broker = RecordingBroker(repository, SESSION_ID)
    provider = FakeModelProvider([])
    runner = ConversationRunner(
        repository=repository,
        broker=broker,
        runtime_factory=_build_runtime_factory(provider),
        trace_dir=tmp_path / "traces",
        redactor_factory=lambda conversation: Redactor(
            Path(conversation.project_root),
        ),
        tool_executor_factory=direct_executor_factory,
    )

    await runner.run_turn(
        conversation.conversation_id,
        SESSION_ID,
        user_message.message_id,
        "will fail",
    )

    failed = await repository.get_run(SESSION_ID)
    assert failed.status is RunStatus.FAILED
    assert failed.error_code == "FakeModelExhaustedError"
    failed_events = [
        event for event in broker.events if event.type is ChatEventType.RUN_FAILED
    ]
    assert len(failed_events) == 1
    serialized = failed_events[0].model_dump_json()
    assert "FakeModelExhaustedError" in serialized
    assert "fake model response script is exhausted" not in serialized
    assert "secret" not in serialized.lower() or "error_code" in serialized


@pytest.mark.asyncio
async def test_runner_cancellation_marks_interrupted_and_reraises(
    tmp_path: Path,
) -> None:
    ConversationRunner, direct_executor_factory = _require_runner_types()
    repository, conversation, _ = await _prepare_conversation(tmp_path)
    user_message, _ = await repository.begin_run(
        conversation.conversation_id,
        content="cancel me",
        session_id=SESSION_ID,
    )
    broker = RecordingBroker(repository, SESSION_ID)
    started = asyncio.Event()

    class HangingProvider:
        async def complete(self, request: Any) -> ModelResponse:
            started.set()
            await asyncio.Event().wait()
            return ModelResponse(content="unreachable")

    def factory(
        conversation: Conversation,
        event_sink: EventSink,
        tool_executor: ToolCallExecutor,
    ) -> AgentLoop:
        return AgentLoop(
            provider=HangingProvider(),
            registry=ToolRegistry(
                [ListDirectoryTool(PathPolicy(Path(conversation.project_root)))],
            ),
            context_builder=ContextBuilder(ContextBudget()),
            event_sink=event_sink,
            config=AgentConfig(max_steps=5),
            tool_executor=tool_executor,
        )

    runner = ConversationRunner(
        repository=repository,
        broker=broker,
        runtime_factory=factory,
        trace_dir=tmp_path / "traces",
        redactor_factory=lambda conversation: Redactor(
            Path(conversation.project_root),
        ),
        tool_executor_factory=direct_executor_factory,
    )

    task = asyncio.create_task(
        runner.run_turn(
            conversation.conversation_id,
            SESSION_ID,
            user_message.message_id,
            "cancel me",
        ),
    )
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    interrupted = await repository.get_run(SESSION_ID)
    assert interrupted.status is RunStatus.INTERRUPTED


@pytest.mark.asyncio
async def test_runner_runtime_factory_failure_marks_failed_safely(
    tmp_path: Path,
) -> None:
    ConversationRunner, direct_executor_factory = _require_runner_types()
    repository, conversation, _ = await _prepare_conversation(tmp_path)
    user_message, _ = await repository.begin_run(
        conversation.conversation_id,
        content="factory will fail",
        session_id=SESSION_ID,
    )
    broker = RecordingBroker(repository, SESSION_ID)

    def exploding_factory(
        conversation: Conversation,
        event_sink: EventSink,
        tool_executor: ToolCallExecutor,
    ) -> AgentLoop:
        raise RuntimeError("do-not-leak-secret")

    runner = ConversationRunner(
        repository=repository,
        broker=broker,
        runtime_factory=exploding_factory,
        trace_dir=tmp_path / "traces",
        redactor_factory=lambda conversation: Redactor(
            Path(conversation.project_root),
        ),
        tool_executor_factory=direct_executor_factory,
    )

    await runner.run_turn(
        conversation.conversation_id,
        SESSION_ID,
        user_message.message_id,
        "factory will fail",
    )

    failed = await repository.get_run(SESSION_ID)
    assert failed.status is RunStatus.FAILED
    assert failed.error_code == "RuntimeError"
    assert failed.status not in RunStatus.active()
    failed_events = [
        event for event in broker.events if event.type is ChatEventType.RUN_FAILED
    ]
    assert len(failed_events) == 1
    serialized = failed_events[0].model_dump_json()
    assert "RuntimeError" in serialized
    assert "do-not-leak-secret" not in serialized
    assert "Traceback" not in serialized


class FailingBrokerOnAssistantCompleted(RecordingBroker):
    async def publish(self, event: ChatEvent) -> None:
        if event.type is ChatEventType.ASSISTANT_MESSAGE_COMPLETED:
            raise RuntimeError("publish-assistant-failed")
        await super().publish(event)


class SlowPublishBroker(RecordingBroker):
    def __init__(
        self,
        repository: ConversationRepository,
        session_id: str,
        *,
        publish_started: asyncio.Event,
        release_publish: asyncio.Event,
    ) -> None:
        super().__init__(repository, session_id)
        self._publish_started = publish_started
        self._release_publish = release_publish

    async def publish(self, event: ChatEvent) -> None:
        if event.type is ChatEventType.ASSISTANT_MESSAGE_COMPLETED:
            self._publish_started.set()
            await self._release_publish.wait()
        await super().publish(event)


class SlowCompleteRunRepository:
    def __init__(
        self,
        repository: ConversationRepository,
        *,
        complete_started: asyncio.Event,
        release_complete: asyncio.Event,
    ) -> None:
        self._repository = repository
        self._complete_started = complete_started
        self._release_complete = release_complete

    def __getattr__(self, name: str) -> Any:
        return getattr(self._repository, name)

    async def complete_run(self, session_id: str, answer: str) -> Any:
        self._complete_started.set()
        await self._release_complete.wait()
        return await self._repository.complete_run(session_id, answer)


class FailingListContextRepository:
    def __init__(self, repository: ConversationRepository) -> None:
        self._repository = repository

    def __getattr__(self, name: str) -> Any:
        return getattr(self._repository, name)

    async def list_context_before(
        self,
        conversation_id: str,
        user_message_id: str,
    ) -> list[Any]:
        raise RuntimeError("do-not-leak-context-secret")


@pytest.mark.asyncio
async def test_runner_publish_failure_after_complete_keeps_completed_state(
    tmp_path: Path,
) -> None:
    ConversationRunner, direct_executor_factory = _require_runner_types()
    repository, conversation, _ = await _prepare_conversation(tmp_path)
    user_message, _ = await repository.begin_run(
        conversation.conversation_id,
        content="publish will fail",
        session_id=SESSION_ID,
    )
    broker = FailingBrokerOnAssistantCompleted(repository, SESSION_ID)
    provider = FakeModelProvider([ModelResponse(content="done answer")])
    runner = ConversationRunner(
        repository=repository,
        broker=broker,
        runtime_factory=_build_runtime_factory(provider),
        trace_dir=tmp_path / "traces",
        redactor_factory=lambda conversation: Redactor(
            Path(conversation.project_root),
        ),
        tool_executor_factory=direct_executor_factory,
    )

    with pytest.raises(RuntimeError, match="publish-assistant-failed"):
        await runner.run_turn(
            conversation.conversation_id,
            SESSION_ID,
            user_message.message_id,
            "publish will fail",
        )

    completed = await repository.get_run(SESSION_ID)
    assert completed.status is RunStatus.COMPLETED
    assert completed.assistant_message_id is not None
    messages = await repository.list_messages(conversation.conversation_id)
    assistant = next(
        message
        for message in messages
        if message.message_id == completed.assistant_message_id
    )
    assert assistant.content == "done answer"
    failed_events = [
        event for event in broker.events if event.type is ChatEventType.RUN_FAILED
    ]
    assert failed_events == []


@pytest.mark.asyncio
async def test_runner_cancel_during_completion_publish_keeps_completed_and_reraises(
    tmp_path: Path,
) -> None:
    ConversationRunner, direct_executor_factory = _require_runner_types()
    repository, conversation, _ = await _prepare_conversation(tmp_path)
    user_message, _ = await repository.begin_run(
        conversation.conversation_id,
        content="cancel during publish",
        session_id=SESSION_ID,
    )
    publish_started = asyncio.Event()
    release_publish = asyncio.Event()
    broker = SlowPublishBroker(
        repository,
        SESSION_ID,
        publish_started=publish_started,
        release_publish=release_publish,
    )
    provider = FakeModelProvider([ModelResponse(content="late answer")])
    runner = ConversationRunner(
        repository=repository,
        broker=broker,
        runtime_factory=_build_runtime_factory(provider),
        trace_dir=tmp_path / "traces",
        redactor_factory=lambda conversation: Redactor(
            Path(conversation.project_root),
        ),
        tool_executor_factory=direct_executor_factory,
    )

    task = asyncio.create_task(
        runner.run_turn(
            conversation.conversation_id,
            SESSION_ID,
            user_message.message_id,
            "cancel during publish",
        ),
    )
    await publish_started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    completed = await repository.get_run(SESSION_ID)
    assert completed.status is RunStatus.COMPLETED
    assert completed.assistant_message_id is not None


@pytest.mark.asyncio
async def test_runner_complete_run_cancel_race_has_single_terminal_state(
    tmp_path: Path,
) -> None:
    ConversationRunner, direct_executor_factory = _require_runner_types()
    repository, conversation, _ = await _prepare_conversation(tmp_path)
    user_message, _ = await repository.begin_run(
        conversation.conversation_id,
        content="complete race",
        session_id=SESSION_ID,
    )
    complete_started = asyncio.Event()
    release_complete = asyncio.Event()
    slow_repository = SlowCompleteRunRepository(
        repository,
        complete_started=complete_started,
        release_complete=release_complete,
    )
    broker = RecordingBroker(repository, SESSION_ID)
    provider = FakeModelProvider([ModelResponse(content="race answer")])
    runner = ConversationRunner(
        repository=slow_repository,
        broker=broker,
        runtime_factory=_build_runtime_factory(provider),
        trace_dir=tmp_path / "traces",
        redactor_factory=lambda conversation: Redactor(
            Path(conversation.project_root),
        ),
        tool_executor_factory=direct_executor_factory,
    )

    loop = asyncio.get_running_loop()
    unretrieved: list[dict[str, Any]] = []
    previous_handler = loop.get_exception_handler()

    def exception_handler(
        active_loop: asyncio.AbstractEventLoop,
        context: dict[str, Any],
    ) -> None:
        unretrieved.append(context)
        if previous_handler is not None:
            previous_handler(active_loop, context)

    loop.set_exception_handler(exception_handler)
    try:
        task = asyncio.create_task(
            runner.run_turn(
                conversation.conversation_id,
                SESSION_ID,
                user_message.message_id,
                "complete race",
            ),
        )
        await complete_started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        release_complete.set()
        await asyncio.sleep(0.05)
    finally:
        loop.set_exception_handler(previous_handler)

    run = await repository.get_run(SESSION_ID)
    assert run.status in {RunStatus.COMPLETED, RunStatus.INTERRUPTED}
    if run.status is RunStatus.COMPLETED:
        assert run.assistant_message_id is not None
    assert not any(
        "Task exception was never retrieved" in str(context)
        for context in unretrieved
    )


@pytest.mark.asyncio
async def test_runner_list_context_before_failure_marks_failed_safely(
    tmp_path: Path,
) -> None:
    ConversationRunner, direct_executor_factory = _require_runner_types()
    repository, conversation, _ = await _prepare_conversation(tmp_path)
    user_message, _ = await repository.begin_run(
        conversation.conversation_id,
        content="context fails",
        session_id=SESSION_ID,
    )
    failing_repository = FailingListContextRepository(repository)
    broker = RecordingBroker(repository, SESSION_ID)
    provider = FakeModelProvider([ModelResponse(content="unused")])
    runner = ConversationRunner(
        repository=failing_repository,
        broker=broker,
        runtime_factory=_build_runtime_factory(provider),
        trace_dir=tmp_path / "traces",
        redactor_factory=lambda conversation: Redactor(
            Path(conversation.project_root),
        ),
        tool_executor_factory=direct_executor_factory,
    )

    await runner.run_turn(
        conversation.conversation_id,
        SESSION_ID,
        user_message.message_id,
        "context fails",
    )

    failed = await repository.get_run(SESSION_ID)
    assert failed.status is RunStatus.FAILED
    assert failed.error_code == "RuntimeError"
    failed_events = [
        event for event in broker.events if event.type is ChatEventType.RUN_FAILED
    ]
    assert len(failed_events) == 1
    serialized = failed_events[0].model_dump_json()
    assert "RuntimeError" in serialized
    assert "do-not-leak-context-secret" not in serialized
    assert "Traceback" not in serialized
