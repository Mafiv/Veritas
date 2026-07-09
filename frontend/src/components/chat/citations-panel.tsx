"use client";

import { FileText } from "lucide-react";
import type { Citation } from "@/lib/api-client";
import { cn } from "@/lib/utils";

export function CitationsPanel({
  citations,
  activeId,
  onSelect,
  className,
}: {
  citations: Citation[];
  activeId?: string | null;
  onSelect?: (c: Citation) => void;
  className?: string;
}) {
  if (!citations.length) {
    return (
      <div className={cn("flex h-full flex-col p-5", className)}>
        <h2 className="font-display text-sm font-semibold uppercase tracking-wider text-slate">
          Sources
        </h2>
        <p className="mt-6 text-sm text-muted-foreground">
          Citations appear here as Veritas streams grounded answers.
        </p>
      </div>
    );
  }

  return (
    <div className={cn("flex h-full flex-col", className)}>
      <div className="border-b border-line px-5 py-4">
        <h2 className="font-display text-sm font-semibold uppercase tracking-wider text-slate">
          Sources · {citations.length}
        </h2>
      </div>
      <ul className="flex-1 space-y-3 overflow-y-auto p-4">
        {citations.map((c) => (
          <li key={c.chunk_id}>
            <button
              type="button"
              onClick={() => onSelect?.(c)}
              className={cn(
                "w-full rounded-xl border p-3 text-left transition-colors",
                activeId === c.chunk_id
                  ? "border-signal bg-signal-soft/50"
                  : "border-line bg-white hover:border-signal/50",
              )}
            >
              <div className="mb-1.5 flex items-center gap-2">
                <span className="citation-chip !m-0">{c.citation_index}</span>
                <span className="truncate text-xs font-semibold text-ink">
                  {c.document_name}
                </span>
              </div>
              {c.heading && (
                <p className="mb-1 truncate text-xs text-signal-deep">{c.heading}</p>
              )}
              <p className="line-clamp-4 text-xs leading-relaxed text-slate">
                {c.snippet}
              </p>
              <div className="mt-2 flex items-center gap-2 text-[10px] uppercase tracking-wide text-muted-foreground">
                <FileText className="h-3 w-3" />
                {c.page_number ? `Page ${c.page_number}` : "Excerpt"}
                <span>·</span>
                <span>score {c.score.toFixed(2)}</span>
              </div>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
