import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "../../web/chat/App";
import * as api from "../../web/chat/state/api";
import type {
  ChatEvent,
  ChatMessage,
  ChatToolActivity,
  Conversation,
  RunRecord,
} from "../../web/chat/state/types";

const { listActivitiesMock, listRunsMock } = vi.hoisted(() => ({
  listActivitiesMock: vi.fn(),
  listRunsMock: vi.fn(),
}));

vi.mock("../../web/chat/state/api", async () => {
  const actual = await vi.importActual<typeof import("../../web/chat/state/api")>(
    "../../web/chat/state/api",
  );
  return {
    ...actual,
    listConversations: vi.fn(),
    createConversation: vi.fn(),
    getConversation: vi.fn(),
    patchConversation: vi.fn(),
    listMessages: vi.fn(),
    listRuns: listRunsMock,
    listActivities: listActivitiesMock,
    postMessage: vi.fn(),
    getRun: vi.fn(),
    getConversationState: vi.fn(),
    decideApproval: vi.fn(),
  };
});

class MockEventSource {
  static instances: MockEventSource[] = [];
  readonly url: string;
  closed = false;
  onerror: ((event: Event) => void) | null = null;
  private readonly listeners = new Map<string, Set<(event: MessageEvent<string>) => void>>();

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: (event: MessageEvent<string>) => void): void {
    const current = this.listeners.get(type) ?? new Set();
    current.add(listener);
    this.listeners.set(type, current);
  }

  close(): void {
    this.closed = true;
  }

  emit(type: string, payload: Record<string, unknown>): void {
    const event = new MessageEvent(type, {
      data: JSON.stringify({
        event_id: "event-1",
        conversation_id: "11111111-1111-4111-8111-111111111111",
        session_id: "33333333-3333-4333-8333-333333333333",
        type,
        occurred_at: "2026-08-02T00:00:02Z",
        data: payload,
      }),
    });
    for (const listener of this.listeners.get(type) ?? []) {
      listener(event);
    }
  }

  triggerError(): void {
    this.onerror?.(new Event("error"));
  }
}

const CONVERSATION_A: Conversation = {
  conversation_id: "11111111-1111-4111-8111-111111111111",
  title: "Runtime study",
  project_root: "D:\\canonical\\project",
  permission_mode: "PROJECT_READ_ONLY",
  created_at: "2026-08-02T00:00:00Z",
  updated_at: "2026-08-02T00:00:00Z",
};

const CONVERSATION_B: Conversation = {
  conversation_id: "22222222-2222-4222-8222-222222222222",
  title: "External access",
  project_root: "D:\\canonical\\other",
  permission_mode: "ASK_FOR_ACCESS",
  created_at: "2026-08-02T00:00:01Z",
  updated_at: "2026-08-02T00:00:01Z",
};

const MESSAGE_USER: ChatMessage = {
  message_id: "aaaa0000-0000-4000-8000-000000000001",
  conversation_id: CONVERSATION_A.conversation_id,
  role: "user",
  content: "hello",
  sequence: 1,
  created_at: "2026-08-02T00:00:00Z",
};

function latestEventSource(): MockEventSource {
  const instance = MockEventSource.instances.at(-1);
  if (!instance) {
    throw new Error("Expected EventSource to be created");
  }
  return instance;
}

function assistantCompletedEvent(content: string): ChatEvent {
  return {
    event_id: "event-assistant",
    conversation_id: CONVERSATION_A.conversation_id,
    session_id: "session-new",
    type: "assistant.message.completed",
    occurred_at: "2026-08-02T00:00:03Z",
    data: {
      message_id: "bbbb0000-0000-4000-8000-000000000002",
      content,
      sequence: 2,
    },
  };
}

beforeEach(() => {
  MockEventSource.instances = [];
  vi.stubGlobal("EventSource", MockEventSource);
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockReturnValue({
      matches: false,
      media: "(max-width: 800px)",
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }),
  );
  window.localStorage.clear();
  vi.mocked(api.listConversations).mockResolvedValue([]);
  listActivitiesMock.mockResolvedValue([]);
  vi.mocked(api.getConversation).mockImplementation(async (conversationId) => {
    if (conversationId === CONVERSATION_A.conversation_id) {
      return CONVERSATION_A;
    }
    return CONVERSATION_B;
  });
  vi.mocked(api.listMessages).mockResolvedValue([]);
  listRunsMock.mockResolvedValue([]);
  vi.mocked(api.getConversationState).mockResolvedValue({
    latest_run: null,
    pending_approval: null,
  });
  vi.mocked(api.getRun).mockResolvedValue({
    session_id: "session-known",
    conversation_id: CONVERSATION_A.conversation_id,
    user_message_id: MESSAGE_USER.message_id,
    trace_path: "traces/session-known.jsonl",
    assistant_message_id: null,
    status: "completed",
    error_code: null,
    created_at: "2026-08-02T00:00:00Z",
    started_at: null,
    finished_at: null,
  } satisfies RunRecord);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("App", () => {
  it("shows an empty state with New conversation and no fake messages", async () => {
    render(<App />);
    expect(await screen.findByRole("button", { name: "New conversation" })).toBeInTheDocument();
    expect(screen.queryByRole("article", { name: /message/i })).not.toBeInTheDocument();
    expect(screen.queryByText("Example assistant")).not.toBeInTheDocument();
  });

  it("requires title, project_root, and permission_mode to create a conversation", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole("button", { name: "New conversation" }));

    const createButton = screen.getByRole("button", { name: "Create conversation" });
    await user.click(createButton);
    expect(api.createConversation).not.toHaveBeenCalled();

    await user.type(screen.getByLabelText("Title"), "  ");
    await user.type(screen.getByLabelText("Project root"), "  ");
    await user.click(createButton);
    expect(api.createConversation).not.toHaveBeenCalled();
  });

  it("uses the backend canonical project_root after creation", async () => {
    const user = userEvent.setup();
    vi.mocked(api.createConversation).mockResolvedValue(CONVERSATION_A);
    vi.mocked(api.listConversations)
      .mockResolvedValueOnce([])
      .mockResolvedValue([CONVERSATION_A]);

    render(<App />);
    await user.click(await screen.findByRole("button", { name: "New conversation" }));
    await user.type(screen.getByLabelText("Title"), "Runtime study");
    await user.type(screen.getByLabelText("Project root"), "D:\\raw\\input");
    await user.selectOptions(screen.getByLabelText("Permission mode"), "PROJECT_READ_ONLY");
    await user.click(screen.getByRole("button", { name: "Create conversation" }));

    await waitFor(() => {
      expect(screen.getAllByText("D:\\canonical\\project").length).toBeGreaterThan(0);
    });
    expect(screen.queryByText("D:\\raw\\input")).not.toBeInTheDocument();
  });

  it("loads HTTP state before opening SSE when selecting a conversation", async () => {
    const user = userEvent.setup();
    const callOrder: string[] = [];
    vi.mocked(api.listConversations).mockResolvedValue([CONVERSATION_A, CONVERSATION_B]);
    vi.mocked(api.getConversation).mockImplementation(async (conversationId) => {
      callOrder.push(`getConversation:${conversationId}`);
      return conversationId === CONVERSATION_A.conversation_id
        ? CONVERSATION_A
        : CONVERSATION_B;
    });
    vi.mocked(api.listMessages).mockImplementation(async (conversationId) => {
      callOrder.push(`listMessages:${conversationId}`);
      return conversationId === CONVERSATION_A.conversation_id ? [MESSAGE_USER] : [];
    });
    listRunsMock.mockImplementation(async (conversationId: string) => {
      callOrder.push(`listRuns:${conversationId}`);
      return [];
    });
    listActivitiesMock.mockImplementation(async (conversationId: string) => {
      callOrder.push(`listActivities:${conversationId}`);
      return [];
    });
    vi.mocked(api.getConversationState).mockImplementation(async (conversationId) => {
      callOrder.push(`getConversationState:${conversationId}`);
      return { latest_run: null, pending_approval: null };
    });

    render(<App />);

    await waitFor(() => {
      expect(latestEventSource().url).toContain(CONVERSATION_A.conversation_id);
    });

    const initialEventSource = latestEventSource();

    await waitFor(() => {
      expect(callOrder).toEqual([
        `getConversation:${CONVERSATION_A.conversation_id}`,
        `listMessages:${CONVERSATION_A.conversation_id}`,
        `listRuns:${CONVERSATION_A.conversation_id}`,
        `listActivities:${CONVERSATION_A.conversation_id}`,
        `getConversationState:${CONVERSATION_A.conversation_id}`,
        `listActivities:${CONVERSATION_A.conversation_id}`,
      ]);
    });

    callOrder.length = 0;

    await user.click(screen.getByRole("button", { name: /External access/i }));

    await waitFor(() => {
      expect(latestEventSource().url).toContain(CONVERSATION_B.conversation_id);
    });

    expect(initialEventSource.closed).toBe(true);
    expect(callOrder).toEqual([
      `getConversation:${CONVERSATION_B.conversation_id}`,
      `listMessages:${CONVERSATION_B.conversation_id}`,
      `listRuns:${CONVERSATION_B.conversation_id}`,
      `listActivities:${CONVERSATION_B.conversation_id}`,
      `getConversationState:${CONVERSATION_B.conversation_id}`,
      `listActivities:${CONVERSATION_B.conversation_id}`,
    ]);
    expect(latestEventSource().closed).toBe(false);
  });

  it("closes the previous EventSource when switching conversations", async () => {
    const user = userEvent.setup();
    vi.mocked(api.listConversations).mockResolvedValue([CONVERSATION_A, CONVERSATION_B]);
    vi.mocked(api.listMessages).mockImplementation(async (conversationId) =>
      conversationId === CONVERSATION_A.conversation_id ? [MESSAGE_USER] : [],
    );

    render(<App />);
    await waitFor(() => {
      expect(MockEventSource.instances.length).toBe(1);
    });
    const firstSource = latestEventSource();

    await user.click(await screen.findByRole("button", { name: /External access/i }));
    await waitFor(() => {
      expect(MockEventSource.instances.length).toBe(2);
    });

    expect(firstSource.closed).toBe(true);
    expect(screen.queryByText("hello")).not.toBeInTheDocument();
  });

  it("disables composer after sending a message without optimistic assistant text", async () => {
    const user = userEvent.setup();
    vi.mocked(api.listConversations).mockResolvedValue([CONVERSATION_A]);
    vi.mocked(api.listMessages).mockResolvedValue([]);
    vi.mocked(api.postMessage).mockResolvedValue({ session_id: "session-new" });

    render(<App />);
    await screen.findByLabelText("Message");
    await user.type(screen.getByLabelText("Message"), "What is in README?");
    await user.click(screen.getByRole("button", { name: "Send message" }));

    expect(api.postMessage).toHaveBeenCalledWith(CONVERSATION_A.conversation_id, {
      query: "What is in README?",
    });
    expect(screen.getByRole("button", { name: "Send message" })).toBeDisabled();
    expect(screen.queryByText("optimistic assistant")).not.toBeInTheDocument();
  });

  it("loads the posted run so live tool activity is expanded while the run is active", async () => {
    const user = userEvent.setup();
    const runningRun: RunRecord = {
      session_id: "33333333-3333-4333-8333-333333333333",
      conversation_id: CONVERSATION_A.conversation_id,
      user_message_id: MESSAGE_USER.message_id,
      trace_path: "traces/session-new.jsonl",
      assistant_message_id: null,
      status: "running",
      error_code: null,
      created_at: "2026-08-02T00:00:00Z",
      started_at: "2026-08-02T00:00:01Z",
      finished_at: null,
    };
    vi.mocked(api.listConversations).mockResolvedValue([CONVERSATION_A]);
    vi.mocked(api.postMessage).mockResolvedValue({ session_id: runningRun.session_id });
    vi.mocked(api.listMessages).mockResolvedValue([MESSAGE_USER]);
    listRunsMock.mockResolvedValueOnce([]).mockResolvedValue([runningRun]);

    render(<App />);
    await user.type(await screen.findByLabelText("Message"), "inspect");
    await user.click(screen.getByRole("button", { name: "Send message" }));
    await waitFor(() => expect(listRunsMock).toHaveBeenCalledTimes(2));
    latestEventSource().emit("tool.requested", {
      tool_call_id: "call-live",
      name: "read_file",
      arguments_summary: "README.md",
    });

    expect(
      await screen.findByRole("button", { name: /1 tool activity/i }),
    ).toHaveAttribute("aria-expanded", "true");
  });

  it("adds the assistant message only after SSE or HTTP reload", async () => {
    const user = userEvent.setup();
    vi.mocked(api.listConversations).mockResolvedValue([CONVERSATION_A]);
    vi.mocked(api.listMessages)
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([
        MESSAGE_USER,
        {
          message_id: "bbbb0000-0000-4000-8000-000000000002",
          conversation_id: CONVERSATION_A.conversation_id,
          role: "assistant",
          content: "final answer",
          sequence: 2,
          created_at: "2026-08-02T00:00:03Z",
        },
      ]);
    vi.mocked(api.postMessage).mockResolvedValue({ session_id: "session-new" });

    render(<App />);
    await screen.findByLabelText("Message");
    await user.type(screen.getByLabelText("Message"), "question");
    await user.click(screen.getByRole("button", { name: "Send message" }));

    await waitFor(() => {
      expect(MockEventSource.instances.length).toBe(1);
    });
    latestEventSource().emit("assistant.message.completed", {
      message_id: "bbbb0000-0000-4000-8000-000000000002",
      content: "sse answer",
      sequence: 2,
    });
    expect(await screen.findByText("sse answer")).toBeInTheDocument();
  });

  it("renders script-like message content as plain text", async () => {
    vi.mocked(api.listConversations).mockResolvedValue([CONVERSATION_A]);
    vi.mocked(api.listMessages).mockResolvedValue([
      {
        ...MESSAGE_USER,
        content: "safe text\n\n<script>alert(1)</script>",
      },
    ]);

    render(<App />);
    expect(await screen.findByText("safe text")).toBeInTheDocument();
    expect(document.querySelector("script")).toBeNull();
  });

  it("renders a message-centric turn with Markdown, grouped tools, and exact Trace link", async () => {
    const user = userEvent.setup();
    const userMessage = { ...MESSAGE_USER, content: "# Inspect project" };
    const assistantMessage: ChatMessage = {
      ...MESSAGE_USER,
      message_id: "bbbb0000-0000-4000-8000-000000000002",
      role: "assistant",
      content: "| file | result |\n| - | - |\n| README.md | found |",
      sequence: 2,
    };
    const completedRun: RunRecord = {
      session_id: "session-structured",
      conversation_id: CONVERSATION_A.conversation_id,
      user_message_id: userMessage.message_id,
      trace_path: "traces/session-structured.jsonl",
      assistant_message_id: assistantMessage.message_id,
      status: "completed",
      error_code: null,
      created_at: "2026-08-02T00:00:00Z",
      started_at: "2026-08-02T00:00:01Z",
      finished_at: "2026-08-02T00:00:02Z",
    };
    const activity: ChatToolActivity = {
      conversation_id: CONVERSATION_A.conversation_id,
      session_id: completedRun.session_id,
      tool_call_id: "call-structured",
      tool_name: "read_file",
      status: "completed",
      arguments_summary: "README.md",
      result_summary: "12 lines",
      started_at: "2026-08-02T00:00:01Z",
      finished_at: "2026-08-02T00:00:02Z",
      last_event_id: "event-structured",
    };
    vi.mocked(api.listConversations).mockResolvedValue([CONVERSATION_A]);
    vi.mocked(api.listMessages).mockResolvedValue([userMessage, assistantMessage]);
    listRunsMock.mockResolvedValue([completedRun]);
    listActivitiesMock.mockResolvedValue([activity]);

    render(<App />);

    expect(await screen.findByRole("heading", { name: "Inspect project" })).toBeInTheDocument();
    expect(screen.getByRole("table")).toBeInTheDocument();
    const activityToggle = screen.getByRole("button", { name: /1 tool activity/i });
    expect(activityToggle).toHaveAttribute("aria-expanded", "false");
    await user.click(activityToggle);
    expect(screen.getByText("read_file")).toBeInTheDocument();
    expect(screen.getByText("12 lines")).toBeInTheDocument();
    expect(screen.queryByText(/event-structured/)).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open trace for this turn" })).toHaveAttribute(
      "href",
      `/trace?conversation_id=${CONVERSATION_A.conversation_id}&session_id=session-structured`,
    );
  });

  it("handles approval decisions with local disable and server conflict", async () => {
    const user = userEvent.setup();
    vi.mocked(api.listConversations).mockResolvedValue([CONVERSATION_A]);
    vi.mocked(api.decideApproval).mockRejectedValue(new api.ChatApiError(409, "conflict"));

    render(<App />);
    await waitFor(() => {
      expect(MockEventSource.instances.length).toBe(1);
    });

    latestEventSource().emit("approval.requested", {
      approval_id: "44444444-4444-4444-8444-444444444444",
      tool_call_id: "call-1",
      tool_name: "read_file",
      canonical_path: "/tmp/external.txt",
      operation: "read",
      scope: "external_exact_path",
    });

    const approveButton = await screen.findByRole("button", { name: "Approve once" });
    await user.click(approveButton);
    expect(api.decideApproval).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Approve once" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Deny" })).toBeDisabled();
    expect(await screen.findByRole("alert")).toHaveTextContent("conflict");
  });

  it("prevents duplicate approval API calls on rapid clicks", async () => {
    const user = userEvent.setup();
    let resolveDecision: (() => void) | undefined;
    vi.mocked(api.listConversations).mockResolvedValue([CONVERSATION_A]);
    vi.mocked(api.decideApproval).mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveDecision = () => resolve({
            approval_id: "44444444-4444-4444-8444-444444444444",
            conversation_id: CONVERSATION_A.conversation_id,
            session_id: "33333333-3333-4333-8333-333333333333",
            tool_call_id: "call-1",
            tool_name: "read_file",
            canonical_path: "/tmp/external.txt",
            operation: "read",
            status: "approved",
            requested_at: "2026-08-02T00:00:01Z",
            decided_at: "2026-08-02T00:00:02Z",
          });
        }),
    );

    render(<App />);
    await waitFor(() => {
      expect(MockEventSource.instances.length).toBe(1);
    });
    latestEventSource().emit("approval.requested", {
      approval_id: "44444444-4444-4444-8444-444444444444",
      tool_call_id: "call-1",
      tool_name: "read_file",
      canonical_path: "/tmp/external.txt",
      operation: "read",
      scope: "external_exact_path",
    });

    const denyButton = await screen.findByRole("button", { name: "Deny" });
    await user.click(denyButton);
    await user.click(denyButton);
    expect(api.decideApproval).toHaveBeenCalledTimes(1);
    resolveDecision?.();
  });

  it("allows permission mode updates only while idle", async () => {
    const user = userEvent.setup();
    vi.mocked(api.listConversations).mockResolvedValue([CONVERSATION_A]);
    vi.mocked(api.patchConversation).mockResolvedValue({
      ...CONVERSATION_A,
      permission_mode: "ASK_FOR_ACCESS",
    });

    render(<App />);
    const permissionSelect = await screen.findByLabelText("Permission mode");
    expect(permissionSelect).toBeEnabled();
    await user.selectOptions(permissionSelect, "ASK_FOR_ACCESS");
    await waitFor(() => {
      expect(api.patchConversation).toHaveBeenCalledWith(CONVERSATION_A.conversation_id, {
        permission_mode: "ASK_FOR_ACCESS",
      });
    });

    latestEventSource().emit("run.started", { status: "running" });
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Send message" })).toBeDisabled();
      expect(screen.getByLabelText("Permission mode")).toBeDisabled();
    });
  });

  it("re-fetches HTTP state after SSE error before reconnecting", async () => {
    vi.mocked(api.listConversations).mockResolvedValue([CONVERSATION_A]);
    vi.mocked(api.listMessages).mockResolvedValue([MESSAGE_USER]);
    vi.mocked(api.getConversationState).mockResolvedValue({
      latest_run: {
        session_id: "session-known",
        conversation_id: CONVERSATION_A.conversation_id,
        user_message_id: MESSAGE_USER.message_id,
        trace_path: "traces/session-known.jsonl",
        assistant_message_id: null,
        status: "running",
        error_code: null,
        created_at: "2026-08-02T00:00:00Z",
        started_at: "2026-08-02T00:00:01Z",
        finished_at: null,
      },
      pending_approval: null,
    });

    render(<App />);
    await waitFor(() => {
      expect(MockEventSource.instances.length).toBe(1);
    });
    const firstSource = latestEventSource();
    latestEventSource().emit("run.started", { status: "running" });
    await waitFor(() => {
      expect(firstSource.closed).toBe(false);
    });
    vi.mocked(api.getConversation).mockClear();
    vi.mocked(api.listMessages).mockClear();
    vi.mocked(api.getConversationState).mockClear();

    firstSource.triggerError();

    await waitFor(() => {
      expect(api.getConversation).toHaveBeenCalled();
      expect(api.listMessages).toHaveBeenCalled();
      expect(api.getConversationState).toHaveBeenCalled();
      expect(MockEventSource.instances.length).toBeGreaterThan(1);
    });
  });

  it("waits for conversation state recovery before opening SSE on fresh load", async () => {
    const callOrder: string[] = [];
    vi.mocked(api.listConversations).mockResolvedValue([CONVERSATION_A]);
    vi.mocked(api.getConversation).mockImplementation(async (conversationId) => {
      callOrder.push(`getConversation:${conversationId}`);
      return CONVERSATION_A;
    });
    vi.mocked(api.listMessages).mockImplementation(async (conversationId) => {
      callOrder.push(`listMessages:${conversationId}`);
      return [MESSAGE_USER];
    });
    listRunsMock.mockImplementation(async (conversationId: string) => {
      callOrder.push(`listRuns:${conversationId}`);
      return [];
    });
    listActivitiesMock.mockImplementation(async (conversationId: string) => {
      callOrder.push(`listActivities:${conversationId}`);
      return [];
    });
    vi.mocked(api.getConversationState).mockImplementation(async (conversationId) => {
      callOrder.push(`getConversationState:${conversationId}`);
      return { latest_run: null, pending_approval: null };
    });

    render(<App />);
    await waitFor(() => {
      expect(MockEventSource.instances.length).toBe(1);
    });
    expect(callOrder).toEqual([
      `getConversation:${CONVERSATION_A.conversation_id}`,
      `listMessages:${CONVERSATION_A.conversation_id}`,
      `listRuns:${CONVERSATION_A.conversation_id}`,
      `listActivities:${CONVERSATION_A.conversation_id}`,
      `getConversationState:${CONVERSATION_A.conversation_id}`,
      `listActivities:${CONVERSATION_A.conversation_id}`,
    ]);
  });

  it("keeps messages usable when activity recovery fails and retries only activity", async () => {
    const user = userEvent.setup();
    vi.mocked(api.listConversations).mockResolvedValue([CONVERSATION_A]);
    vi.mocked(api.listMessages).mockResolvedValue([MESSAGE_USER]);
    listActivitiesMock
      .mockRejectedValueOnce(new api.ChatApiError(503, "activity unavailable"))
      .mockRejectedValueOnce(new api.ChatApiError(503, "activity unavailable"))
      .mockResolvedValue([]);

    render(<App />);

    expect(await screen.findByText("hello")).toBeInTheDocument();
    const retry = await screen.findByRole("button", { name: "Retry activity" });
    expect(MockEventSource.instances).toHaveLength(1);
    const messagesCalls = vi.mocked(api.listMessages).mock.calls.length;
    await user.click(retry);
    await waitFor(() => expect(listActivitiesMock).toHaveBeenCalledTimes(3));
    expect(vi.mocked(api.listMessages)).toHaveBeenCalledTimes(messagesCalls);
    expect(screen.queryByRole("button", { name: "Retry activity" })).not.toBeInTheDocument();
  });

  it("refetches activities after terminal SSE events", async () => {
    vi.mocked(api.listConversations).mockResolvedValue([CONVERSATION_A]);
    vi.mocked(api.listMessages).mockResolvedValue([MESSAGE_USER]);

    render(<App />);
    await waitFor(() => expect(MockEventSource.instances).toHaveLength(1));
    await waitFor(() => expect(listActivitiesMock).toHaveBeenCalledTimes(2));
    latestEventSource().emit("run.completed", { status: "completed" });
    await waitFor(() => expect(listActivitiesMock).toHaveBeenCalledTimes(3));
  });

  it("disables composer and permission mode for recovered running state", async () => {
    vi.mocked(api.listConversations).mockResolvedValue([CONVERSATION_A]);
    vi.mocked(api.listMessages).mockResolvedValue([MESSAGE_USER]);
    vi.mocked(api.getConversationState).mockResolvedValue({
      latest_run: {
        session_id: "session-running",
        conversation_id: CONVERSATION_A.conversation_id,
        user_message_id: MESSAGE_USER.message_id,
        trace_path: "traces/session-running.jsonl",
        assistant_message_id: null,
        status: "running",
        error_code: null,
        created_at: "2026-08-02T00:00:00Z",
        started_at: "2026-08-02T00:00:01Z",
        finished_at: null,
      },
      pending_approval: null,
    });

    render(<App />);
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Send message" })).toBeDisabled();
      expect(screen.getByLabelText("Permission mode")).toBeDisabled();
    });
  });

  it("rebuilds recovered waiting approval card with exact fields", async () => {
    vi.mocked(api.listConversations).mockResolvedValue([CONVERSATION_A]);
    vi.mocked(api.listMessages).mockResolvedValue([MESSAGE_USER]);
    vi.mocked(api.getConversationState).mockResolvedValue({
      latest_run: {
        session_id: "session-waiting",
        conversation_id: CONVERSATION_A.conversation_id,
        user_message_id: MESSAGE_USER.message_id,
        trace_path: "traces/session-waiting.jsonl",
        assistant_message_id: null,
        status: "waiting_approval",
        error_code: null,
        created_at: "2026-08-02T00:00:00Z",
        started_at: "2026-08-02T00:00:01Z",
        finished_at: null,
      },
      pending_approval: {
        approval_id: "44444444-4444-4444-8444-444444444444",
        conversation_id: CONVERSATION_A.conversation_id,
        session_id: "session-waiting",
        tool_call_id: "call-1",
        tool_name: "read_file",
        canonical_path: "/tmp/external.txt",
        operation: "read",
        scope: "external_exact_path",
        status: "pending",
        requested_at: "2026-08-02T00:00:01Z",
      },
    });

    render(<App />);
    const card = await screen.findByRole("article", { name: "Approval request" });
    expect(within(card).getByText("read_file")).toBeInTheDocument();
    expect(within(card).getByText("/tmp/external.txt")).toBeInTheDocument();
    expect(within(card).getByText("read")).toBeInTheDocument();
    expect(within(card).getByText("external exact path")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send message" })).toBeDisabled();
    expect(screen.getByLabelText("Permission mode")).toBeDisabled();
    expect(document.body.textContent).not.toContain("recovered-approval-");
    expect(document.body.textContent).not.toContain("1970-01-01T00:00:00Z");
  });

  it("keeps idle controls enabled for recovered completed state", async () => {
    const assistantMessage: ChatMessage = {
      ...MESSAGE_USER,
      message_id: "bbbb0000-0000-4000-8000-000000000002",
      role: "assistant",
      content: "completed answer",
      sequence: 2,
    };
    vi.mocked(api.listConversations).mockResolvedValue([CONVERSATION_A]);
    vi.mocked(api.listMessages).mockResolvedValue([MESSAGE_USER, assistantMessage]);
    listRunsMock.mockResolvedValue([
      {
        session_id: "session-done",
        conversation_id: CONVERSATION_A.conversation_id,
        user_message_id: MESSAGE_USER.message_id,
        trace_path: "traces/session-done.jsonl",
        assistant_message_id: assistantMessage.message_id,
        status: "completed",
        error_code: null,
        created_at: "2026-08-02T00:00:00Z",
        started_at: "2026-08-02T00:00:01Z",
        finished_at: "2026-08-02T00:00:02Z",
      },
    ]);
    vi.mocked(api.getConversationState).mockResolvedValue({
      latest_run: {
        session_id: "session-done",
        conversation_id: CONVERSATION_A.conversation_id,
        user_message_id: MESSAGE_USER.message_id,
        trace_path: "traces/session-done.jsonl",
        assistant_message_id: "bbbb0000-0000-4000-8000-000000000002",
        status: "completed",
        error_code: null,
        created_at: "2026-08-02T00:00:00Z",
        started_at: "2026-08-02T00:00:01Z",
        finished_at: "2026-08-02T00:00:02Z",
      },
      pending_approval: null,
    });

    render(<App />);
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Send message" })).toBeEnabled();
      expect(screen.getByLabelText("Permission mode")).toBeEnabled();
      expect(
        screen.getByRole("link", { name: "Open trace for this turn" }),
      ).toHaveAttribute(
        "href",
        `/trace?conversation_id=${CONVERSATION_A.conversation_id}&session_id=session-done`,
      );
    });
  });

  it("shows accessible error when conversation state recovery fails", async () => {
    vi.mocked(api.listConversations).mockResolvedValue([CONVERSATION_A]);
    vi.mocked(api.getConversationState).mockRejectedValue(
      new api.ChatApiError(404, "not found"),
    );

    render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent("not found");
    expect(MockEventSource.instances.length).toBe(0);
  });

  it("exposes a responsive layout class contract for narrow screens", async () => {
    render(<App />);
    expect(await screen.findByTestId("chat-shell")).toHaveClass("chat-shell--responsive");
  });

  it("starts with the desktop conversation sidebar expanded and persists collapse", async () => {
    const user = userEvent.setup();
    render(<App />);

    const shell = await screen.findByTestId("chat-shell");
    const toggle = screen.getByRole("button", { name: "Collapse conversations" });
    expect(shell).toHaveClass("chat-shell--sidebar-open");
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.queryByRole("heading", { name: "Agent Foundations Chat" })).not.toBeInTheDocument();

    await user.click(toggle);

    expect(shell).toHaveClass("chat-shell--sidebar-closed");
    expect(screen.getByRole("button", { name: "Expand conversations" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
    expect(window.localStorage.getItem("agent-foundations.chat.sidebar")).toBe("collapsed");
  });

  it("restores a stored collapsed desktop sidebar preference", async () => {
    window.localStorage.setItem("agent-foundations.chat.sidebar", "collapsed");
    render(<App />);

    expect(await screen.findByTestId("chat-shell")).toHaveClass("chat-shell--sidebar-closed");
    expect(screen.getByRole("button", { name: "Expand conversations" })).toBeInTheDocument();
  });

  it("starts mobile with the drawer closed regardless of desktop preference", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "matchMedia",
      vi.fn().mockReturnValue({
        matches: true,
        media: "(max-width: 800px)",
        onchange: null,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      }),
    );
    window.localStorage.setItem("agent-foundations.chat.sidebar", "expanded");

    render(<App />);

    const shell = await screen.findByTestId("chat-shell");
    expect(shell).toHaveClass("chat-shell--mobile", "chat-shell--sidebar-closed");
    const menu = screen.getByRole("button", { name: "Open conversations" });
    expect(menu).toHaveAttribute("aria-expanded", "false");

    await user.click(menu);

    expect(shell).toHaveClass("chat-shell--sidebar-open");
    expect(screen.getByRole("button", { name: "Close conversations" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    expect(screen.getByRole("button", { name: "Close conversation drawer" })).toBeInTheDocument();
  });

  it("uses a compact conversation toolbar with short and full project context", async () => {
    vi.mocked(api.listConversations).mockResolvedValue([CONVERSATION_A]);
    render(<App />);

    expect(await screen.findByRole("heading", { name: "Runtime study" })).toBeInTheDocument();
    expect(screen.getByText("project")).toBeInTheDocument();
    expect(screen.getByLabelText("Permission mode")).toBeInTheDocument();
    const detailsButton = screen.getByRole("button", { name: "Conversation details" });
    expect(detailsButton).toBeInTheDocument();
    expect(within(detailsButton.parentElement as HTMLElement).getByText(
      CONVERSATION_A.project_root,
    )).toBeInTheDocument();
  });

  it("shows messages and compact working state without rendering activity details", async () => {
    vi.mocked(api.listConversations).mockResolvedValue([CONVERSATION_A]);
    vi.mocked(api.listMessages).mockResolvedValue([MESSAGE_USER]);

    render(<App />);
    await waitFor(() => expect(MockEventSource.instances.length).toBe(1));
    latestEventSource().emit("run.started", { status: "running" });
    latestEventSource().emit("tool.requested", {
      name: "read_file",
      arguments_summary: "README.md",
      status: "requested",
    });

    expect(await screen.findByText("Agent is working…")).toBeInTheDocument();
    expect(screen.queryByText("Tool requested")).not.toBeInTheDocument();
    expect(screen.queryByText("README.md")).not.toBeInTheDocument();
    expect(document.body.textContent).not.toContain("Active session:");
  });

  it("renders an exact trace link beside every completed assistant turn", async () => {
    const firstAssistantId = "bbbb0000-0000-4000-8000-000000000002";
    const secondUserId = "aaaa0000-0000-4000-8000-000000000003";
    const secondAssistantId = "bbbb0000-0000-4000-8000-000000000004";
    vi.mocked(api.listConversations).mockResolvedValue([CONVERSATION_A]);
    vi.mocked(api.listMessages).mockResolvedValue([
      MESSAGE_USER,
      {
        ...MESSAGE_USER,
        message_id: firstAssistantId,
        role: "assistant",
        content: "first answer",
        sequence: 2,
      },
      {
        ...MESSAGE_USER,
        message_id: secondUserId,
        content: "second question",
        sequence: 3,
      },
      {
        ...MESSAGE_USER,
        message_id: secondAssistantId,
        role: "assistant",
        content: "second answer",
        sequence: 4,
      },
    ]);
    listRunsMock.mockResolvedValue([
      {
        session_id: "session-first",
        conversation_id: CONVERSATION_A.conversation_id,
        user_message_id: MESSAGE_USER.message_id,
        trace_path: "traces/session-first.jsonl",
        assistant_message_id: firstAssistantId,
        status: "completed",
        error_code: null,
        created_at: "2026-08-02T00:00:00Z",
        started_at: "2026-08-02T00:00:01Z",
        finished_at: "2026-08-02T00:00:02Z",
      },
      {
        session_id: "session-second",
        conversation_id: CONVERSATION_A.conversation_id,
        user_message_id: secondUserId,
        trace_path: "traces/session-second.jsonl",
        assistant_message_id: secondAssistantId,
        status: "completed",
        error_code: null,
        created_at: "2026-08-02T00:00:03Z",
        started_at: "2026-08-02T00:00:04Z",
        finished_at: "2026-08-02T00:00:05Z",
      },
    ] satisfies RunRecord[]);

    render(<App />);

    const links = await screen.findAllByRole("link", {
      name: "Open trace for this turn",
    });
    expect(links).toHaveLength(2);
    expect(links[0]).toHaveAttribute(
      "href",
      `/trace?conversation_id=${CONVERSATION_A.conversation_id}&session_id=session-first`,
    );
    expect(links[1]).toHaveAttribute(
      "href",
      `/trace?conversation_id=${CONVERSATION_A.conversation_id}&session_id=session-second`,
    );
  });

  it("pauses auto-follow while reading older messages and can jump to latest", async () => {
    const user = userEvent.setup();
    const scrollTo = vi.fn();
    vi.stubGlobal("scrollTo", scrollTo);
    Object.defineProperty(window, "innerHeight", { configurable: true, value: 600 });
    Object.defineProperty(window, "scrollY", { configurable: true, value: 0 });
    Object.defineProperty(document.documentElement, "scrollHeight", {
      configurable: true,
      value: 1600,
    });
    vi.mocked(api.listConversations).mockResolvedValue([CONVERSATION_A]);
    vi.mocked(api.listMessages).mockResolvedValue([MESSAGE_USER]);

    render(<App />);
    await waitFor(() => expect(MockEventSource.instances.length).toBe(1));
    window.dispatchEvent(new Event("scroll"));
    latestEventSource().emit("assistant.message.completed", {
      message_id: "bbbb0000-0000-4000-8000-000000000002",
      content: "new response while reading",
      sequence: 2,
    });

    const jumpButton = await screen.findByRole("button", { name: "Jump to latest" });
    expect(scrollTo).not.toHaveBeenCalled();
    await user.click(jumpButton);
    expect(scrollTo).toHaveBeenCalledWith({ top: 1600, behavior: "auto" });
  });
});
