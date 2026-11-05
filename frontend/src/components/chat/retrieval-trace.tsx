"use client";

import { useState } from "react";
import { ChevronDown } from "lucide-react";
import type { RetrievalTrace } from "@/lib/api-client";
import { cn } from "@/lib/utils";

const STAGES = ["condense", "expand", "embed", "search", "rerank", "generate"];

/** "Why this answer?" — the retrieval trace stored with every assistant message. */
export function RetrievalTracePanel({ trace }: { trace: RetrievalTrace }) {
  const [open, setOpen] = useState(false);
  const total = Object.values(trace.timings_ms).reduce((a, b) => a + b, 0);
  const rewritten = trace.standalone_query !== trace.question;

  return (
    <div className="w-full max-w-[92%] px-1 text-xs text-slate">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-1 rounded-md py-1 hover:text-ink"
        aria-expanded={open}
      >
        <ChevronDown className={cn("h-3.5 w-3.5 transition-transform", open && "rotate-180")} />
        Why this answer?
        <span className="text-slate/70">
          · {trace.sources.length} sources · {Math.round(total)} ms
          {trace.abstained && " · abstained"}
        </span>
      </button>

      {open && (
        <div className="mt-2 space-y-3 rounded-xl border border-line bg-white p-3 shadow-soft">
          {rewritten && (
            <p>
              <span className="font-medium text-ink">Searched for:</span> “{trace.standalone_query}”
              <span className="text-slate/70"> (follow-up rewritten using the conversation)</span>
            </p>
          )}
          <div className="flex flex-wrap gap-x-4 gap-y-1">
            {STAGES.filter((s) => s in trace.timings_ms).map((s) => (
              <span key={s}>
                {s} <span className="font-mono text-ink">{Math.round(trace.timings_ms[s])} ms</span>
              </span>
            ))}
            <span>
              reranker <span className="font-mono text-ink">{trace.reranker}</span>
            </span>
            <span>
              candidates <span className="font-mono text-ink">{trace.candidates}</span>
            </span>
          </div>
          {trace.sources.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[480px] text-left">
                <thead className="text-slate/80">
                  <tr>
                    <th className="py-1 pr-2 font-medium">#</th>
                    <th className="py-1 pr-2 font-medium">Source</th>
                    <th className="py-1 pr-2 text-right font-medium">Vector</th>
                    <th className="py-1 pr-2 text-right font-medium">BM25</th>
                    <th className="py-1 pr-2 text-right font-medium">Fused</th>
                    <th className="py-1 text-right font-medium">Final</th>
                  </tr>
                </thead>
                <tbody className="font-mono text-ink">
                  {trace.sources.map((s, i) => (
                    <tr key={s.chunk_id} className="border-t border-line">
                      <td className="py-1 pr-2">{i + 1}</td>
                      <td className="max-w-[200px] truncate py-1 pr-2 font-sans">
                        {s.document}
                        {s.page ? ` p.${s.page}` : ""}
                      </td>
                      <td className="py-1 pr-2 text-right">{s.vector_score.toFixed(3)}</td>
                      <td className="py-1 pr-2 text-right">{s.keyword_score.toFixed(2)}</td>
                      <td className="py-1 pr-2 text-right">{s.fused_score.toFixed(4)}</td>
                      <td className="py-1 text-right">{s.final_score.toFixed(3)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
