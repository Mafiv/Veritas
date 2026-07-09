"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { PanelRightOpen, Upload } from "lucide-react";
import { toast } from "sonner";
import { ChatComposer } from "@/components/chat/composer";
import { CitationsPanel } from "@/components/chat/citations-panel";
import { ChatEmptyState } from "@/components/chat/empty-state";
import { MessageList } from "@/components/chat/message-list";
import { ThreadsRail } from "@/components/chat/threads-rail";
import { EmptyState } from "@/components/shared/empty-state";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import {
  api,
  streamChat,
  type Citation,
  type Document,
  type Thread,
  type UsageStats,
} from "@/lib/api-client";
import { useAppStore, useChatStore } from "@/lib/store";
import { cn } from "@/lib/utils";

/*
  Recommended layout:
  | Sidebar | Threads (compact) | Chat (~70%) | Sources (only when citations) |
*/

export default function ChatPage() {
  const router = useRouter();
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
  const [usage, setUsage] = useState<UsageStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeCite, setActiveCite] = useState<string | null>(null);
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [sourcesCollapsed, setSourcesCollapsed] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!workspace) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const [t, d, u] = await Promise.all([
          api.listThreads(workspace.id),
          api.listDocuments(workspace.id),
          api.usage().catch(() => null),
        ]);
        if (cancelled) return;
        setThreads(t);
        setDocs(d.items);
        setUsage(u);
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

  // Auto-open sources when citations arrive; keep collapsed preference otherwise
  useEffect(() => {
    if (citations.length > 0) {
      setSourcesCollapsed(false);
    }
  }, [citations.length]);

  const readyDocs = useMemo(
    () => docs.filter((d) => d.status === "ready"),
    [docs],
  );

  const stats = useMemo(() => {
    const chunks =
      usage?.chunks_total ??
      docs.reduce((sum, d) => sum + (d.chunk_count || 0), 0);
    const bytes = docs.reduce((sum, d) => sum + (d.file_size || 0), 0);
    const storageLabel =
      bytes >= 1024 * 1024
        ? `${(bytes / (1024 * 1024)).toFixed(0)} MB`
        : `${Math.max(1, Math.round(bytes / 1024))} KB`;
    return {
      documents: usage?.documents_count ?? docs.length,
      chunks,
      embeddings: chunks,
      storageLabel: docs.length ? storageLabel : "0 MB",
    };
  }, [docs, usage]);

  const showSourcesPanel = citations.length > 0 && !sourcesCollapsed;

  async function openThread(id: string) {
    if (!workspace) return;
    setThreadId(id);
    setCitations([]);
    setActiveCite(null);
    try {
      const msgs = await api.listMessages(workspace.id, id);
      setMessages(
        msgs.map((m) => ({
          ...m,
          role: m.role as "user" | "assistant" | "system",
        })),
      );
      const lastAssistant = [...msgs].reverse().find((m) => m.role === "assistant");
      if (lastAssistant?.citations?.length) {
        setCitations(lastAssistant.citations);
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not load thread");
    }
  }

  async function handleSend(question: string) {
    if (!workspace || isStreaming) return;
    if (!readyDocs.length) {
      toast.error("Upload at least one document before asking questions.");
      router.push("/documents");
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
    setSourcesCollapsed(false);

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
          onThread: (id) => setThreadId(id),
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
      <div className="flex h-full min-h-0 flex-1">
        <div className="hidden w-[220px] border-r border-line p-4 lg:block">
          <Skeleton className="mb-3 h-4 w-16" />
          <Skeleton className="mb-2 h-9 w-full" />
          <Skeleton className="mb-2 h-8 w-full" />
          <Skeleton className="h-8 w-full" />
        </div>
        <div className="flex-1 p-8">
          <Skeleton className="mb-4 h-8 w-40" />
          <Skeleton className="mb-6 h-4 w-72" />
          <Skeleton className="h-48 w-full max-w-3xl" />
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

  return (
    <div className="flex min-h-0 flex-1 overflow-hidden">
      <ThreadsRail
        threads={threads}
        activeId={threadId}
        onSelect={openThread}
        onNew={() => reset()}
      />

      <section className="flex min-w-0 flex-1 flex-col bg-paper">
        <div className="flex items-center justify-between gap-3 border-b border-line bg-white/80 px-5 py-4 backdrop-blur">
          <div>
            <h1 className="font-display text-[28px] font-semibold leading-none tracking-tight text-ink">
              Chat
            </h1>
            <p className="mt-1.5 text-base text-slate">
              Ask questions grounded in your documents.
            </p>
          </div>
          <div className="flex items-center gap-2">
            {citations.length > 0 && (
              <Button
                variant="outline"
                size="sm"
                className={cn("rounded-xl", showSourcesPanel && "hidden xl:inline-flex")}
                onClick={() => {
                  if (showSourcesPanel) setSourcesCollapsed(true);
                  else {
                    setSourcesCollapsed(false);
                    setSourcesOpen(true);
                  }
                }}
              >
                <PanelRightOpen className="mr-1.5 h-4 w-4" />
                Sources
                <span className="ml-1.5 rounded-full bg-signal-soft px-1.5 text-[10px] font-semibold text-signal-deep">
                  {citations.length}
                </span>
              </Button>
            )}
            <Button
              size="sm"
              className="btn-gradient hidden rounded-xl sm:inline-flex"
              onClick={() => router.push("/documents")}
            >
              <Upload className="mr-1.5 h-3.5 w-3.5" />
              Upload documents
            </Button>
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto">
          {messages.length === 0 ? (
            <ChatEmptyState
              hasDocuments={readyDocs.length > 0}
              stats={stats}
              onPrompt={handleSend}
              onUpload={() => router.push("/documents")}
            />
          ) : (
            <MessageList
              messages={messages}
              citations={citations}
              workspaceId={workspace.id}
              isStreaming={isStreaming}
              onSelectCitation={(c: Citation) => {
                setActiveCite(c.chunk_id);
                setSourcesCollapsed(false);
                setSourcesOpen(true);
              }}
            />
          )}
        </div>

        <ChatComposer
          onSend={handleSend}
          disabled={isStreaming}
          onAttach={() => router.push("/documents")}
        />
      </section>

      {/* Sources — only when citations exist */}
      {showSourcesPanel && (
        <aside className="hidden w-[300px] shrink-0 border-l border-line xl:block">
          <CitationsPanel
            citations={citations}
            activeId={activeCite}
            onSelect={(c) => setActiveCite(c.chunk_id)}
            onClose={() => setSourcesCollapsed(true)}
          />
        </aside>
      )}

      <Sheet open={sourcesOpen && citations.length > 0} onOpenChange={setSourcesOpen}>
        <SheetContent side="right" className="w-full max-w-sm p-0 sm:max-w-md">
          <SheetHeader className="sr-only">
            <SheetTitle>Sources</SheetTitle>
          </SheetHeader>
          <CitationsPanel
            citations={citations}
            activeId={activeCite}
            onSelect={(c) => setActiveCite(c.chunk_id)}
            onClose={() => setSourcesOpen(false)}
          />
        </SheetContent>
      </Sheet>
    </div>
  );
}
