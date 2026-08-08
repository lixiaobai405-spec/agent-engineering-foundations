import type {
  ApprovalDecisionRequest,
  ApprovalRequest,
  ChatEvent,
  ChatMessage,
  Conversation,
  CreateConversationRequest,
  PatchConversationRequest,
  PostMessageRequest,
  PostMessageResponse,
  RunRecord,
  ConversationStateResponse,
} from "./types";

const CHAT_API_BASE = "/api/chat";

export class ChatApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ChatApiError";
    this.status = status;
    this.detail = detail;
  }
}

export async function requestJson<T>(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(input, init);
  if (!response.ok) {
    throw await buildChatApiError(response);
  }
  return response.json() as Promise<T>;
}

async function buildChatApiError(response: Response): Promise<ChatApiError> {
  const fallback = `Request failed with status ${response.status}`;
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    return new ChatApiError(response.status, fallback);
  }
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string" && body.detail.trim().length > 0) {
      return new ChatApiError(response.status, body.detail);
    }
  } catch {
    // Fall back to a stable generic message.
  }
  return new ChatApiError(response.status, fallback);
}

function chatUrl(path: string): string {
  return `${CHAT_API_BASE}${path}`;
}

function encodeId(value: string): string {
  return encodeURIComponent(value);
}

export async function listConversations(): Promise<Conversation[]> {
  return requestJson<Conversation[]>(chatUrl("/conversations"));
}

export async function createConversation(
  body: CreateConversationRequest,
): Promise<Conversation> {
  return requestJson<Conversation>(chatUrl("/conversations"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function getConversation(conversationId: string): Promise<Conversation> {
  return requestJson<Conversation>(
    chatUrl(`/conversations/${encodeId(conversationId)}`),
  );
}

export async function patchConversation(
  conversationId: string,
  body: PatchConversationRequest,
): Promise<Conversation> {
  return requestJson<Conversation>(
    chatUrl(`/conversations/${encodeId(conversationId)}`),
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
}

export async function listMessages(conversationId: string): Promise<ChatMessage[]> {
  return requestJson<ChatMessage[]>(
    chatUrl(`/conversations/${encodeId(conversationId)}/messages`),
  );
}

export async function listRuns(conversationId: string): Promise<RunRecord[]> {
  return requestJson<RunRecord[]>(
    chatUrl(`/conversations/${encodeId(conversationId)}/runs`),
  );
}

export async function postMessage(
  conversationId: string,
  body: PostMessageRequest,
): Promise<PostMessageResponse> {
  return requestJson<PostMessageResponse>(
    chatUrl(`/conversations/${encodeId(conversationId)}/messages`),
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
}

export async function getRun(sessionId: string): Promise<RunRecord> {
  return requestJson<RunRecord>(chatUrl(`/runs/${encodeId(sessionId)}`));
}

export async function getConversationState(
  conversationId: string,
): Promise<ConversationStateResponse> {
  return requestJson<ConversationStateResponse>(
    chatUrl(`/conversations/${encodeId(conversationId)}/state`),
  );
}

export async function decideApproval(
  approvalId: string,
  body: ApprovalDecisionRequest,
): Promise<ApprovalRequest> {
  return requestJson<ApprovalRequest>(
    chatUrl(`/approvals/${encodeId(approvalId)}/decision`),
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
}

export function conversationEventsUrl(conversationId: string): string {
  return chatUrl(`/conversations/${encodeId(conversationId)}/events`);
}

export type { ChatEvent };
