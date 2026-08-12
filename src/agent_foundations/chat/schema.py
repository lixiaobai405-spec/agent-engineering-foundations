from __future__ import annotations

from agent_foundations.storage.migrations import Migration

_SCHEMA_V1_SQL = """
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

SCHEMA_V1_STATEMENTS = tuple(
    statement.strip()
    for statement in _SCHEMA_V1_SQL.split(";")
    if statement.strip()
)

MIGRATION_V1_TO_V2_STATEMENTS = (
    """
    CREATE TABLE chat_tool_activities (
      session_id TEXT NOT NULL REFERENCES runs(session_id) ON DELETE CASCADE,
      tool_call_id TEXT NOT NULL,
      tool_name TEXT NOT NULL,
      status TEXT NOT NULL CHECK(
        status IN ('running','completed','failed','interrupted')
      ),
      arguments_summary TEXT CHECK(
        arguments_summary IS NULL OR length(arguments_summary) <= 240
      ),
      result_summary TEXT CHECK(
        result_summary IS NULL OR length(result_summary) <= 240
      ),
      started_at TEXT NOT NULL,
      finished_at TEXT,
      last_event_id TEXT NOT NULL,
      PRIMARY KEY(session_id, tool_call_id)
    )
    """,
    """
    CREATE INDEX idx_chat_tool_activities_session_started
    ON chat_tool_activities(session_id, started_at, tool_call_id)
    """,
)

LATEST_CHAT_SCHEMA_VERSION = 2
NEXT_PHASE2_MIGRATION_VERSION = 3

CHAT_MIGRATIONS = (
    Migration(version=1, statements=SCHEMA_V1_STATEMENTS),
    Migration(version=2, statements=MIGRATION_V1_TO_V2_STATEMENTS),
)
