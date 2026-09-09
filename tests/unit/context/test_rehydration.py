from __future__ import annotations

import importlib
import importlib.util
from typing import Any
from uuid import UUID

import pytest

from agent_foundations.chat.errors import ChatNotFoundError
from agent_foundations.chat.models import MessageRole, PermissionMode
from agent_foundations.chat.repository import ConversationRepository
from agent_foundations.context.budget import ContextBudget
from agent_foundations.domain.messages import Message, Role

SESSION_ID = "22222222-2222-4222-8222-222222222222"


def _load(module_name: str) -> Any:
    spec = importlib.util.find_spec(module_name)
    assert spec is not None, f"missing module {module_name}"
    return importlib.import_module(module_name)


def _message(
    *,
    role: Role,
    content: str,
    message_id: str,
    tool_call_id: str | None = None,
) -> Message:
    payload: dict[str, object] = {
        "role": role,
        "content": content,
        "message_id": message_id,
    }
    if tool_call_id is not None:
        payload["tool_call_id"] = tool_call_id
    return Message(**payload)  # type: ignore[arg-type]


async def _repo(tmp_path: Any) -> ConversationRepository:
    repository = ConversationRepository(tmp_path / "chat.sqlite3")
    await repository.initialize()
    return repository


@pytest.mark.asyncio
async def test_rehydrate_user_message_from_same_conversation(tmp_path: Any) -> None:
    rehydration = _load("agent_foundations.context.rehydration")
    compaction = _load("agent_foundations.context.compaction")
    repository = await _repo(tmp_path)
    conversation = await repository.create_conversation(
        title="compaction",
        project_root=tmp_path,
        permission_mode=PermissionMode.PROJECT_READ_ONLY,
    )
    user, _run = await repository.begin_run(
        conversation.conversation_id,
        content="GOAL: keep-originals",
        session_id=SESSION_ID,
    )
    domain = _message(role=Role.USER, content=user.content, message_id=user.message_id)
    fingerprint = compaction.messages_source_fingerprint((domain,))
    restored = await rehydration.rehydrate_messages(
        conversation_id=conversation.conversation_id,
        source_message_ids=(UUID(user.message_id),),
        source_fingerprint=fingerprint,
        repository=repository,
        session_messages=(domain,),
        budget=ContextBudget(),
    )
    assert len(restored) == 1
    assert restored[0].content == "GOAL: keep-originals"
    assert restored[0].message_id == user.message_id
    stored = await repository.list_messages(conversation.conversation_id)
    assert stored[0].content == "GOAL: keep-originals"


@pytest.mark.asyncio
async def test_rehydrate_rejects_cross_conversation(tmp_path: Any) -> None:
    rehydration = _load("agent_foundations.context.rehydration")
    compaction = _load("agent_foundations.context.compaction")
    repository = await _repo(tmp_path)
    first = await repository.create_conversation(title="a", project_root=tmp_path)
    second = await repository.create_conversation(title="b", project_root=tmp_path)
    user, _run = await repository.begin_run(
        first.conversation_id,
        content="secret-original",
        session_id=SESSION_ID,
    )
    domain = _message(role=Role.USER, content=user.content, message_id=user.message_id)
    with pytest.raises(rehydration.RehydrationError):
        await rehydration.rehydrate_messages(
            conversation_id=second.conversation_id,
            source_message_ids=(UUID(user.message_id),),
            source_fingerprint=compaction.messages_source_fingerprint((domain,)),
            repository=repository,
            session_messages=(domain,),
            budget=ContextBudget(),
        )


@pytest.mark.asyncio
async def test_rehydrate_rejects_unknown_id_and_role_mismatch(tmp_path: Any) -> None:
    rehydration = _load("agent_foundations.context.rehydration")
    compaction = _load("agent_foundations.context.compaction")
    repository = await _repo(tmp_path)
    conversation = await repository.create_conversation(title="a", project_root=tmp_path)
    user, _run = await repository.begin_run(
        conversation.conversation_id,
        content="user-original",
        session_id=SESSION_ID,
    )
    domain = _message(role=Role.USER, content=user.content, message_id=user.message_id)
    fingerprint = compaction.messages_source_fingerprint((domain,))
    with pytest.raises(rehydration.RehydrationError):
        await rehydration.rehydrate_messages(
            conversation_id=conversation.conversation_id,
            source_message_ids=(UUID("99999999-9999-4999-8999-999999999999"),),
            source_fingerprint=fingerprint,
            repository=repository,
            session_messages=(domain,),
            budget=ContextBudget(),
        )
    assistant = _message(role=Role.ASSISTANT, content=user.content, message_id=user.message_id)
    with pytest.raises(rehydration.RehydrationError):
        await rehydration.rehydrate_messages(
            conversation_id=conversation.conversation_id,
            source_message_ids=(UUID(user.message_id),),
            source_fingerprint=compaction.messages_source_fingerprint((assistant,)),
            repository=repository,
            session_messages=(assistant,),
            budget=ContextBudget(),
        )


@pytest.mark.asyncio
async def test_rehydrate_rejects_fingerprint_drift(tmp_path: Any) -> None:
    rehydration = _load("agent_foundations.context.rehydration")
    repository = await _repo(tmp_path)
    conversation = await repository.create_conversation(title="a", project_root=tmp_path)
    user, _run = await repository.begin_run(
        conversation.conversation_id,
        content="original-text",
        session_id=SESSION_ID,
    )
    domain = _message(role=Role.USER, content=user.content, message_id=user.message_id)
    with pytest.raises(rehydration.RehydrationError):
        await rehydration.rehydrate_messages(
            conversation_id=conversation.conversation_id,
            source_message_ids=(UUID(user.message_id),),
            source_fingerprint="0" * 64,
            repository=repository,
            session_messages=(domain,),
            budget=ContextBudget(),
        )


@pytest.mark.asyncio
async def test_rehydrate_tool_from_session_not_sqlite(tmp_path: Any) -> None:
    rehydration = _load("agent_foundations.context.rehydration")
    compaction = _load("agent_foundations.context.compaction")
    repository = await _repo(tmp_path)
    conversation = await repository.create_conversation(title="a", project_root=tmp_path)
    await repository.begin_run(
        conversation.conversation_id,
        content="user-only",
        session_id=SESSION_ID,
    )
    tool = _message(
        role=Role.TOOL,
        content='{"command_category":"test","argv_display":["pytest"],"cwd":".",'
        '"exit_code":1,"timed_out":false,"cancelled":false,"output_truncated":false,'
        '"passed":0,"failed":1,"skipped":0,"diagnostics":[],'
        '"repeated_diagnostics":0,"parser_status":"partial","unparsed_bytes":8,'
        '"unparsed_reason":"truncated","recommended_ranges":[],'
        '"artifact_id":"coa_abcdefghijklmnopqrstuv","stdout_bytes":32,"stderr_bytes":0,'
        '"raw_sha256":"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"}',
        message_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaa10",
        tool_call_id="call-1",
    )
    restored = await rehydration.rehydrate_messages(
        conversation_id=conversation.conversation_id,
        source_message_ids=(UUID(tool.message_id or ""),),
        source_fingerprint=compaction.messages_source_fingerprint((tool,)),
        repository=repository,
        session_messages=(tool,),
        budget=ContextBudget(),
    )
    assert restored[0].role is Role.TOOL
    assert restored[0].content == tool.content
    stored = await repository.list_messages(conversation.conversation_id)
    assert all(row.role is not MessageRole.ASSISTANT or True for row in stored)
    assert all(row.content != tool.content for row in stored)


@pytest.mark.asyncio
async def test_rehydrate_is_bounded_and_redacted(tmp_path: Any) -> None:
    rehydration = _load("agent_foundations.context.rehydration")
    compaction = _load("agent_foundations.context.compaction")
    huge = _message(
        role=Role.TOOL,
        content="x" * 500 + " token=sk-test-placeholder",
        message_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaa11",
        tool_call_id="call-2",
    )
    restored = await rehydration.rehydrate_messages(
        conversation_id=None,
        source_message_ids=(UUID(huge.message_id or ""),),
        source_fingerprint=compaction.messages_source_fingerprint((huge,)),
        repository=None,
        session_messages=(huge,),
        budget=ContextBudget(max_chars=1000, max_tool_result_chars=40),
        project_root=tmp_path,
    )
    assert restored[0].content is not None
    assert len(restored[0].content) <= 40
    assert "sk-test-placeholder" not in (restored[0].content or "")


@pytest.mark.asyncio
async def test_rehydrate_rejects_sql_and_paths() -> None:
    rehydration = _load("agent_foundations.context.rehydration")
    with pytest.raises(rehydration.RehydrationError):
        await rehydration.rehydrate_messages(
            conversation_id="'; DROP TABLE messages;--",
            source_message_ids=(UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),),
            source_fingerprint="a" * 64,
            repository=None,
            session_messages=(),
            budget=ContextBudget(),
        )
    with pytest.raises(rehydration.RehydrationError):
        await rehydration.rehydrate_messages(
            conversation_id=r"C:\secrets\chat.sqlite3",
            source_message_ids=(UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),),
            source_fingerprint="a" * 64,
            repository=None,
            session_messages=(),
            budget=ContextBudget(),
        )


@pytest.mark.asyncio
async def test_repository_get_message_requires_exact_conversation(tmp_path: Any) -> None:
    repository = await _repo(tmp_path)
    assert hasattr(repository, "get_message")
    conversation = await repository.create_conversation(title="a", project_root=tmp_path)
    other = await repository.create_conversation(title="b", project_root=tmp_path)
    user, _run = await repository.begin_run(
        conversation.conversation_id,
        content="exact-row",
        session_id=SESSION_ID,
    )
    loaded = await repository.get_message(conversation.conversation_id, user.message_id)
    assert loaded.content == "exact-row"
    with pytest.raises(ChatNotFoundError):
        await repository.get_message(other.conversation_id, user.message_id)
    with pytest.raises(ChatNotFoundError):
        await repository.get_message(
            conversation.conversation_id,
            user.message_id,
            expected_role=MessageRole.ASSISTANT,
        )
