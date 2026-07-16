"use client";

import { useEffect, useState } from "react";
import { Eye, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { api, type Document } from "@/lib/api-client";

function isPdf(doc: Document, contentType?: string) {
  const ct = (contentType || doc.content_type || "").toLowerCase();
  return (
    doc.doc_type === "pdf" ||
    ct.includes("pdf") ||
    doc.original_filename.toLowerCase().endsWith(".pdf")
  );
}

function isTextLike(doc: Document, contentType?: string) {
  const ct = (contentType || doc.content_type || "").toLowerCase();
  const name = doc.original_filename.toLowerCase();
  return (
    ct.startsWith("text/") ||
    ct.includes("markdown") ||
    ct.includes("html") ||
    name.endsWith(".md") ||
    name.endsWith(".markdown") ||
    name.endsWith(".txt") ||
    name.endsWith(".html")
  );
}

export function DocumentPreviewDialog({
  workspaceId,
  document: doc,
  open,
  onOpenChange,
}: {
  workspaceId: string;
  document: Document | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [url, setUrl] = useState<string | null>(null);
  const [text, setText] = useState<string | null>(null);
  const [contentType, setContentType] = useState<string>("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open || !doc) return;
    let objectUrl: string | null = null;
    let cancelled = false;

    (async () => {
      setLoading(true);
      setUrl(null);
      setText(null);
      setContentType("");
      try {
        const { blob, contentType: ct } = await api.fetchDocumentFile(
          workspaceId,
          doc.id,
        );
        if (cancelled) return;
        setContentType(ct);
        if (isTextLike(doc, ct) && !isPdf(doc, ct)) {
          const body = await blob.text();
          if (!cancelled) setText(body);
        } else {
          objectUrl = URL.createObjectURL(blob);
          if (!cancelled) setUrl(objectUrl);
        }
      } catch (err) {
        if (!cancelled) {
          toast.error(err instanceof Error ? err.message : "Could not load preview");
          onOpenChange(false);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [open, doc, workspaceId, onOpenChange]);

  const pdf = doc ? isPdf(doc, contentType) : false;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex h-[min(90vh,880px)] w-[min(96vw,960px)] max-w-none flex-col gap-0 overflow-hidden p-0 sm:rounded-2xl">
        <DialogHeader className="shrink-0 border-b border-line px-5 py-4 pr-12 text-left">
          <DialogTitle className="truncate">
            {doc?.original_filename ?? "Document preview"}
          </DialogTitle>
          <DialogDescription>
            {pdf
              ? "PDF preview — scroll inside the viewer."
              : "Document preview"}
          </DialogDescription>
        </DialogHeader>

        <div className="min-h-0 flex-1 bg-mist/40">
          {loading && (
            <div className="flex h-full items-center justify-center gap-2 text-sm text-slate">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading preview…
            </div>
          )}

          {!loading && url && pdf && (
            <iframe
              title={doc?.original_filename ?? "PDF preview"}
              src={url}
              className="h-full w-full border-0 bg-white"
            />
          )}

          {!loading && url && !pdf && (
            <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center">
              <p className="text-sm text-slate">
                Inline preview isn’t available for this file type. Open it in a new
                tab instead.
              </p>
              <Button asChild variant="outline" className="rounded-xl">
                <a href={url} target="_blank" rel="noreferrer">
                  Open file
                </a>
              </Button>
            </div>
          )}

          {!loading && text != null && (
            <pre className="h-full overflow-auto whitespace-pre-wrap break-words p-5 font-mono text-xs leading-relaxed text-ink">
              {text}
            </pre>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

export function PreviewDocumentButton({
  workspaceId,
  document: doc,
  className,
  label = "Preview",
}: {
  workspaceId: string;
  document: Document;
  className?: string;
  label?: string;
}) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className={className}
        onClick={() => setOpen(true)}
        aria-label={`Preview ${doc.original_filename}`}
        title="Preview"
      >
        <Eye className="h-4 w-4 text-slate" />
        <span className="sr-only">{label}</span>
      </Button>
      <DocumentPreviewDialog
        workspaceId={workspaceId}
        document={doc}
        open={open}
        onOpenChange={setOpen}
      />
    </>
  );
}

export function PreviewDocumentTextButton({
  workspaceId,
  document: doc,
}: {
  workspaceId: string;
  document: Document;
}) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="h-7 rounded-lg px-2.5 text-xs"
        onClick={(e) => {
          e.stopPropagation();
          setOpen(true);
        }}
      >
        <Eye className="mr-1.5 h-3.5 w-3.5" />
        Preview
      </Button>
      <DocumentPreviewDialog
        workspaceId={workspaceId}
        document={doc}
        open={open}
        onOpenChange={setOpen}
      />
    </>
  );
}
