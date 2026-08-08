import { useState } from "react";

import type { ChatEvent } from "../state/types";

function readString(data: Record<string, unknown>, key: string): string | null {
  const value = data[key];
  return typeof value === "string" && value.length > 0 ? value : null;
}

function activityLabel(type: ChatEvent["type"]): string {
  switch (type) {
    case "model.requested":
      return "Thinking";
    case "tool.requested":
      return "Tool requested";
    case "tool.completed":
      return "Tool completed";
    case "tool.failed":
      return "Tool failed";
    case "run.completed":
      return "Run completed";
    case "run.failed":
      return "Run failed";
    case "run.started":
      return "Run started";
    case "approval.requested":
      return "Approval requested";
    case "approval.resolved":
      return "Approval resolved";
    case "assistant.message.completed":
      return "Assistant message completed";
    default:
      return type;
  }
}

export function ActivityCard({ event }: { event: ChatEvent }) {
  const [expanded, setExpanded] = useState(false);
  const name = readString(event.data, "name");
  const status = readString(event.data, "status");
  const argumentsSummary = readString(event.data, "arguments_summary");
  const resultSummary = readString(event.data, "result_summary");
  const summary = argumentsSummary ?? resultSummary ?? status ?? name ?? "Activity update";

  return (
    <article className="activity-card" aria-label={`${activityLabel(event.type)} activity`}>
      <header className="activity-card__header">
        <h3 className="activity-card__title">{activityLabel(event.type)}</h3>
        {status ? <p className="activity-card__status">{status}</p> : null}
      </header>
      {name ? <p className="activity-card__name">{name}</p> : null}
      <p className="activity-card__summary">{summary}</p>
      <button
        type="button"
        className="activity-card__expand"
        aria-expanded={expanded}
        onClick={() => setExpanded((current) => !current)}
      >
        Expand activity details
      </button>
      {expanded ? (
        <div className="activity-card__expanded" data-testid="activity-details">
          {argumentsSummary ? (
            <p className="activity-card__arguments">{argumentsSummary}</p>
          ) : null}
          {resultSummary ? (
            <p className="activity-card__result">{resultSummary}</p>
          ) : null}
          {!argumentsSummary && !resultSummary && status ? (
            <p className="activity-card__status-detail">{status}</p>
          ) : null}
        </div>
      ) : null}
      {event.type === "run.completed" ? (
        <p>
          <a
            className="activity-card__trace-link"
            href={`/trace?session_id=${encodeURIComponent(event.session_id)}`}
          >
            Open trace
          </a>
        </p>
      ) : null}
    </article>
  );
}
