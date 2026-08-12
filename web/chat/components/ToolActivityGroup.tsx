import { useEffect, useState } from "react";

import type {
  ActiveApproval,
  ApprovalDecision,
  ChatToolActivity,
  RunRecord,
} from "../state/types";
import { ApprovalCard } from "./ApprovalCard";

function isActiveStatus(status: RunRecord["status"]): boolean {
  return status === "queued" || status === "running" || status === "waiting_approval";
}

function timing(activity: ChatToolActivity): string {
  if (!activity.finished_at) {
    return `Started ${activity.started_at}`;
  }
  const elapsed =
    new Date(activity.finished_at).getTime() - new Date(activity.started_at).getTime();
  return Number.isFinite(elapsed) && elapsed >= 0
    ? `${elapsed} ms`
    : `${activity.started_at} – ${activity.finished_at}`;
}

export function ToolActivityGroup({
  run,
  activities,
  approval,
  approvalDisabled,
  onApprovalDecision,
}: {
  run: RunRecord;
  activities: ChatToolActivity[];
  approval: ActiveApproval | null;
  approvalDisabled: boolean;
  onApprovalDecision: (
    approvalId: string,
    decision: ApprovalDecision,
  ) => Promise<void>;
}) {
  const [manualExpanded, setManualExpanded] = useState<boolean | null>(null);
  useEffect(() => {
    setManualExpanded(null);
  }, [run.session_id]);

  const expanded = manualExpanded ?? isActiveStatus(run.status);
  const matchingApproval = approval
    ? activities.some((activity) => activity.tool_call_id === approval.tool_call_id)
    : false;
  const label = `${activities.length} tool ${activities.length === 1 ? "activity" : "activities"}`;

  return (
    <section className="tool-activity-group" aria-label={`Tools for run ${run.session_id}`}>
      <button
        type="button"
        className="tool-activity-group__toggle"
        aria-expanded={expanded}
        onClick={() => setManualExpanded(!expanded)}
      >
        <span>{label}</span>
        <span className="tool-activity-group__run-status">Run {run.status}</span>
      </button>
      {expanded ? (
        <div className="tool-activity-group__content">
          <ol className="tool-activity-group__items">
            {activities.map((activity) => (
              <li key={`${activity.session_id}:${activity.tool_call_id}`}>
                <article
                  className="tool-activity-group__item"
                  aria-label={`${activity.tool_name} ${activity.status}`}
                >
                  <header>
                    <strong>{activity.tool_name}</strong>
                    <span>{activity.status}</span>
                  </header>
                  {activity.arguments_summary ? <p>{activity.arguments_summary}</p> : null}
                  {activity.result_summary ? <p>{activity.result_summary}</p> : null}
                  <time>{timing(activity)}</time>
                </article>
                {approval?.tool_call_id === activity.tool_call_id ? (
                  <ApprovalCard
                    approval={approval}
                    disabled={approvalDisabled}
                    onDecision={onApprovalDecision}
                  />
                ) : null}
              </li>
            ))}
          </ol>
          {approval && !matchingApproval ? (
            <div className="tool-activity-group__approval-fallback">
              <ApprovalCard
                approval={approval}
                disabled={approvalDisabled}
                onDecision={onApprovalDecision}
              />
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
