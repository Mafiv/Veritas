"use client";

import { useCallback, useEffect, useState } from "react";
import { FolderHeart, Plus } from "lucide-react";
import { toast } from "sonner";
import { EmptyState } from "@/components/shared/empty-state";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type Collection, type Document } from "@/lib/api-client";
import { useAppStore } from "@/lib/store";

export default function CollectionsPage() {
  const workspace = useAppStore((s) => s.workspace);
  const [collections, setCollections] = useState<Collection[]>([]);
  const [docs, setDocs] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    if (!workspace) return;
    setLoading(true);
    try {
      const [cols, d] = await Promise.all([
        api.listCollections(workspace.id),
        api.listDocuments(workspace.id),
      ]);
      setCollections(cols);
      setDocs(d.items.filter((x) => x.status === "ready"));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to load collections");
    } finally {
      setLoading(false);
    }
  }, [workspace]);

  useEffect(() => {
    load();
  }, [load]);

  async function create() {
    if (!workspace || !name.trim()) return;
    setCreating(true);
    try {
      const col = await api.createCollection(workspace.id, {
        name: name.trim(),
        document_ids: docs.slice(0, 3).map((d) => d.id),
      });
      setCollections((prev) => [col, ...prev]);
      setName("");
      toast.success("Collection created");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Create failed");
    } finally {
      setCreating(false);
    }
  }

  async function addDoc(collectionId: string, documentId: string) {
    if (!workspace) return;
    try {
      const updated = await api.addToCollection(workspace.id, collectionId, documentId);
      setCollections((prev) =>
        prev.map((c) => (c.id === collectionId ? updated : c)),
      );
      toast.success("Document added");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Add failed");
    }
  }

  if (!workspace) {
    return (
      <EmptyState
        title="No workspace selected"
        description="Select a workspace to manage collections."
      />
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col px-6 py-10">
      <h1 className="font-display text-[28px] font-semibold tracking-tight text-ink">
        Collections
      </h1>
      <p className="mt-2 text-base text-slate">
        Group documents into curated sets for focused research threads.
      </p>

      <div className="mt-8 flex gap-2">
        <Input
          placeholder="Collection name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="max-w-sm"
        />
        <Button
          className="btn-gradient rounded-xl"
          onClick={create}
          disabled={creating || !name.trim()}
        >
          <Plus className="h-4 w-4" />
          Create
        </Button>
      </div>

      {loading && (
        <div className="mt-8 space-y-3">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      )}

      {!loading && collections.length === 0 && (
        <div className="mt-10 rounded-3xl border border-dashed border-line bg-white/70 px-6 py-16 text-center">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-signal-soft text-signal-deep">
            <FolderHeart className="h-6 w-6" />
          </div>
          <h2 className="font-display text-xl font-semibold text-ink">
            Curate your evidence
          </h2>
          <p className="mx-auto mt-2 max-w-md text-sm text-slate">
            Create a collection, add ready documents, then scope chat to that set.
          </p>
        </div>
      )}

      {!loading && collections.length > 0 && (
        <ul className="mt-8 space-y-4">
          {collections.map((col) => (
            <li
              key={col.id}
              className="rounded-xl border border-line bg-white p-5 shadow-soft"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h3 className="font-display text-lg font-semibold text-ink">
                    {col.name}
                  </h3>
                  {col.description && (
                    <p className="mt-1 text-sm text-slate">{col.description}</p>
                  )}
                  <p className="mt-2 text-xs text-muted-foreground">
                    {col.document_count} document{col.document_count === 1 ? "" : "s"}
                  </p>
                </div>
              </div>
              {docs.length > 0 && (
                <div className="mt-4 flex flex-wrap gap-2">
                  {docs.slice(0, 6).map((d) => (
                    <button
                      key={d.id}
                      type="button"
                      onClick={() => addDoc(col.id, d.id)}
                      className="rounded-lg border border-line bg-mist/50 px-2.5 py-1 text-[11px] text-ink-soft hover:border-signal hover:text-signal-deep"
                    >
                      + {d.original_filename}
                    </button>
                  ))}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
