"use client";

import { useState } from "react";
import { ArrowUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

export function ChatComposer({
  onSend,
  disabled,
  suggestions,
}: {
  onSend: (question: string) => void;
  disabled?: boolean;
  suggestions?: string[];
}) {
  const [value, setValue] = useState("");

  function submit() {
    const q = value.trim();
    if (!q || disabled) return;
    onSend(q);
    setValue("");
  }

  return (
    <div className="border-t border-line bg-white/80 backdrop-blur-sm">
      {suggestions && suggestions.length > 0 && (
        <div className="mx-auto flex max-w-3xl gap-2 overflow-x-auto px-4 pt-3">
          {suggestions.slice(0, 4).map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => onSend(s)}
              disabled={disabled}
              className="shrink-0 rounded-full border border-line bg-mist/80 px-3 py-1.5 text-xs text-ink-soft transition hover:border-signal hover:bg-signal-soft"
            >
              {s}
            </button>
          ))}
        </div>
      )}
      <div className="mx-auto flex max-w-3xl items-end gap-2 px-4 py-3">
        <Textarea
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="Ask a question grounded in your documents…"
          className={cn(
            "min-h-[52px] max-h-40 resize-none border-line bg-white shadow-none",
          )}
          rows={2}
          disabled={disabled}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
        />
        <Button
          variant="signal"
          size="icon"
          className="h-[52px] w-[52px] shrink-0 rounded-xl"
          onClick={submit}
          disabled={disabled || !value.trim()}
          aria-label="Send"
        >
          <ArrowUp className="h-5 w-5" />
        </Button>
      </div>
    </div>
  );
}
