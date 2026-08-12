import { useEffect, useState } from "react";
import type { BundledLanguage } from "shiki";

interface DisplayToken {
  content: string;
  color?: string;
}

type DisplayLines = DisplayToken[][];

const highlightCache = new Map<string, Promise<DisplayLines | null>>();

function highlightedLines(code: string, language: string): Promise<DisplayLines | null> {
  const key = `${language}\u0000${code}`;
  const cached = highlightCache.get(key);
  if (cached) {
    return cached;
  }
  const pending = import("shiki")
    .then(({ codeToTokens }) =>
      codeToTokens(code, {
        lang: (language || "text") as BundledLanguage,
        theme: "github-dark-default",
      }),
    )
    .then((result) => result.tokens as DisplayLines)
    .catch(() => null);
  highlightCache.set(key, pending);
  return pending;
}

export function CodeBlock({ code, language }: { code: string; language: string }) {
  const [tokens, setTokens] = useState<DisplayLines | null>(null);
  const [highlightFailed, setHighlightFailed] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let active = true;
    setTokens(null);
    setHighlightFailed(false);
    void highlightedLines(code, language).then((result) => {
      if (!active) {
        return;
      }
      if (result === null) {
        setHighlightFailed(true);
      } else {
        setTokens(result);
      }
    });
    return () => {
      active = false;
    };
  }, [code, language]);

  async function copyCode(): Promise<void> {
    await navigator.clipboard.writeText(code);
    setCopied(true);
  }

  return (
    <figure className="code-block" data-testid="code-block">
      <figcaption className="code-block__toolbar">
        <span>{language || "text"}</span>
        <button type="button" aria-label="Copy code" onClick={() => void copyCode()}>
          {copied ? "Copied" : "Copy"}
        </button>
      </figcaption>
      <pre className="code-block__pre">
        <code>
          {tokens && !highlightFailed
            ? tokens.map((line, lineIndex) => (
                <span className="code-line" key={lineIndex}>
                  {line.map((token, tokenIndex) => (
                    <span key={tokenIndex} style={{ color: token.color }}>
                      {token.content}
                    </span>
                  ))}
                  {"\n"}
                </span>
              ))
            : code}
        </code>
      </pre>
    </figure>
  );
}
