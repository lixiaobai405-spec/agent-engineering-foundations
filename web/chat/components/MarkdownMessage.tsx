import { Component, Fragment, type ErrorInfo, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { CodeBlock } from "./CodeBlock";

const BLOCKED_ELEMENTS = ["img", "iframe", "object", "embed", "video", "audio"];

function safeUrl(url: string): string | undefined {
  try {
    const parsed = new URL(url, window.location.origin);
    return parsed.protocol === "http:" || parsed.protocol === "https:"
      ? parsed.href
      : undefined;
  } catch {
    return undefined;
  }
}

interface BoundaryProps {
  fallback: ReactNode;
  children: ReactNode;
}

interface BoundaryState {
  failed: boolean;
}

export class MarkdownErrorBoundary extends Component<BoundaryProps, BoundaryState> {
  state: BoundaryState = { failed: false };

  static getDerivedStateFromError(): BoundaryState {
    return { failed: true };
  }

  override componentDidCatch(_error: Error, _info: ErrorInfo): void {
    // The visible plain-text fallback is intentional; message content is not logged.
  }

  override render(): ReactNode {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}

export function MarkdownMessage({ content }: { content: string }) {
  return (
    <MarkdownErrorBoundary fallback={<p className="message-plain">{content}</p>}>
      <div className="message-markdown">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          skipHtml
          disallowedElements={BLOCKED_ELEMENTS}
          urlTransform={(url) => safeUrl(url) ?? ""}
          components={{
            a: ({ children, href }) =>
              href ? (
                <a href={href} target="_blank" rel="noopener noreferrer">
                  {children}
                </a>
              ) : (
                <Fragment>{children}</Fragment>
              ),
            pre: ({ children }) => <Fragment>{children}</Fragment>,
            table: ({ children, ...props }) => (
              <div className="table-scroll">
                <table {...props}>{children}</table>
              </div>
            ),
            code: ({ children, className }) => {
              const source = String(children);
              const language = /language-([^\s]+)/.exec(className ?? "")?.[1];
              if (language || source.includes("\n")) {
                return <CodeBlock code={source} language={language ?? "text"} />;
              }
              return <code className={className}>{children}</code>;
            },
          }}
        >
          {content}
        </ReactMarkdown>
      </div>
    </MarkdownErrorBoundary>
  );
}
