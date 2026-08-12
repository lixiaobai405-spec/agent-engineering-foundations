from __future__ import annotations

import asyncio
import json
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, cast
from uuid import uuid4

from pydantic import ValidationError

from agent_foundations.security.approvals import (
    AuthorizationRecord,
    AuthorizationStatus,
)
from agent_foundations.security.models import (
    PermissionProfileName,
    PolicyRequest,
    PolicyResource,
)
from agent_foundations.storage.database import SqliteDatabase
from agent_foundations.storage.migrations import get_application_migrations

if TYPE_CHECKING:
    from agent_foundations.security.capabilities import Capability


class AuthorizationRepositoryError(RuntimeError):
    """Base authorization persistence error."""


class AuthorizationNotFoundError(AuthorizationRepositoryError):
    """Authorization or capability row does not exist."""


class AuthorizationConflictError(AuthorizationRepositoryError):
    """Stable tool-call identity is bound to different authorization facts."""


class AuthorizationCorruptStateError(AuthorizationRepositoryError):
    """Stored authorization state is unknown, malformed, or inconsistent."""


def _serialize_datetime(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _deserialize_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("stored timestamp must be timezone-aware")
    return parsed.astimezone(UTC)


def _resource_from_json(value: str) -> PolicyResource:
    try:
        payload = json.loads(value)
        if not isinstance(payload, dict):
            raise ValueError("resource_json must be an object")
        return PolicyResource.model_validate(payload)
    except (json.JSONDecodeError, ValidationError, ValueError, TypeError) as exc:
        raise AuthorizationCorruptStateError("stored resource_json is invalid") from exc


def _row_to_authorization(row: sqlite3.Row) -> AuthorizationRecord:
    try:
        return AuthorizationRecord(
            authorization_id=row["authorization_id"],
            run_id=row["run_id"],
            tool_call_id=row["tool_call_id"],
            tool_name=row["tool_name"],
            resource=_resource_from_json(row["resource_json"]),
            operation=row["operation"],
            profile_name=PermissionProfileName(row["profile_name"]),
            profile_version=row["profile_version"],
            status=AuthorizationStatus(row["status"]),
            requested_at=_deserialize_datetime(row["requested_at"]),
            decided_at=(
                _deserialize_datetime(row["decided_at"])
                if row["decided_at"] is not None
                else None
            ),
        )
    except (ValidationError, ValueError) as exc:
        raise AuthorizationCorruptStateError("stored authorization row is invalid") from exc


def _row_to_capability(row: sqlite3.Row) -> Capability:
    from agent_foundations.security.capabilities import Capability

    try:
        return Capability(
            capability_id=row["capability_id"],
            authorization_id=row["authorization_id"],
            run_id=row["run_id"],
            tool_call_id=row["tool_call_id"],
            tool_name=row["tool_name"],
            resource=_resource_from_json(row["resource_json"]),
            operation=row["operation"],
            profile_version=row["profile_version"],
            issued_at=_deserialize_datetime(row["issued_at"]),
            expires_at=_deserialize_datetime(row["expires_at"]),
            consumed_at=(
                _deserialize_datetime(row["consumed_at"])
                if row["consumed_at"] is not None
                else None
            ),
        )
    except (ValidationError, ValueError) as exc:
        raise AuthorizationCorruptStateError("stored capability row is invalid") from exc


_AUTHORIZATION_COLUMNS = """
authorization_id, run_id, tool_call_id, tool_name, resource_json, operation,
profile_name, profile_version, status, requested_at, decided_at
"""

_CAPABILITY_COLUMNS = """
capability_id, authorization_id, run_id, tool_call_id, tool_name, resource_json,
operation, profile_version, issued_at, expires_at, consumed_at
"""


class AuthorizationRepository:
    def __init__(self, database: SqliteDatabase) -> None:
        self._database = database
        self._before_capability_insert: Callable[[], None] | None = None

    @classmethod
    def from_path(cls, path: Path) -> AuthorizationRepository:
        return cls(SqliteDatabase(path, get_application_migrations()))

    async def initialize(self) -> None:
        await self._database.initialize()

    async def create_pending(
        self,
        request: PolicyRequest,
        profile_name: PermissionProfileName,
        *,
        authorization_id: str,
        requested_at: datetime,
    ) -> AuthorizationRecord:
        return await asyncio.to_thread(
            self._create_pending_sync,
            request,
            profile_name,
            authorization_id,
            requested_at,
        )

    async def record_denied(
        self,
        request: PolicyRequest,
        profile_name: PermissionProfileName,
        *,
        authorization_id: str | None,
        decided_at: datetime,
    ) -> AuthorizationRecord:
        return await asyncio.to_thread(
            self._record_denied_sync,
            request,
            profile_name,
            authorization_id,
            decided_at,
        )

    async def invalidate_pending(
        self,
        authorization_id: str,
        *,
        decided_at: datetime,
    ) -> AuthorizationRecord:
        return await asyncio.to_thread(
            self._invalidate_pending_sync,
            authorization_id,
            decided_at,
        )

    async def issue_capability(
        self,
        request: PolicyRequest,
        profile_name: PermissionProfileName,
        *,
        authorization_id: str | None,
        target_status: AuthorizationStatus,
        issued_at: datetime,
        expires_at: datetime,
    ) -> Capability:
        return await asyncio.to_thread(
            self._issue_capability_sync,
            request,
            profile_name,
            authorization_id,
            target_status,
            issued_at,
            expires_at,
        )

    async def consume_capability(
        self,
        capability_id: str,
        execution: PolicyRequest,
        *,
        consumed_at: datetime,
    ) -> Capability:
        return await asyncio.to_thread(
            self._consume_capability_sync,
            capability_id,
            execution,
            consumed_at,
        )

    async def get_authorization(self, authorization_id: str) -> AuthorizationRecord:
        return await asyncio.to_thread(self._get_authorization_sync, authorization_id)

    async def get_capability(self, capability_id: str) -> Capability:
        return await asyncio.to_thread(self._get_capability_sync, capability_id)

    async def count_capabilities(self, authorization_id: str) -> int:
        return await asyncio.to_thread(self._count_capabilities_sync, authorization_id)

    async def find_capability_for_execution(
        self,
        run_id: str,
        tool_call_id: str,
    ) -> Capability | None:
        return await asyncio.to_thread(
            self._find_capability_for_execution_sync,
            run_id,
            tool_call_id,
        )

    def _create_pending_sync(
        self,
        request: PolicyRequest,
        profile_name: PermissionProfileName,
        authorization_id: str,
        requested_at: datetime,
    ) -> AuthorizationRecord:
        from agent_foundations.security.capabilities import canonical_resource_json

        resource_json = canonical_resource_json(request.resource)
        with self._database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                existing = self._find_authorization_for_call(
                    connection,
                    request.run_id,
                    request.tool_call_id,
                )
                if existing is not None:
                    self._assert_exact_authorization(
                        existing,
                        request,
                        profile_name,
                        resource_json,
                    )
                    connection.commit()
                    return _row_to_authorization(existing)
                connection.execute(
                    f"""
                    INSERT INTO authorization_requests ({_AUTHORIZATION_COLUMNS})
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                    """,
                    (
                        authorization_id,
                        request.run_id,
                        request.tool_call_id,
                        request.tool_name,
                        resource_json,
                        request.operation,
                        profile_name.value,
                        request.profile_version,
                        AuthorizationStatus.PENDING.value,
                        _serialize_datetime(requested_at),
                    ),
                )
                row = self._get_authorization_row(connection, authorization_id)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return _row_to_authorization(row)

    def _record_denied_sync(
        self,
        request: PolicyRequest,
        profile_name: PermissionProfileName,
        authorization_id: str | None,
        decided_at: datetime,
    ) -> AuthorizationRecord:
        from agent_foundations.security.capabilities import canonical_resource_json

        resource_json = canonical_resource_json(request.resource)
        with self._database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                existing = self._find_authorization_for_call(
                    connection,
                    request.run_id,
                    request.tool_call_id,
                )
                if existing is None:
                    resolved_id = authorization_id or str(uuid4())
                    connection.execute(
                        f"""
                        INSERT INTO authorization_requests ({_AUTHORIZATION_COLUMNS})
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            resolved_id,
                            request.run_id,
                            request.tool_call_id,
                            request.tool_name,
                            resource_json,
                            request.operation,
                            profile_name.value,
                            request.profile_version,
                            AuthorizationStatus.DENIED.value,
                            _serialize_datetime(decided_at),
                            _serialize_datetime(decided_at),
                        ),
                    )
                else:
                    self._assert_exact_authorization(
                        existing,
                        request,
                        profile_name,
                        resource_json,
                    )
                    if (
                        authorization_id is not None
                        and existing["authorization_id"] != authorization_id
                    ):
                        raise AuthorizationConflictError("authorization_id mismatch")
                    current = self._parse_status(existing["status"])
                    if current is AuthorizationStatus.DENIED:
                        connection.commit()
                        return _row_to_authorization(existing)
                    if current is not AuthorizationStatus.PENDING:
                        raise AuthorizationConflictError(
                            "resolved authorization cannot change to denied",
                        )
                    connection.execute(
                        """
                        UPDATE authorization_requests
                        SET status = ?, decided_at = ?
                        WHERE authorization_id = ? AND status = ?
                        """,
                        (
                            AuthorizationStatus.DENIED.value,
                            _serialize_datetime(decided_at),
                            existing["authorization_id"],
                            AuthorizationStatus.PENDING.value,
                        ),
                    )
                    resolved_id = existing["authorization_id"]
                row = self._get_authorization_row(connection, resolved_id)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return _row_to_authorization(row)

    def _invalidate_pending_sync(
        self,
        authorization_id: str,
        decided_at: datetime,
    ) -> AuthorizationRecord:
        with self._database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._get_authorization_row(connection, authorization_id)
                status = self._parse_status(row["status"])
                if status is AuthorizationStatus.PENDING:
                    connection.execute(
                        """
                        UPDATE authorization_requests
                        SET status = ?, decided_at = ?
                        WHERE authorization_id = ? AND status = ?
                        """,
                        (
                            AuthorizationStatus.INVALIDATED.value,
                            _serialize_datetime(decided_at),
                            authorization_id,
                            AuthorizationStatus.PENDING.value,
                        ),
                    )
                    row = self._get_authorization_row(connection, authorization_id)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return _row_to_authorization(row)

    def _issue_capability_sync(
        self,
        request: PolicyRequest,
        profile_name: PermissionProfileName,
        authorization_id: str | None,
        target_status: AuthorizationStatus,
        issued_at: datetime,
        expires_at: datetime,
    ) -> Capability:
        from agent_foundations.security.capabilities import (
            CapabilityConsumedError,
            canonical_resource_json,
        )

        resource_json = canonical_resource_json(request.resource)
        with self._database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                authorization = self._find_authorization_for_call(
                    connection,
                    request.run_id,
                    request.tool_call_id,
                )
                if authorization is None:
                    if target_status is not AuthorizationStatus.POLICY_ALLOWED:
                        raise AuthorizationConflictError(
                            "approved issuance requires a pending authorization",
                        )
                    resolved_authorization_id = authorization_id or str(uuid4())
                    connection.execute(
                        f"""
                        INSERT INTO authorization_requests ({_AUTHORIZATION_COLUMNS})
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                        """,
                        (
                            resolved_authorization_id,
                            request.run_id,
                            request.tool_call_id,
                            request.tool_name,
                            resource_json,
                            request.operation,
                            profile_name.value,
                            request.profile_version,
                            AuthorizationStatus.POLICY_ALLOWED.value,
                            _serialize_datetime(issued_at),
                        ),
                    )
                else:
                    self._assert_exact_authorization(
                        authorization,
                        request,
                        profile_name,
                        resource_json,
                    )
                    if (
                        authorization_id is not None
                        and authorization["authorization_id"] != authorization_id
                    ):
                        raise AuthorizationConflictError("authorization_id mismatch")
                    resolved_authorization_id = authorization["authorization_id"]
                    current = self._parse_status(authorization["status"])
                    if target_status is AuthorizationStatus.POLICY_ALLOWED:
                        if current is not AuthorizationStatus.POLICY_ALLOWED:
                            raise AuthorizationConflictError(
                                "human authorization cannot become policy allow",
                            )
                    elif target_status is AuthorizationStatus.APPROVED:
                        if current is AuthorizationStatus.PENDING:
                            connection.execute(
                                """
                                UPDATE authorization_requests
                                SET status = ?, decided_at = ?
                                WHERE authorization_id = ? AND status = ?
                                """,
                                (
                                    AuthorizationStatus.APPROVED.value,
                                    _serialize_datetime(issued_at),
                                    resolved_authorization_id,
                                    AuthorizationStatus.PENDING.value,
                                ),
                            )
                        elif current is not AuthorizationStatus.APPROVED:
                            raise AuthorizationConflictError(
                                "authorization status does not permit issuance",
                            )
                    else:
                        raise AuthorizationConflictError("invalid issuance status")

                existing_capability = self._find_capability_for_authorization(
                    connection,
                    resolved_authorization_id,
                )
                if existing_capability is not None:
                    self._assert_exact_capability(existing_capability, request, resource_json)
                    capability = _row_to_capability(existing_capability)
                    if capability.consumed_at is not None:
                        raise CapabilityConsumedError(
                            "consumed capability cannot be reissued",
                        )
                    connection.commit()
                    return capability

                if self._before_capability_insert is not None:
                    self._before_capability_insert()
                capability_id = str(uuid4())
                connection.execute(
                    f"""
                    INSERT INTO capabilities ({_CAPABILITY_COLUMNS})
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                    """,
                    (
                        capability_id,
                        resolved_authorization_id,
                        request.run_id,
                        request.tool_call_id,
                        request.tool_name,
                        resource_json,
                        request.operation,
                        request.profile_version,
                        _serialize_datetime(issued_at),
                        _serialize_datetime(expires_at),
                    ),
                )
                row = self._get_capability_row(connection, capability_id)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return _row_to_capability(row)

    def _consume_capability_sync(
        self,
        capability_id: str,
        execution: PolicyRequest,
        consumed_at: datetime,
    ) -> Capability:
        from agent_foundations.security.capabilities import (
            CapabilityConsumedError,
            CapabilityExpiredError,
            CapabilityMismatchError,
            CapabilityNotYetValidError,
            canonical_resource_json,
        )

        resource_json = canonical_resource_json(execution.resource)
        with self._database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    f"""
                    SELECT c.{_CAPABILITY_COLUMNS.replace(',', ', c.')},
                           a.status AS authorization_status,
                           a.run_id AS authorization_run_id,
                           a.tool_call_id AS authorization_tool_call_id,
                           a.tool_name AS authorization_tool_name,
                           a.resource_json AS authorization_resource_json,
                           a.operation AS authorization_operation,
                           a.profile_version AS authorization_profile_version
                    FROM capabilities AS c
                    JOIN authorization_requests AS a
                      ON a.authorization_id = c.authorization_id
                    WHERE c.capability_id = ?
                    """,
                    (capability_id,),
                ).fetchone()
                if row is None:
                    raise AuthorizationNotFoundError(
                        f"capability not found: {capability_id}",
                    )
                status = self._parse_status(row["authorization_status"])
                if status not in {
                    AuthorizationStatus.POLICY_ALLOWED,
                    AuthorizationStatus.APPROVED,
                }:
                    raise AuthorizationCorruptStateError(
                        "authorization status does not permit consumption",
                    )
                self._assert_join_consistent(row)
                if not self._capability_matches_execution(row, execution, resource_json):
                    raise CapabilityMismatchError("capability does not match exact execution")
                capability = _row_to_capability(row)
                if capability.consumed_at is not None:
                    raise CapabilityConsumedError("capability already consumed")
                if consumed_at < capability.issued_at:
                    raise CapabilityNotYetValidError("capability is not yet valid")
                if consumed_at >= capability.expires_at:
                    raise CapabilityExpiredError("capability expired")
                cursor = connection.execute(
                    """
                    UPDATE capabilities
                    SET consumed_at = ?
                    WHERE capability_id = ? AND consumed_at IS NULL
                    """,
                    (_serialize_datetime(consumed_at), capability_id),
                )
                if cursor.rowcount != 1:
                    raise CapabilityConsumedError("capability already consumed")
                updated = self._get_capability_row(connection, capability_id)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return _row_to_capability(updated)

    def _get_authorization_sync(self, authorization_id: str) -> AuthorizationRecord:
        with self._database.connect() as connection:
            row = self._get_authorization_row(connection, authorization_id)
        return _row_to_authorization(row)

    def _get_capability_sync(self, capability_id: str) -> Capability:
        with self._database.connect() as connection:
            row = self._get_capability_row(connection, capability_id)
        return _row_to_capability(row)

    def _count_capabilities_sync(self, authorization_id: str) -> int:
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM capabilities WHERE authorization_id = ?",
                (authorization_id,),
            ).fetchone()
        return int(row["count"])

    def _find_capability_for_execution_sync(
        self,
        run_id: str,
        tool_call_id: str,
    ) -> Capability | None:
        with self._database.connect() as connection:
            row = connection.execute(
                f"""
                SELECT {_CAPABILITY_COLUMNS}
                FROM capabilities
                WHERE run_id = ? AND tool_call_id = ?
                """,
                (run_id, tool_call_id),
            ).fetchone()
        return None if row is None else _row_to_capability(row)

    @staticmethod
    def _find_authorization_for_call(
        connection: sqlite3.Connection,
        run_id: str,
        tool_call_id: str,
    ) -> sqlite3.Row | None:
        return cast(
            sqlite3.Row | None,
            connection.execute(
            f"""
            SELECT {_AUTHORIZATION_COLUMNS}
            FROM authorization_requests
            WHERE run_id = ? AND tool_call_id = ?
            """,
            (run_id, tool_call_id),
            ).fetchone(),
        )

    @staticmethod
    def _find_capability_for_authorization(
        connection: sqlite3.Connection,
        authorization_id: str,
    ) -> sqlite3.Row | None:
        return cast(
            sqlite3.Row | None,
            connection.execute(
            f"""
            SELECT {_CAPABILITY_COLUMNS}
            FROM capabilities
            WHERE authorization_id = ?
            """,
            (authorization_id,),
            ).fetchone(),
        )

    @staticmethod
    def _get_authorization_row(
        connection: sqlite3.Connection,
        authorization_id: str,
    ) -> sqlite3.Row:
        row = connection.execute(
            f"""
            SELECT {_AUTHORIZATION_COLUMNS}
            FROM authorization_requests
            WHERE authorization_id = ?
            """,
            (authorization_id,),
        ).fetchone()
        if row is None:
            raise AuthorizationNotFoundError(
                f"authorization not found: {authorization_id}",
            )
        return cast(sqlite3.Row, row)

    @staticmethod
    def _get_capability_row(
        connection: sqlite3.Connection,
        capability_id: str,
    ) -> sqlite3.Row:
        row = connection.execute(
            f"""
            SELECT {_CAPABILITY_COLUMNS}
            FROM capabilities
            WHERE capability_id = ?
            """,
            (capability_id,),
        ).fetchone()
        if row is None:
            raise AuthorizationNotFoundError(f"capability not found: {capability_id}")
        return cast(sqlite3.Row, row)

    @staticmethod
    def _parse_status(value: str) -> AuthorizationStatus:
        try:
            return AuthorizationStatus(value)
        except ValueError as exc:
            raise AuthorizationCorruptStateError(
                f"unknown authorization status: {value}",
            ) from exc

    @staticmethod
    def _assert_exact_authorization(
        row: sqlite3.Row,
        request: PolicyRequest,
        profile_name: PermissionProfileName,
        resource_json: str,
    ) -> None:
        expected = (
            request.run_id,
            request.tool_call_id,
            request.tool_name,
            resource_json,
            request.operation,
            profile_name.value,
            request.profile_version,
        )
        actual = (
            row["run_id"],
            row["tool_call_id"],
            row["tool_name"],
            row["resource_json"],
            row["operation"],
            row["profile_name"],
            row["profile_version"],
        )
        if actual != expected:
            raise AuthorizationConflictError(
                "run/tool-call identity conflicts with different authorization facts",
            )

    @staticmethod
    def _assert_exact_capability(
        row: sqlite3.Row,
        request: PolicyRequest,
        resource_json: str,
    ) -> None:
        if not AuthorizationRepository._capability_matches_execution(
            row,
            request,
            resource_json,
        ):
            raise AuthorizationConflictError(
                "existing capability conflicts with exact request",
            )

    @staticmethod
    def _capability_matches_execution(
        row: sqlite3.Row,
        execution: PolicyRequest,
        resource_json: str,
    ) -> bool:
        actual = (
            row["run_id"],
            row["tool_call_id"],
            row["tool_name"],
            row["resource_json"],
            row["operation"],
            row["profile_version"],
        )
        expected = (
            execution.run_id,
            execution.tool_call_id,
            execution.tool_name,
            resource_json,
            execution.operation,
            execution.profile_version,
        )
        return actual == expected

    @staticmethod
    def _assert_join_consistent(row: sqlite3.Row) -> None:
        pairs = (
            (row["run_id"], row["authorization_run_id"]),
            (row["tool_call_id"], row["authorization_tool_call_id"]),
            (row["tool_name"], row["authorization_tool_name"]),
            (row["resource_json"], row["authorization_resource_json"]),
            (row["operation"], row["authorization_operation"]),
            (row["profile_version"], row["authorization_profile_version"]),
        )
        inconsistent = any(
            capability_value != authorization_value
            for capability_value, authorization_value in pairs
        )
        if inconsistent:
            raise AuthorizationCorruptStateError(
                "capability and authorization facts are inconsistent",
            )
