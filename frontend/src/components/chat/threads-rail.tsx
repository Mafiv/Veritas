"use client";

import { useMemo, useState } from "react";
import { MessageSquarePlus, Search } from "lucide-react";
import type { Thread } from "@/lib/api-client";
import { cn } from "@/lib/utils";
import { Input } from "@/components/ui/input";

function dayLabel(dateStr: string): string {
  const d = new Date(dateStr);
  const now = new Date();
  const startToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const startThat = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const diffDays = Math.round((startToday.getTime() - startThat.getTime()) / 86400000);
  if (diffDays === 0) return "Today";
  if (diffDays === 1) return "Yesterday";
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function groupThreads(threads: Thread[]) {
  const groups: { label: string; items: Thread[] }[] = [];
  const map = new Map<string, Thread[]>();
  for (const t of threads) {
    const label = dayLabel(t.updated_at);
    if (!map.has(label)) map.set(label, []);
    map.get(label)!.push(t);
  }
  for (const [label, items] of map) {
    groups.push({ label, items });
  }
  return groups;
}

export function ThreadsRail({
  threads,
  activeId,
  onSelect,
  onNew,
}: {
  threads: Thread[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
}) {
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return threads;
    return threads.filter((t) => t.title.toLowerCase().includes(q));
  }, [threads, query]);

  const groups = useMemo(() => groupThreads(filtered), [filtered]);

  return (
    <aside className="hidden w-[220px] shrink-0 flex-col border-r border-line bg-white/80 lg:flex">
      <div className="flex items-center justify-between px-3 pb-2 pt-4">
        <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate">
          Threads
        </p>
        <button
          type="button"
          onClick={onNew}
          className="rounded-lg p-1.5 text-slate transition hover:bg-signal-soft hover:text-signal-deep"
          aria-label="New chat"
          title="New chat"
        >
          <MessageSquarePlus className="h-4 w-4" />
        </button>
      </div>

      <div className="px-3 pb-3">
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search conversations…"
            className="h-9 rounded-xl border-line bg-mist/50 pl-8 text-xs shadow-none"
          />
        </div>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto px-2 pb-4">
        {groups.length === 0 ? (
          <p className="px-2 py-6 text-center text-xs leading-relaxed text-muted-foreground">
            No conversations yet.
            <br />
            Ask your first question.
          </p>
        ) : (
          groups.map((group) => (
            <div key={group.label} className="animate-fade-in">
              <p className="mb-1 px-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-slate">
                {group.label}
              </p>
              <div className="space-y-0.5">
                {group.items.map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    onClick={() => onSelect(t.id)}
                    className={cn(
                      "thread-item w-full rounded-xl px-2.5 py-2 text-left",
                      activeId === t.id
                        ? "bg-signal-soft/70 text-ink"
                        : "hover:bg-mist/80",
                    )}
                  >
                    <p className="truncate text-[13px] font-medium text-ink">
                      {t.title}
                    </p>
                    <p className="mt-0.5 text-[10px] text-muted-foreground">
                      {t.message_count} message{t.message_count === 1 ? "" : "s"}
                    </p>
                  </button>
                ))}
              </div>
            </div>
          ))
        )}
      </div>
    </aside>
  );
}
