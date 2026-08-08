import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ChatComposer } from "../../web/chat/components/ChatComposer";

describe("ChatComposer", () => {
  it("starts at one row and keeps an accessible compact submit action", () => {
    render(<ChatComposer disabled={false} onSubmit={vi.fn()} />);

    expect(screen.getByRole("textbox", { name: "Message" })).toHaveAttribute("rows", "1");
    expect(screen.getByRole("button", { name: "Send message" })).toBeInTheDocument();
  });

  it("grows with content and caps at six lines with internal scrolling", () => {
    render(<ChatComposer disabled={false} onSubmit={vi.fn()} />);
    const textarea = screen.getByRole<HTMLTextAreaElement>("textbox", { name: "Message" });

    Object.defineProperty(textarea, "scrollHeight", { configurable: true, value: 96 });
    fireEvent.change(textarea, { target: { value: "line one\nline two\nline three" } });
    expect(textarea).toHaveStyle({ height: "96px", overflowY: "hidden" });

    Object.defineProperty(textarea, "scrollHeight", { configurable: true, value: 240 });
    fireEvent.change(textarea, { target: { value: "six or more lines of content" } });
    expect(textarea).toHaveStyle({ height: "144px", overflowY: "auto" });
  });

  it("resets its value and measured height after successful submit", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<ChatComposer disabled={false} onSubmit={onSubmit} />);
    const textarea = screen.getByRole<HTMLTextAreaElement>("textbox", { name: "Message" });
    Object.defineProperty(textarea, "scrollHeight", { configurable: true, value: 72 });
    fireEvent.change(textarea, { target: { value: "hello" } });

    await user.click(screen.getByRole("button", { name: "Send message" }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith("hello"));
    expect(textarea).toHaveValue("");
    expect(textarea.style.height).toBe("");
    expect(textarea.style.overflowY).toBe("");
  });
});
