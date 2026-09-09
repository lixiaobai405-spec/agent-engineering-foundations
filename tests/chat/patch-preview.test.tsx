import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ApprovalCard } from "../../web/chat/components/ApprovalCard";

describe("controlled patch authorization", () => {
  it("shows safe policy, resource, operation, tool, one-time, and sandbox facts", () => {
    render(
      <ApprovalCard
        approval={{
          approval_id: "approval-2",
          tool_call_id: "call-2",
          tool_name: "apply_patch",
          canonical_path: "patch:0123456789ab",
          operation: "apply",
          scope: "project_internal",
          policy_decision: "ask",
          resource_kind: "project_path",
          one_time: true,
          backend: "docker",
          patch: {
            patch_id: "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
            files: [
              {
                path: "README.md",
                operation: "modify",
                hunk_count: 1,
                baseline_status: "matched",
                summary: "+1 -1",
              },
            ],
          },
        }}
        disabled={false}
        onDecision={vi.fn()}
      />,
    );

    expect(screen.getByText(/Policy: ask/i)).toBeTruthy();
    expect(screen.getAllByText(/project_path/i).length).toBeGreaterThan(0);
    expect(screen.getByText("apply", { exact: true })).toBeTruthy();
    expect(screen.getByText("apply_patch", { exact: true })).toBeTruthy();
    expect(screen.getByText(/one-time/i)).toBeTruthy();
    expect(screen.getByText(/Docker sandbox/i)).toBeTruthy();
    expect(screen.getByRole("region", { name: /Patch preview/i })).toBeTruthy();
    expect(screen.getByText(/README\.md/)).toBeTruthy();
    expect(screen.getByText(/\+1 -1/)).toBeTruthy();
  });
});
