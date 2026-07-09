"use client";

import { useMemo, useState } from "react";
import { ThumbsDown, ThumbsUp } from "lucide-react";
import type { Citation } from "@/lib/api-client";
import type { ChatMessageLocal } from "@/lib/store";
import { api } from "@/lib/api-client";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

function renderWithCitations(
  content: string,
  citations: Citation[],
  onCite: (c: Citation) => void,
) {
  const parts = content.split(/(\[\d+\])/g);
  return parts.map((part, i) => {
    const match = part.match(/^\[(\d+)\]$/);
    if (match) {
      const idx = Number(match[1]);
      const cite = citations.find((c) => c.citation_index === idx);
      return (
        <button
          key={i}
          type="button"
          className="citation-chip"
          title={cite?.snippet || `Source ${idx}`}
          onClick={() => cite && onCite(cite)}
        >
          {idx}
        </button>
      );
    }
    return <span key={i}>{part}</span>;
  });
}

export function MessageList({
  messages,
  citations,
  workspaceId,
  onSelectCitation,
}: {
  messages: ChatMessageLocal[];
  citations: Citation[];
  workspaceId: string;
  onSelectCitation: (c: Citation) => void;
}) {
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 py-6">
      {messages.map((m) => (
        <MessageBubble
          key={m.id}
          message={m}
          citations={m.citations || citations}
          workspaceId={workspaceId}
          onSelectCitation={onSelectCitation}
        />
      ))}
    </div>
  );
}

function MessageBubble({
  message,
  citations,
  workspaceId,
  onSelectCitation,
}: {
  message: ChatMessageLocal;
  citations: Citation[];
  workspaceId: string;
  onSelectCitation: (c: Citation) => void;
}) {
  const isUser = message.role === "user";
  const [feedback, setFeedback] = useState(message.feedback);

  const body = useMemo(() => {
    if (isUser) return message.content;
    return renderWithCitations(message.content, citations, onSelectCitation);
  }, [message.content, citations, isUser, onSelectCitation]);

  async function sendFeedback(value: "up" | "down") {
    if (!message.thread_id || message.id.startsWith("temp-")) return;
    try {
      await api.feedback(workspaceId, message.thread_id, message.id, value);
      setFeedback(value);
    } catch {
      /* ignore */
    }
  }

  return (
    <div
      className={cn(
        "animate-rise flex flex-col gap-2",
        isUser ? "items-end" : "items-start",
      )}
    >
      <div
        className={cn(
          "max-w-[92%] rounded-2xl px-4 py-3 text-[15px] leading-relaxed whitespace-pre-wrap",
          isUser
            ? "bg-ink text-primary-foreground"
            : "bg-white border border-line shadow-soft text-ink",
          message.streaming && !isUser && "stream-caret",
        )}
      >
        {body}
      </div>
      {!isUser && !message.streaming && (
        <div className="flex items-center gap-1 px-1">
          <Button
            variant="ghost"
            size="icon"
            className={cn("h-8 w-8", feedback === "up" && "text-success")}
            onClick={() => sendFeedback("up")}
            aria-label="Helpful"
          >
            <ThumbsUp className="h-3.5 w-3.5" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className={cn("h-8 w-8", feedback === "down" && "text-danger")}
            onClick={() => sendFeedback("down")}
            aria-label="Not helpful"
          >
            <ThumbsDown className="h-3.5 w-3.5" />
          </Button>
        </div>
      )}
    </div>
  );
}
