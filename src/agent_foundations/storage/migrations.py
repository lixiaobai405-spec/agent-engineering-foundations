from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Migration:
    version: int
    statements: tuple[str, ...]


def validate_migration_sequence(
    migrations: tuple[Migration, ...],
) -> tuple[Migration, ...]:
    if not migrations:
        raise ValueError("migration sequence must not be empty")
    for migration in migrations:
        if migration.version < 1:
            raise ValueError("migration version must be a positive integer")

    versions = [migration.version for migration in migrations]
    if versions[0] != 1:
        raise ValueError("migration sequence must start at version 1")
    if len(set(versions)) != len(versions):
        raise ValueError("duplicate migration version")
    for expected, actual in enumerate(versions, start=1):
        if actual != expected:
            raise ValueError("migration sequence must be strictly consecutive")
    return migrations


def get_application_migrations() -> tuple[Migration, ...]:
    from agent_foundations.chat.schema import CHAT_MIGRATIONS
    from agent_foundations.durable.schema import DURABLE_MIGRATIONS
    from agent_foundations.security.schema import AUTHORIZATION_MIGRATIONS
    from agent_foundations.tools.patch.schema import PATCH_MIGRATIONS

    return validate_migration_sequence(
        (
            *CHAT_MIGRATIONS,
            *DURABLE_MIGRATIONS,
            *PATCH_MIGRATIONS,
            *AUTHORIZATION_MIGRATIONS,
        ),
    )
