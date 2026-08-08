import { useRef, useState } from "react";

const MAX_COMPOSER_HEIGHT = 144;

export function ChatComposer({
  disabled,
  disabledReason,
  onSubmit,
}: {
  disabled: boolean;
  disabledReason?: string | null;
  onSubmit: (query: string) => Promise<void>;
}) {
  const [value, setValue] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  function resizeTextarea(textarea: HTMLTextAreaElement): void {
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, MAX_COMPOSER_HEIGHT)}px`;
    textarea.style.overflowY =
      textarea.scrollHeight > MAX_COMPOSER_HEIGHT ? "auto" : "hidden";
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const query = value.trim();
    if (!query || disabled || submitting) {
      return;
    }
    setSubmitting(true);
    try {
      await onSubmit(query);
      setValue("");
      if (textareaRef.current) {
        textareaRef.current.style.height = "";
        textareaRef.current.style.overflowY = "";
      }
    } finally {
      setSubmitting(false);
    }
  }

  const isDisabled = disabled || submitting;

  return (
    <form className="chat-composer" onSubmit={(event) => void handleSubmit(event)}>
      <label className="visually-hidden" htmlFor="chat-message-input">
        Message
      </label>
      <div className="chat-composer__input-row">
        <textarea
          ref={textareaRef}
          id="chat-message-input"
          name="message"
          value={value}
          disabled={isDisabled}
          onChange={(event) => {
            setValue(event.target.value);
            resizeTextarea(event.currentTarget);
          }}
          placeholder="Message Agent…"
          rows={1}
        />
        <button type="submit" aria-label="Send message" disabled={isDisabled}>
          Send
        </button>
      </div>
      {disabledReason ? (
        <p className="chat-composer__status" role="status">
          {disabledReason}
        </p>
      ) : null}
    </form>
  );
}
