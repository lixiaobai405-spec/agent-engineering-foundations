import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ApprovalCard } from "../../web/chat/components/ApprovalCard";
import { ToolActivityGroup } from "../../web/chat/components/ToolActivityGroup";
import { parseApprovalFromEvent } from "../../web/chat/components/ApprovalCard";
import { ChatApiError } from "../../web/chat/state/api";
import type {
  ActiveApproval,
  ChatEvent,
  ChatToolActivity,
  RunRecord,
} from "../../web/chat/state/types";

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

describe("ToolActivityGroup", () => {
  const run: RunRecord = {
    session_id: "33333333-3333-4333-8333-333333333333",
    conversation_id: "11111111-1111-4111-8111-111111111111",
    user_message_id: "user-1",
    trace_path: "traces/session.jsonl",
    assistant_message_id: null,
    status: "completed",
    error_code: null,
    created_at: "2026-08-08T00:00:00Z",
    started_at: "2026-08-08T00:00:01Z",
    finished_at: "2026-08-08T00:00:03Z",
  };
  const activities: ChatToolActivity[] = [
    {
      conversation_id: run.conversation_id,
      session_id: run.session_id,
      tool_call_id: "call-1",
      tool_name: "read_file",
      status: "completed",
      arguments_summary: "README.md",
      result_summary: "10 lines",
      started_at: "2026-08-08T00:00:01Z",
      finished_at: "2026-08-08T00:00:02Z",
      last_event_id: "event-1",
    },
    {
      conversation_id: run.conversation_id,
      session_id: run.session_id,
      tool_call_id: "call-2",
      tool_name: "search_text",
      status: "failed",
      arguments_summary: "authenticate",
      result_summary: "not found",
      started_at: "2026-08-08T00:00:02Z",
      finished_at: "2026-08-08T00:00:03Z",
      last_event_id: "event-2",
    },
  ];

  it("collapses terminal runs by default and preserves a manual override", async () => {
    const user = userEvent.setup();
    const { rerender } = render(
      <ToolActivityGroup
        run={run}
        activities={activities}
        approval={null}
        approvalDisabled={false}
        onApprovalDecision={vi.fn()}
      />,
    );
    const toggle = screen.getByRole("button", { name: /2 tool activities/i });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("README.md")).not.toBeInTheDocument();

    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("README.md")).toBeInTheDocument();
    expect(screen.getByText("failed")).toBeInTheDocument();

    rerender(
      <ToolActivityGroup
        run={{ ...run, status: "running" }}
        activities={activities}
        approval={null}
        approvalDisabled={false}
        onApprovalDecision={vi.fn()}
      />,
    );
    expect(toggle).toHaveAttribute("aria-expanded", "true");
  });

  it("expands active runs and nests approval under the exact tool row", () => {
    const approval: ActiveApproval = {
      approval_id: "approval-1",
      tool_call_id: "call-2",
      tool_name: "search_text",
      canonical_path: "D:\\external\\note.txt",
      operation: "read",
      scope: "external_exact_path",
    };
    render(
      <ToolActivityGroup
        run={{ ...run, status: "waiting_approval" }}
        activities={activities}
        approval={approval}
        approvalDisabled={false}
        onApprovalDecision={vi.fn()}
      />,
    );
    const toggle = screen.getByRole("button", { name: /2 tool activities/i });
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    const rows = screen.getAllByRole("listitem");
    expect(within(rows[0]!).queryByRole("article", { name: "Approval request" })).toBeNull();
    expect(within(rows[1]!).getByRole("article", { name: "Approval request" })).toBeInTheDocument();
  });

  it("renders one fallback approval when no matching activity exists", () => {
    const approval: ActiveApproval = {
      approval_id: "approval-missing",
      tool_call_id: "missing-call",
      tool_name: "read_file",
      canonical_path: "D:\\external\\missing.txt",
      operation: "read",
      scope: "external_exact_path",
    };
    render(
      <ToolActivityGroup
        run={{ ...run, status: "waiting_approval" }}
        activities={activities}
        approval={approval}
        approvalDisabled={false}
        onApprovalDecision={vi.fn()}
      />,
    );
    expect(screen.getAllByRole("article", { name: "Approval request" })).toHaveLength(1);
  });
});
