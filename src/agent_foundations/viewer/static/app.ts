import {
  autoScrollBehavior,
  formatUiError,
  nextLiveEvents,
  resolveTraceQuerySelection,
  type StandaloneTraceRun,
  type TraceEvent,
  type TraceNavigation,
  type TraceNavigationConversation,
  type TraceNavigationTurn,
  viewFor,
} from "./state.js";

const SSE_EVENT_TYPES = [
  "session.started",
  "user.message",
  "model.request.started",
  "model.response.received",
  "tool.call.requested",
  "tool.call.validated",
  "tool.call.completed",
  "tool.call.failed",
  "agent.final_answer",
  "agent.loop.stopped",
  "session.completed",
  "session.failed",
] as const;

const byId = <T extends HTMLElement>(id: string): T => {
  const element = document.getElementById(id);
  if (!element) {
    throw new Error(`Missing element: ${id}`);
  }
  return element as T;
};

const timeline = byId<HTMLOListElement>("timeline");
const detail = byId<HTMLPreElement>("detail");
const tabs = byId<HTMLElement>("tabs");
const eventFilter = byId<HTMLSelectElement>("event-filter");
const traceNavigation = byId<HTMLElement>("trace-navigation");
const autoScroll = byId<HTMLInputElement>("auto-scroll");
const copyButton = byId<HTMLButtonElement>("copy-json");
const copySessionButton = byId<HTMLButtonElement>("copy-session-id");
const liveEventsButton = byId<HTMLButtonElement>("live-events");
const eventCount = byId<HTMLElement>("event-count");
const sessionSummary = byId<HTMLElement>("session-summary");
const connection = byId<HTMLElement>("connection");
const liveDot = byId<HTMLElement>("live-dot");

let events: TraceEvent[] = [];
let navigation: TraceNavigation = { chat_conversations: [], standalone_runs: [] };
let selected: TraceEvent | null = null;
let loadedSessionId: string | null = null;
let activeConversationId: string | null = null;
let activeTab = "Overview";
const tabNames = [
  "Overview",
  "Model Input",
  "Model Output",
  "Tool Arguments",
  "Tool Result",
  "Context Snapshot",
  "Raw JSON",
  "Error",
];

function renderTabs(): void {
  tabs.replaceChildren(
    ...tabNames.map((name) => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = name;
      button.classList.toggle("active", name === activeTab);
      button.addEventListener("click", () => {
        activeTab = name;
        renderTabs();
        renderDetail();
      });
      return button;
    }),
  );
}

function renderDetail(): void {
  detail.textContent = selected
    ? JSON.stringify(viewFor(selected, activeTab), null, 2)
    : "Select an event from the timeline.";
  copyButton.disabled = selected === null;
}

function createTimelineItem(event: TraceEvent): HTMLLIElement {
  const item = document.createElement("li");
  const button = document.createElement("button");
  button.type = "button";
  button.className = "event";
  button.classList.toggle("active", selected?.event_id === event.event_id);

  const step = document.createElement("span");
  step.className = "step";
  step.textContent = String(event.step_id);

  const eventType = document.createElement("span");
  eventType.className = "event-type";
  eventType.textContent = event.event_type;

  const eventStatus = document.createElement("span");
  eventStatus.className = "event-status";
  eventStatus.textContent = event.status;

  const eventSummary = document.createElement("span");
  eventSummary.className = "event-summary";
  eventSummary.textContent = event.summary;

  button.append(step, eventType, eventStatus, eventSummary);
  button.addEventListener("click", () => {
    selected = event;
    renderTimeline();
    renderDetail();
  });
  item.append(button);
  return item;
}

function renderTimeline(): void {
  const visible = events.filter(
    (event) => eventFilter.value === "*" || event.event_type === eventFilter.value,
  );
  timeline.replaceChildren(...visible.map((event) => createTimelineItem(event)));
  eventCount.textContent = `${visible.length} events`;
  if (autoScroll.checked) {
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    timeline.lastElementChild?.scrollIntoView({
      behavior: autoScrollBehavior(reducedMotion),
      block: "nearest",
    });
  }
}

function updateFilters(): void {
  const current = eventFilter.value;
  const types = [...new Set(events.map((event) => event.event_type))].sort();
  eventFilter.replaceChildren(
    new Option("All events", "*"),
    ...types.map((type) => new Option(type, type)),
  );
  eventFilter.value = types.includes(current) ? current : "*";
}

function updateSessionSummary(): void {
  sessionSummary.classList.remove("error");
  const session = loadedSessionId ?? events[0]?.session_id ?? "none";
  sessionSummary.textContent = `Session: ${session}\nEvents: ${events.length}`;
  copySessionButton.disabled = loadedSessionId === null;
}

function showUiError(message: string): void {
  sessionSummary.classList.add("error");
  sessionSummary.textContent = message;
}

function setEvents(next: TraceEvent[]): void {
  events = next;
  selected = events.at(-1) ?? null;
  updateFilters();
  renderTimeline();
  renderDetail();
  updateSessionSummary();
}

function appendLiveEvent(event: TraceEvent): void {
  const next = nextLiveEvents(events, event, loadedSessionId);
  if (next === events) {
    return;
  }
  events = next;
  selected = event;
  updateFilters();
  renderTimeline();
  renderDetail();
  updateSessionSummary();
}

function formatTraceTime(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat(undefined, {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(parsed);
}

function runButton(
  run: TraceNavigationTurn | StandaloneTraceRun,
  label: string,
  conversationId: string | null,
): HTMLButtonElement {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "trace-run";
  button.dataset.sessionId = run.session_id;
  button.disabled = !run.trace_available;
  button.setAttribute(
    "aria-current",
    loadedSessionId === run.session_id ? "true" : "false",
  );
  button.title = run.session_id;

  const heading = document.createElement("span");
  heading.className = "trace-run-heading";
  heading.textContent = `${label} · ${formatTraceTime(run.started_at)}`;

  const preview = document.createElement("span");
  preview.className = "trace-run-preview";
  preview.textContent = run.user_message_preview;

  const metadata = document.createElement("span");
  metadata.className = "trace-run-meta";
  metadata.textContent = run.trace_available
    ? `${run.status} · ${run.short_id}`
    : `${run.status} · ${run.short_id} · Trace unavailable`;

  button.append(heading, preview, metadata);
  if (run.trace_available) {
    button.addEventListener("click", () => {
      void selectTrace(run.session_id, conversationId, true);
    });
  }
  return button;
}

function conversationGroup(
  conversation: TraceNavigationConversation,
): HTMLDetailsElement {
  const group = document.createElement("details");
  group.className = "navigation-group";
  group.dataset.conversationId = conversation.conversation_id;
  group.open = activeConversationId === conversation.conversation_id;

  const summary = document.createElement("summary");
  const title = document.createElement("span");
  title.className = "navigation-title";
  title.textContent = conversation.title;
  const count = document.createElement("span");
  count.className = "navigation-count";
  count.textContent = `${conversation.turns.length} turns`;
  summary.append(title, count);

  const root = document.createElement("span");
  root.className = "navigation-root";
  root.textContent = conversation.project_root;
  root.title = conversation.project_root;

  const runs = document.createElement("div");
  runs.className = "trace-runs";
  if (conversation.turns.length === 0) {
    runs.textContent = "No turns yet";
  } else {
    runs.replaceChildren(
      ...conversation.turns.map((turn) =>
        runButton(turn, `Turn ${turn.turn_number}`, conversation.conversation_id),
      ),
    );
  }
  group.append(summary, root, runs);
  return group;
}

function standaloneGroup(): HTMLDetailsElement {
  const group = document.createElement("details");
  group.id = "standalone-runs";
  group.className = "navigation-group";
  group.open = loadedSessionId !== null && activeConversationId === null;

  const summary = document.createElement("summary");
  const title = document.createElement("span");
  title.className = "navigation-title";
  title.textContent = "Standalone runs";
  const count = document.createElement("span");
  count.className = "navigation-count";
  count.textContent = String(navigation.standalone_runs.length);
  summary.append(title, count);

  const runs = document.createElement("div");
  runs.className = "trace-runs";
  if (navigation.standalone_runs.length === 0) {
    runs.textContent = "No standalone runs";
  } else {
    runs.replaceChildren(
      ...navigation.standalone_runs.map((run) => runButton(run, "Run", null)),
    );
  }
  group.append(summary, runs);
  return group;
}

function renderNavigation(): void {
  const groups = navigation.chat_conversations.map(conversationGroup);
  groups.push(standaloneGroup());
  traceNavigation.replaceChildren(...groups);
  liveEventsButton.classList.toggle("active", loadedSessionId === null);
}

async function loadNavigation(): Promise<TraceNavigation> {
  const response = await fetch("/api/trace-navigation");
  if (!response.ok) {
    throw new Error(`Trace navigation failed: ${response.status}`);
  }
  navigation = (await response.json()) as TraceNavigation;
  renderNavigation();
  return navigation;
}

function updateTraceQuery(sessionId: string | null, conversationId: string | null): void {
  const url = new URL(window.location.href);
  if (sessionId === null) {
    url.searchParams.delete("session_id");
    url.searchParams.delete("conversation_id");
  } else {
    url.searchParams.set("session_id", sessionId);
    if (conversationId === null) {
      url.searchParams.delete("conversation_id");
    } else {
      url.searchParams.set("conversation_id", conversationId);
    }
  }
  window.history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
}

async function applyTraceQuery(index: TraceNavigation): Promise<void> {
  const selection = resolveTraceQuerySelection(index, window.location.search);
  if (selection.kind === "none") {
    return;
  }
  if (selection.kind === "missing") {
    showUiError(
      formatUiError(
        "Load trace",
        new Error(`session_id not found: ${selection.sessionId}`),
      ),
    );
    return;
  }
  loadedSessionId = selection.sessionId;
  activeConversationId = selection.conversationId;
  renderNavigation();
  if (!selection.traceAvailable) {
    copySessionButton.disabled = false;
    showUiError(`Trace unavailable for session: ${selection.sessionId}`);
    return;
  }
  await loadSelectedSession(selection.sessionId);
}

async function loadSelectedSession(sessionId: string): Promise<void> {
  const response = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}`);
  if (!response.ok) {
    throw new Error(`Session load failed: ${response.status}`);
  }
  loadedSessionId = sessionId;
  setEvents((await response.json()) as TraceEvent[]);
}

async function selectTrace(
  sessionId: string,
  conversationId: string | null,
  updateQuery: boolean,
): Promise<void> {
  loadedSessionId = sessionId;
  activeConversationId = conversationId;
  if (updateQuery) {
    updateTraceQuery(sessionId, conversationId);
  }
  renderNavigation();
  try {
    await loadSelectedSession(sessionId);
  } catch (error) {
    showUiError(formatUiError("Load session", error));
  }
}

function selectLiveEvents(): void {
  loadedSessionId = null;
  activeConversationId = null;
  updateTraceQuery(null, null);
  setEvents([]);
  sessionSummary.textContent = "Listening for live events";
  copySessionButton.disabled = true;
  renderNavigation();
}

function parseTraceEvent(data: string): TraceEvent {
  return JSON.parse(data) as TraceEvent;
}

function connectLive(): void {
  const source = new EventSource("/api/events/stream");
  source.onopen = () => {
    connection.textContent = "Live";
    liveDot.classList.add("connected");
  };
  source.onerror = () => {
    connection.textContent = "Reconnecting";
    liveDot.classList.remove("connected");
  };
  for (const type of SSE_EVENT_TYPES) {
    source.addEventListener(type, (message) => {
      appendLiveEvent(parseTraceEvent((message as MessageEvent<string>).data));
    });
  }
}

eventFilter.addEventListener("change", renderTimeline);
liveEventsButton.addEventListener("click", selectLiveEvents);
copyButton.addEventListener("click", () => {
  if (selected) {
    void navigator.clipboard.writeText(JSON.stringify(selected, null, 2));
  }
});
copySessionButton.addEventListener("click", () => {
  if (loadedSessionId !== null) {
    void navigator.clipboard.writeText(loadedSessionId);
  }
});

renderTabs();
renderDetail();
void loadNavigation()
  .then((index) => applyTraceQuery(index))
  .catch((error: unknown) => {
    showUiError(formatUiError("Load trace navigation", error));
  });
connectLive();
