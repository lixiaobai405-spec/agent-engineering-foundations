from __future__ import annotations

import importlib.util
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from agent_foundations.security.models import (
    PermissionProfileName,
    PolicyDecision,
    PolicyOutcome,
    PolicyRequest,
    PolicyResource,
    ResourceScope,
    SideEffectKind,
    ToolManifest,
)
from agent_foundations.storage.database import FutureSchemaVersionError, SqliteDatabase
from agent_foundations.storage.migrations import Migration, get_application_migrations

NOW = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)


def _components() -> tuple[Any, ...]:
    assert importlib.util.find_spec("agent_foundations.security.schema") is not None, (
        "Task 13 schema module is missing"
    )
    from agent_foundations.security.capabilities import CapabilityIssuer
    from agent_foundations.security.repository import (
        AuthorizationCorruptStateError,
        AuthorizationRepository,
    )

    return AuthorizationRepository, AuthorizationCorruptStateError, CapabilityIssuer


def _request() -> PolicyRequest:
    return PolicyRequest(
        profile_version=1,
        run_id="11111111-1111-4111-8111-111111111111",
        tool_call_id="call-1",
        tool_name="read_file",
        manifest=ToolManifest(
            name="read_file",
            resource_kind="project_path",
            operations=("read",),
            side_effect=SideEffectKind.NONE,
            sandbox_required=False,
        ),
        resource=PolicyResource(
            kind="project_path",
            scope=ResourceScope.PROJECT_INTERNAL,
            identifier="README.md",
        ),
        operation="read",
    )


@pytest.mark.asyncio
async def test_empty_database_migrates_idempotently_to_v7(tmp_path: Path) -> None:
    AuthorizationRepository, _Corrupt, _Issuer = _components()
    path = tmp_path / "state.sqlite3"
    repository = AuthorizationRepository.from_path(path)
    await repository.initialize()
    await repository.initialize()

    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 7
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'",
            )
        }
    assert {"authorization_requests", "capabilities", "approval_requests"} <= tables


@pytest.mark.asyncio
async def test_v6_upgrade_preserves_existing_tables_rows_and_indexes(tmp_path: Path) -> None:
    AuthorizationRepository, _Corrupt, _Issuer = _components()
    path = tmp_path / "state.sqlite3"
    migrations = get_application_migrations()
    assert migrations[-1].version == 7
    await SqliteDatabase(path, migrations[:-1]).initialize()
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            INSERT INTO conversations (
                conversation_id, title, project_root, permission_mode,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                "Preserved",
                str(tmp_path),
                "PROJECT_READ_ONLY",
                NOW.isoformat(),
                NOW.isoformat(),
            ),
        )
        connection.commit()

    repository = AuthorizationRepository.from_path(path)
    await repository.initialize()
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 7
        assert connection.execute("SELECT title FROM conversations").fetchone()[0] == (
            "Preserved"
        )
        indexes = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'",
            )
        }
    assert "one_active_run_per_conversation" in indexes


@pytest.mark.asyncio
@pytest.mark.parametrize("starting_version", range(1, 7))
async def test_each_real_v1_through_v6_database_upgrades_to_v7(
    tmp_path: Path,
    starting_version: int,
) -> None:
    AuthorizationRepository, _Corrupt, _Issuer = _components()
    path = tmp_path / f"v{starting_version}.sqlite3"
    migrations = get_application_migrations()
    await SqliteDatabase(path, migrations[:starting_version]).initialize()
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            INSERT INTO conversations (
                conversation_id, title, project_root, permission_mode,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                f"00000000-0000-4000-8000-{starting_version:012d}",
                f"Preserved v{starting_version}",
                str(tmp_path),
                "PROJECT_READ_ONLY",
                NOW.isoformat(),
                NOW.isoformat(),
            ),
        )
        connection.commit()

    await AuthorizationRepository.from_path(path).initialize()
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 7
        assert connection.execute("SELECT title FROM conversations").fetchone()[0] == (
            f"Preserved v{starting_version}"
        )


@pytest.mark.asyncio
async def test_migration_failure_rolls_back_user_version_and_schema(tmp_path: Path) -> None:
    _components()
    path = tmp_path / "rollback.sqlite3"
    migrations = get_application_migrations()
    broken = (
        *migrations[:6],
        Migration(
            version=7,
            statements=(
                "CREATE TABLE task13_rollback_probe (id TEXT PRIMARY KEY)",
                "THIS IS NOT VALID SQL",
            ),
        ),
    )

    with pytest.raises(sqlite3.OperationalError):
        await SqliteDatabase(path, broken).initialize()

    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 0
        assert connection.execute(
            """
            SELECT COUNT(*) FROM sqlite_master
            WHERE type = 'table' AND name = 'task13_rollback_probe'
            """,
        ).fetchone()[0] == 0


@pytest.mark.asyncio
async def test_future_schema_is_rejected(tmp_path: Path) -> None:
    AuthorizationRepository, _Corrupt, _Issuer = _components()
    path = tmp_path / "state.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA user_version = 8")
    with pytest.raises(FutureSchemaVersionError):
        await AuthorizationRepository.from_path(path).initialize()


@pytest.mark.asyncio
async def test_authorization_update_and_capability_insert_rollback_together(
    tmp_path: Path,
) -> None:
    AuthorizationRepository, _Corrupt, CapabilityIssuer = _components()
    path = tmp_path / "state.sqlite3"
    repository = AuthorizationRepository.from_path(path)
    await repository.initialize()
    repository._before_capability_insert = lambda: (_ for _ in ()).throw(
        sqlite3.OperationalError("injected capability insert failure"),
    )
    from agent_foundations.security.approvals import (
        AuthorizationApproval,
        AuthorizationStatus,
    )

    approval = AuthorizationApproval(
        repository,
        PermissionProfileName.ASK_ALWAYS,
        clock=lambda: NOW,
    )
    issuer = CapabilityIssuer(
        repository,
        PermissionProfileName.ASK_ALWAYS,
        ttl=timedelta(minutes=5),
        clock=lambda: NOW,
    )

    pending = await approval.request(
        _request(),
        authorization_id="22222222-2222-4222-8222-222222222222",
    )
    approved = approval.decide(pending, AuthorizationStatus.APPROVED)
    with pytest.raises(sqlite3.OperationalError, match="injected capability"):
        await issuer.issue(
            _request(),
            PolicyOutcome(
                decision=PolicyDecision.ASK,
                rule_id="test.ask",
                reason_code="test",
            ),
            approved,
        )

    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "SELECT status FROM authorization_requests",
        ).fetchone()[0] == "pending"
        assert connection.execute("SELECT COUNT(*) FROM capabilities").fetchone()[0] == 0


@pytest.mark.asyncio
async def test_unknown_stored_status_fails_closed(tmp_path: Path) -> None:
    AuthorizationRepository, AuthorizationCorruptStateError, _Issuer = _components()
    path = tmp_path / "state.sqlite3"
    repository = AuthorizationRepository.from_path(path)
    await repository.initialize()
    resource_json = (
        '{"identifier":"README.md","kind":"project_path",'
        '"scope":"project_internal"}'
    )
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA ignore_check_constraints = ON")
        connection.execute(
            """
            INSERT INTO authorization_requests (
                authorization_id, run_id, tool_call_id, tool_name, resource_json,
                operation, profile_name, profile_version, status, requested_at, decided_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                "22222222-2222-4222-8222-222222222222",
                _request().run_id,
                _request().tool_call_id,
                _request().tool_name,
                resource_json,
                _request().operation,
                PermissionProfileName.ASK_ALWAYS.value,
                1,
                "corrupt-status",
                NOW.isoformat(),
            ),
        )
        connection.commit()

    with pytest.raises(AuthorizationCorruptStateError):
        await repository.get_authorization("22222222-2222-4222-8222-222222222222")
