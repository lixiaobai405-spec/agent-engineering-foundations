import { useState } from "react";

import { ChatApiError } from "../state/api";
import type { ActiveApproval, ApprovalDecision, ChatEvent } from "../state/types";
import { PatchPreviewCard } from "./PatchPreviewCard";

function readRequiredString(data: Record<string, unknown>, key: string): string | null {
  const value = data[key];
  return typeof value === "string" && value.trim().length > 0 ? value : null;
}

function approvalTitle(approval: ActiveApproval): string {
  if (approval.resource_kind === "sandbox_command") {
    return "Controlled command approval";
  }
  if (approval.resource_kind === "project_path" && approval.operation === "apply") {
    return "Controlled patch approval";
  }
  if (approval.resource_kind === "project_path" && approval.scope === "external_exact_path") {
    return "External read approval";
  }
  return "Approval request";
}

export function parseApprovalFromEvent(event: ChatEvent): ActiveApproval | null {
  if (event.type !== "approval.requested") {
    return null;
  }
  const approvalId = readRequiredString(event.data, "approval_id");
  const toolCallId = readRequiredString(event.data, "tool_call_id");
  const toolName = readRequiredString(event.data, "tool_name");
  const canonicalPath = readRequiredString(event.data, "canonical_path");
  const resourceKind = readRequiredString(event.data, "resource_kind");
  const operation = event.data.operation;
  const scope = event.data.scope;
  const decision = event.data.policy_decision;
  if (
    !approvalId ||
    !toolCallId ||
    !toolName ||
    !canonicalPath ||
    !resourceKind ||
    !["read", "apply", "run"].includes(String(operation)) ||
    !["external_exact_path", "project_internal"].includes(String(scope)) ||
    !(decision === "allow" || decision === "ask" || decision === "deny")
  ) {
    return null;
  }
  const parsed: ActiveApproval = {
    approval_id: approvalId,
    tool_call_id: toolCallId,
    tool_name: toolName,
    canonical_path: canonicalPath,
    operation: operation as ActiveApproval["operation"],
    scope: scope as ActiveApproval["scope"],
    policy_decision: decision,
    resource_kind: resourceKind,
  };
  if (event.data.one_time === true) {
    parsed.one_time = true;
  }
  if (event.data.backend === "docker") {
    parsed.backend = "docker";
  }
  return parsed;
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
  const isPatch = approval.resource_kind === "project_path" && approval.operation === "apply";
  const isCommand = approval.resource_kind === "sandbox_command";
  const isExternalRead =
    approval.resource_kind === "project_path" && approval.scope === "external_exact_path";

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
      <h3 className="approval-card__title">{approvalTitle(approval)}</h3>
      <p className="approval-card__tool">{toolName}</p>
      <p className="approval-card__path">{canonicalPath}</p>
      <p className="approval-card__meta">
        <span>{approval.operation}</span>
        {approval.resource_kind ? <span>{approval.resource_kind}</span> : null}
        <span>{approval.scope.replaceAll("_", " ")}</span>
      </p>
      <p className="approval-card__scope">
        {isPatch
          ? "One-time project patch authorization through the Docker sandbox."
          : isCommand
            ? "One-time in-project command through the Docker sandbox, not full computer access."
            : isExternalRead
              ? "One-time approval for this session, tool call, exact path, and read only."
              : "One-time approval for this session and tool call."}
      </p>
      <p>Policy: {approval.policy_decision ?? "ask"}</p>
      <p>Resource: {approval.resource_kind ?? "unknown"}</p>
      {isPatch ? <p>Project capability, not full computer access.</p> : null}
      {approval.patch ? <PatchPreviewCard preview={approval.patch} /> : null}
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
