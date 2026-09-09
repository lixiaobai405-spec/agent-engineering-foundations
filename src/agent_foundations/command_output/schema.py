from __future__ import annotations

from agent_foundations.storage.migrations import Migration

COMMAND_OUTPUT_SCHEMA_VERSION = 9
COMMAND_OUTPUT_READS_SCHEMA_VERSION = 10

_COMMAND_OUTPUT_V9_SQL = """
CREATE TABLE command_output_artifacts (
  artifact_id TEXT PRIMARY KEY CHECK(
    length(artifact_id) = 26 AND artifact_id LIKE 'coa_%'
  ),
  run_id TEXT NOT NULL REFERENCES durable_runs(run_id) ON DELETE CASCADE,
  effect_id TEXT NOT NULL UNIQUE,
  execution_id TEXT NOT NULL UNIQUE,
  stdout_bytes INTEGER NOT NULL CHECK(stdout_bytes >= 0),
  stderr_bytes INTEGER NOT NULL CHECK(stderr_bytes >= 0),
  sha256 TEXT NOT NULL CHECK(length(sha256) = 64),
  created_at TEXT NOT NULL CHECK(length(trim(created_at)) > 0),
  retention_status TEXT NOT NULL CHECK(
    retention_status IN (
      'active',
      'retained',
      'pending_delete',
      'deleted',
      'delete_failed',
      'evicted'
    )
  ),
  parser_status TEXT NOT NULL CHECK(
    parser_status IN ('pending', 'complete', 'partial', 'failed')
  )
);
CREATE INDEX idx_command_output_artifacts_run_created
ON command_output_artifacts(run_id, created_at);
CREATE INDEX idx_command_output_artifacts_status_created
ON command_output_artifacts(retention_status, created_at)
"""

_COMMAND_OUTPUT_V10_SQL = """
CREATE TABLE command_output_reads (
  read_id TEXT PRIMARY KEY CHECK(length(trim(read_id)) > 0),
  run_id TEXT NOT NULL REFERENCES durable_runs(run_id) ON DELETE CASCADE,
  artifact_id TEXT NOT NULL CHECK(
    length(artifact_id) = 26 AND artifact_id LIKE 'coa_%'
  ),
  selector_json TEXT NOT NULL CHECK(length(trim(selector_json)) > 0),
  reason TEXT NOT NULL CHECK(length(trim(reason)) > 0 AND length(reason) <= 240),
  returned_bytes INTEGER NOT NULL CHECK(returned_bytes >= 0),
  returned_lines INTEGER NOT NULL CHECK(returned_lines >= 0),
  decision TEXT NOT NULL CHECK(length(trim(decision)) > 0),
  created_at TEXT NOT NULL CHECK(length(trim(created_at)) > 0)
);
CREATE INDEX idx_command_output_reads_run_created
ON command_output_reads(run_id, created_at)
"""

COMMAND_OUTPUT_MIGRATION = Migration(
    version=COMMAND_OUTPUT_SCHEMA_VERSION,
    statements=tuple(
        statement.strip()
        for statement in _COMMAND_OUTPUT_V9_SQL.split(";")
        if statement.strip()
    ),
)

COMMAND_OUTPUT_READS_MIGRATION = Migration(
    version=COMMAND_OUTPUT_READS_SCHEMA_VERSION,
    statements=tuple(
        statement.strip()
        for statement in _COMMAND_OUTPUT_V10_SQL.split(";")
        if statement.strip()
    ),
)

COMMAND_OUTPUT_MIGRATIONS = (COMMAND_OUTPUT_MIGRATION, COMMAND_OUTPUT_READS_MIGRATION)
