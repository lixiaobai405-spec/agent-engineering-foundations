import type { ChatMessage, ChatToolActivity, RunRecord } from "./types";

export interface ConversationTurn {
  run: RunRecord;
  userMessage: ChatMessage;
  assistantMessage: ChatMessage | null;
  activities: ChatToolActivity[];
}

function compareRuns(left: RunRecord, right: RunRecord): number {
  return (
    left.created_at.localeCompare(right.created_at) ||
    left.session_id.localeCompare(right.session_id)
  );
}

function compareActivities(
  left: ChatToolActivity,
  right: ChatToolActivity,
): number {
  return (
    left.started_at.localeCompare(right.started_at) ||
    left.tool_call_id.localeCompare(right.tool_call_id)
  );
}

export function buildConversationTurns(
  messages: ChatMessage[],
  runs: RunRecord[],
  activities: ChatToolActivity[],
): ConversationTurn[] {
  const messagesById = new Map(
    messages.map((message) => [message.message_id, message]),
  );
  return [...runs].sort(compareRuns).flatMap((run) => {
    const userMessage = messagesById.get(run.user_message_id);
    if (!userMessage) {
      return [];
    }
    return [
      {
        run,
        userMessage,
        assistantMessage: run.assistant_message_id
          ? messagesById.get(run.assistant_message_id) ?? null
          : null,
        activities: activities
          .filter(
            (activity) =>
              activity.conversation_id === run.conversation_id &&
              activity.session_id === run.session_id,
          )
          .sort(compareActivities),
      },
    ];
  });
}
