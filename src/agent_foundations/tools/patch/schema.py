from __future__ import annotations

from agent_foundations.storage.migrations import Migration

_PATCH_PROPOSAL_V6_SQL = """
CREATE TABLE patch_proposals (
  run_id TEXT NOT NULL REFERENCES durable_runs(run_id) ON DELETE CASCADE,
  patch_id TEXT NOT NULL CHECK(length(patch_id) = 64),
  project_root_fingerprint TEXT NOT NULL CHECK(length(project_root_fingerprint) = 64),
  patch_json TEXT NOT NULL CHECK(
    length(trim(patch_json)) > 0 AND length(patch_json) <= 1048576
  ),
  created_at TEXT NOT NULL CHECK(length(trim(created_at)) > 0),
  PRIMARY KEY (run_id, patch_id)
)
"""

PATCH_PROPOSAL_SCHEMA_VERSION = 6

PATCH_PROPOSAL_MIGRATION = Migration(
    version=PATCH_PROPOSAL_SCHEMA_VERSION,
    statements=tuple(
        statement.strip()
        for statement in _PATCH_PROPOSAL_V6_SQL.split(";")
        if statement.strip()
    ),
)

PATCH_MIGRATIONS = (PATCH_PROPOSAL_MIGRATION,)
