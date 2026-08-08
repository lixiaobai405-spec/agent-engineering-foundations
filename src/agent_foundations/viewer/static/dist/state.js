export function viewFor(event, tab) {
    const payload = event.payload;
    const modelInput = payload.request ??
        (payload.context !== undefined || payload.tools !== undefined
            ? { messages: payload.context ?? [], tools: payload.tools ?? [] }
            : payload.messages ?? "Not available for this event");
    const views = {
        Overview: {
            event_type: event.event_type,
            status: event.status,
            step_id: event.step_id,
            summary: event.summary,
            duration_ms: event.duration_ms,
        },
        "Model Input": modelInput,
        "Model Output": payload.response ?? payload.content ?? payload.tool_calls ?? "Not available for this event",
        "Tool Arguments": payload.arguments ?? "Not available for this event",
        "Tool Result": payload.result ?? "Not available for this event",
        "Context Snapshot": payload.context ?? "Not available for this event",
        "Raw JSON": event,
        Error: payload.error ?? (event.status === "failed" ? payload : "No error"),
    };
    return views[tab];
}
export function nextLiveEvents(current, incoming, historicalSessionId) {
    if (historicalSessionId !== null) {
        return current;
    }
    const activeSessionId = current[0]?.session_id;
    if (activeSessionId !== undefined && activeSessionId !== incoming.session_id) {
        return [incoming];
    }
    return [...current, incoming];
}
export function formatUiError(action, error) {
    const detail = error instanceof Error ? error.message : "Unknown error";
    return `${action} failed: ${detail}. Check the Viewer and try again.`;
}
export function autoScrollBehavior(reducedMotion) {
    return reducedMotion ? "auto" : "smooth";
}
export function resolveSessionQuerySelection(sessions, search) {
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
export function resolveTraceQuerySelection(navigation, search) {
    const params = new URLSearchParams(search.startsWith("?") ? search.slice(1) : search);
    const sessionId = params.get("session_id");
    if (sessionId === null || sessionId === "") {
        return { kind: "none" };
    }
    const requestedConversationId = params.get("conversation_id");
    for (const conversation of navigation.chat_conversations) {
        if (requestedConversationId !== null &&
            conversation.conversation_id !== requestedConversationId) {
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
        const run = navigation.standalone_runs.find((candidate) => candidate.session_id === sessionId);
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
