from __future__ import annotations

from agent_foundations.storage.migrations import Migration

_AUTHORIZATION_V7_SQL = """
CREATE TABLE authorization_requests (
  authorization_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  tool_call_id TEXT NOT NULL,
  tool_name TEXT NOT NULL,
  resource_json TEXT NOT NULL CHECK(
    length(trim(resource_json)) > 0 AND length(resource_json) <= 2048
  ),
  operation TEXT NOT NULL,
  profile_name TEXT NOT NULL,
  profile_version INTEGER NOT NULL CHECK(profile_version >= 1),
  status TEXT NOT NULL CHECK(
    status IN (
      'policy_allowed', 'pending', 'approved', 'denied', 'invalidated', 'conflict'
    )
  ),
  requested_at TEXT NOT NULL,
  decided_at TEXT,
  UNIQUE(run_id, tool_call_id)
);
CREATE TABLE capabilities (
  capability_id TEXT PRIMARY KEY,
  authorization_id TEXT NOT NULL REFERENCES authorization_requests(authorization_id),
  run_id TEXT NOT NULL,
  tool_call_id TEXT NOT NULL,
  tool_name TEXT NOT NULL,
  resource_json TEXT NOT NULL CHECK(
    length(trim(resource_json)) > 0 AND length(resource_json) <= 2048
  ),
  operation TEXT NOT NULL,
  profile_version INTEGER NOT NULL CHECK(profile_version >= 1),
  issued_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  consumed_at TEXT
);
CREATE UNIQUE INDEX one_capability_per_authorization
ON capabilities(authorization_id);
CREATE INDEX idx_capabilities_execution
ON capabilities(run_id, tool_call_id);
"""

AUTHORIZATION_SCHEMA_VERSION = 7

AUTHORIZATION_MIGRATION = Migration(
    version=AUTHORIZATION_SCHEMA_VERSION,
    statements=tuple(
        statement.strip()
        for statement in _AUTHORIZATION_V7_SQL.split(";")
        if statement.strip()
    ),
)

AUTHORIZATION_MIGRATIONS = (AUTHORIZATION_MIGRATION,)
