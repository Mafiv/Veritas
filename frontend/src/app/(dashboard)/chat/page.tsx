"use client";

import { useEffect, useMemo, useState } from "react";
import { PanelRightOpen } from "lucide-react";
import { toast } from "sonner";
import { ChatComposer } from "@/components/chat/composer";
import { CitationsPanel } from "@/components/chat/citations-panel";
import { MessageList } from "@/components/chat/message-list";
import { EmptyState } from "@/components/shared/empty-state";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { api, streamChat, type Citation, type Document, type Thread } from "@/lib/api-client";
import { useAppStore, useChatStore } from "@/lib/store";
import { cn, formatRelative } from "@/lib/utils";

/*
  Chat layout wireframe:
  ┌──────────┬────────────────────────────┬─────────────┐
  │ threads  │  messages (stream+cites)   │  sources    │
  │ list     │  composer                  │  panel      │
  └──────────┴────────────────────────────┴─────────────┘
  Mobile: threads + sources collapse into sheets.
*/

export default function ChatPage() {
  const workspace = useAppStore((s) => s.workspace);
  const {
    messages,
    citations,
    threadId,
    isStreaming,
    setMessages,
    appendMessage,
    updateLastAssistant,
    setCitations,
    setThreadId,
    setStreaming,
    reset,
  } = useChatStore();

  const [threads, setThreads] = useState<Thread[]>([]);
  const [docs, setDocs] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeCite, setActiveCite] = useState<string | null>(null);
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!workspace) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const [t, d] = await Promise.all([
          api.listThreads(workspace.id),
          api.listDocuments(workspace.id),
        ]);
        if (cancelled) return;
        setThreads(t);
        setDocs(d.items);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load chat");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [workspace?.id]);

  const suggestions = useMemo(() => {
    const qs = docs
      .filter((d) => d.status === "ready" && d.suggested_questions?.length)
      .flatMap((d) => d.suggested_questions || []);
    return Array.from(new Set(qs)).slice(0, 4);
  }, [docs]);

  async function openThread(id: string) {
    if (!workspace) return;
    setThreadId(id);
    setCitations([]);
    try {
      const msgs = await api.listMessages(workspace.id, id);
      setMessages(
        msgs.map((m) => ({
          ...m,
          role: m.role as "user" | "assistant" | "system",
        })),
      );
      const lastAssistant = [...msgs].reverse().find((m) => m.role === "assistant");
      if (lastAssistant?.citations) setCitations(lastAssistant.citations);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not load thread");
    }
  }

  async function handleSend(question: string) {
    if (!workspace || isStreaming) return;
    if (!docs.some((d) => d.status === "ready")) {
      toast.error("Upload and wait for at least one document to finish indexing.");
      return;
    }

    const userMsg = {
      id: `temp-u-${Date.now()}`,
      thread_id: threadId || "pending",
      role: "user" as const,
      content: question,
      created_at: new Date().toISOString(),
    };
    const assistantMsg = {
      id: `temp-a-${Date.now()}`,
      thread_id: threadId || "pending",
      role: "assistant" as const,
      content: "",
      created_at: new Date().toISOString(),
      streaming: true,
      citations: [],
    };
    appendMessage(userMsg);
    appendMessage(assistantMsg);
    setStreaming(true);
    setCitations([]);

    let localThread = threadId;
    let answer = "";

    try {
      await streamChat(
        workspace.id,
        {
          question,
          thread_id: threadId || undefined,
          use_hyde: true,
          use_rerank: true,
        },
        {
          onThread: (id) => {
            localThread = id;
            setThreadId(id);
          },
          onCitations: (cites) => {
            setCitations(cites);
            updateLastAssistant({ citations: cites });
          },
          onToken: (token) => {
            answer += token;
            updateLastAssistant({ content: answer, streaming: true });
          },
          onDone: (data) => {
            answer = data.answer;
            setCitations(data.citations);
            updateLastAssistant({
              content: data.answer,
              citations: data.citations,
              streaming: false,
            });
          },
          onMessage: (data) => {
            localThread = data.thread_id;
            setThreadId(data.thread_id);
            updateLastAssistant({
              id: data.message_id,
              thread_id: data.thread_id,
              streaming: false,
            });
          },
        },
      );
      const refreshed = await api.listThreads(workspace.id);
      setThreads(refreshed);
      if (localThread) {
        // keep selection
      }
    } catch (err) {
      updateLastAssistant({
        content: "Something went wrong generating this answer. Please try again.",
        streaming: false,
      });
      toast.error(err instanceof Error ? err.message : "Chat failed");
    } finally {
      setStreaming(false);
    }
  }

  if (!workspace) {
    return (
      <EmptyState
        title="No workspace selected"
        description="Create or select a workspace from the sidebar to start chatting."
      />
    );
  }

  if (loading) {
    return (
      <div className="flex h-full gap-0">
        <div className="hidden w-56 border-r border-line p-4 md:block">
          <Skeleton className="mb-3 h-4 w-20" />
          <Skeleton className="mb-2 h-8 w-full" />
          <Skeleton className="mb-2 h-8 w-full" />
          <Skeleton className="h-8 w-full" />
        </div>
        <div className="flex-1 p-6">
          <Skeleton className="mx-auto h-24 w-full max-w-3xl" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <EmptyState
        title="Couldn’t load chat"
        description={error}
        actionLabel="Retry"
        onAction={() => window.location.reload()}
      />
    );
  }

  const readyDocs = docs.filter((d) => d.status === "ready");

  return (
    <div className="flex h-[calc(100vh-0px)] min-h-0 flex-1">
      {/* Threads rail */}
      <aside className="hidden w-56 shrink-0 flex-col border-r border-line bg-white/50 md:flex">
        <div className="flex items-center justify-between px-3 py-3">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-slate">
            Threads
          </p>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2 text-xs"
            onClick={() => reset()}
          >
            New
          </Button>
        </div>
        <div className="flex-1 space-y-0.5 overflow-y-auto px-2 pb-3">
          {threads.length === 0 ? (
            <p className="px-2 py-4 text-xs text-muted-foreground">
              No conversations yet. Ask your first question.
            </p>
          ) : (
            threads.map((t) => (
              <button
                key={t.id}
                type="button"
                onClick={() => openThread(t.id)}
                className={cn(
                  "w-full rounded-lg px-2.5 py-2 text-left transition",
                  threadId === t.id ? "bg-mist" : "hover:bg-mist/70",
                )}
              >
                <p className="truncate text-sm font-medium text-ink">{t.title}</p>
                <p className="text-[10px] text-muted-foreground">
                  {formatRelative(t.updated_at)} · {t.message_count} msgs
                </p>
              </button>
            ))
          )}
        </div>
      </aside>

      {/* Main chat */}
      <section className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center justify-between border-b border-line bg-white/60 px-4 py-3">
          <div>
            <h1 className="font-display text-lg font-semibold text-ink">Chat</h1>
            <p className="text-xs text-muted-foreground">
              {workspace.name} · {readyDocs.length} indexed document
              {readyDocs.length === 1 ? "" : "s"}
            </p>
          </div>
          <Button
            variant="outline"
            size="sm"
            className="lg:hidden"
            onClick={() => setSourcesOpen(true)}
          >
            <PanelRightOpen className="mr-1.5 h-4 w-4" />
            Sources
          </Button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto">
          {messages.length === 0 ? (
            <EmptyState
              title="Ask with evidence"
              description={
                readyDocs.length
                  ? "Questions are answered only from your uploaded documents, with inline citations."
                  : "Upload your first document to get started — then come back and ask anything."
              }
              actionLabel={readyDocs.length ? undefined : "Go to Documents"}
              onAction={
                readyDocs.length
                  ? undefined
                  : () => {
                      window.location.href = "/documents";
                    }
              }
              icon={readyDocs.length ? "docs" : "upload"}
            />
          ) : (
            <MessageList
              messages={messages}
              citations={citations}
              workspaceId={workspace.id}
              onSelectCitation={(c: Citation) => {
                setActiveCite(c.chunk_id);
                setSourcesOpen(true);
              }}
            />
          )}
        </div>

        <ChatComposer
          onSend={handleSend}
          disabled={isStreaming}
          suggestions={messages.length === 0 ? suggestions : undefined}
        />
      </section>

      {/* Sources panel desktop */}
      <aside className="hidden w-80 shrink-0 border-l border-line bg-white/70 lg:block">
        <CitationsPanel
          citations={citations}
          activeId={activeCite}
          onSelect={(c) => setActiveCite(c.chunk_id)}
        />
      </aside>

      <Sheet open={sourcesOpen} onOpenChange={setSourcesOpen}>
        <SheetContent side="right" className="p-0">
          <SheetHeader className="sr-only">
            <SheetTitle>Sources</SheetTitle>
          </SheetHeader>
          <CitationsPanel
            citations={citations}
            activeId={activeCite}
            onSelect={(c) => setActiveCite(c.chunk_id)}
          />
        </SheetContent>
      </Sheet>
    </div>
  );
}
