"use client";

import { useCallback, useRef, useState } from "react";
import { FileUp, X } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { api, type Document } from "@/lib/api-client";
import { cn, formatBytes } from "@/lib/utils";

interface FileProgress {
  id: string;
  file: File;
  progress: number;
  status: "uploading" | "done" | "error";
  error?: string;
  document?: Document;
}

export function DocumentDropzone({
  workspaceId,
  onUploaded,
}: {
  workspaceId: string;
  onUploaded?: (doc: Document) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [files, setFiles] = useState<FileProgress[]>([]);

  const uploadOne = useCallback(
    async (entry: FileProgress) => {
      try {
        // Simulated progress while request runs
        const timer = setInterval(() => {
          setFiles((prev) =>
            prev.map((f) =>
              f.id === entry.id && f.progress < 90
                ? { ...f, progress: f.progress + 8 }
                : f,
            ),
          );
        }, 200);

        const doc = await api.uploadDocument(workspaceId, entry.file);
        clearInterval(timer);
        setFiles((prev) =>
          prev.map((f) =>
            f.id === entry.id
              ? { ...f, progress: 100, status: "done", document: doc }
              : f,
          ),
        );
        onUploaded?.(doc);
        toast.success(`${entry.file.name} indexed`);
      } catch (err) {
        const message = err instanceof Error ? err.message : "Upload failed";
        setFiles((prev) =>
          prev.map((f) =>
            f.id === entry.id ? { ...f, status: "error", error: message } : f,
          ),
        );
        toast.error(message);
      }
    },
    [workspaceId, onUploaded],
  );

  const handleFiles = useCallback(
    (list: FileList | File[]) => {
      const arr = Array.from(list);
      const entries: FileProgress[] = arr.map((file) => ({
        id: `${file.name}-${file.size}-${Date.now()}`,
        file,
        progress: 5,
        status: "uploading",
      }));
      setFiles((prev) => [...entries, ...prev]);
      entries.forEach(uploadOne);
    },
    [uploadOne],
  );

  return (
    <div className="space-y-4">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          if (e.dataTransfer.files?.length) handleFiles(e.dataTransfer.files);
        }}
        onClick={() => inputRef.current?.click()}
        className={cn(
          "cursor-pointer rounded-2xl border-2 border-dashed px-6 py-12 text-center transition-colors",
          dragging
            ? "border-signal bg-signal-soft/60"
            : "border-line bg-white/70 hover:border-signal hover:bg-signal-soft/30",
        )}
      >
        <input
          ref={inputRef}
          type="file"
          className="hidden"
          multiple
          accept=".pdf,.md,.markdown,.txt,.html,.docx"
          onChange={(e) => e.target.files && handleFiles(e.target.files)}
        />
        <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-mist text-ink-soft">
          <FileUp className="h-5 w-5" />
        </div>
        <p className="font-display text-lg font-semibold text-ink">
          Drop documents here
        </p>
        <p className="mt-1 text-sm text-muted-foreground">
          PDF, Markdown, Notion HTML, DOCX, or plain text — up to 25MB each
        </p>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="mt-4"
          onClick={(e) => {
            e.stopPropagation();
            inputRef.current?.click();
          }}
        >
          Browse files
        </Button>
      </div>

      {files.length > 0 && (
        <ul className="space-y-2">
          {files.map((f) => (
            <li
              key={f.id}
              className="flex items-center gap-3 rounded-xl border border-line bg-white px-4 py-3"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-2">
                  <p className="truncate text-sm font-medium text-ink">
                    {f.file.name}
                  </p>
                  <span className="shrink-0 text-xs text-muted-foreground">
                    {formatBytes(f.file.size)}
                  </span>
                </div>
                {f.status === "uploading" && (
                  <Progress value={f.progress} className="mt-2" />
                )}
                {f.status === "done" && (
                  <p className="mt-1 text-xs text-success">
                    Ready · {f.document?.chunk_count ?? 0} chunks
                  </p>
                )}
                {f.status === "error" && (
                  <p className="mt-1 text-xs text-danger">{f.error}</p>
                )}
              </div>
              <button
                type="button"
                className="text-muted-foreground hover:text-ink"
                onClick={() =>
                  setFiles((prev) => prev.filter((x) => x.id !== f.id))
                }
                aria-label="Dismiss"
              >
                <X className="h-4 w-4" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
