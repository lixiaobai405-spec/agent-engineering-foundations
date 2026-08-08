export type Json = null | boolean | number | string | Json[] | { [key: string]: Json };

export type TraceEvent = {
  event_id: string;
  session_id: string;
  step_id: number;
  event_type: string;
  status: string;
  timestamp: string;
  duration_ms: number | null;
  summary: string;
  payload: Record<string, Json>;
};

export type TraceNavigationTurn = {
  session_id: string;
  short_id: string;
  turn_number: number;
  user_message_preview: string;
  status: string;
  started_at: string;
  trace_available: boolean;
};

export type TraceNavigationConversation = {
  conversation_id: string;
  title: string;
  project_root: string;
  turns: TraceNavigationTurn[];
};

export type StandaloneTraceRun = Omit<TraceNavigationTurn, "turn_number">;

export type TraceNavigation = {
  chat_conversations: TraceNavigationConversation[];
  standalone_runs: StandaloneTraceRun[];
};

export function viewFor(event: TraceEvent, tab: string): Json {
  const payload = event.payload;
  const modelInput =
    payload.request ??
    (payload.context !== undefined || payload.tools !== undefined
      ? { messages: payload.context ?? [], tools: payload.tools ?? [] }
      : payload.messages ?? "Not available for this event");
  const views: Record<string, Json> = {
    Overview: {
      event_type: event.event_type,
      status: event.status,
      step_id: event.step_id,
      summary: event.summary,
      duration_ms: event.duration_ms,
    },
    "Model Input": modelInput,
    "Model Output":
      payload.response ?? payload.content ?? payload.tool_calls ?? "Not available for this event",
    "Tool Arguments": payload.arguments ?? "Not available for this event",
    "Tool Result": payload.result ?? "Not available for this event",
    "Context Snapshot": payload.context ?? "Not available for this event",
    "Raw JSON": event as unknown as Json,
    Error: payload.error ?? (event.status === "failed" ? payload : "No error"),
  };
  return views[tab];
}

export function nextLiveEvents(
  current: TraceEvent[],
  incoming: TraceEvent,
  historicalSessionId: string | null,
): TraceEvent[] {
  if (historicalSessionId !== null) {
    return current;
  }
  const activeSessionId = current[0]?.session_id;
  if (activeSessionId !== undefined && activeSessionId !== incoming.session_id) {
    return [incoming];
  }
  return [...current, incoming];
}

export function formatUiError(action: string, error: unknown): string {
  const detail = error instanceof Error ? error.message : "Unknown error";
  return `${action} failed: ${detail}. Check the Viewer and try again.`;
}

export function autoScrollBehavior(reducedMotion: boolean): ScrollBehavior {
  return reducedMotion ? "auto" : "smooth";
}

export type SessionQuerySelection =
  | { kind: "none" }
  | { kind: "selected"; sessionId: string }
  | { kind: "missing"; sessionId: string };

export function resolveSessionQuerySelection(
  sessions: string[],
  search: string,
): SessionQuerySelection {
  const params = new URLSearchParams(search.startsWith("?") ? search.slice(1) : search);
  const sessionId = params.get("session_id");
  if (sessionId === null || sessionId === "") {
    return { kind: "none" };
  }
  if (sessions.includes(sessionId)) {
    return { kind: "selected", sessionId };
  }
  return { kind: "missing", sessionId };
}

export type TraceQuerySelection =
  | { kind: "none" }
  | {
      kind: "selected";
      sessionId: string;
      conversationId: string | null;
      traceAvailable: boolean;
    }
  | { kind: "missing"; sessionId: string };

export function resolveTraceQuerySelection(
  navigation: TraceNavigation,
  search: string,
): TraceQuerySelection {
  const params = new URLSearchParams(search.startsWith("?") ? search.slice(1) : search);
  const sessionId = params.get("session_id");
  if (sessionId === null || sessionId === "") {
    return { kind: "none" };
  }

  const requestedConversationId = params.get("conversation_id");
  for (const conversation of navigation.chat_conversations) {
    if (
      requestedConversationId !== null &&
      conversation.conversation_id !== requestedConversationId
    ) {
      continue;
    }
    const turn = conversation.turns.find((candidate) => candidate.session_id === sessionId);
    if (turn !== undefined) {
      return {
        kind: "selected",
        sessionId,
        conversationId: conversation.conversation_id,
        traceAvailable: turn.trace_available,
      };
    }
  }

  if (requestedConversationId === null) {
    const run = navigation.standalone_runs.find(
      (candidate) => candidate.session_id === sessionId,
    );
    if (run !== undefined) {
      return {
        kind: "selected",
        sessionId,
        conversationId: null,
        traceAvailable: run.trace_available,
      };
    }
  }
  return { kind: "missing", sessionId };
}
