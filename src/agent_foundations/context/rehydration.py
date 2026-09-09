from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from uuid import UUID

from agent_foundations.chat.errors import ChatNotFoundError
from agent_foundations.chat.models import MessageRole
from agent_foundations.chat.repository import ConversationRepository
from agent_foundations.command_output.sanitize import sanitize_streams
from agent_foundations.context.budget import ContextBudget
from agent_foundations.context.compaction import messages_source_fingerprint
from agent_foundations.domain.messages import Message, Role

_UNSAFE_SELECTOR = frozenset(";/\\'\" \t\n")


class RehydrationError(ValueError):
    """Provenance, fingerprint, or selector validation failed."""


def _require_uuid(value: str) -> str:
    if value != value.strip() or any(character in _UNSAFE_SELECTOR for character in value):
        raise RehydrationError("rehydration selector must be a UUID")
    if "--" in value or ":" in value:
        raise RehydrationError("rehydration selector must be a UUID")
    try:
        UUID(value)
    except ValueError as exc:
        raise RehydrationError("rehydration selector must be a UUID") from exc
    return value


async def rehydrate_messages(
    *,
    conversation_id: str | None,
    source_message_ids: tuple[UUID, ...],
    source_fingerprint: str,
    repository: ConversationRepository | None,
    session_messages: Sequence[Message],
    budget: ContextBudget,
    project_root: Path | None = None,
) -> tuple[Message, ...]:
    if conversation_id is not None:
        _require_uuid(conversation_id)
    for message_id in source_message_ids:
        _require_uuid(str(message_id))

    by_id = {
        message.message_id: message
        for message in session_messages
        if message.message_id is not None
    }
    recovered: list[Message] = []
    for message_uuid in source_message_ids:
        key = str(message_uuid)
        session_message = by_id.get(key)
        if session_message is not None and session_message.role in {Role.TOOL, Role.SYSTEM}:
            recovered.append(session_message)
            continue
        if repository is None or conversation_id is None:
            if session_message is None:
                raise RehydrationError(f"message not found: {key}")
            recovered.append(session_message)
            continue
        expected_role = None
        if session_message is not None:
            expected_role = MessageRole(session_message.role.value)
        try:
            row = await repository.get_message(
                conversation_id,
                key,
                expected_role=expected_role,
            )
        except ChatNotFoundError as exc:
            raise RehydrationError(f"message not found: {key}") from exc
        recovered.append(
            Message(
                role=Role(row.role.value),
                content=row.content,
                message_id=row.message_id,
            )
        )

    actual = messages_source_fingerprint(recovered)
    if actual != source_fingerprint:
        raise RehydrationError("source fingerprint drift")
    return tuple(_bound_and_redact(message, budget, project_root) for message in recovered)


def _bound_and_redact(
    message: Message,
    budget: ContextBudget,
    project_root: Path | None,
) -> Message:
    content = message.content or ""
    if message.role is Role.TOOL:
        limit = budget.max_tool_result_chars
        if len(content) > limit:
            suffix = "..."
            if limit <= len(suffix):
                content = suffix[:limit]
            else:
                content = content[: limit - len(suffix)] + suffix
    if project_root is not None:
        redacted, _stderr = sanitize_streams(
            stdout=content.encode("utf-8"),
            stderr=b"",
            project_root=project_root,
        )
        content = redacted
        if message.role is Role.TOOL and len(content) > budget.max_tool_result_chars:
            content = content[: budget.max_tool_result_chars]
    if content == (message.content or ""):
        return message
    return message.model_copy(update={"content": content})
