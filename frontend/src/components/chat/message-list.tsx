"use client";

import { useMemo, useState } from "react";
import { ThumbsDown, ThumbsUp } from "lucide-react";
import type { Citation } from "@/lib/api-client";
import { AnswerMarkdown } from "@/components/chat/answer-markdown";
import { RetrievalTracePanel } from "@/components/chat/retrieval-trace";
import type { ChatMessageLocal } from "@/lib/store";
import { api } from "@/lib/api-client";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

export function MessageList({
  messages,
  citations,
  workspaceId,
  isStreaming,
  onSelectCitation,
}: {
  messages: ChatMessageLocal[];
  citations: Citation[];
  workspaceId: string;
  isStreaming?: boolean;
  onSelectCitation: (c: Citation) => void;
}) {
  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-7 px-5 py-8">
      {messages.map((m) => (
        <MessageBubble
          key={m.id}
          message={m}
          citations={m.citations || citations}
          workspaceId={workspaceId}
          onSelectCitation={onSelectCitation}
        />
      ))}
      {isStreaming && messages[messages.length - 1]?.streaming && (
        <div className="animate-fade-in flex items-center gap-2 px-1 text-xs text-slate">
          <span className="typing-dots" aria-hidden>
            <span />
            <span />
            <span />
          </span>
          Searching sources and writing…
        </div>
      )}
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
    if (!message.content && message.streaming) {
      return (
        <span className="typing-dots inline-flex items-center py-1" aria-label="Thinking">
          <span />
          <span />
          <span />
        </span>
      );
    }
    return (
      <AnswerMarkdown content={message.content} citations={citations} onCite={onSelectCitation} />
    );
  }, [message.content, message.streaming, citations, isUser, onSelectCitation]);

  const status = message.token_usage?.status;
  const trace = message.token_usage?.trace;

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
          "max-w-[92%] rounded-2xl px-4 py-3.5 text-[15px] leading-relaxed",
          isUser
            ? "bg-ink text-primary-foreground whitespace-pre-wrap"
            : "border border-line bg-white text-ink shadow-soft",
          message.streaming && message.content && !isUser && "stream-caret",
        )}
      >
        {body}
        {!isUser && (status === "interrupted" || status === "error") && (
          <p className="mt-2 text-xs text-slate">
            {status === "interrupted"
              ? "Stopped — this answer is incomplete."
              : "The answer could not be completed. Please try again."}
          </p>
        )}
      </div>
      {!isUser && !message.streaming && trace && <RetrievalTracePanel trace={trace} />}
      {!isUser && !message.streaming && message.content && (
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
