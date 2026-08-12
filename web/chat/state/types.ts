export type PermissionMode = "PROJECT_READ_ONLY" | "ASK_FOR_ACCESS";

export type MessageRole = "user" | "assistant";

export type RunStatus =
  | "queued"
  | "running"
  | "waiting_approval"
  | "completed"
  | "failed"
  | "interrupted";

export type ApprovalStatus = "pending" | "approved" | "denied" | "invalidated";

export type ApprovalDecision = "approve" | "deny";

export type ToolActivityStatus =
  | "running"
  | "completed"
  | "failed"
  | "interrupted";

export type ChatEventType =
  | "run.started"
  | "model.requested"
  | "tool.requested"
  | "tool.completed"
  | "tool.failed"
  | "approval.requested"
  | "approval.resolved"
  | "assistant.message.completed"
  | "run.completed"
  | "run.failed";

export const CHAT_EVENT_TYPES: readonly ChatEventType[] = [
  "run.started",
  "model.requested",
  "tool.requested",
  "tool.completed",
  "tool.failed",
  "approval.requested",
  "approval.resolved",
  "assistant.message.completed",
  "run.completed",
  "run.failed",
] as const;

export interface Conversation {
  conversation_id: string;
  title: string;
  project_root: string;
  permission_mode: PermissionMode;
  created_at: string;
  updated_at: string;
}

export interface ChatMessage {
  message_id: string;
  conversation_id: string;
  role: MessageRole;
  content: string;
  sequence: number;
  created_at: string;
}

export interface RunRecord {
  session_id: string;
  conversation_id: string;
  user_message_id: string;
  trace_path: string;
  assistant_message_id: string | null;
  status: RunStatus;
  error_code: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface ApprovalRequest {
  approval_id: string;
  conversation_id: string;
  session_id: string;
  tool_call_id: string;
  tool_name: string;
  canonical_path: string;
  operation: "read";
  status: ApprovalStatus;
  requested_at: string;
  decided_at: string | null;
}

export interface ChatEvent {
  event_id: string;
  conversation_id: string;
  session_id: string;
  type: ChatEventType;
  occurred_at: string;
  data: Record<string, unknown>;
}

export interface ChatToolActivity {
  conversation_id: string;
  session_id: string;
  tool_call_id: string;
  tool_name: string;
  status: ToolActivityStatus;
  arguments_summary: string | null;
  result_summary: string | null;
  started_at: string;
  finished_at: string | null;
  last_event_id: string;
}

export interface ActiveApproval {
  approval_id: string;
  tool_call_id: string;
  tool_name: string;
  canonical_path: string;
  operation: "read";
  scope: "external_exact_path";
}

export interface CreateConversationRequest {
  title: string;
  project_root: string;
  permission_mode: PermissionMode;
}

export interface PatchConversationRequest {
  title?: string;
  permission_mode?: PermissionMode;
}

export interface PostMessageRequest {
  query: string;
}

export interface PostMessageResponse {
  session_id: string;
}

export interface ApprovalDecisionRequest {
  decision: ApprovalDecision;
}

export interface PendingApprovalState {
  approval_id: string;
  conversation_id: string;
  session_id: string;
  tool_call_id: string;
  tool_name: string;
  canonical_path: string;
  operation: "read";
  scope: "external_exact_path";
  status: "pending";
  requested_at: string;
}

export interface ConversationStateResponse {
  latest_run: RunRecord | null;
  pending_approval: PendingApprovalState | null;
}
