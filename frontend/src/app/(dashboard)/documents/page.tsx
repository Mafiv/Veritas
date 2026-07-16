"use client";

import { useCallback, useEffect, useState } from "react";
import { RefreshCw, Share2, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { DocumentDropzone } from "@/components/upload/dropzone";
import { PreviewDocumentButton } from "@/components/upload/document-preview";
import { EmptyState } from "@/components/shared/empty-state";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  api,
  type Document,
  type Entity,
  type IngestionJob,
} from "@/lib/api-client";
import { useAppStore } from "@/lib/store";
import { cn, formatBytes, formatRelative } from "@/lib/utils";

const statusStyles: Record<string, string> = {
  ready: "bg-signal-soft text-signal-deep",
  processing: "bg-mist text-ink-soft",
  pending: "bg-mist text-ink-soft",
  failed: "bg-red-50 text-danger",
};

export default function DocumentsPage() {
  const workspace = useAppStore((s) => s.workspace);
  const [docs, setDocs] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [jobs, setJobs] = useState<Record<string, IngestionJob>>({});
  const [entities, setEntities] = useState<Record<string, Entity[]>>({});
  const [expanded, setExpanded] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!workspace) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.listDocuments(workspace.id);
      setDocs(res.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load documents");
    } finally {
      setLoading(false);
    }
  }, [workspace]);

  useEffect(() => {
    load();
  }, [load]);

  // Poll ingestion status for non-ready docs
  useEffect(() => {
    if (!workspace) return;
    const pending = docs.filter((d) => d.status === "pending" || d.status === "processing");
    if (pending.length === 0) return;
    const timer = setInterval(async () => {
      for (const doc of pending) {
        try {
          const job = await api.documentStatus(workspace.id, doc.id);
          setJobs((prev) => ({ ...prev, [doc.id]: job }));
          if (job.status === "done" || job.status === "failed") {
            await load();
          }
        } catch {
          /* ignore */
        }
      }
    }, 2500);
    return () => clearInterval(timer);
  }, [docs, workspace, load]);

  async function remove(doc: Document) {
    if (!workspace) return;
    if (!confirm(`Delete ${doc.original_filename}?`)) return;
    try {
      await api.deleteDocument(workspace.id, doc.id);
      setDocs((prev) => prev.filter((d) => d.id !== doc.id));
      toast.success("Document deleted");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Delete failed");
    }
  }

  async function reprocess(doc: Document) {
    if (!workspace) return;
    try {
      const updated = await api.reprocessDocument(workspace.id, doc.id);
      setDocs((prev) => prev.map((d) => (d.id === doc.id ? updated : d)));
      toast.success("Reprocessing started");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Reprocess failed");
    }
  }

  async function share(doc: Document) {
    if (!workspace) return;
    try {
      const link = await api.createSharedLink(workspace.id, {
        resource_type: "document",
        resource_id: doc.id,
      });
      const url = `${window.location.origin}/share/${link.token}`;
      await navigator.clipboard.writeText(url);
      toast.success("Share link copied");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Share failed");
    }
  }

  async function toggleDetails(doc: Document) {
    if (expanded === doc.id) {
      setExpanded(null);
      return;
    }
    setExpanded(doc.id);
    if (!workspace || entities[doc.id]) return;
    try {
      const ents = await api.documentEntities(workspace.id, doc.id);
      setEntities((prev) => ({ ...prev, [doc.id]: ents }));
    } catch {
      /* optional */
    }
  }

  if (!workspace) {
    return (
      <EmptyState
        title="No workspace selected"
        description="Select a workspace to manage documents."
      />
    );
  }

  return (
    <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
      <div className="mx-auto w-full max-w-5xl px-4 py-8 md:px-8">
      <div className="mb-8">
        <h1 className="font-display text-[28px] font-semibold tracking-tight text-ink">
          Documents
        </h1>
        <p className="mt-2 text-base text-slate">
          Upload PDFs, Markdown, Notion exports, and text. Veritas chunks, embeds, and
          indexes them for grounded retrieval.
        </p>
      </div>

      <DocumentDropzone
        workspaceId={workspace.id}
        onUploaded={(doc) => setDocs((prev) => [doc, ...prev.filter((d) => d.id !== doc.id)])}
      />

      <div className="mt-10">
        <h2 className="font-display text-lg font-semibold text-ink">Library</h2>

        {loading && (
          <div className="mt-4 space-y-3">
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-20 w-full" />
          </div>
        )}

        {!loading && error && (
          <EmptyState
            title="Couldn’t load documents"
            description={error}
            actionLabel="Retry"
            onAction={load}
          />
        )}

        {!loading && !error && docs.length === 0 && (
          <EmptyState
            className="mt-4 rounded-2xl border border-dashed border-line bg-white/50"
            title="Upload your first document to get started"
            description="Drop a PDF or markdown file above. We’ll extract text, chunk it semantically, and generate suggested questions."
            icon="upload"
          />
        )}

        {!loading && !error && docs.length > 0 && (
          <ul className="mt-4 space-y-3">
            {docs.map((doc) => {
              const job = jobs[doc.id];
              return (
                <li
                  key={doc.id}
                  className="rounded-xl border border-line bg-white p-4 shadow-soft"
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <button
                      type="button"
                      className="min-w-0 flex-1 text-left"
                      onClick={() => toggleDetails(doc)}
                    >
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="truncate font-medium text-ink">
                          {doc.original_filename}
                        </p>
                        <span
                          className={cn(
                            "rounded-md px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide",
                            statusStyles[doc.status] || statusStyles.pending,
                          )}
                        >
                          {doc.status}
                        </span>
                        {job && (doc.status === "processing" || doc.status === "pending") && (
                          <span className="text-[10px] text-muted-foreground">
                            stage · {job.stage}
                          </span>
                        )}
                        {doc.version > 1 && (
                          <span className="text-[10px] text-muted-foreground">
                            v{doc.version}
                          </span>
                        )}
                      </div>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {formatBytes(doc.file_size)} · {doc.chunk_count} chunks ·{" "}
                        {doc.page_count} pages · {formatRelative(doc.created_at)}
                      </p>
                      {doc.summary && (
                        <p className="mt-2 text-sm leading-relaxed text-slate line-clamp-2">
                          {doc.summary}
                        </p>
                      )}
                      {doc.error_message && (
                        <p className="mt-2 text-xs text-danger">{doc.error_message}</p>
                      )}
                      {doc.suggested_questions && doc.suggested_questions.length > 0 && (
                        <div className="mt-3 flex flex-wrap gap-2">
                          {doc.suggested_questions.slice(0, 3).map((q) => (
                            <span
                              key={q}
                              className="rounded-full bg-mist px-2.5 py-1 text-[11px] text-ink-soft"
                            >
                              {q}
                            </span>
                          ))}
                        </div>
                      )}
                      {expanded === doc.id && entities[doc.id] && entities[doc.id].length > 0 && (
                        <div className="mt-3 flex flex-wrap gap-1.5">
                          {entities[doc.id].slice(0, 12).map((e) => (
                            <span
                              key={e.id}
                              className="rounded-md border border-line px-2 py-0.5 text-[10px] text-ink-soft"
                            >
                              {e.name}
                              <span className="ml-1 text-muted-foreground">{e.entity_type}</span>
                            </span>
                          ))}
                        </div>
                      )}
                    </button>
                    <div className="flex items-center gap-1">
                      <PreviewDocumentButton
                        workspaceId={workspace.id}
                        document={doc}
                      />
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => share(doc)}
                        aria-label="Share document"
                      >
                        <Share2 className="h-4 w-4 text-slate" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => reprocess(doc)}
                        aria-label="Reprocess document"
                      >
                        <RefreshCw className="h-4 w-4 text-slate" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => remove(doc)}
                        aria-label="Delete document"
                      >
                        <Trash2 className="h-4 w-4 text-slate" />
                      </Button>
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>
      </div>
    </div>
  );
}
