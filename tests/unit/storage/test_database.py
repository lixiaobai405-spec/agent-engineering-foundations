from __future__ import annotations

import asyncio
import importlib.util
import sqlite3
from pathlib import Path
from typing import Any

import pytest

CONVERSATION_ID = "11111111-1111-4111-8111-111111111111"
MESSAGE_ID = "33333333-3333-4333-8333-333333333333"
SESSION_ID = "22222222-2222-4222-8222-222222222222"
APPROVAL_ID = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
NOW_TEXT = "2026-08-02T12:00:00+00:00"
TRACE_PATH = "traces/session.jsonl"
ACTIVITY_EVENT_ID = "12345678-1234-4234-8234-123456789001"


def _require_storage_package() -> None:
    assert importlib.util.find_spec("agent_foundations.storage") is not None


def _require_chat_schema() -> None:
    assert importlib.util.find_spec("agent_foundations.chat.schema") is not None


def _import_storage() -> tuple[Any, Any, Any]:
    _require_storage_package()
    from agent_foundations.storage.database import SqliteDatabase
    from agent_foundations.storage.migrations import Migration, validate_migration_sequence

    return SqliteDatabase, Migration, validate_migration_sequence


def _import_chat_schema() -> tuple[Any, Any, Any]:
    _require_chat_schema()
    from agent_foundations.chat.schema import (
        CHAT_MIGRATIONS,
        MIGRATION_V1_TO_V2_STATEMENTS,
        SCHEMA_V1_STATEMENTS,
    )

    return CHAT_MIGRATIONS, SCHEMA_V1_STATEMENTS, MIGRATION_V1_TO_V2_STATEMENTS


def _tables(connection: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'",
        )
    }


def _indexes(connection: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index'",
        )
    }


def _insert_v1_core_rows(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        INSERT INTO conversations (
            conversation_id, title, project_root, permission_mode, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            CONVERSATION_ID,
            "fixture conversation",
            "/tmp/project",
            "PROJECT_READ_ONLY",
            NOW_TEXT,
            NOW_TEXT,
        ),
    )
    connection.execute(
        """
        INSERT INTO messages (
            message_id, conversation_id, role, content, sequence, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (MESSAGE_ID, CONVERSATION_ID, "user", "fixture question", 1, NOW_TEXT),
    )
    connection.execute(
        """
        INSERT INTO runs (
            session_id, conversation_id, user_message_id, assistant_message_id,
            trace_path, status, error_code, created_at, started_at, finished_at
        ) VALUES (?, ?, ?, NULL, ?, ?, NULL, ?, NULL, NULL)
        """,
        (SESSION_ID, CONVERSATION_ID, MESSAGE_ID, TRACE_PATH, "completed", NOW_TEXT),
    )
    connection.execute(
        """
        INSERT INTO approval_requests (
            approval_id, conversation_id, session_id, tool_call_id, tool_name,
            canonical_path, operation, status, requested_at, decided_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
        """,
        (
            APPROVAL_ID,
            CONVERSATION_ID,
            SESSION_ID,
            "call-1",
            "read_file",
            "README.md",
            "read",
            "pending",
            NOW_TEXT,
        ),
    )


def _insert_v2_activity_row(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        INSERT INTO chat_tool_activities (
            session_id, tool_call_id, tool_name, status,
            arguments_summary, result_summary, started_at, finished_at, last_event_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            SESSION_ID,
            "call-activity",
            "read_file",
            "completed",
            "README.md",
            "12 lines",
            NOW_TEXT,
            NOW_TEXT,
            ACTIVITY_EVENT_ID,
        ),
    )


def _create_real_v1_database(path: Path) -> dict[str, list[tuple[object, ...]]]:
    _, SCHEMA_V1_STATEMENTS, _ = _import_chat_schema()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        for statement in SCHEMA_V1_STATEMENTS:
            connection.execute(statement)
        _insert_v1_core_rows(connection)
        connection.execute("PRAGMA user_version = 1")
        connection.commit()
        preserved = {
            table: [
                tuple(row)
                for row in connection.execute(f"SELECT * FROM {table} ORDER BY rowid")
            ]
            for table in (
                "conversations",
                "messages",
                "runs",
                "approval_requests",
            )
        }
    finally:
        connection.close()
    return preserved


def _create_real_v2_database(path: Path) -> dict[str, Any]:
    CHAT_MIGRATIONS, _, MIGRATION_V1_TO_V2 = _import_chat_schema()
    preserved_v1 = _create_real_v1_database(path)
    connection = sqlite3.connect(path)
    try:
        for statement in MIGRATION_V1_TO_V2:
            connection.execute(statement)
        _insert_v2_activity_row(connection)
        connection.execute("PRAGMA user_version = 2")
        connection.commit()
        activity_rows = [
            tuple(row)
            for row in connection.execute(
                "SELECT * FROM chat_tool_activities ORDER BY rowid",
            )
        ]
        indexes = _indexes(connection)
    finally:
        connection.close()
    return {
        "v1_rows": preserved_v1,
        "activity_rows": activity_rows,
        "indexes": indexes,
    }


def test_chat_schema_version_constants() -> None:
    _require_chat_schema()
    from agent_foundations.chat.schema import (
        LATEST_CHAT_SCHEMA_VERSION,
        NEXT_PHASE2_MIGRATION_VERSION,
    )

    assert LATEST_CHAT_SCHEMA_VERSION == 2
    assert NEXT_PHASE2_MIGRATION_VERSION == 3


@pytest.mark.asyncio
async def test_migration_is_frozen() -> None:
    _, Migration, _ = _import_storage()
    migration = Migration(version=1, statements=("CREATE TABLE t (id INTEGER)",))
    with pytest.raises((TypeError, AttributeError)):
        migration.version = 2


def test_validate_migration_sequence_rejects_duplicate_version() -> None:
    _, Migration, validate_migration_sequence = _import_storage()
    with pytest.raises(ValueError, match="duplicate migration"):
        validate_migration_sequence(
            (
                Migration(version=1, statements=()),
                Migration(version=1, statements=()),
            ),
        )


def test_validate_migration_sequence_rejects_missing_version() -> None:
    _, Migration, validate_migration_sequence = _import_storage()
    with pytest.raises(ValueError, match="consecutive"):
        validate_migration_sequence(
            (
                Migration(version=1, statements=()),
                Migration(version=3, statements=()),
            ),
        )


def test_validate_migration_sequence_rejects_not_starting_at_one() -> None:
    _, Migration, validate_migration_sequence = _import_storage()
    with pytest.raises(ValueError, match="version 1"):
        validate_migration_sequence((Migration(version=2, statements=()),))


def test_validate_migration_sequence_rejects_unordered_versions() -> None:
    _, Migration, validate_migration_sequence = _import_storage()
    with pytest.raises(ValueError, match="version 1"):
        validate_migration_sequence(
            (
                Migration(version=2, statements=()),
                Migration(version=1, statements=()),
            ),
        )


@pytest.mark.asyncio
async def test_empty_database_migrates_sequentially_to_v2(tmp_path: Path) -> None:
    SqliteDatabase, _, _ = _import_storage()
    CHAT_MIGRATIONS, _, _ = _import_chat_schema()
    path = tmp_path / "nested" / "chat.sqlite3"
    database = SqliteDatabase(path, CHAT_MIGRATIONS)
    await database.initialize()
    assert path.is_file()
    with database.connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        assert _tables(connection) >= {
            "conversations",
            "messages",
            "runs",
            "approval_requests",
            "chat_tool_activities",
        }
        assert "one_active_run_per_conversation" in _indexes(connection)
        assert "idx_chat_tool_activities_session_started" in _indexes(connection)


@pytest.mark.asyncio
async def test_initialize_is_idempotent(tmp_path: Path) -> None:
    SqliteDatabase, _, _ = _import_storage()
    CHAT_MIGRATIONS, _, _ = _import_chat_schema()
    database = SqliteDatabase(tmp_path / "chat.sqlite3", CHAT_MIGRATIONS)
    await database.initialize()
    await database.initialize()
    with database.connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2


@pytest.mark.asyncio
async def test_existing_v1_database_upgrades_to_v2_without_data_loss(
    tmp_path: Path,
) -> None:
    SqliteDatabase, _, _ = _import_storage()
    CHAT_MIGRATIONS, _, _ = _import_chat_schema()
    path = tmp_path / "chat.sqlite3"
    preserved_before = _create_real_v1_database(path)
    database = SqliteDatabase(path, CHAT_MIGRATIONS)
    await database.initialize()
    with database.connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        assert "chat_tool_activities" in _tables(connection)
        preserved_after = {
            table: [
                tuple(row)
                for row in connection.execute(f"SELECT * FROM {table} ORDER BY rowid")
            ]
            for table in preserved_before
        }
    assert preserved_after == preserved_before


@pytest.mark.asyncio
async def test_existing_v2_database_is_adopted_without_reapplying_ddl(
    tmp_path: Path,
) -> None:
    SqliteDatabase, _, _ = _import_storage()
    CHAT_MIGRATIONS, _, _ = _import_chat_schema()
    path = tmp_path / "chat.sqlite3"
    fixture = _create_real_v2_database(path)
    database = SqliteDatabase(path, CHAT_MIGRATIONS)
    await database.initialize()
    await database.initialize()
    with database.connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        activity_rows = [
            tuple(row)
            for row in connection.execute(
                "SELECT * FROM chat_tool_activities ORDER BY rowid",
            )
        ]
        indexes = _indexes(connection)
        for table, rows in fixture["v1_rows"].items():
            after = [
                tuple(row)
                for row in connection.execute(f"SELECT * FROM {table} ORDER BY rowid")
            ]
            assert after == rows
    assert activity_rows == fixture["activity_rows"]
    assert indexes == fixture["indexes"]


@pytest.mark.asyncio
async def test_failed_empty_database_migration_rolls_back_entire_transaction(
    tmp_path: Path,
) -> None:
    SqliteDatabase, Migration, _ = _import_storage()
    _, SCHEMA_V1_STATEMENTS, _ = _import_chat_schema()
    broken = (
        Migration(version=1, statements=SCHEMA_V1_STATEMENTS),
        Migration(
            version=2,
            statements=(
                "CREATE TABLE chat_tool_activities (session_id TEXT PRIMARY KEY)",
                "CREATE TABLE chat_tool_activities (session_id TEXT PRIMARY KEY)",
            ),
        ),
    )
    path = tmp_path / "chat.sqlite3"
    database = SqliteDatabase(path, broken)
    with pytest.raises(sqlite3.OperationalError):
        await database.initialize()
    with database.connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 0
        assert "conversations" not in _tables(connection)


@pytest.mark.asyncio
async def test_failed_v1_to_v2_migration_rolls_back_to_v1(tmp_path: Path) -> None:
    SqliteDatabase, Migration, _ = _import_storage()
    path = tmp_path / "chat.sqlite3"
    preserved_before = _create_real_v1_database(path)
    broken = (
        Migration(version=1, statements=()),
        Migration(
            version=2,
            statements=(
                "CREATE TABLE chat_tool_activities (session_id TEXT PRIMARY KEY)",
                "CREATE TABLE chat_tool_activities (session_id TEXT PRIMARY KEY)",
            ),
        ),
    )
    database = SqliteDatabase(path, broken)
    with pytest.raises(sqlite3.OperationalError):
        await database.initialize()
    with database.connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        assert "chat_tool_activities" not in _tables(connection)
        preserved_after = {
            table: [
                tuple(row)
                for row in connection.execute(f"SELECT * FROM {table} ORDER BY rowid")
            ]
            for table in preserved_before
        }
    assert preserved_after == preserved_before


@pytest.mark.asyncio
async def test_initialize_rejects_future_user_version(tmp_path: Path) -> None:
    SqliteDatabase, _, _ = _import_storage()
    from agent_foundations.storage.database import FutureSchemaVersionError

    CHAT_MIGRATIONS, _, _ = _import_chat_schema()
    path = tmp_path / "chat.sqlite3"
    database = SqliteDatabase(path, CHAT_MIGRATIONS)
    await database.initialize()
    with database.connect() as connection:
        connection.execute("PRAGMA user_version = 99")
        connection.commit()
    with pytest.raises(FutureSchemaVersionError):
        await database.initialize()


def test_connect_sets_row_factory_foreign_keys_and_busy_timeout(
    tmp_path: Path,
) -> None:
    SqliteDatabase, _, _ = _import_storage()
    CHAT_MIGRATIONS, _, _ = _import_chat_schema()
    database = SqliteDatabase(tmp_path / "chat.sqlite3", CHAT_MIGRATIONS)
    with database.connect() as connection:
        assert connection.row_factory is sqlite3.Row
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 5000


@pytest.mark.asyncio
async def test_concurrent_initialize_on_same_path_both_succeed(tmp_path: Path) -> None:
    SqliteDatabase, _, _ = _import_storage()
    CHAT_MIGRATIONS, _, _ = _import_chat_schema()
    path = tmp_path / "chat.sqlite3"
    first = SqliteDatabase(path, CHAT_MIGRATIONS)
    second = SqliteDatabase(path, CHAT_MIGRATIONS)
    results = await asyncio.gather(
        first.initialize(),
        second.initialize(),
        return_exceptions=True,
    )
    assert len(results) == 2
    assert all(result is None for result in results)
    with first.connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        assert _tables(connection) >= {
            "conversations",
            "messages",
            "runs",
            "approval_requests",
            "chat_tool_activities",
        }


@pytest.mark.asyncio
async def test_conversation_repository_constructor_remains_compatible(
    tmp_path: Path,
) -> None:
    from agent_foundations.chat.repository import ConversationRepository

    repository = ConversationRepository(tmp_path / "chat.sqlite3")
    await repository.initialize()
    with repository._connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 7
