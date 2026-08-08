import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";

import { ChatComposer } from "./components/ChatComposer";
import { ConversationList } from "./components/ConversationList";
import { MessageTimeline } from "./components/MessageTimeline";
import {
  ChatApiError,
  createConversation,
  decideApproval,
  getConversation,
  getConversationState,
  listConversations,
  listMessages,
  listRuns,
  patchConversation,
  postMessage,
} from "./state/api";
import { ConversationEventStream } from "./state/events";
import { initialState, reduceChatState } from "./state/reducer";
import type {
  ApprovalDecision,
  Conversation,
  CreateConversationRequest,
  RunStatus,
} from "./state/types";

const ACTIVE_RUN_STATUSES = new Set<RunStatus>([
  "queued",
  "running",
  "waiting_approval",
]);
const SIDEBAR_STORAGE_KEY = "agent-foundations.chat.sidebar";
const MOBILE_QUERY = "(max-width: 800px)";

function isMobileViewport(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia(MOBILE_QUERY).matches;
}

function initialDesktopSidebarOpen(): boolean {
  try {
    return window.localStorage.getItem(SIDEBAR_STORAGE_KEY) !== "collapsed";
  } catch {
    return true;
  }
}

function projectName(projectRoot: string): string {
  const trimmedRoot = projectRoot.replace(/[\\/]+$/, "");
  return trimmedRoot.split(/[\\/]/).at(-1) || projectRoot;
}

function errorMessage(error: unknown): string {
  if (error instanceof ChatApiError) {
    return error.detail;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "Request failed";
}

export function App() {
  const [state, dispatch] = useReducer(reduceChatState, initialState);
  const eventStreamRef = useRef(new ConversationEventStream());
  const selectionEpochRef = useRef(0);
  const sessionByConversationRef = useRef<Record<string, string>>({});
  const reconnectingRef = useRef(false);
  const previousContentTokenRef = useRef<string | null>(null);
  const [isFollowingLatest, setIsFollowingLatest] = useState(true);
  const [isMobile, setIsMobile] = useState(isMobileViewport);
  const [desktopSidebarOpen, setDesktopSidebarOpen] = useState(
    initialDesktopSidebarOpen,
  );
  const [mobileDrawerOpen, setMobileDrawerOpen] = useState(false);
  const [conversationDetailsOpen, setConversationDetailsOpen] = useState(false);
  const sidebarOpen = isMobile ? mobileDrawerOpen : desktopSidebarOpen;

  const activeId = state.activeConversationId;
  const activeConversation = useMemo(
    () =>
      state.conversations.find(
        (conversation) => conversation.conversation_id === activeId,
      ) ?? null,
    [activeId, state.conversations],
  );
  const messages = activeId ? state.messagesByConversation[activeId] ?? [] : [];
  const runs = activeId ? state.runsByConversation[activeId] ?? [] : [];
  const runStatus = activeId ? state.runStatusByConversation[activeId] : undefined;
  const activeSessionId = activeId
    ? state.activeSessionIdByConversation[activeId] ?? null
    : null;
  const activeApproval = activeId
    ? state.activeApprovalByConversation[activeId] ?? null
    : null;
  const messagesError = activeId
    ? state.messagesErrorByConversation[activeId] ?? null
    : null;

  const isRunActive =
    runStatus !== undefined && ACTIVE_RUN_STATUSES.has(runStatus);
  const hasPendingApproval = activeApproval !== null;
  const composerDisabled = !activeId || isRunActive || hasPendingApproval;
  const permissionDisabled = !activeId || isRunActive || hasPendingApproval;

  const composerDisabledReason = useMemo(() => {
    if (!activeId) {
      return "Select a conversation to send a message.";
    }
    if (hasPendingApproval) {
      return "Waiting for approval decision.";
    }
    if (isRunActive) {
      return "A run is active for this conversation.";
    }
    return null;
  }, [activeId, hasPendingApproval, isRunActive]);

  const reloadConversations = useCallback(async () => {
    dispatch({ type: "conversations.loading" });
    try {
      const conversations = await listConversations();
      dispatch({ type: "conversations.loaded", conversations });
    } catch (error) {
      dispatch({ type: "conversations.error", error: errorMessage(error) });
    }
  }, []);

  useEffect(() => {
    void reloadConversations();
  }, [reloadConversations]);

  useEffect(() => {
    if (typeof window.matchMedia !== "function") {
      return;
    }
    const mediaQuery = window.matchMedia(MOBILE_QUERY);
    const handleViewportChange = (event: MediaQueryListEvent) => {
      setIsMobile(event.matches);
      setMobileDrawerOpen(false);
    };
    setIsMobile(mediaQuery.matches);
    mediaQuery.addEventListener("change", handleViewportChange);
    return () => mediaQuery.removeEventListener("change", handleViewportChange);
  }, []);

  const restoreConversationHttp = useCallback(
    async (conversationId: string, epoch: number): Promise<boolean> => {
      dispatch({ type: "messages.loading", conversationId });
      try {
        const [
          _conversation,
          messagesForConversation,
          runsForConversation,
          conversations,
          conversationState,
        ] =
          await Promise.all([
            getConversation(conversationId),
            listMessages(conversationId),
            listRuns(conversationId),
            listConversations(),
            getConversationState(conversationId),
          ]);
        if (epoch !== selectionEpochRef.current) {
          return false;
        }
        dispatch({ type: "conversations.loaded", conversations });
        dispatch({
          type: "messages.loaded",
          conversationId,
          messages: messagesForConversation,
        });
        dispatch({
          type: "runs.loaded",
          conversationId,
          runs: runsForConversation,
        });
        dispatch({
          type: "conversation.state.loaded",
          conversationId,
          state: conversationState,
        });
        if (conversationState.latest_run) {
          sessionByConversationRef.current[conversationId] =
            conversationState.latest_run.session_id;
        } else {
          delete sessionByConversationRef.current[conversationId];
        }
        return true;
      } catch (error) {
        if (epoch !== selectionEpochRef.current) {
          return false;
        }
        dispatch({
          type: "messages.error",
          conversationId,
          error: errorMessage(error),
        });
        return false;
      }
    },
    [],
  );

  const connectStream = useCallback((conversationId: string, epoch: number) => {
    eventStreamRef.current.connect(
      conversationId,
      (event) => {
        if (epoch !== selectionEpochRef.current) {
          return;
        }
        dispatch({ type: "event.received", event });
        sessionByConversationRef.current[conversationId] = event.session_id;
        if (event.type === "run.completed" || event.type === "run.failed") {
          void (async () => {
            const [messagesForConversation, runsForConversation, conversationState] =
              await Promise.all([
                listMessages(conversationId),
                listRuns(conversationId),
                getConversationState(conversationId),
              ]);
            if (epoch !== selectionEpochRef.current) {
              return;
            }
            dispatch({
              type: "messages.loaded",
              conversationId,
              messages: messagesForConversation,
            });
            dispatch({
              type: "runs.loaded",
              conversationId,
              runs: runsForConversation,
            });
            dispatch({
              type: "conversation.state.loaded",
              conversationId,
              state: conversationState,
            });
          })();
        }
      },
      () => {
        if (epoch !== selectionEpochRef.current || reconnectingRef.current) {
          return;
        }
        reconnectingRef.current = true;
        eventStreamRef.current.close();
        void (async () => {
          try {
            const restored = await restoreConversationHttp(conversationId, epoch);
            if (!restored || epoch !== selectionEpochRef.current) {
              return;
            }
            connectStream(conversationId, epoch);
          } finally {
            reconnectingRef.current = false;
          }
        })();
      },
    );
  }, [restoreConversationHttp]);

  useEffect(() => {
    if (!activeId) {
      eventStreamRef.current.close();
      return;
    }

    const epoch = ++selectionEpochRef.current;
    eventStreamRef.current.close();

    void (async () => {
      dispatch({ type: "conversation.selected", conversationId: activeId });
      const restored = await restoreConversationHttp(activeId, epoch);
      if (!restored || epoch !== selectionEpochRef.current) {
        return;
      }
      connectStream(activeId, epoch);
    })();

    return () => {
      selectionEpochRef.current += 1;
      eventStreamRef.current.close();
    };
  }, [activeId, connectStream, restoreConversationHttp]);

  useEffect(
    () => () => {
      eventStreamRef.current.close();
    },
    [],
  );

  const scrollToLatest = useCallback(() => {
    if (document.documentElement.scrollHeight <= window.innerHeight) {
      setIsFollowingLatest(true);
      return;
    }
    window.scrollTo({
      top: document.documentElement.scrollHeight,
      behavior: "auto",
    });
    setIsFollowingLatest(true);
  }, []);

  useEffect(() => {
    const updateFollowingState = () => {
      const distanceFromBottom =
        document.documentElement.scrollHeight - (window.scrollY + window.innerHeight);
      setIsFollowingLatest(distanceFromBottom <= 96);
    };
    updateFollowingState();
    window.addEventListener("scroll", updateFollowingState, { passive: true });
    return () => window.removeEventListener("scroll", updateFollowingState);
  }, []);

  useEffect(() => {
    const contentToken = `${activeId ?? "none"}:${messages.length}:${activeApproval?.approval_id ?? "none"}:${activeSessionId ?? "none"}`;
    if (previousContentTokenRef.current === null) {
      previousContentTokenRef.current = contentToken;
      return;
    }
    if (previousContentTokenRef.current !== contentToken) {
      previousContentTokenRef.current = contentToken;
      if (isFollowingLatest) {
        scrollToLatest();
      }
    }
  }, [activeApproval, activeId, activeSessionId, isFollowingLatest, messages.length, scrollToLatest]);

  async function handleCreate(request: CreateConversationRequest): Promise<void> {
    const created = await createConversation(request);
    const conversations = await listConversations();
    dispatch({ type: "conversations.loaded", conversations });
    dispatch({
      type: "conversation.selected",
      conversationId: created.conversation_id,
    });
    setMobileDrawerOpen(false);
  }

  function handleSelect(conversationId: string): void {
    dispatch({ type: "conversation.selected", conversationId });
    setMobileDrawerOpen(false);
  }

  function toggleDesktopSidebar(): void {
    setDesktopSidebarOpen((current) => {
      const next = !current;
      try {
        window.localStorage.setItem(
          SIDEBAR_STORAGE_KEY,
          next ? "expanded" : "collapsed",
        );
      } catch {
        // The layout remains usable when browser storage is unavailable.
      }
      return next;
    });
  }

  async function handleSubmitMessage(query: string): Promise<void> {
    if (!activeId) {
      return;
    }
    const { session_id: sessionId } = await postMessage(activeId, { query });
    sessionByConversationRef.current[activeId] = sessionId;
    dispatch({
      type: "event.received",
      event: {
        event_id: `local-run-started-${sessionId}`,
        conversation_id: activeId,
        session_id: sessionId,
        type: "run.started",
        occurred_at: new Date().toISOString(),
        data: { status: "running" },
      },
    });
    const messagesForConversation = await listMessages(activeId);
    dispatch({
      type: "messages.loaded",
      conversationId: activeId,
      messages: messagesForConversation,
    });
  }

  async function handleApprovalDecision(
    approvalId: string,
    decision: ApprovalDecision,
  ): Promise<void> {
    await decideApproval(approvalId, { decision });
  }

  async function handlePermissionModeChange(
    event: React.ChangeEvent<HTMLSelectElement>,
  ): Promise<void> {
    if (!activeId || permissionDisabled) {
      return;
    }
    const updated = await patchConversation(activeId, {
      permission_mode: event.target.value as Conversation["permission_mode"],
    });
    const conversations = state.conversations.map((conversation) =>
      conversation.conversation_id === activeId ? updated : conversation,
    );
    dispatch({ type: "conversations.loaded", conversations });
  }

  return (
    <div
      className={`chat-shell chat-shell--responsive chat-shell--message-first ${
        isMobile ? "chat-shell--mobile" : "chat-shell--desktop"
      } ${sidebarOpen ? "chat-shell--sidebar-open" : "chat-shell--sidebar-closed"}`}
      data-testid="chat-shell"
    >
      <div className="chat-layout">
        <aside
          id="conversation-sidebar"
          className="chat-sidebar"
          aria-hidden={isMobile && !sidebarOpen ? "true" : undefined}
        >
          <div className="chat-sidebar__header">
            <span className="chat-sidebar__brand">AF Chat</span>
            {isMobile ? (
              <button
                type="button"
                className="chat-sidebar__toggle"
                aria-label="Close conversations"
                aria-controls="conversation-sidebar"
                aria-expanded={sidebarOpen}
                onClick={() => setMobileDrawerOpen(false)}
              >
                <span aria-hidden="true">×</span>
              </button>
            ) : (
              <button
                type="button"
                className="chat-sidebar__toggle"
                aria-label={
                  sidebarOpen ? "Collapse conversations" : "Expand conversations"
                }
                aria-controls="conversation-sidebar"
                aria-expanded={sidebarOpen}
                onClick={toggleDesktopSidebar}
              >
                <span aria-hidden="true">{sidebarOpen ? "‹" : "›"}</span>
              </button>
            )}
          </div>
          <div className="chat-sidebar__content">
            <ConversationList
              conversations={state.conversations}
              activeId={activeId}
              onSelect={handleSelect}
              onCreate={handleCreate}
            />
          </div>
        </aside>
        {isMobile && sidebarOpen ? (
          <button
            type="button"
            className="chat-sidebar-backdrop"
            aria-label="Close conversation drawer"
            onClick={() => setMobileDrawerOpen(false)}
          />
        ) : null}
        <main className="chat-main">
          {isMobile && !sidebarOpen ? (
            <button
              type="button"
              className="chat-mobile-menu"
              aria-label="Open conversations"
              aria-controls="conversation-sidebar"
              aria-expanded="false"
              onClick={() => setMobileDrawerOpen(true)}
            >
              <span aria-hidden="true">☰</span>
            </button>
          ) : null}
          {state.loadingConversations ? (
            <p role="status" aria-live="polite">
              Loading conversations...
            </p>
          ) : null}
          {state.conversationsError ? (
            <p role="alert">{state.conversationsError}</p>
          ) : null}
          {activeConversation ? (
            <section className="chat-conversation" aria-label="Active conversation">
              <header className="chat-conversation__toolbar">
                <div className="chat-conversation__identity">
                  <h1>{activeConversation.title}</h1>
                  <span>{projectName(activeConversation.project_root)}</span>
                </div>
                <div className="chat-conversation__controls">
                  <label className="visually-hidden" htmlFor="permission-mode">
                    Permission mode
                  </label>
                  <select
                    id="permission-mode"
                    value={activeConversation.permission_mode}
                    disabled={permissionDisabled}
                    onChange={(event) => void handlePermissionModeChange(event)}
                  >
                    <option value="PROJECT_READ_ONLY">PROJECT_READ_ONLY</option>
                    <option value="ASK_FOR_ACCESS">ASK_FOR_ACCESS</option>
                  </select>
                  <div className="chat-conversation__details">
                    <button
                      type="button"
                      aria-label="Conversation details"
                      aria-expanded={conversationDetailsOpen}
                      onClick={() => setConversationDetailsOpen((current) => !current)}
                    >
                      <span aria-hidden="true">•••</span>
                    </button>
                    <div
                      className="chat-conversation__details-menu"
                      hidden={!conversationDetailsOpen}
                    >
                      <strong>Project root</strong>
                      <p>{activeConversation.project_root}</p>
                    </div>
                  </div>
                </div>
              </header>
              <div className="chat-timeline">
                <MessageTimeline
                  messages={messages}
                  runs={runs}
                  activeApproval={activeApproval}
                  isRunActive={isRunActive}
                  onApprovalDecision={handleApprovalDecision}
                  approvalDisabled={false}
                />
              </div>
              {messagesError ? <p role="alert">{messagesError}</p> : null}
              {!isFollowingLatest ? (
                <button
                  type="button"
                  className="chat-jump-latest"
                  onClick={scrollToLatest}
                >
                  Jump to latest
                </button>
              ) : null}
              <div className="chat-composer-panel">
                <ChatComposer
                  disabled={composerDisabled}
                  disabledReason={composerDisabledReason}
                  onSubmit={handleSubmitMessage}
                />
              </div>
            </section>
          ) : (
            <p role="status">Select or create a conversation to begin.</p>
          )}
        </main>
      </div>
    </div>
  );
}
