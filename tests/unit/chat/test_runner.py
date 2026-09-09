from __future__ import annotations

import asyncio
from datetime import UTC, datetime
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
    ToolActivityStatus,
)
from agent_foundations.chat.repository import ConversationRepository
from agent_foundations.context.budget import ContextBudget
from agent_foundations.context.builder import ContextBuilder
from agent_foundations.domain.messages import Role
from agent_foundations.domain.model import ModelResponse
from agent_foundations.domain.tool import ToolCall
from agent_foundations.providers.fake import FakeModelProvider
from agent_foundations.runtime.agent import AgentConfig
from agent_foundations.runtime.loop import AgentLoop
from agent_foundations.runtime.redaction import Redactor
from agent_foundations.runtime.tool_execution import ToolCallExecutor
from agent_foundations.runtime.trace import EventSink, NoOpEventSink
from tests.unit.tools.registry_helpers import readonly_tool_registry

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
            registry=readonly_tool_registry(Path(conversation.project_root)),
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

    contents = [message.content for message in provider.requests[0].messages]
    assert contents[0] == AgentConfig().system_prompt
    visible = [
        content
        for content in contents
        if not (isinstance(content, str) and content.startswith("[repository context]"))
    ]
    assert visible == [
        AgentConfig().system_prompt,
        "old question",
        "old answer",
        "new question",
    ]
    assert provider.requests[0].messages[0].role is Role.SYSTEM
    assert all(
        message.role in {Role.USER, Role.ASSISTANT}
        or (
            message.role is Role.SYSTEM
            and (message.content or "").startswith("[repository context]")
        )
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
async def test_runner_persists_tool_activity_without_raw_result(
    tmp_path: Path,
) -> None:
    ConversationRunner, direct_executor_factory = _require_runner_types()
    repository, conversation, _project_root = await _prepare_conversation(tmp_path)
    user_message, _run = await repository.begin_run(
        conversation.conversation_id,
        content="list project",
        session_id=SESSION_ID,
    )
    provider = FakeModelProvider(
        [
            ModelResponse(
                tool_calls=(
                    ToolCall(
                        id="call-1",
                        name="list_directory",
                        arguments={"path": "."},
                    ),
                ),
            ),
            ModelResponse(content="done"),
        ],
    )
    runner = ConversationRunner(
        repository=repository,
        broker=RecordingBroker(repository, SESSION_ID),
        runtime_factory=_build_runtime_factory(provider),
        trace_dir=tmp_path / "traces",
        redactor_factory=lambda item: Redactor(Path(item.project_root)),
        tool_executor_factory=direct_executor_factory,
    )

    await runner.run_turn(
        conversation.conversation_id,
        SESSION_ID,
        user_message.message_id,
        "list project",
    )

    [activity] = await repository.list_tool_activities(conversation.conversation_id)
    assert activity.status is ToolActivityStatus.COMPLETED
    assert activity.tool_call_id == "call-1"
    assert activity.arguments_summary == "."
    assert activity.result_summary == "1 entry"
    serialized = activity.model_dump_json()
    assert "README.md" not in serialized
    assert '"entries"' not in serialized


@pytest.mark.asyncio
async def test_runner_chat_projection_failure_does_not_fail_runtime(
    tmp_path: Path,
) -> None:
    ConversationRunner, direct_executor_factory = _require_runner_types()
    repository, conversation, _project_root = await _prepare_conversation(tmp_path)
    user_message, _run = await repository.begin_run(
        conversation.conversation_id,
        content="list project",
        session_id=SESSION_ID,
    )

    class ProjectionFailingRepository:
        def __getattr__(self, name: str) -> Any:
            return getattr(repository, name)

        async def upsert_tool_activity(self, activity: Any) -> Any:
            raise RuntimeError("projection-storage-secret")

    provider = FakeModelProvider(
        [
            ModelResponse(
                tool_calls=(
                    ToolCall(id="call-1", name="list_directory", arguments={"path": "."}),
                ),
            ),
            ModelResponse(content="done despite projection failure"),
        ],
    )
    runner = ConversationRunner(
        repository=ProjectionFailingRepository(),
        broker=RecordingBroker(repository, SESSION_ID),
        runtime_factory=_build_runtime_factory(provider),
        trace_dir=tmp_path / "traces",
        redactor_factory=lambda item: Redactor(Path(item.project_root)),
        tool_executor_factory=direct_executor_factory,
    )

    await runner.run_turn(
        conversation.conversation_id,
        SESSION_ID,
        user_message.message_id,
        "list project",
    )

    completed = await repository.get_run(SESSION_ID)
    assert completed.status is RunStatus.COMPLETED
    trace_text = (tmp_path / "traces" / f"{SESSION_ID}.jsonl").read_text("utf-8")
    assert "tool.call.completed" in trace_text
    assert "projection-storage-secret" not in trace_text


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
            registry=readonly_tool_registry(Path(conversation.project_root)),
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


def _model_request_id(session_id: str) -> str:
    from uuid import UUID, uuid5

    from agent_foundations.runtime.state_machine import AgentRunPhase

    return str(
        uuid5(UUID(session_id), f"model:1:{AgentRunPhase.READY_FOR_MODEL.value}"),
    )


async def _open_durable(repository: ConversationRepository) -> Any:
    from agent_foundations.durable.repository import DurableRunRepository

    durable = DurableRunRepository(repository._database_path)
    await durable.initialize()
    return durable


def _resilient_runtime_factory(inner: Any, *, max_attempts: int) -> Any:
    from agent_foundations.providers.resilient import ResilientModelProvider, RetryPolicy
    from agent_foundations.runtime.provider_attempt_budget import ProviderAttemptBudget
    from agent_foundations.runtime.rate_limit import (
        FakeClock,
        FakeSleeper,
        TokenBucketRateLimiter,
    )

    clock = FakeClock()
    sleeper = FakeSleeper(clock)
    provider = ResilientModelProvider(
        inner,
        policy=RetryPolicy(max_attempts=max_attempts),
        budget=ProviderAttemptBudget(max_attempts=max_attempts),
        limiter=TokenBucketRateLimiter(
            capacity=8,
            refill_per_second=8.0,
            clock=clock,
            sleeper=sleeper,
        ),
        clock=clock,
        sleeper=sleeper,
    )

    def factory(
        conversation: Conversation,
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


@pytest.mark.asyncio
async def test_chat_crash_after_reserve_new_runner_does_not_recall_inner(
    tmp_path: Path,
) -> None:
    from agent_foundations.domain.errors import ProviderTimeoutError
    from agent_foundations.durable.repository import CheckpointNotFoundError
    from agent_foundations.runtime.provider_attempt_budget import (
        ProviderAttemptExhaustedError,
    )

    ConversationRunner, direct_executor_factory = _require_runner_types()
    repository, conversation, project_root = await _prepare_conversation(tmp_path)
    durable = await _open_durable(repository)
    user_message, _ = await repository.begin_run(
        conversation.conversation_id,
        content="crash after reserve",
        session_id=SESSION_ID,
    )

    class CrashAfterReserveInner:
        calls = 0

        async def complete(self, request: Any) -> ModelResponse:
            type(self).calls += 1
            raise ProviderTimeoutError("simulated crash after reserve")

    class ForbiddenInner:
        calls = 0

        async def complete(self, request: Any) -> ModelResponse:
            type(self).calls += 1
            return ModelResponse(content="should-not-run")

    first_inner = CrashAfterReserveInner()
    runner = ConversationRunner(
        repository=repository,
        broker=RecordingBroker(repository, SESSION_ID),
        runtime_factory=_resilient_runtime_factory(first_inner, max_attempts=1),
        trace_dir=tmp_path / "traces",
        redactor_factory=lambda item: Redactor(Path(item.project_root)),
        tool_executor_factory=direct_executor_factory,
        durable_repository=durable,
    )
    await runner.run_turn(
        conversation.conversation_id,
        SESSION_ID,
        user_message.message_id,
        "crash after reserve",
    )
    assert first_inner.calls == 1

    restarted = await _open_durable(repository)
    try:
        checkpoint = await restarted.load_latest_checkpoint(SESSION_ID)
        attempts = dict(checkpoint.state.provider_attempts)
    except CheckpointNotFoundError:
        attempts = {}

    second_inner = ForbiddenInner()
    runner2 = ConversationRunner(
        repository=repository,
        broker=RecordingBroker(repository, SESSION_ID),
        runtime_factory=_resilient_runtime_factory(second_inner, max_attempts=1),
        trace_dir=tmp_path / "traces-restart",
        redactor_factory=lambda item: Redactor(Path(item.project_root)),
        tool_executor_factory=direct_executor_factory,
        durable_repository=restarted,
    )
    loop = runner2._runtime_factory(
        conversation,
        NoOpEventSink(),
        direct_executor_factory(conversation, SESSION_ID),
    )
    run_kwargs: dict[str, Any] = {"session_id": SESSION_ID, "history": ()}
    import inspect

    parameters = inspect.signature(AgentLoop.run).parameters
    if "provider_attempts" in parameters:
        run_kwargs["provider_attempts"] = attempts
    if "checkpoint_sink" in parameters:
        run_kwargs["checkpoint_sink"] = None
    try:
        await loop.run(project_root, "crash after reserve", **run_kwargs)
    except ProviderAttemptExhaustedError:
        pass
    assert second_inner.calls == 0
    request_key = _model_request_id(SESSION_ID)
    assert attempts.get(request_key) == 1
    durable_run = await restarted.get_run(SESSION_ID)
    assert durable_run.attempt == 1


@pytest.mark.asyncio
async def test_run_turn_forwards_checkpoint_sink_and_does_not_treat_interrupt_as_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent_foundations.durable.repository import CheckpointNotFoundError

    ConversationRunner, direct_executor_factory = _require_runner_types()
    repository, conversation, _ = await _prepare_conversation(tmp_path)
    durable = await _open_durable(repository)
    user_message, _ = await repository.begin_run(
        conversation.conversation_id,
        content="cancel after reserve",
        session_id=SESSION_ID,
    )
    started = asyncio.Event()

    class HangAfterReserveInner:
        async def complete(self, request: Any) -> ModelResponse:
            started.set()
            await asyncio.Event().wait()
            return ModelResponse(content="unreachable")

    seen: dict[str, Any] = {}
    original_run = AgentLoop.run

    async def tracking_run(
        self: AgentLoop,
        root: Path,
        query: str,
        **kwargs: Any,
    ) -> Any:
        seen.update(kwargs)
        return await original_run(self, root, query, **kwargs)

    monkeypatch.setattr(AgentLoop, "run", tracking_run)
    runner = ConversationRunner(
        repository=repository,
        broker=RecordingBroker(repository, SESSION_ID),
        runtime_factory=_resilient_runtime_factory(
            HangAfterReserveInner(),
            max_attempts=1,
        ),
        trace_dir=tmp_path / "traces",
        redactor_factory=lambda item: Redactor(Path(item.project_root)),
        tool_executor_factory=direct_executor_factory,
        durable_repository=durable,
    )
    task = asyncio.create_task(
        runner.run_turn(
            conversation.conversation_id,
            SESSION_ID,
            user_message.message_id,
            "cancel after reserve",
        ),
    )
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    interrupted = await repository.get_run(SESSION_ID)
    assert interrupted.status is RunStatus.INTERRUPTED
    assert seen.get("checkpoint_sink") is not None
    assert seen.get("session_id") == SESSION_ID
    try:
        checkpoint = await durable.load_latest_checkpoint(SESSION_ID)
        attempts = dict(checkpoint.state.provider_attempts)
    except CheckpointNotFoundError:
        attempts = {}
    assert attempts.get(_model_request_id(SESSION_ID)) == 1
    durable_run = await durable.get_run(SESSION_ID)
    assert durable_run.attempt == 1
    assert durable_run.status.value == "cancelled"


def _durable_run(run_id: str, project_root: Path, status: Any) -> Any:
    from agent_foundations.durable.models import DurableRun

    now = datetime(2026, 9, 8, 12, 0, 0, tzinfo=UTC)
    return DurableRun(
        run_id=run_id,
        project_root=str(project_root),
        status=status,
        schema_version=1,
        state_version=0,
        attempt=1,
        created_at=now,
        updated_at=now,
    )


async def _running_chat_and_runner(
    tmp_path: Path,
    durable_status: Any | None,
) -> tuple[Any, Any, Any]:
    ConversationRunner, direct_executor_factory = _require_runner_types()
    repository, conversation, project_root = await _prepare_conversation(tmp_path)
    _, run = await repository.begin_run(
        conversation.conversation_id,
        content="interrupt durable",
        session_id=SESSION_ID,
    )
    await repository.transition_run(
        run.session_id,
        RunStatus.QUEUED,
        RunStatus.RUNNING,
    )
    durable = await _open_durable(repository)
    if durable_status is not None:
        await durable.create_run(
            _durable_run(run.session_id, project_root, durable_status),
        )
    runner = ConversationRunner(
        repository=repository,
        broker=RecordingBroker(repository, SESSION_ID),
        runtime_factory=_build_runtime_factory(
            FakeModelProvider([ModelResponse(content="ok")]),
        ),
        trace_dir=tmp_path / "traces",
        redactor_factory=lambda item: Redactor(Path(item.project_root)),
        tool_executor_factory=direct_executor_factory,
        durable_repository=durable,
    )
    return repository, durable, runner


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "durable_status",
    ["created", "running", "waiting_approval", "paused"],
)
async def test_safe_interrupt_run_cancels_cancelable_durable(
    tmp_path: Path,
    durable_status: str,
) -> None:
    from agent_foundations.durable.models import DurableRunStatus

    status = DurableRunStatus(durable_status)
    repository, durable, runner = await _running_chat_and_runner(tmp_path, status)
    await runner._safe_interrupt_run(SESSION_ID)
    assert (await repository.get_run(SESSION_ID)).status is RunStatus.INTERRUPTED
    assert (await durable.get_run(SESSION_ID)).status is DurableRunStatus.CANCELLED


@pytest.mark.asyncio
@pytest.mark.parametrize("durable_status", ["completed", "failed", "cancelled"])
async def test_safe_interrupt_run_skips_terminal_durable(
    tmp_path: Path,
    durable_status: str,
) -> None:
    from agent_foundations.durable.models import DurableRunStatus

    expected = DurableRunStatus(durable_status)
    repository, durable, runner = await _running_chat_and_runner(tmp_path, expected)
    await runner._safe_interrupt_run(SESSION_ID)
    assert (await repository.get_run(SESSION_ID)).status is RunStatus.INTERRUPTED
    assert (await durable.get_run(SESSION_ID)).status is expected


@pytest.mark.asyncio
async def test_safe_interrupt_run_skips_missing_durable_row(tmp_path: Path) -> None:
    from agent_foundations.durable.repository import DurableRunNotFoundError

    repository, durable, runner = await _running_chat_and_runner(tmp_path, None)
    await runner._safe_interrupt_run(SESSION_ID)
    assert (await repository.get_run(SESSION_ID)).status is RunStatus.INTERRUPTED
    with pytest.raises(DurableRunNotFoundError):
        await durable.get_run(SESSION_ID)
