import { conversationEventsUrl } from "./api";
import {
  CHAT_EVENT_TYPES,
  type ChatEvent,
  type ChatEventType,
} from "./types";

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

export function isValidChatEventType(value: string): value is ChatEventType {
  return (CHAT_EVENT_TYPES as readonly string[]).includes(value);
}

export function parseChatEvent(raw: MessageEvent<string>): ChatEvent | null {
  if (!isValidChatEventType(raw.type)) {
    return null;
  }
  let payload: unknown;
  try {
    payload = JSON.parse(raw.data);
  } catch {
    return null;
  }
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const record = payload as Record<string, unknown>;
  if (
    !isNonEmptyString(record.event_id) ||
    !isNonEmptyString(record.conversation_id) ||
    !isNonEmptyString(record.session_id) ||
    !isNonEmptyString(record.occurred_at) ||
    record.type !== raw.type ||
    typeof record.data !== "object" ||
    record.data === null ||
    Array.isArray(record.data)
  ) {
    return null;
  }
  return {
    event_id: record.event_id,
    conversation_id: record.conversation_id,
    session_id: record.session_id,
    type: raw.type,
    occurred_at: record.occurred_at,
    data: record.data as Record<string, unknown>,
  };
}

export class ConversationEventStream {
  private source: EventSource | null = null;
  private conversationId: string | null = null;

  connect(
    conversationId: string,
    onEvent: (event: ChatEvent) => void,
    onError?: (error: Event) => void,
  ): void {
    if (this.conversationId === conversationId && this.source) {
      return;
    }
    this.close();
    this.conversationId = conversationId;
    const source = new EventSource(conversationEventsUrl(conversationId));
    for (const eventType of CHAT_EVENT_TYPES) {
      source.addEventListener(eventType, (raw) => {
        const event = parseChatEvent(raw as MessageEvent<string>);
        if (event) {
          onEvent(event);
        }
      });
    }
    if (onError) {
      source.onerror = onError;
    }
    this.source = source;
  }

  close(): void {
    this.source?.close();
    this.source = null;
    this.conversationId = null;
  }

  get activeConversationId(): string | null {
    return this.conversationId;
  }
}
