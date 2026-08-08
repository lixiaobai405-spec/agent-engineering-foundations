import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ActivityCard } from "../../web/chat/components/ActivityCard";
import { ApprovalCard } from "../../web/chat/components/ApprovalCard";
import { parseApprovalFromEvent } from "../../web/chat/components/ApprovalCard";
import { ChatApiError } from "../../web/chat/state/api";
import type { ActiveApproval, ChatEvent } from "../../web/chat/state/types";

function makeEvent(
  overrides: Partial<ChatEvent> & Pick<ChatEvent, "type" | "conversation_id">,
): ChatEvent {
  return {
    event_id: "55555555-5555-4555-8555-555555555555",
    session_id: "33333333-3333-4333-8333-333333333333",
    occurred_at: "2026-08-02T00:00:01Z",
    data: {},
    ...overrides,
  };
}

describe("ActivityCard", () => {
  it("shows only safe projected summary fields with expand control", async () => {
    const user = userEvent.setup();
    const event = makeEvent({
      conversation_id: "11111111-1111-4111-8111-111111111111",
      type: "tool.requested",
      data: {
        name: "read_file",
        status: "started",
        arguments_summary: "path=README.md",
        secret: "must-not-render",
      },
    });

    render(<ActivityCard event={event} />);

    expect(screen.getByText("Tool requested")).toBeInTheDocument();
    expect(screen.getByText("read_file")).toBeInTheDocument();
    expect(screen.getByText("started")).toBeInTheDocument();
    expect(screen.getByText("path=README.md")).toBeInTheDocument();
    expect(screen.queryByText("must-not-render")).not.toBeInTheDocument();
    expect(screen.queryByText(/secret/i)).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Expand activity details" }));
    const details = screen.getByTestId("activity-details");
    expect(within(details).getByText("path=README.md")).toBeInTheDocument();
    expect(within(details).queryByText("must-not-render")).not.toBeInTheDocument();
  });

  it("renders a trace link for run.completed using the event session_id", () => {
    const sessionId = "22222222-2222-4222-8222-222222222222";
    render(
      <ActivityCard
        event={makeEvent({
          conversation_id: "11111111-1111-4111-8111-111111111111",
          session_id: sessionId,
          type: "run.completed",
          data: { status: "completed" },
        })}
      />,
    );

    const link = screen.getByRole("link", { name: "Open trace" });
    expect(link).toHaveAttribute(
      "href",
      `/trace?session_id=${encodeURIComponent(sessionId)}`,
    );
  });
});

describe("ApprovalCard", () => {
  const approvalView: ActiveApproval = {
    approval_id: "44444444-4444-4444-8444-444444444444",
    tool_call_id: "call-1",
    tool_name: "read_file",
    canonical_path: "/tmp/external.txt",
    operation: "read",
    scope: "external_exact_path",
  };

  const approvalEvent = makeEvent({
    conversation_id: "11111111-1111-4111-8111-111111111111",
    type: "approval.requested",
    data: {
      approval_id: approvalView.approval_id,
      tool_call_id: approvalView.tool_call_id,
      tool_name: approvalView.tool_name,
      canonical_path: approvalView.canonical_path,
      operation: approvalView.operation,
      scope: approvalView.scope,
    },
  });

  it("parses live SSE approval.requested into the approval view model", () => {
    expect(parseApprovalFromEvent(approvalEvent)).toEqual(approvalView);
  });

  it("shows one-time external read approval details and action buttons", () => {
    render(
      <ApprovalCard
        approval={approvalView}
        disabled={false}
        onDecision={vi.fn()}
      />,
    );

    const card = screen.getByRole("article", { name: "Approval request" });
    expect(within(card).getByText("read_file")).toBeInTheDocument();
    expect(within(card).getByText("/tmp/external.txt")).toBeInTheDocument();
    expect(within(card).getByText("read")).toBeInTheDocument();
    expect(within(card).getByText(/external exact path/i)).toBeInTheDocument();
    expect(within(card).getByText(/one-time/i)).toBeInTheDocument();
    expect(within(card).getByRole("button", { name: "Approve once" })).toBeEnabled();
    expect(within(card).getByRole("button", { name: "Deny" })).toBeEnabled();
  });

  it("disables both buttons immediately after a decision starts", async () => {
    const user = userEvent.setup();
    let resolveDecision: (() => void) | undefined;
    const onDecision = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          resolveDecision = resolve;
        }),
    );

    render(
      <ApprovalCard
        approval={approvalView}
        disabled={false}
        onDecision={onDecision}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Approve once" }));
    expect(screen.getByRole("button", { name: "Approve once" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Deny" })).toBeDisabled();
    resolveDecision?.();
    await Promise.resolve();
  });

  it("shows an accessible alert on server conflict without re-enabling buttons", async () => {
    const user = userEvent.setup();
    const onDecision = vi.fn().mockRejectedValue(new ChatApiError(409, "conflict"));

    render(
      <ApprovalCard
        approval={approvalView}
        disabled={false}
        onDecision={onDecision}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Deny" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("conflict");
    expect(screen.getByRole("button", { name: "Approve once" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Deny" })).toBeDisabled();
  });
});
