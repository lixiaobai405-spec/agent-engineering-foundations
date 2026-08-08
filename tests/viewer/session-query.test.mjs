import assert from "node:assert/strict";
import test from "node:test";

import {
  resolveSessionQuerySelection,
  resolveTraceQuerySelection,
} from "../../src/agent_foundations/viewer/static/dist/state.js";

const navigation = {
  chat_conversations: [
    {
      conversation_id: "conversation-a",
      title: "Runtime study",
      project_root: "D:/project",
      turns: [
        {
          session_id: "chat-session",
          short_id: "chat-ses",
          turn_number: 1,
          user_message_preview: "Explain the loop",
          status: "completed",
          started_at: "2026-08-08T04:00:00Z",
          trace_available: true,
        },
      ],
    },
  ],
  standalone_runs: [
    {
      session_id: "standalone-session",
      short_id: "standalo",
      user_message_preview: "Analyze the project",
      status: "completed",
      started_at: "2026-08-08T03:00:00Z",
      trace_available: false,
    },
  ],
};

test("session_id query selects an existing session", () => {
  assert.deepEqual(
    resolveSessionQuerySelection(["browser-session", "other"], "?session_id=browser-session"),
    { kind: "selected", sessionId: "browser-session" },
  );
});

test("session_id query reports a recoverable missing session", () => {
  assert.deepEqual(
    resolveSessionQuerySelection(["other"], "session_id=browser-session"),
    { kind: "missing", sessionId: "browser-session" },
  );
});

test("absent session_id query leaves selection unchanged", () => {
  assert.deepEqual(resolveSessionQuerySelection(["browser-session"], ""), { kind: "none" });
});

test("conversation and session query selects the exact chat turn", () => {
  assert.deepEqual(
    resolveTraceQuerySelection(
      navigation,
      "?conversation_id=conversation-a&session_id=chat-session",
    ),
    {
      kind: "selected",
      sessionId: "chat-session",
      conversationId: "conversation-a",
      traceAvailable: true,
    },
  );
});

test("mismatched conversation does not select a session from another thread", () => {
  assert.deepEqual(
    resolveTraceQuerySelection(
      navigation,
      "?conversation_id=conversation-b&session_id=chat-session",
    ),
    { kind: "missing", sessionId: "chat-session" },
  );
});

test("session-only query keeps standalone deep links and availability", () => {
  assert.deepEqual(
    resolveTraceQuerySelection(navigation, "?session_id=standalone-session"),
    {
      kind: "selected",
      sessionId: "standalone-session",
      conversationId: null,
      traceAvailable: false,
    },
  );
});
