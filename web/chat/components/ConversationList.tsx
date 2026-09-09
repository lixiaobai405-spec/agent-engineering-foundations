import { useState } from "react";

import type {
  Conversation,
  CreateConversationRequest,
  PermissionProfile,
} from "../state/types";
import { PermissionProfileSelect } from "./PermissionProfileSelect";

export function ConversationList({
  conversations,
  activeId,
  onSelect,
  onCreate,
}: {
  conversations: Conversation[];
  activeId: string | null;
  onSelect: (conversationId: string) => void;
  onCreate: (request: CreateConversationRequest) => Promise<void>;
}) {
  const [showForm, setShowForm] = useState(false);
  const [title, setTitle] = useState("");
  const [projectRoot, setProjectRoot] = useState("");
  const [permissionProfile, setPermissionProfile] =
    useState<PermissionProfile>("PROJECT_READ_ONLY");
  const [submitting, setSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  async function handleCreate(event: React.FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const trimmedTitle = title.trim();
    const trimmedRoot = projectRoot.trim();
    if (!trimmedTitle || !trimmedRoot) {
      return;
    }
    setSubmitting(true);
    setErrorMessage(null);
    try {
      await onCreate({
        title: trimmedTitle,
        project_root: trimmedRoot,
        permission_profile: permissionProfile,
      });
      setTitle("");
      setProjectRoot("");
      setPermissionProfile("PROJECT_READ_ONLY");
      setShowForm(false);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Failed to create conversation");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <nav className="conversation-list" aria-label="Conversations">
      <button type="button" onClick={() => setShowForm((current) => !current)}>
        New conversation
      </button>
      {showForm ? (
        <form className="conversation-list__form" onSubmit={(event) => void handleCreate(event)}>
          <label htmlFor="conversation-title">Title</label>
          <input
            id="conversation-title"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
          />
          <label htmlFor="conversation-project-root">Project root</label>
          <input
            id="conversation-project-root"
            value={projectRoot}
            onChange={(event) => setProjectRoot(event.target.value)}
          />
          <PermissionProfileSelect
            value={permissionProfile}
            disabled={submitting}
            onChange={setPermissionProfile}
          />
          <button type="submit" disabled={submitting}>
            Create conversation
          </button>
          {errorMessage ? <p role="alert">{errorMessage}</p> : null}
        </form>
      ) : null}
      <ul className="conversation-list__items">
        {conversations.map((conversation) => (
          <li key={conversation.conversation_id}>
            <button
              type="button"
              className={
                conversation.conversation_id === activeId
                  ? "conversation-list__item conversation-list__item--active"
                  : "conversation-list__item"
              }
              aria-current={conversation.conversation_id === activeId ? "page" : undefined}
              onClick={() => onSelect(conversation.conversation_id)}
            >
              <span className="conversation-list__title">{conversation.title}</span>
              <span className="conversation-list__root">{conversation.project_root}</span>
              <span className="conversation-list__mode">
                {conversation.permission_profile}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </nav>
  );
}
