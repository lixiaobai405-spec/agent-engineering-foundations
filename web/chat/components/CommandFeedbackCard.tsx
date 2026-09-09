import { useState } from "react";

import {
  createCommandOutputDownloadTicket,
  fetchCommandOutputPage,
} from "../state/api";
import type { ChatToolActivity } from "../state/types";

const ARTIFACT_RE = /artifact=(coa_[A-Za-z0-9_-]{22})/;

export function parseArtifactId(summary: string | null): string | null {
  if (!summary) {
    return null;
  }
  const match = ARTIFACT_RE.exec(summary);
  return match?.[1] ?? null;
}

type StreamTab = "stdout" | "stderr";

function defaultSelectedTab(stdoutLines: string[], stderrLines: string[]): StreamTab {
  if (stdoutLines.length > 0) {
    return "stdout";
  }
  if (stderrLines.length > 0) {
    return "stderr";
  }
  return "stdout";
}

export function CommandFeedbackCard({
  conversationId,
  sessionId,
  activity,
}: {
  conversationId: string;
  sessionId: string;
  activity: ChatToolActivity;
}) {
  const artifactId = parseArtifactId(activity.result_summary);
  const [open, setOpen] = useState(false);
  const [stdoutLines, setStdoutLines] = useState<string[] | null>(null);
  const [stderrLines, setStderrLines] = useState<string[] | null>(null);
  const [selected, setSelected] = useState<StreamTab>("stdout");
  const [error, setError] = useState<string | null>(null);

  if (activity.tool_name !== "run_command" || artifactId === null) {
    return null;
  }

  const resolvedId = artifactId;

  async function loadPage(): Promise<void> {
    setError(null);
    try {
      const stdoutPage = await fetchCommandOutputPage(conversationId, sessionId, resolvedId, {
        stream: "stdout",
        startLine: 1,
        lineCount: 50,
      });
      const stderrPage = await fetchCommandOutputPage(conversationId, sessionId, resolvedId, {
        stream: "stderr",
        startLine: 1,
        lineCount: 50,
      });
      setStdoutLines(stdoutPage.lines);
      setStderrLines(stderrPage.lines);
      setSelected(defaultSelectedTab(stdoutPage.lines, stderrPage.lines));
      setOpen(true);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to load sanitized output");
    }
  }

  async function downloadRaw(): Promise<void> {
    const ticket = await createCommandOutputDownloadTicket(
      conversationId,
      sessionId,
      resolvedId,
    );
    window.location.assign(
      `/api/chat/conversations/${encodeURIComponent(conversationId)}/runs/${encodeURIComponent(sessionId)}/command-artifacts/${encodeURIComponent(resolvedId)}/raw?ticket=${encodeURIComponent(ticket.ticket)}`,
    );
  }

  const activeLines = selected === "stdout" ? stdoutLines : stderrLines;
  const emptyCopy = selected === "stdout" ? "No stdout" : "No stderr";

  return (
    <section className="command-feedback-card" aria-label="Command feedback">
      <p className="command-feedback-card__summary">{activity.result_summary}</p>
      <div className="command-feedback-card__actions">
        <button type="button" onClick={() => void loadPage()}>
          Show sanitized output
        </button>
        <button type="button" onClick={() => void downloadRaw()}>
          Download raw output
        </button>
      </div>
      {error ? <p role="alert">{error}</p> : null}
      {open && stdoutLines !== null && stderrLines !== null ? (
        <div className="command-feedback-card__streams">
          <div className="command-feedback-card__tabs" role="tablist" aria-label="Command output streams">
            <button
              type="button"
              role="tab"
              aria-selected={selected === "stdout"}
              onClick={() => setSelected("stdout")}
            >
              Stdout
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={selected === "stderr"}
              onClick={() => setSelected("stderr")}
            >
              Stderr
            </button>
          </div>
          <pre className="command-feedback-card__page" role="tabpanel">
            {activeLines !== null && activeLines.length > 0 ? activeLines.join("\n") : emptyCopy}
          </pre>
        </div>
      ) : null}
    </section>
  );
}
