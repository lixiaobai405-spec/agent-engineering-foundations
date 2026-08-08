import { ApprovalCard } from "./ApprovalCard";
import type {
  ActiveApproval,
  ApprovalDecision,
  ChatMessage,
  RunRecord,
} from "../state/types";

export function MessageTimeline({
  messages,
  runs,
  activeApproval,
  isRunActive,
  onApprovalDecision,
  approvalDisabled,
}: {
  messages: ChatMessage[];
  runs: RunRecord[];
  activeApproval: ActiveApproval | null;
  isRunActive: boolean;
  onApprovalDecision: (approvalId: string, decision: ApprovalDecision) => Promise<void>;
  approvalDisabled: boolean;
}) {
  const sessionByAssistantMessage = new Map<string, string>();
  for (const run of runs) {
    if (run.assistant_message_id) {
      sessionByAssistantMessage.set(run.assistant_message_id, run.session_id);
    }
  }
  const conversationId = messages[0]?.conversation_id ?? runs[0]?.conversation_id;

  return (
    <section className="message-timeline" aria-label="Conversation timeline">
      <ol className="message-timeline__messages">
        {messages.map((message) => (
          <li key={message.message_id}>
            <article
              className="message-timeline__message"
              aria-label={`${message.role} message`}
            >
              <header>
                <strong>{message.role}</strong>
              </header>
              <p className="message-timeline__content">{message.content}</p>
              {message.role === "assistant" &&
              conversationId &&
              sessionByAssistantMessage.has(message.message_id) ? (
                <a
                  className="message-timeline__trace-link"
                  href={`/trace?conversation_id=${encodeURIComponent(conversationId)}&session_id=${encodeURIComponent(sessionByAssistantMessage.get(message.message_id)!)}`}
                >
                  Open trace for this turn
                </a>
              ) : null}
            </article>
          </li>
        ))}
      </ol>
      {activeApproval ? (
        <ApprovalCard
          approval={activeApproval}
          disabled={approvalDisabled}
          onDecision={onApprovalDecision}
        />
      ) : null}
      {isRunActive && !activeApproval ? (
        <p className="message-timeline__working" role="status" aria-live="polite">
          Agent is working…
        </p>
      ) : null}
      {messages.length === 0 && !isRunActive && !activeApproval ? (
        <p className="message-timeline__empty" role="status">
          No messages yet.
        </p>
      ) : null}
    </section>
  );
}
