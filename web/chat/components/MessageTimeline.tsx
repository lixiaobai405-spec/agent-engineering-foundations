import { ApprovalCard } from "./ApprovalCard";
import { MarkdownMessage } from "./MarkdownMessage";
import { ToolActivityGroup } from "./ToolActivityGroup";
import { buildConversationTurns } from "../state/turns";
import type {
  ActiveApproval,
  ApprovalDecision,
  ChatMessage,
  ChatToolActivity,
  RunRecord,
} from "../state/types";

function MessageBubble({ message }: { message: ChatMessage }) {
  return (
    <article
      className={`message-bubble message-bubble--${message.role}`}
      aria-label={`${message.role} message`}
    >
      <header>
        <strong>{message.role}</strong>
      </header>
      <MarkdownMessage content={message.content} />
    </article>
  );
}

export function MessageTimeline({
  messages,
  runs,
  activities,
  activeApproval,
  activeSessionId,
  isRunActive,
  onApprovalDecision,
  approvalDisabled,
}: {
  messages: ChatMessage[];
  runs: RunRecord[];
  activities: ChatToolActivity[];
  activeApproval: ActiveApproval | null;
  activeSessionId: string | null;
  isRunActive: boolean;
  onApprovalDecision: (approvalId: string, decision: ApprovalDecision) => Promise<void>;
  approvalDisabled: boolean;
}) {
  const turns = buildConversationTurns(messages, runs, activities);
  const claimedMessageIds = new Set<string>();
  for (const turn of turns) {
    claimedMessageIds.add(turn.userMessage.message_id);
    if (turn.assistantMessage) {
      claimedMessageIds.add(turn.assistantMessage.message_id);
    }
  }
  const unclaimedMessages = messages
    .filter((message) => !claimedMessageIds.has(message.message_id))
    .sort((left, right) => left.sequence - right.sequence);
  const approvalHasTurn =
    activeApproval !== null &&
    activeSessionId !== null &&
    turns.some((turn) => turn.run.session_id === activeSessionId);

  return (
    <section className="message-timeline" aria-label="Conversation timeline">
      <ol className="message-timeline__turns">
        {turns.map((turn) => {
          const approvalForTurn =
            activeApproval && turn.run.session_id === activeSessionId
              ? activeApproval
              : null;
          return (
            <li key={turn.run.session_id}>
              <article className="conversation-turn">
                <MessageBubble message={turn.userMessage} />
                {turn.activities.length > 0 || approvalForTurn ? (
                  <ToolActivityGroup
                    run={turn.run}
                    activities={turn.activities}
                    approval={approvalForTurn}
                    approvalDisabled={approvalDisabled}
                    onApprovalDecision={onApprovalDecision}
                  />
                ) : null}
                {turn.assistantMessage ? (
                  <MessageBubble message={turn.assistantMessage} />
                ) : null}
                <a
                  className="message-timeline__trace-link"
                  href={`/trace?conversation_id=${encodeURIComponent(turn.run.conversation_id)}&session_id=${encodeURIComponent(turn.run.session_id)}`}
                >
                  Open trace for this turn
                </a>
              </article>
            </li>
          );
        })}
        {unclaimedMessages.map((message) => (
          <li key={message.message_id}>
            <MessageBubble message={message} />
          </li>
        ))}
      </ol>
      {activeApproval && !approvalHasTurn ? (
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
