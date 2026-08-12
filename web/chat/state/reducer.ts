import { isValidChatEventType } from "./events";
import type {
  ActiveApproval,
  ChatEvent,
  ChatMessage,
  ChatToolActivity,
  Conversation,
  ConversationStateResponse,
  PendingApprovalState,
  RunRecord,
  RunStatus,
  ToolActivityStatus,
} from "./types";

export interface ChatState {
  conversations: Conversation[];
  activeConversationId: string | null;
  messagesByConversation: Record<string, ChatMessage[]>;
  runsByConversation: Record<string, RunRecord[]>;
  activitiesByConversation: Record<string, ChatToolActivity[]>;
  activitiesErrorByConversation: Record<string, string | null>;
  runStatusByConversation: Record<string, RunStatus>;
  activeSessionIdByConversation: Record<string, string | null>;
  latestSessionIdByConversation: Record<string, string | null>;
  activeApprovalByConversation: Record<string, ActiveApproval | null>;
  loadingConversations: boolean;
  conversationsError: string | null;
  loadingMessagesByConversation: Record<string, boolean>;
  messagesErrorByConversation: Record<string, string | null>;
}

export const initialState: ChatState = {
  conversations: [],
  activeConversationId: null,
  messagesByConversation: {},
  runsByConversation: {},
  activitiesByConversation: {},
  activitiesErrorByConversation: {},
  runStatusByConversation: {},
  activeSessionIdByConversation: {},
  latestSessionIdByConversation: {},
  activeApprovalByConversation: {},
  loadingConversations: false,
  conversationsError: null,
  loadingMessagesByConversation: {},
  messagesErrorByConversation: {},
};

export type ChatAction =
  | { type: "conversations.loading" }
  | { type: "conversations.loaded"; conversations: Conversation[] }
  | { type: "conversations.error"; error: string }
  | { type: "conversation.selected"; conversationId: string | null }
  | { type: "messages.loading"; conversationId: string }
  | { type: "messages.loaded"; conversationId: string; messages: ChatMessage[] }
  | { type: "runs.loaded"; conversationId: string; runs: RunRecord[] }
  | {
      type: "activities.loaded";
      conversationId: string;
      activities: ChatToolActivity[];
    }
  | { type: "activities.error"; conversationId: string; error: string }
  | { type: "messages.error"; conversationId: string; error: string }
  | { type: "run.loaded"; conversationId: string; run: RunRecord | null }
  | {
      type: "conversation.state.loaded";
      conversationId: string;
      state: ConversationStateResponse;
    }
  | { type: "event.received"; event: ChatEvent };

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function isValidEventEnvelope(event: ChatEvent): boolean {
  return (
    isNonEmptyString(event.event_id) &&
    isNonEmptyString(event.conversation_id) &&
    isNonEmptyString(event.session_id) &&
    isNonEmptyString(event.occurred_at) &&
    isValidChatEventType(event.type) &&
    typeof event.data === "object" &&
    event.data !== null &&
    !Array.isArray(event.data)
  );
}

function mergeMessages(
  existing: ChatMessage[],
  incoming: ChatMessage[],
): ChatMessage[] {
  const byId = new Map<string, ChatMessage>();
  for (const message of existing) {
    byId.set(message.message_id, message);
  }
  for (const message of incoming) {
    byId.set(message.message_id, message);
  }
  return [...byId.values()].sort((left, right) => left.sequence - right.sequence);
}

const TERMINAL_ACTIVITY_STATUSES = new Set<ToolActivityStatus>([
  "completed",
  "failed",
  "interrupted",
]);

function activityKey(activity: ChatToolActivity): string {
  return `${activity.session_id}\u0000${activity.tool_call_id}`;
}

function mergeActivities(
  existing: ChatToolActivity[],
  incoming: ChatToolActivity[],
): ChatToolActivity[] {
  const byKey = new Map<string, ChatToolActivity>();
  for (const activity of existing) {
    byKey.set(activityKey(activity), activity);
  }
  for (const activity of incoming) {
    const key = activityKey(activity);
    const current = byKey.get(key);
    if (current && TERMINAL_ACTIVITY_STATUSES.has(current.status)) {
      continue;
    }
    byKey.set(key, current ? {
      ...activity,
      arguments_summary: activity.arguments_summary ?? current.arguments_summary,
      result_summary: activity.result_summary ?? current.result_summary,
      started_at: current.started_at,
    } : activity);
  }
  return [...byKey.values()].sort(
    (left, right) =>
      left.started_at.localeCompare(right.started_at) ||
      left.tool_call_id.localeCompare(right.tool_call_id),
  );
}

function activityFromEvent(event: ChatEvent): ChatToolActivity | null {
  if (
    event.type !== "tool.requested" &&
    event.type !== "tool.completed" &&
    event.type !== "tool.failed"
  ) {
    return null;
  }
  const toolCallId = event.data.tool_call_id;
  const toolName = event.data.name;
  if (!isNonEmptyString(toolCallId) || !isNonEmptyString(toolName)) {
    return null;
  }
  const status: ToolActivityStatus =
    event.type === "tool.requested"
      ? "running"
      : event.type === "tool.completed"
        ? "completed"
        : "failed";
  const argumentsSummary = event.data.arguments_summary;
  const resultSummary = event.data.result_summary;
  return {
    conversation_id: event.conversation_id,
    session_id: event.session_id,
    tool_call_id: toolCallId,
    tool_name: toolName,
    status,
    arguments_summary: isNonEmptyString(argumentsSummary) ? argumentsSummary : null,
    result_summary: isNonEmptyString(resultSummary) ? resultSummary : null,
    started_at: event.occurred_at,
    finished_at: status === "running" ? null : event.occurred_at,
    last_event_id: event.event_id,
  };
}

function assistantMessageFromEvent(event: ChatEvent): ChatMessage | null {
  const messageId = event.data.message_id;
  const content = event.data.content;
  const sequence = event.data.sequence;
  if (
    !isNonEmptyString(messageId) ||
    !isNonEmptyString(content) ||
    typeof sequence !== "number"
  ) {
    return null;
  }
  return {
    message_id: messageId,
    conversation_id: event.conversation_id,
    role: "assistant",
    content,
    sequence,
    created_at: event.occurred_at,
  };
}

function approvalFromEvent(event: ChatEvent): ActiveApproval | null {
  const approvalId = event.data.approval_id;
  const toolCallId = event.data.tool_call_id;
  const toolName = event.data.tool_name;
  const canonicalPath = event.data.canonical_path;
  const operation = event.data.operation;
  const scope = event.data.scope;
  if (
    !isNonEmptyString(approvalId) ||
    !isNonEmptyString(toolCallId) ||
    !isNonEmptyString(toolName) ||
    !isNonEmptyString(canonicalPath) ||
    operation !== "read" ||
    scope !== "external_exact_path"
  ) {
    return null;
  }
  return {
    approval_id: approvalId,
    tool_call_id: toolCallId,
    tool_name: toolName,
    canonical_path: canonicalPath,
    operation: "read",
    scope: "external_exact_path",
  };
}

function isTerminalRunStatus(status: RunStatus): boolean {
  return status === "completed" || status === "failed" || status === "interrupted";
}

function isActiveRunStatus(status: RunStatus): boolean {
  return status === "queued" || status === "running" || status === "waiting_approval";
}

function activeApprovalFromPending(
  pending: PendingApprovalState,
): ActiveApproval {
  return {
    approval_id: pending.approval_id,
    tool_call_id: pending.tool_call_id,
    tool_name: pending.tool_name,
    canonical_path: pending.canonical_path,
    operation: "read",
    scope: "external_exact_path",
  };
}

function applyRecoveredRunState(
  state: ChatState,
  conversationId: string,
  run: RunRecord | null,
  pendingApproval: PendingApprovalState | null,
): ChatState {
  if (run === null) {
    const nextRunStatus = { ...state.runStatusByConversation };
    delete nextRunStatus[conversationId];
    return {
      ...state,
      runStatusByConversation: nextRunStatus,
      activeSessionIdByConversation: {
        ...state.activeSessionIdByConversation,
        [conversationId]: null,
      },
      latestSessionIdByConversation: {
        ...state.latestSessionIdByConversation,
        [conversationId]: null,
      },
      activeApprovalByConversation: {
        ...state.activeApprovalByConversation,
        [conversationId]: null,
      },
    };
  }

  const nextState: ChatState = {
    ...state,
    runStatusByConversation: {
      ...state.runStatusByConversation,
      [conversationId]: run.status,
    },
    latestSessionIdByConversation: {
      ...state.latestSessionIdByConversation,
      [conversationId]: run.session_id,
    },
    activeSessionIdByConversation: {
      ...state.activeSessionIdByConversation,
      [conversationId]: isActiveRunStatus(run.status) ? run.session_id : null,
    },
    activeApprovalByConversation: {
      ...state.activeApprovalByConversation,
      [conversationId]:
        pendingApproval !== null ? activeApprovalFromPending(pendingApproval) : null,
    },
  };
  return nextState;
}

function resolveActiveConversationId(
  conversations: Conversation[],
  currentActiveId: string | null,
): string | null {
  if (conversations.length === 0) {
    return null;
  }
  if (
    currentActiveId !== null &&
    conversations.some(
      (conversation) => conversation.conversation_id === currentActiveId,
    )
  ) {
    return currentActiveId;
  }
  return conversations[0]?.conversation_id ?? null;
}

export function reduceChatState(state: ChatState, action: ChatAction): ChatState {
  switch (action.type) {
    case "conversations.loading":
      return {
        ...state,
        loadingConversations: true,
        conversationsError: null,
      };
    case "conversations.loaded":
      return {
        ...state,
        conversations: action.conversations,
        activeConversationId: resolveActiveConversationId(
          action.conversations,
          state.activeConversationId,
        ),
        loadingConversations: false,
        conversationsError: null,
      };
    case "conversations.error":
      return {
        ...state,
        loadingConversations: false,
        conversationsError: action.error,
      };
    case "conversation.selected":
      return {
        ...state,
        activeConversationId: action.conversationId,
      };
    case "messages.loading":
      return {
        ...state,
        loadingMessagesByConversation: {
          ...state.loadingMessagesByConversation,
          [action.conversationId]: true,
        },
        messagesErrorByConversation: {
          ...state.messagesErrorByConversation,
          [action.conversationId]: null,
        },
      };
    case "messages.loaded":
      return {
        ...state,
        messagesByConversation: {
          ...state.messagesByConversation,
          [action.conversationId]: mergeMessages(
            state.messagesByConversation[action.conversationId] ?? [],
            action.messages,
          ),
        },
        loadingMessagesByConversation: {
          ...state.loadingMessagesByConversation,
          [action.conversationId]: false,
        },
        messagesErrorByConversation: {
          ...state.messagesErrorByConversation,
          [action.conversationId]: null,
        },
      };
    case "messages.error":
      return {
        ...state,
        loadingMessagesByConversation: {
          ...state.loadingMessagesByConversation,
          [action.conversationId]: false,
        },
        messagesErrorByConversation: {
          ...state.messagesErrorByConversation,
          [action.conversationId]: action.error,
        },
      };
    case "runs.loaded":
      return {
        ...state,
        runsByConversation: {
          ...state.runsByConversation,
          [action.conversationId]: action.runs,
        },
      };
    case "activities.loaded":
      return {
        ...state,
        activitiesByConversation: {
          ...state.activitiesByConversation,
          [action.conversationId]: mergeActivities(
            state.activitiesByConversation[action.conversationId] ?? [],
            action.activities,
          ),
        },
        activitiesErrorByConversation: {
          ...state.activitiesErrorByConversation,
          [action.conversationId]: null,
        },
      };
    case "activities.error":
      return {
        ...state,
        activitiesErrorByConversation: {
          ...state.activitiesErrorByConversation,
          [action.conversationId]: action.error,
        },
      };
    case "run.loaded": {
      return applyRecoveredRunState(
        state,
        action.conversationId,
        action.run,
        null,
      );
    }
    case "conversation.state.loaded":
      return applyRecoveredRunState(
        state,
        action.conversationId,
        action.state.latest_run,
        action.state.pending_approval,
      );
    case "event.received": {
      if (!isValidEventEnvelope(action.event)) {
        return state;
      }
      const { event } = action;
      const conversationId = event.conversation_id;
      const liveActivity = activityFromEvent(event);
      let nextState: ChatState = liveActivity
        ? {
            ...state,
            activitiesByConversation: {
              ...state.activitiesByConversation,
              [conversationId]: mergeActivities(
                state.activitiesByConversation[conversationId] ?? [],
                [liveActivity],
              ),
            },
          }
        : state;

      switch (event.type) {
        case "run.started":
          nextState = {
            ...nextState,
            runStatusByConversation: {
              ...nextState.runStatusByConversation,
              [conversationId]: "running",
            },
            activeSessionIdByConversation: {
              ...nextState.activeSessionIdByConversation,
              [conversationId]: event.session_id,
            },
            latestSessionIdByConversation: {
              ...nextState.latestSessionIdByConversation,
              [conversationId]: event.session_id,
            },
            activeApprovalByConversation: {
              ...nextState.activeApprovalByConversation,
              [conversationId]: null,
            },
          };
          break;
        case "approval.requested": {
          const approval = approvalFromEvent(event);
          nextState = {
            ...nextState,
            runStatusByConversation: {
              ...nextState.runStatusByConversation,
              [conversationId]: "waiting_approval",
            },
            activeSessionIdByConversation: {
              ...nextState.activeSessionIdByConversation,
              [conversationId]: event.session_id,
            },
            activeApprovalByConversation: {
              ...nextState.activeApprovalByConversation,
              [conversationId]: approval,
            },
          };
          break;
        }
        case "approval.resolved":
          nextState = {
            ...nextState,
            runStatusByConversation: {
              ...nextState.runStatusByConversation,
              [conversationId]: "running",
            },
            activeApprovalByConversation: {
              ...nextState.activeApprovalByConversation,
              [conversationId]: null,
            },
          };
          break;
        case "assistant.message.completed": {
          const assistantMessage = assistantMessageFromEvent(event);
          if (assistantMessage) {
            nextState = {
              ...nextState,
              messagesByConversation: {
                ...nextState.messagesByConversation,
                [conversationId]: mergeMessages(
                  nextState.messagesByConversation[conversationId] ?? [],
                  [assistantMessage],
                ),
              },
            };
          }
          break;
        }
        case "run.completed":
          nextState = {
            ...nextState,
            runStatusByConversation: {
              ...nextState.runStatusByConversation,
              [conversationId]: "completed",
            },
            activeSessionIdByConversation: {
              ...nextState.activeSessionIdByConversation,
              [conversationId]: null,
            },
            latestSessionIdByConversation: {
              ...nextState.latestSessionIdByConversation,
              [conversationId]: event.session_id,
            },
            activeApprovalByConversation: {
              ...nextState.activeApprovalByConversation,
              [conversationId]: null,
            },
          };
          break;
        case "run.failed":
          nextState = {
            ...nextState,
            runStatusByConversation: {
              ...nextState.runStatusByConversation,
              [conversationId]: "failed",
            },
            activeSessionIdByConversation: {
              ...nextState.activeSessionIdByConversation,
              [conversationId]: null,
            },
            latestSessionIdByConversation: {
              ...nextState.latestSessionIdByConversation,
              [conversationId]: event.session_id,
            },
            activeApprovalByConversation: {
              ...nextState.activeApprovalByConversation,
              [conversationId]: null,
            },
          };
          break;
        default:
          break;
      }
      return nextState;
    }
    default:
      return state;
  }
}
