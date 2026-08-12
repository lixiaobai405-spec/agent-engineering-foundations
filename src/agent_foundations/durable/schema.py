from __future__ import annotations

from agent_foundations.storage.migrations import Migration

_DURABLE_V3_SQL = """
CREATE TABLE durable_runs (
  run_id TEXT PRIMARY KEY,
  project_root TEXT NOT NULL CHECK(length(trim(project_root)) > 0),
  status TEXT NOT NULL CHECK(
    status IN (
      'created',
      'running',
      'paused',
      'waiting_approval',
      'completed',
      'failed',
      'cancelled'
    )
  ),
  schema_version INTEGER NOT NULL CHECK(schema_version >= 1),
  state_version INTEGER NOT NULL CHECK(state_version >= 0),
  attempt INTEGER NOT NULL CHECK(attempt >= 1),
  created_at TEXT NOT NULL CHECK(length(trim(created_at)) > 0),
  updated_at TEXT NOT NULL CHECK(length(trim(updated_at)) > 0)
);
CREATE TABLE run_checkpoints (
  checkpoint_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES durable_runs(run_id) ON DELETE CASCADE,
  sequence INTEGER NOT NULL CHECK(sequence >= 1),
  schema_version INTEGER NOT NULL CHECK(schema_version >= 1),
  state_json TEXT NOT NULL CHECK(length(trim(state_json)) > 0),
  created_at TEXT NOT NULL CHECK(length(trim(created_at)) > 0),
  UNIQUE(run_id, sequence)
)
"""

DURABLE_SCHEMA_VERSION = 3

DURABLE_RUN_MIGRATION = Migration(
    version=DURABLE_SCHEMA_VERSION,
    statements=tuple(
        statement.strip()
        for statement in _DURABLE_V3_SQL.split(";")
        if statement.strip()
    ),
)

DURABLE_MIGRATION = DURABLE_RUN_MIGRATION

_RUN_LEASE_V4_SQL = """
CREATE TABLE run_leases (
  lease_token TEXT PRIMARY KEY CHECK(length(trim(lease_token)) > 0),
  run_id TEXT NOT NULL REFERENCES durable_runs(run_id) ON DELETE CASCADE,
  owner_id TEXT NOT NULL CHECK(length(trim(owner_id)) > 0),
  acquired_at TEXT NOT NULL CHECK(length(trim(acquired_at)) > 0),
  expires_at TEXT NOT NULL CHECK(length(trim(expires_at)) > 0),
  renewed_at TEXT,
  renewal_count INTEGER NOT NULL DEFAULT 0 CHECK(renewal_count >= 0),
  released_at TEXT,
  release_reason TEXT CHECK(
    release_reason IS NULL OR release_reason IN ('explicit_release', 'expired_takeover')
  ),
  predecessor_token TEXT REFERENCES run_leases(lease_token),
  CHECK(
    (released_at IS NULL AND release_reason IS NULL)
    OR (released_at IS NOT NULL AND release_reason IS NOT NULL)
  ),
  CHECK(expires_at > acquired_at)
);
CREATE UNIQUE INDEX idx_run_leases_active_run
ON run_leases(run_id)
WHERE released_at IS NULL;
CREATE INDEX idx_run_leases_run_acquired
ON run_leases(run_id, acquired_at)
"""

RUN_LEASE_SCHEMA_VERSION = 4

RUN_LEASE_MIGRATION = Migration(
    version=RUN_LEASE_SCHEMA_VERSION,
    statements=tuple(
        statement.strip()
        for statement in _RUN_LEASE_V4_SQL.split(";")
        if statement.strip()
    ),
)

_SIDE_EFFECT_V5_SQL = """
CREATE TABLE side_effects (
  effect_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES durable_runs(run_id) ON DELETE CASCADE,
  tool_call_id TEXT NOT NULL CHECK(length(trim(tool_call_id)) > 0),
  tool_name TEXT NOT NULL CHECK(length(trim(tool_name)) > 0),
  idempotency_key TEXT NOT NULL UNIQUE,
  intent_digest TEXT NOT NULL CHECK(length(intent_digest) = 64),
  intent_summary TEXT NOT NULL CHECK(
    length(trim(intent_summary)) > 0 AND length(intent_summary) <= 240
  ),
  status TEXT NOT NULL CHECK(
    status IN (
      'intent_recorded',
      'executing',
      'committed',
      'failed',
      'unknown',
      'rolled_back'
    )
  ),
  result_json TEXT CHECK(result_json IS NULL OR length(result_json) <= 65536),
  error_code TEXT,
  execution_owner_id TEXT,
  created_at TEXT NOT NULL CHECK(length(trim(created_at)) > 0),
  updated_at TEXT NOT NULL CHECK(length(trim(updated_at)) > 0),
  executing_at TEXT,
  resolved_at TEXT,
  UNIQUE(run_id, tool_call_id, tool_name)
)
"""

SIDE_EFFECT_SCHEMA_VERSION = 5

SIDE_EFFECT_MIGRATION = Migration(
    version=SIDE_EFFECT_SCHEMA_VERSION,
    statements=tuple(
        statement.strip()
        for statement in _SIDE_EFFECT_V5_SQL.split(";")
        if statement.strip()
    ),
)

DURABLE_MIGRATIONS = (
    DURABLE_RUN_MIGRATION,
    RUN_LEASE_MIGRATION,
    SIDE_EFFECT_MIGRATION,
)
