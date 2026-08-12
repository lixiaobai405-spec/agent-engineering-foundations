import { describe, expect, it } from "vitest";

import { buildConversationTurns } from "../../web/chat/state/turns";
import type { ChatMessage, ChatToolActivity, RunRecord } from "../../web/chat/state/types";

const conversationId = "11111111-1111-4111-8111-111111111111";

function message(messageId: string, role: "user" | "assistant", sequence: number): ChatMessage {
  return {
    message_id: messageId,
    conversation_id: conversationId,
    role,
    content: `${role}-${sequence}`,
    sequence,
    created_at: `2026-08-08T00:00:0${sequence}Z`,
  };
}

function run(sessionId: string, userMessageId: string, assistantMessageId: string | null, createdAt: string): RunRecord {
  return {
    session_id: sessionId,
    conversation_id: conversationId,
    user_message_id: userMessageId,
    trace_path: `traces/${sessionId}.jsonl`,
    assistant_message_id: assistantMessageId,
    status: "completed",
    error_code: null,
    created_at: createdAt,
    started_at: createdAt,
    finished_at: createdAt,
  };
}

function activity(sessionId: string, toolCallId: string): ChatToolActivity {
  return {
    conversation_id: conversationId,
    session_id: sessionId,
    tool_call_id: toolCallId,
    tool_name: "read_file",
    status: "completed",
    arguments_summary: "README.md",
    result_summary: "10 lines",
    started_at: "2026-08-08T00:00:02Z",
    finished_at: "2026-08-08T00:00:03Z",
    last_event_id: `event-${toolCallId}`,
  };
}

describe("buildConversationTurns", () => {
  it("keeps every run and its activity in the matching turn despite out-of-order input", () => {
    const user1 = message("user-1", "user", 1);
    const assistant1 = message("assistant-1", "assistant", 2);
    const user2 = message("user-2", "user", 3);
    const firstRun = run("session-1", user1.message_id, assistant1.message_id, "2026-08-08T00:00:01Z");
    const secondRun = run("session-2", user2.message_id, null, "2026-08-08T00:00:04Z");
    const firstActivity = activity(firstRun.session_id, "call-1");
    const secondActivity = activity(secondRun.session_id, "call-2");

    expect(
      buildConversationTurns(
        [user2, assistant1, user1],
        [secondRun, firstRun],
        [secondActivity, firstActivity],
      ),
    ).toEqual([
      {
        run: firstRun,
        userMessage: user1,
        assistantMessage: assistant1,
        activities: [firstActivity],
      },
      {
        run: secondRun,
        userMessage: user2,
        assistantMessage: null,
        activities: [secondActivity],
      },
    ]);
  });

  it("omits a run without its persisted user message and never invents activity", () => {
    const orphanRun = run("session-orphan", "missing", null, "2026-08-08T00:00:01Z");
    expect(buildConversationTurns([], [orphanRun], [])).toEqual([]);
  });
});
