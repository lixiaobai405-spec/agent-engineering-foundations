import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ToolActivityGroup } from "../../web/chat/components/ToolActivityGroup";
import type { ChatToolActivity, RunRecord } from "../../web/chat/state/types";

const ARTIFACT_ID = "coa_AAAAAAAAAAAAAAAAAAAAAA";

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

const activity: ChatToolActivity = {
  conversation_id: run.conversation_id,
  session_id: run.session_id,
  tool_call_id: "call-run",
  tool_name: "run_command",
  status: "completed",
  arguments_summary: "python -m pytest tests",
  result_summary: `exit=1 failed=1 parser=complete artifact=${ARTIFACT_ID}`,
  started_at: "2026-08-08T00:00:01Z",
  finished_at: "2026-08-08T00:00:02Z",
  last_event_id: "event-run",
};

function mockPages(stdout: string[], stderr: string[]) {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    const isStdout = url.includes("stream=stdout");
    const isStderr = url.includes("stream=stderr");
    const lines = isStdout ? stdout : isStderr ? stderr : ["UNEXPECTED_STREAM"];
    return {
      ok: true,
      headers: { get: () => "application/json" },
      json: async () => ({
        artifact_id: ARTIFACT_ID,
        lines,
      }),
    };
  });
}

function collectedUrls(fetchMock: ReturnType<typeof vi.fn>): string[] {
  return fetchMock.mock.calls.map((call: unknown) => {
    const args = Array.isArray(call) ? (call as unknown[]) : [];
    return String(args[0] ?? "");
  });
}

async function expandFeedback(user: ReturnType<typeof userEvent.setup>): Promise<void> {
  await user.click(screen.getByRole("button", { name: /1 tool activity/i }));
  await user.click(screen.getByRole("button", { name: /Show sanitized output/i }));
}

describe("command feedback card", () => {
  it("keeps logs collapsed and does not prefetch raw output", async () => {
    const fetchMock = mockPages(["[REDACTED]"], []);
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(
      <ToolActivityGroup
        run={run}
        activities={[activity]}
        approval={null}
        approvalDisabled={false}
        onApprovalDecision={vi.fn()}
      />,
    );

    const groupToggle = screen.getByRole("button", { name: /1 tool activity/i });
    await user.click(groupToggle);
    expect(screen.getByText("run_command")).toBeInTheDocument();
    expect(screen.queryByText("fixture-secret-raw-output")).not.toBeInTheDocument();
    const show = screen.getByRole("button", { name: /Show sanitized output/i });
    expect(show).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();

    await user.click(show);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const urls = collectedUrls(fetchMock);
    expect(urls.some((url) => url.includes("/pages") && url.includes("stream=stdout"))).toBe(
      true,
    );
    expect(urls.some((url) => url.includes("/pages") && url.includes("stream=stderr"))).toBe(
      true,
    );
    expect(urls.some((url) => url.includes("/raw") || url.includes("download"))).toBe(false);
    vi.unstubAllGlobals();
  });

  it("stdout-only defaults to Stdout and shows No stderr on the other tab", async () => {
    const fetchMock = mockPages(["FAILED tests/test_boom.py::test_boom"], []);
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(
      <ToolActivityGroup
        run={run}
        activities={[activity]}
        approval={null}
        approvalDisabled={false}
        onApprovalDecision={vi.fn()}
      />,
    );

    await expandFeedback(user);
    await waitFor(() => {
      expect(screen.getByText("FAILED tests/test_boom.py::test_boom")).toBeInTheDocument();
    });
    const stdoutTab = screen.getByRole("tab", { name: "Stdout" });
    const stderrTab = screen.getByRole("tab", { name: "Stderr" });
    expect(stdoutTab).toHaveAttribute("aria-selected", "true");
    expect(screen.queryByText("No stdout")).not.toBeInTheDocument();
    expect(screen.queryByText("No stderr")).not.toBeInTheDocument();
    await user.click(stderrTab);
    expect(stderrTab).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("No stderr")).toBeInTheDocument();
    expect(screen.queryByText("FAILED tests/test_boom.py::test_boom")).not.toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("stderr-only defaults to Stderr and shows No stdout on the other tab", async () => {
    const fetchMock = mockPages([], ["Traceback (most recent call last)"]);
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(
      <ToolActivityGroup
        run={run}
        activities={[activity]}
        approval={null}
        approvalDisabled={false}
        onApprovalDecision={vi.fn()}
      />,
    );

    await expandFeedback(user);
    await waitFor(() => {
      expect(screen.getByText("Traceback (most recent call last)")).toBeInTheDocument();
    });
    expect(screen.getByRole("tab", { name: "Stderr" })).toHaveAttribute("aria-selected", "true");
    await user.click(screen.getByRole("tab", { name: "Stdout" }));
    expect(screen.getByText("No stdout")).toBeInTheDocument();
    expect(screen.queryByText("Traceback (most recent call last)")).not.toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("keeps both streams on separate tabs without concatenating them", async () => {
    const fetchMock = mockPages(["stdout-line-alpha"], ["stderr-line-beta"]);
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(
      <ToolActivityGroup
        run={run}
        activities={[activity]}
        approval={null}
        approvalDisabled={false}
        onApprovalDecision={vi.fn()}
      />,
    );

    await expandFeedback(user);
    await waitFor(() => {
      expect(screen.getByText("stdout-line-alpha")).toBeInTheDocument();
    });
    const panel = screen.getByRole("tabpanel");
    expect(within(panel).getByText("stdout-line-alpha")).toBeInTheDocument();
    expect(within(panel).queryByText("stderr-line-beta")).toBeNull();
    await user.click(screen.getByRole("tab", { name: "Stderr" }));
    expect(within(screen.getByRole("tabpanel")).getByText("stderr-line-beta")).toBeInTheDocument();
    expect(within(screen.getByRole("tabpanel")).queryByText("stdout-line-alpha")).toBeNull();
    expect(screen.queryByText(/stdout-line-alpha\nstderr-line-beta/)).toBeNull();
    vi.unstubAllGlobals();
  });

  it("shows empty-state copy on both tabs when both streams have no lines", async () => {
    const fetchMock = mockPages([], []);
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(
      <ToolActivityGroup
        run={run}
        activities={[activity]}
        approval={null}
        approvalDisabled={false}
        onApprovalDecision={vi.fn()}
      />,
    );

    await expandFeedback(user);
    await waitFor(() => {
      expect(screen.getByRole("tab", { name: "Stdout" })).toHaveAttribute(
        "aria-selected",
        "true",
      );
    });
    expect(screen.getByText("No stdout")).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "Stderr" }));
    expect(screen.getByText("No stderr")).toBeInTheDocument();
    vi.unstubAllGlobals();
  });
});
