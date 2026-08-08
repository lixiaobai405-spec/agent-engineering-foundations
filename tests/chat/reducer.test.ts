import { describe, expect, expectTypeOf, it } from "vitest";

import { initialState, reduceChatState } from "../../web/chat/state/reducer";
import type {
  ApprovalRequest,
  ChatEvent,
  ChatMessage,
  Conversation,
  RunRecord,
} from "../../web/chat/state/types";

const CONVERSATION_A: Conversation = {
  conversation_id: "11111111-1111-4111-8111-111111111111",
  title: "Runtime study",
  project_root: "D:\\project",
  permission_mode: "PROJECT_READ_ONLY",
  created_at: "2026-08-02T00:00:00Z",
  updated_at: "2026-08-02T00:00:00Z",
};

const CONVERSATION_B: Conversation = {
  conversation_id: "22222222-2222-4222-8222-222222222222",
  title: "External access",
  project_root: "D:\\other",
  permission_mode: "ASK_FOR_ACCESS",
  created_at: "2026-08-02T00:00:00Z",
  updated_at: "2026-08-02T00:01:00Z",
};

function makeEvent(
  overrides: Partial<ChatEvent> & Pick<ChatEvent, "type" | "conversation_id">,
): ChatEvent {
  return {
    event_id: "55555555-5555-4555-8555-555555555555",
    session_id: "33333333-3333-4333-8333-333333333333",
    occurred_at: "2026-08-02T00:00:01Z",
    data: {},
    ...overrides,
  };
}

function loadConversations(conversations: Conversation[]) {
  return reduceChatState(initialState, {
    type: "conversations.loaded",
    conversations,
  });
}

function selectConversation(state: ReturnType<typeof loadConversations>, conversationId: string) {
  return reduceChatState(state, {
    type: "conversation.selected",
    conversationId,
  });
}

describe("reduceChatState", () => {
  it("keeps conversations, messages, activities, and run state separate", () => {
    const selected = loadConversations([CONVERSATION_A]);
    const running = makeEvent({
      conversation_id: CONVERSATION_A.conversation_id,
      type: "run.started",
      data: { status: "running" },
    });
    const next = reduceChatState(selected, { type: "event.received", event: running });
    expect(next.activeConversationId).toBe(CONVERSATION_A.conversation_id);
    expect(next.runStatusByConversation[CONVERSATION_A.conversation_id]).toBe("running");
    expect(next.activitiesByConversation[CONVERSATION_A.conversation_id]).toEqual([running]);
  });

  it("selects the first conversation when loading a non-empty list", () => {
    const loaded = loadConversations([CONVERSATION_A, CONVERSATION_B]);
    expect(loaded.activeConversationId).toBe(CONVERSATION_A.conversation_id);
  });

  it("clears active conversation when the loaded list is empty", () => {
    const withActive = loadConversations([CONVERSATION_A]);
    const cleared = reduceChatState(withActive, {
      type: "conversations.loaded",
      conversations: [],
    });
    expect(cleared.activeConversationId).toBeNull();
  });

  it("keeps the current active conversation when it still exists in the reloaded list", () => {
    const initial = loadConversations([CONVERSATION_A, CONVERSATION_B]);
    const selected = selectConversation(initial, CONVERSATION_B.conversation_id);
    const reloaded = reduceChatState(selected, {
      type: "conversations.loaded",
      conversations: [CONVERSATION_B, CONVERSATION_A],
    });
    expect(reloaded.activeConversationId).toBe(CONVERSATION_B.conversation_id);
  });

  it("selects the first conversation when the active conversation is no longer present", () => {
    const initial = loadConversations([CONVERSATION_A, CONVERSATION_B]);
    const selected = selectConversation(initial, CONVERSATION_B.conversation_id);
    const reloaded = reduceChatState(selected, {
      type: "conversations.loaded",
      conversations: [CONVERSATION_A],
    });
    expect(reloaded.activeConversationId).toBe(CONVERSATION_A.conversation_id);
  });

  it("establishes state after HTTP conversation and message loads", () => {
    const withConversations = loadConversations([CONVERSATION_A, CONVERSATION_B]);
    const selected = selectConversation(withConversations, CONVERSATION_A.conversation_id);
    const messages: ChatMessage[] = [
      {
        message_id: "aaaa0000-0000-4000-8000-000000000001",
        conversation_id: CONVERSATION_A.conversation_id,
        role: "user",
        content: "first question",
        sequence: 1,
        created_at: "2026-08-02T00:00:00Z",
      },
    ];
    const loaded = reduceChatState(selected, {
      type: "messages.loaded",
      conversationId: CONVERSATION_A.conversation_id,
      messages,
    });
    expect(loaded.conversations).toEqual([CONVERSATION_A, CONVERSATION_B]);
    expect(loaded.activeConversationId).toBe(CONVERSATION_A.conversation_id);
    expect(loaded.messagesByConversation[CONVERSATION_A.conversation_id]).toEqual(messages);
  });

  it("does not share messages or activities when switching conversations", () => {
    const base = loadConversations([CONVERSATION_A, CONVERSATION_B]);
    const selectedA = selectConversation(base, CONVERSATION_A.conversation_id);
    const withMessagesA = reduceChatState(selectedA, {
      type: "messages.loaded",
      conversationId: CONVERSATION_A.conversation_id,
      messages: [
        {
          message_id: "aaaa0000-0000-4000-8000-000000000001",
          conversation_id: CONVERSATION_A.conversation_id,
          role: "user",
          content: "only a",
          sequence: 1,
          created_at: "2026-08-02T00:00:00Z",
        },
      ],
    });
    const withActivityA = reduceChatState(withMessagesA, {
      type: "event.received",
      event: makeEvent({
        conversation_id: CONVERSATION_A.conversation_id,
        type: "tool.requested",
        data: { name: "read_file" },
      }),
    });
    const selectedB = selectConversation(withActivityA, CONVERSATION_B.conversation_id);
    expect(selectedB.messagesByConversation[CONVERSATION_B.conversation_id] ?? []).toEqual([]);
    expect(selectedB.activitiesByConversation[CONVERSATION_B.conversation_id] ?? []).toEqual([]);
    expect(selectedB.messagesByConversation[CONVERSATION_A.conversation_id]).toHaveLength(1);
    expect(selectedB.activitiesByConversation[CONVERSATION_A.conversation_id]).toHaveLength(1);
  });

  it("merges assistant.message.completed into the current conversation", () => {
    const selected = selectConversation(loadConversations([CONVERSATION_A]), CONVERSATION_A.conversation_id);
    const withUser = reduceChatState(selected, {
      type: "messages.loaded",
      conversationId: CONVERSATION_A.conversation_id,
      messages: [
        {
          message_id: "aaaa0000-0000-4000-8000-000000000001",
          conversation_id: CONVERSATION_A.conversation_id,
          role: "user",
          content: "question",
          sequence: 1,
          created_at: "2026-08-02T00:00:00Z",
        },
      ],
    });
    const completed = reduceChatState(withUser, {
      type: "event.received",
      event: makeEvent({
        conversation_id: CONVERSATION_A.conversation_id,
        type: "assistant.message.completed",
        data: {
          message_id: "bbbb0000-0000-4000-8000-000000000002",
          content: "answer",
          sequence: 2,
        },
      }),
    });
    expect(completed.messagesByConversation[CONVERSATION_A.conversation_id]).toEqual([
      {
        message_id: "aaaa0000-0000-4000-8000-000000000001",
        conversation_id: CONVERSATION_A.conversation_id,
        role: "user",
        content: "question",
        sequence: 1,
        created_at: "2026-08-02T00:00:00Z",
      },
      {
        message_id: "bbbb0000-0000-4000-8000-000000000002",
        conversation_id: CONVERSATION_A.conversation_id,
        role: "assistant",
        content: "answer",
        sequence: 2,
        created_at: "2026-08-02T00:00:01Z",
      },
    ]);
  });

  it("does not duplicate assistant messages after a later HTTP reload", () => {
    const selected = selectConversation(loadConversations([CONVERSATION_A]), CONVERSATION_A.conversation_id);
    const assistantMessage: ChatMessage = {
      message_id: "bbbb0000-0000-4000-8000-000000000002",
      conversation_id: CONVERSATION_A.conversation_id,
      role: "assistant",
      content: "answer",
      sequence: 2,
      created_at: "2026-08-02T00:00:02Z",
    };
    const afterEvent = reduceChatState(selected, {
      type: "event.received",
      event: makeEvent({
        conversation_id: CONVERSATION_A.conversation_id,
        type: "assistant.message.completed",
        data: {
          message_id: assistantMessage.message_id,
          content: assistantMessage.content,
          sequence: assistantMessage.sequence,
        },
      }),
    });
    const afterReload = reduceChatState(afterEvent, {
      type: "messages.loaded",
      conversationId: CONVERSATION_A.conversation_id,
      messages: [assistantMessage],
    });
    const messages = afterReload.messagesByConversation[CONVERSATION_A.conversation_id] ?? [];
    expect(messages).toHaveLength(1);
    expect(messages[0]?.message_id).toBe(assistantMessage.message_id);
  });

  it("enters waiting state on approval.requested", () => {
    const selected = selectConversation(loadConversations([CONVERSATION_A]), CONVERSATION_A.conversation_id);
    const next = reduceChatState(selected, {
      type: "event.received",
      event: makeEvent({
        conversation_id: CONVERSATION_A.conversation_id,
        type: "approval.requested",
        data: {
          approval_id: "44444444-4444-4444-8444-444444444444",
          tool_call_id: "call-1",
          tool_name: "read_file",
          canonical_path: "/tmp/external.txt",
          operation: "read",
          scope: "external_exact_path",
        },
      }),
    });
    expect(next.runStatusByConversation[CONVERSATION_A.conversation_id]).toBe("waiting_approval");
    expect(next.activeApprovalByConversation[CONVERSATION_A.conversation_id]).toEqual({
      approval_id: "44444444-4444-4444-8444-444444444444",
      tool_call_id: "call-1",
      tool_name: "read_file",
      canonical_path: "/tmp/external.txt",
      operation: "read",
      scope: "external_exact_path",
    });
  });

  it("clears active approval on approval.resolved", () => {
    const waiting = reduceChatState(
      selectConversation(loadConversations([CONVERSATION_A]), CONVERSATION_A.conversation_id),
      {
        type: "event.received",
        event: makeEvent({
          conversation_id: CONVERSATION_A.conversation_id,
          type: "approval.requested",
          data: {
            approval_id: "44444444-4444-4444-8444-444444444444",
            tool_call_id: "call-1",
            tool_name: "read_file",
            canonical_path: "/tmp/external.txt",
            operation: "read",
            scope: "external_exact_path",
          },
        }),
      },
    );
    const resolved = reduceChatState(waiting, {
      type: "event.received",
      event: makeEvent({
        conversation_id: CONVERSATION_A.conversation_id,
        type: "approval.resolved",
        data: {
          approval_id: "44444444-4444-4444-8444-444444444444",
          status: "approved",
        },
      }),
    });
    expect(resolved.activeApprovalByConversation[CONVERSATION_A.conversation_id]).toBeNull();
    expect(resolved.runStatusByConversation[CONVERSATION_A.conversation_id]).toBe("running");
  });

  it("clears active run state on run.completed, run.failed, and interrupted run reload", () => {
    const running = reduceChatState(loadConversations([CONVERSATION_A]), {
      type: "event.received",
      event: makeEvent({
        conversation_id: CONVERSATION_A.conversation_id,
        type: "run.started",
        session_id: "session-1",
        data: { status: "running" },
      }),
    });
    const completed = reduceChatState(running, {
      type: "event.received",
      event: makeEvent({
        conversation_id: CONVERSATION_A.conversation_id,
        session_id: "session-1",
        type: "run.completed",
        data: { status: "completed" },
      }),
    });
    expect(completed.runStatusByConversation[CONVERSATION_A.conversation_id]).toBe("completed");
    expect(completed.activeSessionIdByConversation[CONVERSATION_A.conversation_id]).toBeNull();

    const failed = reduceChatState(running, {
      type: "event.received",
      event: makeEvent({
        conversation_id: CONVERSATION_A.conversation_id,
        session_id: "session-2",
        type: "run.failed",
        data: { status: "failed", error_code: "FakeModelExhaustedError" },
      }),
    });
    expect(failed.runStatusByConversation[CONVERSATION_A.conversation_id]).toBe("failed");
    expect(failed.activeSessionIdByConversation[CONVERSATION_A.conversation_id]).toBeNull();

    const interrupted = reduceChatState(running, {
      type: "run.loaded",
      conversationId: CONVERSATION_A.conversation_id,
      run: {
        session_id: "session-3",
        conversation_id: CONVERSATION_A.conversation_id,
        user_message_id: "aaaa0000-0000-4000-8000-000000000001",
        trace_path: "traces/session-3.jsonl",
        assistant_message_id: null,
        status: "interrupted",
        error_code: null,
        created_at: "2026-08-02T00:00:00Z",
        started_at: null,
        finished_at: null,
      },
    });
    expect(interrupted.runStatusByConversation[CONVERSATION_A.conversation_id]).toBe("interrupted");
    expect(interrupted.activeSessionIdByConversation[CONVERSATION_A.conversation_id]).toBeNull();
  });

  it("does not pollute the active conversation with events from another conversation", () => {
    const selected = selectConversation(loadConversations([CONVERSATION_A, CONVERSATION_B]), CONVERSATION_A.conversation_id);
    const next = reduceChatState(selected, {
      type: "event.received",
      event: makeEvent({
        conversation_id: CONVERSATION_B.conversation_id,
        type: "tool.requested",
        data: { name: "read_file" },
      }),
    });
    expect(next.activitiesByConversation[CONVERSATION_B.conversation_id]).toHaveLength(1);
    expect(next.activitiesByConversation[CONVERSATION_A.conversation_id] ?? []).toEqual([]);
    expect(next.runStatusByConversation[CONVERSATION_A.conversation_id]).toBeUndefined();
  });

  it("ignores unknown event types and invalid event envelopes", () => {
    const base = loadConversations([CONVERSATION_A]);
    const unknownType = reduceChatState(base, {
      type: "event.received",
      event: {
        ...makeEvent({
          conversation_id: CONVERSATION_A.conversation_id,
          type: "run.started",
        }),
        type: "run.unknown" as ChatEvent["type"],
      },
    });
    expect(unknownType).toEqual(base);

    const invalidEnvelope = reduceChatState(base, {
      type: "event.received",
      event: {
        event_id: "",
        conversation_id: "",
        session_id: "",
        type: "run.started",
        occurred_at: "",
        data: {},
      },
    });
    expect(invalidEnvelope).toEqual(base);
  });

  it("models nullable backend fields as required keys with null", () => {
    type RunRecordNullableFields = Pick<
      RunRecord,
      "assistant_message_id" | "error_code" | "started_at" | "finished_at"
    >;
    expectTypeOf<RunRecordNullableFields>().toEqualTypeOf<{
      assistant_message_id: string | null;
      error_code: string | null;
      started_at: string | null;
      finished_at: string | null;
    }>();

    type ApprovalRequestNullableFields = Pick<ApprovalRequest, "decided_at">;
    expectTypeOf<ApprovalRequestNullableFields>().toEqualTypeOf<{
      decided_at: string | null;
    }>();
  });

  it("is a pure reducer without browser network dependencies", () => {
    expect(typeof reduceChatState).toBe("function");
    expect(reduceChatState).not.toBe(globalThis.fetch);
    expect(reduceChatState).not.toBe(globalThis.EventSource);
    const next = reduceChatState(initialState, {
      type: "conversations.loaded",
      conversations: [CONVERSATION_A],
    });
    expect(initialState.conversations).toEqual([]);
    expect(next.conversations).toEqual([CONVERSATION_A]);
    expect(next.activeConversationId).toBe(CONVERSATION_A.conversation_id);
  });
});

describe("conversation.state.loaded HTTP recovery", () => {
  const RUNNING_RUN: RunRecord = {
    session_id: "33333333-3333-4333-8333-333333333333",
    conversation_id: CONVERSATION_A.conversation_id,
    user_message_id: "aaaa0000-0000-4000-8000-000000000001",
    trace_path: "traces/session.jsonl",
    assistant_message_id: null,
    status: "running",
    error_code: null,
    created_at: "2026-08-02T00:00:00Z",
    started_at: "2026-08-02T00:00:01Z",
    finished_at: null,
  };

  const COMPLETED_RUN: RunRecord = {
    ...RUNNING_RUN,
    status: "completed",
    assistant_message_id: "bbbb0000-0000-4000-8000-000000000002",
    finished_at: "2026-08-02T00:00:02Z",
  };

  const PENDING_APPROVAL = {
    approval_id: "44444444-4444-4444-8444-444444444444",
    conversation_id: CONVERSATION_A.conversation_id,
    session_id: RUNNING_RUN.session_id,
    tool_call_id: "call-1",
    tool_name: "read_file",
    canonical_path: "/tmp/external.txt",
    operation: "read" as const,
    scope: "external_exact_path" as const,
    status: "pending" as const,
    requested_at: "2026-08-02T00:00:01Z",
  };

  it("restores a running run from HTTP recovery without SSE events", () => {
    const selected = selectConversation(loadConversations([CONVERSATION_A]), CONVERSATION_A.conversation_id);
    const next = reduceChatState(selected, {
      type: "conversation.state.loaded",
      conversationId: CONVERSATION_A.conversation_id,
      state: { latest_run: RUNNING_RUN, pending_approval: null },
    });
    expect(next.runStatusByConversation[CONVERSATION_A.conversation_id]).toBe("running");
    expect(next.activeSessionIdByConversation[CONVERSATION_A.conversation_id]).toBe(
      RUNNING_RUN.session_id,
    );
    expect(next.latestSessionIdByConversation[CONVERSATION_A.conversation_id]).toBe(
      RUNNING_RUN.session_id,
    );
    expect(next.activitiesByConversation[CONVERSATION_A.conversation_id] ?? []).toEqual([]);
  });

  it("restores waiting approval and pending approval from HTTP recovery", () => {
    const selected = selectConversation(loadConversations([CONVERSATION_A]), CONVERSATION_A.conversation_id);
    const waitingRun = { ...RUNNING_RUN, status: "waiting_approval" as const };
    const next = reduceChatState(selected, {
      type: "conversation.state.loaded",
      conversationId: CONVERSATION_A.conversation_id,
      state: {
        latest_run: waitingRun,
        pending_approval: PENDING_APPROVAL,
      },
    });
    expect(next.runStatusByConversation[CONVERSATION_A.conversation_id]).toBe("waiting_approval");
    expect(next.activeApprovalByConversation[CONVERSATION_A.conversation_id]).toEqual({
      approval_id: PENDING_APPROVAL.approval_id,
      tool_call_id: PENDING_APPROVAL.tool_call_id,
      tool_name: PENDING_APPROVAL.tool_name,
      canonical_path: PENDING_APPROVAL.canonical_path,
      operation: "read",
      scope: "external_exact_path",
    });
  });

  it("clears active session and approval for terminal runs but keeps latest session", () => {
    const selected = selectConversation(loadConversations([CONVERSATION_A]), CONVERSATION_A.conversation_id);
    const next = reduceChatState(selected, {
      type: "conversation.state.loaded",
      conversationId: CONVERSATION_A.conversation_id,
      state: { latest_run: COMPLETED_RUN, pending_approval: null },
    });
    expect(next.runStatusByConversation[CONVERSATION_A.conversation_id]).toBe("completed");
    expect(next.activeSessionIdByConversation[CONVERSATION_A.conversation_id]).toBeNull();
    expect(next.latestSessionIdByConversation[CONVERSATION_A.conversation_id]).toBe(
      COMPLETED_RUN.session_id,
    );
    expect(next.activeApprovalByConversation[CONVERSATION_A.conversation_id]).toBeNull();
  });

  it("does not mark no-run recovery as completed", () => {
    const selected = selectConversation(loadConversations([CONVERSATION_A]), CONVERSATION_A.conversation_id);
    const next = reduceChatState(selected, {
      type: "conversation.state.loaded",
      conversationId: CONVERSATION_A.conversation_id,
      state: { latest_run: null, pending_approval: null },
    });
    expect(next.runStatusByConversation[CONVERSATION_A.conversation_id]).toBeUndefined();
    expect(next.activeSessionIdByConversation[CONVERSATION_A.conversation_id]).toBeNull();
    expect(next.latestSessionIdByConversation[CONVERSATION_A.conversation_id]).toBeNull();
  });

  it("does not pollute another conversation when recovering state", () => {
    const selected = selectConversation(loadConversations([CONVERSATION_A, CONVERSATION_B]), CONVERSATION_A.conversation_id);
    const next = reduceChatState(selected, {
      type: "conversation.state.loaded",
      conversationId: CONVERSATION_B.conversation_id,
      state: { latest_run: RUNNING_RUN, pending_approval: null },
    });
    expect(next.runStatusByConversation[CONVERSATION_B.conversation_id]).toBe("running");
    expect(next.runStatusByConversation[CONVERSATION_A.conversation_id]).toBeUndefined();
  });
});
