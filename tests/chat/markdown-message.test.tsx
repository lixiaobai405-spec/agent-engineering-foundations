import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Component, type ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const codeToTokensMock = vi.hoisted(() => vi.fn());
vi.mock("shiki", () => ({ codeToTokens: codeToTokensMock }));

import { CodeBlock } from "../../web/chat/components/CodeBlock";
import {
  MarkdownErrorBoundary,
  MarkdownMessage,
} from "../../web/chat/components/MarkdownMessage";

describe("MarkdownMessage", () => {
  it("renders GFM semantics but never raw html, images, or unsafe URLs", () => {
    render(
      <MarkdownMessage
        content={'# Heading\n\n- item\n- [x] done\n\n> quote\n\n|a|b|\n|-|-|\n|1|2|\n\n`inline`\n\n<img src="x">\n\n<script>alert(1)</script>\n\n[bad](javascript:alert(1))\n\n[good](https://example.com/docs)'}
      />,
    );

    expect(screen.getByRole("heading", { name: "Heading" })).toBeInTheDocument();
    expect(screen.getByRole("list")).toBeInTheDocument();
    expect(screen.getByRole("checkbox")).toBeChecked();
    expect(screen.getByText("quote").closest("blockquote")).not.toBeNull();
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByText("inline").closest("code")).not.toBeNull();
    expect(document.querySelector("img")).toBeNull();
    expect(document.querySelector("script")).toBeNull();
    expect(screen.getByText("bad").closest("a")).toBeNull();
    expect(screen.getByRole("link", { name: "good" })).toHaveAttribute(
      "target",
      "_blank",
    );
    expect(screen.getByRole("link", { name: "good" })).toHaveAttribute(
      "rel",
      "noopener noreferrer",
    );
  });

  it("falls back to plain text when rendering throws", () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
    class Thrower extends Component {
      override render(): ReactNode {
        throw new Error("renderer failed");
      }
    }
    render(
      <MarkdownErrorBoundary fallback={<p>literal **message**</p>}>
        <Thrower />
      </MarkdownErrorBoundary>,
    );
    expect(screen.getByText("literal **message**")).toBeInTheDocument();
    consoleError.mockRestore();
  });
});

describe("CodeBlock", () => {
  beforeEach(() => {
    codeToTokensMock.mockReset();
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
    });
  });

  it("shows the language, renders token spans, and copies exact source", async () => {
    const user = userEvent.setup();
    const writeText = vi.spyOn(navigator.clipboard, "writeText");
    const source = "const answer = 42;\n";
    codeToTokensMock.mockResolvedValue({
      tokens: [[{ content: "const", color: "#ff0000" }, { content: " answer = 42;", color: "#ffffff" }]],
    });
    render(<CodeBlock code={source} language="typescript" />);

    expect(screen.getByText("typescript")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("const")).toHaveStyle({ color: "#ff0000" }));
    await user.click(screen.getByRole("button", { name: "Copy code" }));
    expect(writeText).toHaveBeenCalledWith(source);
    expect(screen.getByTestId("code-block")).toContainElement(screen.getByRole("code"));
  });

  it("falls back to unmodified code when highlighting rejects or language is unknown", async () => {
    codeToTokensMock.mockRejectedValue(new Error("unknown language"));
    render(<CodeBlock code={'<script>alert("x")</script>'} language="made-up" />);
    expect(await screen.findByText('<script>alert("x")</script>')).toBeInTheDocument();
    expect(document.querySelector("script")).toBeNull();
  });
});
