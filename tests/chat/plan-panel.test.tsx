import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PlanPanel } from "../../web/chat/components/PlanPanel";
import { initialState, reduceChatState } from "../../web/chat/state/reducer";

const PLAN = {
  plan_id: "plan-1",
  version: 2,
  goal: "inspect the fixture project",
  replan_count: 0,
  max_replans: 2,
  steps: [
    {
      step_id: "read",
      status: "in_progress",
      description: "list project files",
    },
    {
      step_id: "summarize",
      status: "pending",
      description: "write a summary",
    },
  ],
};

describe("PlanPanel", () => {
  it("shows the plan goal and step statuses", () => {
    render(<PlanPanel plan={PLAN} />);
    const region = screen.getByRole("region", { name: "Execution plan" });
    expect(region).toHaveTextContent("inspect the fixture project");
    expect(region).toHaveTextContent("in_progress");
    expect(region).toHaveTextContent("list project files");
    expect(region).toHaveTextContent("pending");
    expect(region).toHaveTextContent("write a summary");
    expect(region).not.toHaveTextContent("evidence");
  });
});


describe("plan state recovery", () => {
  it("restores a plan from GET conversation state", () => {
    const conversationId = "11111111-1111-4111-8111-111111111111";
    const next = reduceChatState(initialState, {
      type: "conversation.state.loaded",
      conversationId,
      state: {
        latest_run: null,
        pending_approval: null,
        plan: PLAN,
      },
    });
    expect(next.planByConversation[conversationId]?.goal).toBe(
      "inspect the fixture project",
    );
    expect(next.planByConversation[conversationId]?.steps[0]?.status).toBe(
      "in_progress",
    );
  });

  it("updates the plan from a plan.updated event", () => {
    const conversationId = "11111111-1111-4111-8111-111111111111";
    const seeded = reduceChatState(initialState, {
      type: "conversation.state.loaded",
      conversationId,
      state: {
        latest_run: null,
        pending_approval: null,
        plan: PLAN,
      },
    });
    const next = reduceChatState(seeded, {
      type: "event.received",
      event: {
        event_id: "55555555-5555-4555-8555-555555555555",
        conversation_id: conversationId,
        session_id: "33333333-3333-4333-8333-333333333333",
        type: "plan.updated",
        occurred_at: "2026-08-02T00:00:02Z",
        data: {
          plan_id: "plan-1",
          version: 3,
          goal: "inspect the fixture project",
          replan_count: 1,
          max_replans: 2,
          steps: [
            {
              step_id: "read",
              status: "completed",
              description: "list project files",
            },
          ],
        },
      },
    });
    expect(next.planByConversation[conversationId]?.version).toBe(3);
    expect(next.planByConversation[conversationId]?.steps[0]?.status).toBe(
      "completed",
    );
  });
});
