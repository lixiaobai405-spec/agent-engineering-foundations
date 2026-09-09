import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { PermissionProfileSelect } from "../../web/chat/components/PermissionProfileSelect";
import { ConversationList } from "../../web/chat/components/ConversationList";

describe("permission profile policy facts", () => {
  it("shows the project-only boundary for full access", () => {
    render(
      <PermissionProfileSelect
        value="PROJECT_FULL_ACCESS"
        disabled={false}
        onChange={vi.fn()}
      />,
    );

    expect(screen.getByLabelText(/Permission profile/i)).toBeTruthy();
    expect(screen.getByText(/not full computer access/i)).toBeTruthy();
    expect(screen.queryByText(/HOST_FULL_ACCESS/i)).toBeNull();
  });

  it("creates conversations from one authoritative profile selector", async () => {
    const user = userEvent.setup();
    const onCreate = vi.fn().mockResolvedValue(undefined);
    render(
      <ConversationList
        conversations={[]}
        activeId={null}
        onSelect={vi.fn()}
        onCreate={onCreate}
      />,
    );

    await user.click(screen.getByRole("button", { name: "New conversation" }));
    expect(screen.queryByLabelText("Permission mode")).toBeNull();
    await user.type(screen.getByLabelText("Title"), "Controlled coding");
    await user.type(screen.getByLabelText("Project root"), "D:\\project");
    await user.selectOptions(screen.getByLabelText("Permission profile"), "RISK_BASED");
    await user.click(screen.getByRole("button", { name: "Create conversation" }));

    expect(onCreate).toHaveBeenCalledWith({
      title: "Controlled coding",
      project_root: "D:\\project",
      permission_profile: "RISK_BASED",
    });
  });
});
