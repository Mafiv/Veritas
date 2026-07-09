"use client";

import Link from "next/link";
import {
  FileSearch,
  FileText,
  GitCompare,
  NotebookPen,
  Search,
  Upload,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const PROMPTS = [
  {
    title: "Summarize a PDF",
    description: "Get a concise brief with page citations",
    icon: FileText,
    color: "text-prompt-purple bg-[#f3eefb]",
    prompt: "Summarize the key findings across my uploaded documents.",
  },
  {
    title: "Compare two documents",
    description: "Spot differences and shared claims",
    icon: GitCompare,
    color: "text-prompt-blue bg-[#eaf4fa]",
    prompt: "Compare the main arguments across my documents and highlight differences.",
  },
  {
    title: "Find information",
    description: "Locate every mention of a topic",
    icon: Search,
    color: "text-prompt-green bg-[#e8f7f0]",
    prompt: 'Find every mention of "authentication" and quote the surrounding context.',
  },
  {
    title: "Generate meeting notes",
    description: "Turn source material into action items",
    icon: NotebookPen,
    color: "text-prompt-orange bg-[#fff4e8]",
    prompt: "Create structured meeting notes with decisions and follow-ups from my documents.",
  },
] as const;

function ResearchIllustration({ className }: { className?: string }) {
  return (
    <div className={cn("relative h-40 w-44", className)} aria-hidden>
      <div className="absolute inset-0 rounded-full bg-signal-soft/40 blur-2xl" />
      <div className="animate-float absolute left-2 top-6 h-24 w-20 rotate-[-8deg] rounded-lg border border-line bg-white shadow-soft">
        <div className="space-y-1.5 p-3">
          <div className="h-1.5 w-10 rounded bg-mist" />
          <div className="h-1.5 w-14 rounded bg-mist" />
          <div className="h-1.5 w-8 rounded bg-mist" />
          <div className="mt-3 h-8 rounded bg-signal-soft/70" />
        </div>
      </div>
      <div className="animate-float absolute right-1 top-2 h-28 w-22 rotate-[7deg] rounded-lg border border-line bg-white shadow-lift [animation-delay:0.6s]">
        <div className="space-y-1.5 p-3">
          <div className="flex items-center gap-1">
            <FileSearch className="h-3.5 w-3.5 text-signal" />
            <div className="h-1.5 w-8 rounded bg-mist" />
          </div>
          <div className="h-1.5 w-12 rounded bg-mist" />
          <div className="h-1.5 w-10 rounded bg-mist" />
          <div className="mt-2 rounded-md border border-signal/20 bg-signal-soft/50 px-2 py-1.5 text-[8px] font-semibold text-signal-deep">
            [1] cited
          </div>
        </div>
      </div>
      <div className="absolute bottom-2 left-1/2 flex h-10 w-10 -translate-x-1/2 items-center justify-center rounded-full bg-signal text-white shadow-lift">
        <Search className="h-4 w-4" />
      </div>
    </div>
  );
}

export function ChatEmptyState({
  hasDocuments,
  stats,
  onPrompt,
  onUpload,
}: {
  hasDocuments: boolean;
  stats: {
    documents: number;
    chunks: number;
    embeddings: number;
    storageLabel: string;
  };
  onPrompt: (prompt: string) => void;
  onUpload: () => void;
}) {
  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col px-6 py-8 md:py-10">
      <div className="animate-rise flex flex-col items-start gap-8 md:flex-row md:items-center md:justify-between">
        <div className="max-w-xl">
          <p className="mb-3 inline-flex items-center gap-1.5 rounded-full bg-signal-soft px-3 py-1 text-xs font-semibold text-signal-deep">
            <Search className="h-3.5 w-3.5" />
            Search across your documents
          </p>
          <h2 className="font-display text-[1.75rem] font-semibold leading-tight tracking-tight text-ink md:text-[2rem]">
            Your AI Research Assistant
          </h2>
          <p className="mt-3 max-w-md text-base leading-relaxed text-slate">
            Ask questions. Find evidence. Get cited answers instantly from your
            files — never approximations.
          </p>

          {!hasDocuments ? (
            <div className="mt-6">
              <Button
                size="lg"
                className="btn-gradient animate-pulse-soft h-11 rounded-xl px-5"
                onClick={onUpload}
              >
                <Upload className="h-4 w-4" />
                Upload Documents
              </Button>
              <p className="mt-2 text-xs text-muted-foreground">
                or drag and drop files on the Documents page
              </p>
            </div>
          ) : (
            <div className="mt-6 flex flex-wrap items-center gap-4 text-sm text-slate">
              <span className="inline-flex items-center gap-2">
                <span className="flex h-6 w-6 items-center justify-center rounded-full bg-signal text-[11px] font-bold text-white">
                  1
                </span>
                Upload
              </span>
              <span className="text-line">→</span>
              <span className="inline-flex items-center gap-2">
                <span className="flex h-6 w-6 items-center justify-center rounded-full bg-signal text-[11px] font-bold text-white">
                  2
                </span>
                Ask
              </span>
              <span className="text-line">→</span>
              <span className="inline-flex items-center gap-2">
                <span className="flex h-6 w-6 items-center justify-center rounded-full bg-signal text-[11px] font-bold text-white">
                  3
                </span>
                Get cited answers
              </span>
            </div>
          )}
        </div>
        <ResearchIllustration className="mx-auto hidden shrink-0 sm:block md:mx-0" />
      </div>

      {!hasDocuments && (
        <div className="animate-rise mt-10 grid gap-3 sm:grid-cols-3" style={{ animationDelay: "80ms" }}>
          {[
            { step: "1", title: "Upload documents", body: "PDF, Markdown, Notion, DOCX" },
            { step: "2", title: "Ask questions", body: "Hybrid search finds the evidence" },
            { step: "3", title: "Get cited answers", body: "Every claim links to a source" },
          ].map((item) => (
            <div
              key={item.step}
              className="rounded-2xl border border-line bg-white p-4 shadow-soft"
            >
              <span className="font-display text-2xl font-semibold text-signal">
                {item.step}
              </span>
              <p className="mt-2 font-medium text-ink">{item.title}</p>
              <p className="mt-1 text-xs text-slate">{item.body}</p>
            </div>
          ))}
        </div>
      )}

      <div className="animate-rise mt-10" style={{ animationDelay: "120ms" }}>
        <h3 className="font-display text-sm font-semibold text-ink">
          What can I help you with?
        </h3>
        <p className="mt-1 text-sm text-slate">Try asking something like…</p>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          {PROMPTS.map((item) => {
            const Icon = item.icon;
            return (
              <button
                key={item.title}
                type="button"
                className="prompt-card flex items-start gap-3 rounded-2xl border border-line bg-white p-4 text-left"
                onClick={() => onPrompt(item.prompt)}
              >
                <span
                  className={cn(
                    "flex h-10 w-10 shrink-0 items-center justify-center rounded-xl",
                    item.color,
                  )}
                >
                  <Icon className="h-4.5 w-4.5 h-[18px] w-[18px]" />
                </span>
                <span>
                  <span className="block text-sm font-semibold text-ink">
                    {item.title}
                  </span>
                  <span className="mt-0.5 block text-xs text-slate">
                    {item.description}
                  </span>
                </span>
              </button>
            );
          })}
        </div>
      </div>

      <div
        className="animate-rise mt-8 grid grid-cols-2 gap-3 rounded-2xl border border-line bg-white p-4 sm:grid-cols-4"
        style={{ animationDelay: "180ms" }}
      >
        {[
          { label: "Documents", value: String(stats.documents) },
          { label: "Chunks", value: stats.chunks.toLocaleString() },
          { label: "Embeddings", value: stats.embeddings.toLocaleString() },
          { label: "Storage", value: stats.storageLabel },
        ].map((stat) => (
          <div key={stat.label} className="px-2 py-1">
            <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate">
              {stat.label}
            </p>
            <p className="mt-1 font-display text-xl font-semibold text-ink">
              {stat.value}
            </p>
          </div>
        ))}
      </div>

      {!hasDocuments && (
        <p className="mt-6 text-center text-sm text-slate">
          Need files first?{" "}
          <Link href="/documents" className="font-semibold text-signal-deep hover:underline">
            Open Documents
          </Link>
        </p>
      )}
    </div>
  );
}
