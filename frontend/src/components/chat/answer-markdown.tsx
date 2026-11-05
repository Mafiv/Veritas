"use client";

import { memo, type ReactNode } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Citation } from "@/lib/api-client";

const CITE_PREFIX = "#cite-";

/**
 * Turn `[n]` markers into markdown links (`[n](#cite-n)`) so the renderer can
 * swap them for citation chips — but never inside code spans/blocks, where
 * `[1]` is usually a list literal.
 */
export function linkCitations(markdown: string): string {
  return markdown
    .split(/(```[\s\S]*?(?:```|$)|`[^`\n]*`)/g)
    .map((part, i) =>
      i % 2 === 1 ? part : part.replace(/\[(\d{1,3})\](?!\()/g, `[$1](${CITE_PREFIX}$1)`),
    )
    .join("");
}

function AnswerMarkdownImpl({
  content,
  citations,
  onCite,
}: {
  content: string;
  citations: Citation[];
  onCite: (c: Citation) => void;
}) {
  const components: Components = {
    a({ href, children }) {
      if (href?.startsWith(CITE_PREFIX)) {
        const idx = Number(href.slice(CITE_PREFIX.length));
        const cite = citations.find((c) => c.citation_index === idx);
        return (
          <button
            type="button"
            className="citation-chip"
            title={cite ? `${cite.document_name}: ${cite.snippet}` : `Source ${idx}`}
            onClick={() => cite && onCite(cite)}
          >
            {idx}
          </button>
        );
      }
      return (
        <a href={href} target="_blank" rel="noopener noreferrer nofollow">
          {children as ReactNode}
        </a>
      );
    },
  };

  return (
    <div className="answer-md">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {linkCitations(content)}
      </ReactMarkdown>
    </div>
  );
}

export const AnswerMarkdown = memo(AnswerMarkdownImpl);
