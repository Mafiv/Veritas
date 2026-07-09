"use client";

import { ChevronRight, FileText, Info, X } from "lucide-react";
import type { Citation } from "@/lib/api-client";
import { cn } from "@/lib/utils";

function confidence(score: number): number {
  // Map fusion/rerank scores into a readable confidence %
  const pct = Math.round(Math.min(0.99, Math.max(0.42, score)) * 100);
  return pct;
}

export function CitationsPanel({
  citations,
  activeId,
  onSelect,
  onClose,
  className,
}: {
  citations: Citation[];
  activeId?: string | null;
  onSelect?: (c: Citation) => void;
  onClose?: () => void;
  className?: string;
}) {
  return (
    <div className={cn("flex h-full flex-col bg-white animate-fade-in", className)}>
      <div className="flex items-center justify-between border-b border-line px-4 py-3.5">
        <div className="flex items-center gap-2">
          <h2 className="font-display text-sm font-semibold text-ink">Sources</h2>
          <span className="rounded-full bg-signal-soft px-2 py-0.5 text-[10px] font-semibold text-signal-deep">
            {citations.length}
          </span>
          <Info className="h-3.5 w-3.5 text-slate" aria-hidden />
        </div>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate hover:bg-mist hover:text-ink"
            aria-label="Collapse sources"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>

      <ul className="flex-1 space-y-2.5 overflow-y-auto p-3">
        {citations.map((c, i) => {
          const conf = confidence(c.score);
          return (
            <li key={c.chunk_id} className="source-card" style={{ animationDelay: `${i * 40}ms` }}>
              <button
                type="button"
                onClick={() => onSelect?.(c)}
                className={cn(
                  "w-full rounded-2xl border p-3.5 text-left transition-colors",
                  activeId === c.chunk_id
                    ? "border-signal bg-signal-soft/40"
                    : "border-line bg-white hover:border-signal/40 hover:bg-mist/30",
                )}
              >
                <div className="mb-2 flex items-start justify-between gap-2">
                  <div className="flex min-w-0 items-center gap-2">
                    <span className="citation-chip !m-0">{c.citation_index}</span>
                    <span className="truncate text-sm font-semibold text-ink">
                      {c.document_name}
                    </span>
                  </div>
                  <ChevronRight className="mt-0.5 h-4 w-4 shrink-0 text-slate" />
                </div>

                {c.heading && (
                  <p className="mb-1.5 truncate text-xs font-medium text-signal-deep">
                    {c.heading}
                  </p>
                )}

                <p className="line-clamp-3 text-xs leading-relaxed text-slate">
                  {c.snippet}
                </p>

                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <span className="inline-flex items-center gap-1 rounded-md bg-mist px-2 py-1 text-[10px] font-medium text-ink-soft">
                    <FileText className="h-3 w-3" />
                    {c.page_number ? `Page ${c.page_number}` : "Excerpt"}
                  </span>
                  <span
                    className={cn(
                      "rounded-md px-2 py-1 text-[10px] font-semibold",
                      conf >= 80
                        ? "bg-signal-soft text-signal-deep"
                        : conf >= 60
                          ? "bg-[#fff4e8] text-prompt-orange"
                          : "bg-mist text-slate",
                    )}
                  >
                    Confidence {conf}%
                  </span>
                </div>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
