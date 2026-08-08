import { useState } from "react";

import { ChatApiError } from "../state/api";
import type { ActiveApproval, ApprovalDecision, ChatEvent } from "../state/types";

function readRequiredString(data: Record<string, unknown>, key: string): string | null {
  const value = data[key];
  return typeof value === "string" && value.trim().length > 0 ? value : null;
}

export function parseApprovalFromEvent(event: ChatEvent): ActiveApproval | null {
  if (event.type !== "approval.requested") {
    return null;
  }
  const approvalId = readRequiredString(event.data, "approval_id");
  const toolCallId = readRequiredString(event.data, "tool_call_id");
  const toolName = readRequiredString(event.data, "tool_name");
  const canonicalPath = readRequiredString(event.data, "canonical_path");
  const operation = event.data.operation;
  const scope = event.data.scope;
  if (
    !approvalId ||
    !toolCallId ||
    !toolName ||
    !canonicalPath ||
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

export function ApprovalCard({
  approval,
  disabled,
  onDecision,
}: {
  approval: ActiveApproval;
  disabled: boolean;
  onDecision: (approvalId: string, decision: ApprovalDecision) => Promise<void>;
}) {
  const [submitting, setSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const { approval_id: approvalId, tool_name: toolName, canonical_path: canonicalPath } =
    approval;

  const locked = disabled || submitting;

  async function handleDecision(decision: ApprovalDecision): Promise<void> {
    if (locked) {
      return;
    }
    setSubmitting(true);
    setErrorMessage(null);
    try {
      await onDecision(approvalId, decision);
    } catch (error) {
      const message =
        error instanceof ChatApiError
          ? error.detail
          : error instanceof Error
            ? error.message
            : "Approval decision failed";
      setErrorMessage(message);
    } finally {
      setSubmitting(true);
    }
  }

  return (
    <article className="approval-card" aria-label="Approval request">
      <h3 className="approval-card__title">External read approval</h3>
      <p className="approval-card__tool">{toolName}</p>
      <p className="approval-card__path">{canonicalPath}</p>
      <p className="approval-card__meta">
        <span>read</span>
        <span>external exact path</span>
      </p>
      <p className="approval-card__scope">
        One-time approval for this session, tool call, exact path, and read only.
      </p>
      <div className="approval-card__actions">
        <button
          type="button"
          disabled={locked}
          onClick={() => void handleDecision("approve")}
        >
          Approve once
        </button>
        <button
          type="button"
          disabled={locked}
          onClick={() => void handleDecision("deny")}
        >
          Deny
        </button>
      </div>
      {errorMessage ? <p role="alert">{errorMessage}</p> : null}
    </article>
  );
}
