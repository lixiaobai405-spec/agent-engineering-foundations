from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from agent_foundations.chat.errors import ChatConflictError, ChatError, ChatNotFoundError
from agent_foundations.chat.models import (
    AccessOperation,
    ApprovalRequest,
    ApprovalStatus,
    ChatMessage,
    Conversation,
    MessageRole,
    PermissionMode,
    RunRecord,
    RunStatus,
    new_id,
    utc_now,
)

_RUN_TRANSITIONS: dict[RunStatus, set[RunStatus]] = {
    RunStatus.QUEUED: {RunStatus.RUNNING, RunStatus.FAILED, RunStatus.INTERRUPTED},
    RunStatus.RUNNING: {
        RunStatus.WAITING_APPROVAL,
        RunStatus.COMPLETED,
        RunStatus.FAILED,
        RunStatus.INTERRUPTED,
    },
    RunStatus.WAITING_APPROVAL: {
        RunStatus.RUNNING,
        RunStatus.FAILED,
        RunStatus.INTERRUPTED,
    },
    RunStatus.COMPLETED: set(),
    RunStatus.FAILED: set(),
    RunStatus.INTERRUPTED: set(),
}

_TERMINAL_RUN_STATUSES = {
    RunStatus.COMPLETED,
    RunStatus.FAILED,
    RunStatus.INTERRUPTED,
}

_SCHEMA_VERSION = 1

_SCHEMA_SQL = """
CREATE TABLE conversations (
  conversation_id TEXT PRIMARY KEY,
  title TEXT NOT NULL CHECK(length(trim(title)) BETWEEN 1 AND 120),
  project_root TEXT NOT NULL,
  permission_mode TEXT NOT NULL CHECK(
    permission_mode IN ('PROJECT_READ_ONLY','ASK_FOR_ACCESS')
  ),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE messages (
  message_id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id),
  role TEXT NOT NULL CHECK(role IN ('user','assistant')),
  content TEXT NOT NULL CHECK(length(content) > 0),
  sequence INTEGER NOT NULL CHECK(sequence >= 1),
  created_at TEXT NOT NULL,
  UNIQUE(conversation_id, sequence)
);
CREATE TABLE runs (
  session_id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id),
  user_message_id TEXT NOT NULL REFERENCES messages(message_id),
  assistant_message_id TEXT REFERENCES messages(message_id),
  trace_path TEXT NOT NULL CHECK(length(trim(trace_path)) > 0),
  status TEXT NOT NULL CHECK(
    status IN (
      'queued',
      'running',
      'waiting_approval',
      'completed',
      'failed',
      'interrupted'
    )
  ),
  error_code TEXT,
  created_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT
);
CREATE UNIQUE INDEX one_active_run_per_conversation
ON runs(conversation_id)
WHERE status IN ('queued','running','waiting_approval');
CREATE TABLE approval_requests (
  approval_id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id),
  session_id TEXT NOT NULL REFERENCES runs(session_id),
  tool_call_id TEXT NOT NULL,
  tool_name TEXT NOT NULL,
  canonical_path TEXT NOT NULL,
  operation TEXT NOT NULL CHECK(operation = 'read'),
  status TEXT NOT NULL CHECK(
    status IN ('pending','approved','denied','invalidated')
  ),
  requested_at TEXT NOT NULL,
  decided_at TEXT,
  UNIQUE(session_id, tool_call_id)
);
"""

_SCHEMA_STATEMENTS = tuple(
    statement.strip()
    for statement in _SCHEMA_SQL.split(";")
    if statement.strip()
)


def _assert_permission_mode_change_allowed(
    connection: sqlite3.Connection,
    conversation_id: str,
) -> None:
    active_statuses = tuple(status.value for status in RunStatus.active())
    placeholders = ", ".join("?" for _ in active_statuses)
    active_run = connection.execute(
        f"""
        SELECT 1
        FROM runs
        WHERE conversation_id = ?
          AND status IN ({placeholders})
        LIMIT 1
        """,
        (conversation_id, *active_statuses),
    ).fetchone()
    pending_approval = connection.execute(
        """
        SELECT 1
        FROM approval_requests
        WHERE conversation_id = ?
          AND status = 'pending'
        LIMIT 1
        """,
        (conversation_id,),
    ).fetchone()
    if active_run is not None or pending_approval is not None:
        raise ChatConflictError(
            "permission mode cannot change while a run or approval is active",
        )


class UnsupportedSchemaVersionError(ChatError):
    """Raised when the on-disk schema is newer than this repository supports."""


class ConversationRepository:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path.resolve()

    async def initialize(self) -> None:
        await asyncio.to_thread(self._initialize_sync)

    async def create_conversation(
        self,
        *,
        title: str,
        project_root: Path,
        permission_mode: PermissionMode,
    ) -> Conversation:
        return await asyncio.to_thread(
            self._create_conversation_sync,
            title,
            project_root,
            permission_mode,
        )

    async def get_conversation(self, conversation_id: str) -> Conversation:
        return await asyncio.to_thread(self._get_conversation_sync, conversation_id)

    async def list_conversations(self) -> list[Conversation]:
        return await asyncio.to_thread(self._list_conversations_sync)

    async def update_conversation(
        self,
        conversation_id: str,
        *,
        title: str | None = None,
        permission_mode: PermissionMode | None = None,
    ) -> Conversation:
        return await asyncio.to_thread(
            self._update_conversation_sync,
            conversation_id,
            title,
            permission_mode,
        )

    async def begin_run(
        self,
        conversation_id: str,
        *,
        content: str,
        session_id: str,
    ) -> tuple[ChatMessage, RunRecord]:
        return await asyncio.to_thread(
            self._begin_run_sync,
            conversation_id,
            content,
            session_id,
        )

    async def get_run(self, session_id: str) -> RunRecord:
        return await asyncio.to_thread(self._get_run_sync, session_id)

    async def list_runs(self, conversation_id: str) -> list[RunRecord]:
        return await asyncio.to_thread(self._list_runs_sync, conversation_id)

    async def list_messages(self, conversation_id: str) -> list[ChatMessage]:
        return await asyncio.to_thread(self._list_messages_sync, conversation_id)

    async def list_context_before(
        self,
        conversation_id: str,
        user_message_id: str,
    ) -> list[ChatMessage]:
        return await asyncio.to_thread(
            self._list_context_before_sync,
            conversation_id,
            user_message_id,
        )

    async def transition_run(
        self,
        session_id: str,
        expected: RunStatus,
        target: RunStatus,
    ) -> RunRecord:
        return await asyncio.to_thread(
            self._transition_run_sync,
            session_id,
            expected,
            target,
        )

    async def complete_run(self, session_id: str, answer: str) -> ChatMessage:
        return await asyncio.to_thread(self._complete_run_sync, session_id, answer)

    async def fail_run(self, session_id: str, error_code: str) -> RunRecord:
        return await asyncio.to_thread(self._fail_run_sync, session_id, error_code)

    async def interrupt_run(self, session_id: str) -> RunRecord:
        return await asyncio.to_thread(self._interrupt_run_sync, session_id)

    async def create_approval(
        self,
        *,
        conversation_id: str,
        session_id: str,
        tool_call_id: str,
        tool_name: str,
        canonical_path: str,
        approval_id: str | None = None,
    ) -> ApprovalRequest:
        return await asyncio.to_thread(
            self._create_approval_sync,
            conversation_id,
            session_id,
            tool_call_id,
            tool_name,
            canonical_path,
            approval_id,
        )

    async def get_approval(self, approval_id: str) -> ApprovalRequest:
        return await asyncio.to_thread(self._get_approval_sync, approval_id)

    async def get_conversation_state(
        self,
        conversation_id: str,
    ) -> tuple[RunRecord | None, ApprovalRequest | None]:
        return await asyncio.to_thread(
            self._get_conversation_state_sync,
            conversation_id,
        )

    async def resolve_approval(
        self,
        approval_id: str,
        decision: ApprovalStatus,
    ) -> ApprovalRequest:
        return await asyncio.to_thread(
            self._resolve_approval_sync,
            approval_id,
            decision,
        )

    async def invalidate_approval(self, approval_id: str) -> ApprovalRequest:
        return await asyncio.to_thread(
            self._invalidate_approval_sync,
            approval_id,
        )

    async def interrupt_unfinished(self) -> tuple[int, int]:
        return await asyncio.to_thread(self._interrupt_unfinished_sync)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._database_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            yield connection
        finally:
            connection.close()

    def _initialize_sync(self) -> None:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version > _SCHEMA_VERSION:
                raise UnsupportedSchemaVersionError(
                    f"unsupported schema version: {version}",
                )
            if version == _SCHEMA_VERSION:
                return
            connection.execute("BEGIN IMMEDIATE")
            try:
                for statement in _SCHEMA_STATEMENTS:
                    connection.execute(statement)
                connection.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
                connection.commit()
            except sqlite3.Error:
                connection.rollback()
                raise

    def _create_conversation_sync(
        self,
        title: str,
        project_root: Path,
        permission_mode: PermissionMode,
    ) -> Conversation:
        now = utc_now()
        conversation = Conversation(
            conversation_id=new_id(),
            title=_normalize_title(title),
            project_root=str(project_root),
            permission_mode=permission_mode,
            created_at=now,
            updated_at=now,
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO conversations (
                    conversation_id,
                    title,
                    project_root,
                    permission_mode,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    conversation.conversation_id,
                    conversation.title,
                    conversation.project_root,
                    conversation.permission_mode.value,
                    _serialize_datetime(conversation.created_at),
                    _serialize_datetime(conversation.updated_at),
                ),
            )
            connection.commit()
        return conversation

    def _get_conversation_sync(self, conversation_id: str) -> Conversation:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    conversation_id,
                    title,
                    project_root,
                    permission_mode,
                    created_at,
                    updated_at
                FROM conversations
                WHERE conversation_id = ?
                """,
                (conversation_id,),
            ).fetchone()
        if row is None:
            raise ChatNotFoundError(f"conversation not found: {conversation_id}")
        return _row_to_conversation(row)

    def _list_conversations_sync(self) -> list[Conversation]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    conversation_id,
                    title,
                    project_root,
                    permission_mode,
                    created_at,
                    updated_at
                FROM conversations
                ORDER BY updated_at DESC, conversation_id ASC
                """,
            ).fetchall()
        return [_row_to_conversation(row) for row in rows]

    def _update_conversation_sync(
        self,
        conversation_id: str,
        title: str | None,
        permission_mode: PermissionMode | None,
    ) -> Conversation:
        if title is None and permission_mode is None:
            return self._get_conversation_sync(conversation_id)

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    """
                    SELECT
                        conversation_id,
                        title,
                        project_root,
                        permission_mode,
                        created_at,
                        updated_at
                    FROM conversations
                    WHERE conversation_id = ?
                    """,
                    (conversation_id,),
                ).fetchone()
                if row is None:
                    raise ChatNotFoundError(f"conversation not found: {conversation_id}")

                current = _row_to_conversation(row)
                next_title = current.title if title is None else _normalize_title(title)
                next_permission_mode = (
                    current.permission_mode
                    if permission_mode is None
                    else permission_mode
                )
                if (
                    permission_mode is not None
                    and permission_mode != current.permission_mode
                ):
                    _assert_permission_mode_change_allowed(connection, conversation_id)

                updated = current.model_copy(
                    update={
                        "title": next_title,
                        "permission_mode": next_permission_mode,
                        "updated_at": utc_now(),
                    },
                )
                connection.execute(
                    """
                    UPDATE conversations
                    SET title = ?, permission_mode = ?, updated_at = ?
                    WHERE conversation_id = ?
                    """,
                    (
                        updated.title,
                        updated.permission_mode.value,
                        _serialize_datetime(updated.updated_at),
                        conversation_id,
                    ),
                )
                connection.commit()
            except (ChatNotFoundError, ChatConflictError, ValueError):
                connection.rollback()
                raise
            except sqlite3.Error:
                connection.rollback()
                raise
        return updated

    def _begin_run_sync(
        self,
        conversation_id: str,
        content: str,
        session_id: str,
    ) -> tuple[ChatMessage, RunRecord]:
        now = utc_now()
        trace_path = _trace_path_for_session(session_id)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                if connection.execute(
                    "SELECT 1 FROM conversations WHERE conversation_id = ?",
                    (conversation_id,),
                ).fetchone() is None:
                    raise ChatNotFoundError(
                        f"conversation not found: {conversation_id}",
                    )
                if _has_active_run(connection, conversation_id):
                    raise ChatConflictError("active run already exists")

                sequence = _next_sequence(connection, conversation_id)
                user_message = ChatMessage(
                    message_id=new_id(),
                    conversation_id=conversation_id,
                    role=MessageRole.USER,
                    content=content,
                    sequence=sequence,
                    created_at=now,
                )
                run = RunRecord(
                    session_id=session_id,
                    conversation_id=conversation_id,
                    user_message_id=user_message.message_id,
                    trace_path=trace_path,
                    status=RunStatus.QUEUED,
                    created_at=now,
                )
                connection.execute(
                    """
                    INSERT INTO messages (
                        message_id,
                        conversation_id,
                        role,
                        content,
                        sequence,
                        created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_message.message_id,
                        user_message.conversation_id,
                        user_message.role.value,
                        user_message.content,
                        user_message.sequence,
                        _serialize_datetime(user_message.created_at),
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO runs (
                        session_id,
                        conversation_id,
                        user_message_id,
                        assistant_message_id,
                        trace_path,
                        status,
                        error_code,
                        created_at,
                        started_at,
                        finished_at
                    ) VALUES (?, ?, ?, NULL, ?, ?, NULL, ?, NULL, NULL)
                    """,
                    (
                        run.session_id,
                        run.conversation_id,
                        run.user_message_id,
                        run.trace_path,
                        run.status.value,
                        _serialize_datetime(run.created_at),
                    ),
                )
                connection.commit()
            except sqlite3.IntegrityError as exc:
                connection.rollback()
                raise _translate_integrity_error(exc) from exc
            except (ChatNotFoundError, ChatConflictError, ValueError):
                connection.rollback()
                raise
            except sqlite3.Error:
                connection.rollback()
                raise
        return user_message, run

    def _get_run_sync(self, session_id: str) -> RunRecord:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    session_id,
                    conversation_id,
                    user_message_id,
                    assistant_message_id,
                    trace_path,
                    status,
                    error_code,
                    created_at,
                    started_at,
                    finished_at
                FROM runs
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
        if row is None:
            raise ChatNotFoundError(f"run not found: {session_id}")
        return _row_to_run(row)

    def _list_runs_sync(self, conversation_id: str) -> list[RunRecord]:
        with self._connect() as connection:
            if connection.execute(
                "SELECT 1 FROM conversations WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone() is None:
                raise ChatNotFoundError(
                    f"conversation not found: {conversation_id}",
                )
            rows = connection.execute(
                """
                SELECT
                    r.session_id,
                    r.conversation_id,
                    r.user_message_id,
                    r.assistant_message_id,
                    r.trace_path,
                    r.status,
                    r.error_code,
                    r.created_at,
                    r.started_at,
                    r.finished_at
                FROM runs AS r
                JOIN messages AS m ON m.message_id = r.user_message_id
                WHERE r.conversation_id = ?
                ORDER BY m.sequence ASC
                """,
                (conversation_id,),
            ).fetchall()
        return [_row_to_run(row) for row in rows]

    def _get_conversation_state_sync(
        self,
        conversation_id: str,
    ) -> tuple[RunRecord | None, ApprovalRequest | None]:
        with self._connect() as connection:
            connection.execute("BEGIN")
            try:
                conversation_row = connection.execute(
                    """
                    SELECT conversation_id
                    FROM conversations
                    WHERE conversation_id = ?
                    """,
                    (conversation_id,),
                ).fetchone()
                if conversation_row is None:
                    raise ChatNotFoundError(
                        f"conversation not found: {conversation_id}",
                    )

                run_row = connection.execute(
                    """
                    SELECT
                        r.session_id,
                        r.conversation_id,
                        r.user_message_id,
                        r.assistant_message_id,
                        r.trace_path,
                        r.status,
                        r.error_code,
                        r.created_at,
                        r.started_at,
                        r.finished_at
                    FROM runs r
                    INNER JOIN messages m ON r.user_message_id = m.message_id
                    WHERE r.conversation_id = ?
                    ORDER BY m.sequence DESC
                    LIMIT 1
                    """,
                    (conversation_id,),
                ).fetchone()
                if run_row is None:
                    connection.commit()
                    return None, None

                latest_run = _row_to_run(run_row)
                if latest_run.status is not RunStatus.WAITING_APPROVAL:
                    connection.commit()
                    return latest_run, None

                approval_row = connection.execute(
                    """
                    SELECT
                        approval_id,
                        conversation_id,
                        session_id,
                        tool_call_id,
                        tool_name,
                        canonical_path,
                        operation,
                        status,
                        requested_at,
                        decided_at
                    FROM approval_requests
                    WHERE conversation_id = ?
                      AND session_id = ?
                      AND status = ?
                    LIMIT 1
                    """,
                    (
                        conversation_id,
                        latest_run.session_id,
                        ApprovalStatus.PENDING.value,
                    ),
                ).fetchone()
                connection.commit()
            except (ChatNotFoundError, ChatConflictError, ValueError):
                connection.rollback()
                raise
            except sqlite3.Error:
                connection.rollback()
                raise

        pending_approval = (
            _row_to_approval(approval_row) if approval_row is not None else None
        )
        return latest_run, pending_approval

    def _list_messages_sync(self, conversation_id: str) -> list[ChatMessage]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    message_id,
                    conversation_id,
                    role,
                    content,
                    sequence,
                    created_at
                FROM messages
                WHERE conversation_id = ?
                ORDER BY sequence ASC
                """,
                (conversation_id,),
            ).fetchall()
        return [_row_to_message(row) for row in rows]

    def _list_context_before_sync(
        self,
        conversation_id: str,
        user_message_id: str,
    ) -> list[ChatMessage]:
        with self._connect() as connection:
            anchor = connection.execute(
                """
                SELECT conversation_id, sequence
                FROM messages
                WHERE message_id = ?
                """,
                (user_message_id,),
            ).fetchone()
            if anchor is None or anchor["conversation_id"] != conversation_id:
                raise ChatNotFoundError(
                    f"message not found in conversation: {user_message_id}",
                )
            rows = connection.execute(
                """
                SELECT
                    message_id,
                    conversation_id,
                    role,
                    content,
                    sequence,
                    created_at
                FROM messages
                WHERE conversation_id = ?
                  AND sequence < ?
                ORDER BY sequence ASC
                """,
                (conversation_id, anchor["sequence"]),
            ).fetchall()
        return [_row_to_message(row) for row in rows]

    def _transition_run_sync(
        self,
        session_id: str,
        expected: RunStatus,
        target: RunStatus,
    ) -> RunRecord:
        now = utc_now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    """
                    SELECT
                        session_id,
                        conversation_id,
                        user_message_id,
                        assistant_message_id,
                        trace_path,
                        status,
                        error_code,
                        created_at,
                        started_at,
                        finished_at
                    FROM runs
                    WHERE session_id = ?
                    """,
                    (session_id,),
                ).fetchone()
                if row is None:
                    raise ChatNotFoundError(f"run not found: {session_id}")
                current = _row_to_run(row)
                _validate_run_transition(current.status, expected, target)
                started_at = current.started_at
                finished_at = current.finished_at
                if target is RunStatus.RUNNING and started_at is None:
                    started_at = now
                if target in _TERMINAL_RUN_STATUSES:
                    finished_at = now
                updated = current.model_copy(
                    update={
                        "status": target,
                        "started_at": started_at,
                        "finished_at": finished_at,
                    },
                )
                connection.execute(
                    """
                    UPDATE runs
                    SET status = ?, started_at = ?, finished_at = ?
                    WHERE session_id = ?
                    """,
                    (
                        updated.status.value,
                        _serialize_optional_datetime(updated.started_at),
                        _serialize_optional_datetime(updated.finished_at),
                        session_id,
                    ),
                )
                connection.commit()
            except (ChatNotFoundError, ChatConflictError):
                connection.rollback()
                raise
            except sqlite3.Error:
                connection.rollback()
                raise
        return updated

    def _complete_run_sync(self, session_id: str, answer: str) -> ChatMessage:
        now = utc_now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    """
                    SELECT
                        session_id,
                        conversation_id,
                        user_message_id,
                        assistant_message_id,
                        trace_path,
                        status,
                        error_code,
                        created_at,
                        started_at,
                        finished_at
                    FROM runs
                    WHERE session_id = ?
                    """,
                    (session_id,),
                ).fetchone()
                if row is None:
                    raise ChatNotFoundError(f"run not found: {session_id}")
                current = _row_to_run(row)
                if current.status is not RunStatus.RUNNING:
                    raise ChatConflictError("run must be running to complete")

                sequence = _next_sequence(connection, current.conversation_id)
                assistant = ChatMessage(
                    message_id=new_id(),
                    conversation_id=current.conversation_id,
                    role=MessageRole.ASSISTANT,
                    content=answer,
                    sequence=sequence,
                    created_at=now,
                )
                connection.execute(
                    """
                    INSERT INTO messages (
                        message_id,
                        conversation_id,
                        role,
                        content,
                        sequence,
                        created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        assistant.message_id,
                        assistant.conversation_id,
                        assistant.role.value,
                        assistant.content,
                        assistant.sequence,
                        _serialize_datetime(assistant.created_at),
                    ),
                )
                connection.execute(
                    """
                    UPDATE runs
                    SET assistant_message_id = ?,
                        status = ?,
                        finished_at = ?
                    WHERE session_id = ?
                    """,
                    (
                        assistant.message_id,
                        RunStatus.COMPLETED.value,
                        _serialize_datetime(now),
                        session_id,
                    ),
                )
                connection.commit()
            except (ChatNotFoundError, ChatConflictError, ValueError):
                connection.rollback()
                raise
            except sqlite3.Error:
                connection.rollback()
                raise
        return assistant

    def _fail_run_sync(self, session_id: str, error_code: str) -> RunRecord:
        if not error_code.strip():
            raise ValueError("error_code must not be empty")
        return self._fail_run_in_transaction(session_id, error_code.strip())

    def _fail_run_in_transaction(self, session_id: str, error_code: str) -> RunRecord:
        now = utc_now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    """
                    SELECT
                        session_id,
                        conversation_id,
                        user_message_id,
                        assistant_message_id,
                        trace_path,
                        status,
                        error_code,
                        created_at,
                        started_at,
                        finished_at
                    FROM runs
                    WHERE session_id = ?
                    """,
                    (session_id,),
                ).fetchone()
                if row is None:
                    raise ChatNotFoundError(f"run not found: {session_id}")
                current = _row_to_run(row)
                _validate_run_transition(
                    current.status,
                    current.status,
                    RunStatus.FAILED,
                )
                updated = current.model_copy(
                    update={
                        "status": RunStatus.FAILED,
                        "error_code": error_code,
                        "finished_at": now,
                    },
                )
                connection.execute(
                    """
                    UPDATE runs
                    SET status = ?, error_code = ?, finished_at = ?
                    WHERE session_id = ?
                    """,
                    (
                        updated.status.value,
                        updated.error_code,
                        _serialize_datetime(now),
                        session_id,
                    ),
                )
                connection.commit()
            except (ChatNotFoundError, ChatConflictError, ValueError):
                connection.rollback()
                raise
            except sqlite3.Error:
                connection.rollback()
                raise
        return updated

    def _interrupt_run_sync(self, session_id: str) -> RunRecord:
        current = self._get_run_sync(session_id)
        if current.status in _TERMINAL_RUN_STATUSES:
            raise ChatConflictError("run is already terminal")
        return self._transition_run_sync(
            session_id,
            current.status,
            RunStatus.INTERRUPTED,
        )

    def _create_approval_sync(
        self,
        conversation_id: str,
        session_id: str,
        tool_call_id: str,
        tool_name: str,
        canonical_path: str,
        approval_id: str | None,
    ) -> ApprovalRequest:
        now = utc_now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                run_row = connection.execute(
                    """
                    SELECT
                        session_id,
                        conversation_id,
                        user_message_id,
                        assistant_message_id,
                        trace_path,
                        status,
                        error_code,
                        created_at,
                        started_at,
                        finished_at
                    FROM runs
                    WHERE session_id = ?
                    """,
                    (session_id,),
                ).fetchone()
                if run_row is None:
                    raise ChatNotFoundError(f"run not found: {session_id}")
                run = _row_to_run(run_row)
                if run.conversation_id != conversation_id:
                    raise ChatConflictError("approval conversation mismatch")
                if run.status is not RunStatus.WAITING_APPROVAL:
                    raise ChatConflictError("run must be waiting for approval")

                approval = ApprovalRequest(
                    approval_id=approval_id or new_id(),
                    conversation_id=conversation_id,
                    session_id=session_id,
                    tool_call_id=tool_call_id,
                    tool_name=tool_name,
                    canonical_path=canonical_path,
                    operation=AccessOperation.READ,
                    status=ApprovalStatus.PENDING,
                    requested_at=now,
                )
                connection.execute(
                    """
                    INSERT INTO approval_requests (
                        approval_id,
                        conversation_id,
                        session_id,
                        tool_call_id,
                        tool_name,
                        canonical_path,
                        operation,
                        status,
                        requested_at,
                        decided_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                    """,
                    (
                        approval.approval_id,
                        approval.conversation_id,
                        approval.session_id,
                        approval.tool_call_id,
                        approval.tool_name,
                        approval.canonical_path,
                        approval.operation.value,
                        approval.status.value,
                        _serialize_datetime(approval.requested_at),
                    ),
                )
                connection.commit()
            except sqlite3.IntegrityError as exc:
                connection.rollback()
                raise _translate_integrity_error(exc) from exc
            except (ChatNotFoundError, ChatConflictError, ValueError):
                connection.rollback()
                raise
            except sqlite3.Error:
                connection.rollback()
                raise
        return approval

    def _get_approval_sync(self, approval_id: str) -> ApprovalRequest:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    approval_id,
                    conversation_id,
                    session_id,
                    tool_call_id,
                    tool_name,
                    canonical_path,
                    operation,
                    status,
                    requested_at,
                    decided_at
                FROM approval_requests
                WHERE approval_id = ?
                """,
                (approval_id,),
            ).fetchone()
        if row is None:
            raise ChatNotFoundError(f"approval not found: {approval_id}")
        return _row_to_approval(row)

    def _resolve_approval_sync(
        self,
        approval_id: str,
        decision: ApprovalStatus,
    ) -> ApprovalRequest:
        if decision not in {ApprovalStatus.APPROVED, ApprovalStatus.DENIED}:
            raise ChatConflictError("approval decision must be approved or denied")
        now = utc_now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    """
                    SELECT
                        approval_id,
                        conversation_id,
                        session_id,
                        tool_call_id,
                        tool_name,
                        canonical_path,
                        operation,
                        status,
                        requested_at,
                        decided_at
                    FROM approval_requests
                    WHERE approval_id = ?
                    """,
                    (approval_id,),
                ).fetchone()
                if row is None:
                    raise ChatNotFoundError(f"approval not found: {approval_id}")
                current = _row_to_approval(row)
                if current.status is not ApprovalStatus.PENDING:
                    raise ChatConflictError("approval is not pending")
                updated = current.model_copy(
                    update={"status": decision, "decided_at": now},
                )
                connection.execute(
                    """
                    UPDATE approval_requests
                    SET status = ?, decided_at = ?
                    WHERE approval_id = ? AND status = 'pending'
                    """,
                    (
                        updated.status.value,
                        _serialize_datetime(now),
                        approval_id,
                    ),
                )
                if connection.total_changes == 0:
                    raise ChatConflictError("approval is not pending")
                connection.commit()
            except (ChatNotFoundError, ChatConflictError):
                connection.rollback()
                raise
            except sqlite3.Error:
                connection.rollback()
                raise
        return updated

    def _invalidate_approval_sync(self, approval_id: str) -> ApprovalRequest:
        now = utc_now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    """
                    SELECT
                        approval_id,
                        conversation_id,
                        session_id,
                        tool_call_id,
                        tool_name,
                        canonical_path,
                        operation,
                        status,
                        requested_at,
                        decided_at
                    FROM approval_requests
                    WHERE approval_id = ?
                    """,
                    (approval_id,),
                ).fetchone()
                if row is None:
                    raise ChatNotFoundError(f"approval not found: {approval_id}")
                current = _row_to_approval(row)
                if current.status is not ApprovalStatus.PENDING:
                    raise ChatConflictError("approval is not pending")
                updated = current.model_copy(
                    update={
                        "status": ApprovalStatus.INVALIDATED,
                        "decided_at": now,
                    },
                )
                connection.execute(
                    """
                    UPDATE approval_requests
                    SET status = ?, decided_at = ?
                    WHERE approval_id = ? AND status = 'pending'
                    """,
                    (
                        updated.status.value,
                        _serialize_datetime(now),
                        approval_id,
                    ),
                )
                if connection.total_changes == 0:
                    raise ChatConflictError("approval is not pending")
                connection.commit()
            except (ChatNotFoundError, ChatConflictError):
                connection.rollback()
                raise
            except sqlite3.Error:
                connection.rollback()
                raise
        return updated

    def _interrupt_unfinished_sync(self) -> tuple[int, int]:
        now = utc_now()
        now_text = _serialize_datetime(now)
        active_statuses = tuple(status.value for status in RunStatus.active())
        placeholders = ", ".join("?" for _ in active_statuses)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                interrupted_runs = connection.execute(
                    f"""
                    UPDATE runs
                    SET status = ?, finished_at = ?
                    WHERE status IN ({placeholders})
                    """,
                    (RunStatus.INTERRUPTED.value, now_text, *active_statuses),
                ).rowcount
                invalidated_approvals = connection.execute(
                    """
                    UPDATE approval_requests
                    SET status = ?, decided_at = ?
                    WHERE status = 'pending'
                    """,
                    (ApprovalStatus.INVALIDATED.value, now_text),
                ).rowcount
                connection.commit()
            except sqlite3.Error:
                connection.rollback()
                raise
        return interrupted_runs, invalidated_approvals


def _trace_path_for_session(session_id: str) -> str:
    return f"traces/{session_id}.jsonl"


def _next_sequence(connection: sqlite3.Connection, conversation_id: str) -> int:
    row = connection.execute(
        """
        SELECT COALESCE(MAX(sequence), 0) + 1
        FROM messages
        WHERE conversation_id = ?
        """,
        (conversation_id,),
    ).fetchone()
    assert row is not None
    return int(row[0])


def _has_active_run(connection: sqlite3.Connection, conversation_id: str) -> bool:
    active_statuses = tuple(status.value for status in RunStatus.active())
    placeholders = ", ".join("?" for _ in active_statuses)
    row = connection.execute(
        f"""
        SELECT 1
        FROM runs
        WHERE conversation_id = ?
          AND status IN ({placeholders})
        LIMIT 1
        """,
        (conversation_id, *active_statuses),
    ).fetchone()
    return row is not None


def _validate_run_transition(
    current: RunStatus,
    expected: RunStatus,
    target: RunStatus,
) -> None:
    if current is not expected:
        raise ChatConflictError("run status mismatch")
    if target not in _RUN_TRANSITIONS[current]:
        raise ChatConflictError("invalid run transition")


def _translate_integrity_error(exc: sqlite3.IntegrityError) -> ChatConflictError:
    message = str(exc).lower()
    if "one_active_run_per_conversation" in message:
        return ChatConflictError("active run already exists")
    if "approval_requests.session_id" in message and "tool_call_id" in message:
        return ChatConflictError("approval already exists for tool call")
    if "approval_requests.approval_id" in message:
        return ChatConflictError("approval already exists")
    if "runs.session_id" in message:
        return ChatConflictError("run already exists")
    raise exc


def _serialize_optional_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return _serialize_datetime(value)


def _normalize_title(title: str) -> str:
    stripped = title.strip()
    if not stripped:
        raise ValueError("title must not be empty")
    if len(stripped) > 120:
        raise ValueError("title must be at most 120 characters")
    return stripped


def _serialize_datetime(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _deserialize_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return parsed.astimezone(UTC)


def _row_to_conversation(row: sqlite3.Row) -> Conversation:
    return Conversation(
        conversation_id=row["conversation_id"],
        title=row["title"],
        project_root=row["project_root"],
        permission_mode=PermissionMode(row["permission_mode"]),
        created_at=_deserialize_datetime(row["created_at"]),
        updated_at=_deserialize_datetime(row["updated_at"]),
    )


def _row_to_message(row: sqlite3.Row) -> ChatMessage:
    return ChatMessage(
        message_id=row["message_id"],
        conversation_id=row["conversation_id"],
        role=MessageRole(row["role"]),
        content=row["content"],
        sequence=row["sequence"],
        created_at=_deserialize_datetime(row["created_at"]),
    )


def _row_to_run(row: sqlite3.Row) -> RunRecord:
    return RunRecord(
        session_id=row["session_id"],
        conversation_id=row["conversation_id"],
        user_message_id=row["user_message_id"],
        trace_path=row["trace_path"],
        assistant_message_id=row["assistant_message_id"],
        status=RunStatus(row["status"]),
        error_code=row["error_code"],
        created_at=_deserialize_datetime(row["created_at"]),
        started_at=(
            _deserialize_datetime(row["started_at"])
            if row["started_at"] is not None
            else None
        ),
        finished_at=(
            _deserialize_datetime(row["finished_at"])
            if row["finished_at"] is not None
            else None
        ),
    )


def _row_to_approval(row: sqlite3.Row) -> ApprovalRequest:
    return ApprovalRequest(
        approval_id=row["approval_id"],
        conversation_id=row["conversation_id"],
        session_id=row["session_id"],
        tool_call_id=row["tool_call_id"],
        tool_name=row["tool_name"],
        canonical_path=row["canonical_path"],
        operation=AccessOperation(row["operation"]),
        status=ApprovalStatus(row["status"]),
        requested_at=_deserialize_datetime(row["requested_at"]),
        decided_at=(
            _deserialize_datetime(row["decided_at"])
            if row["decided_at"] is not None
            else None
        ),
    )
