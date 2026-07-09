"use client";

import { useRef, useState } from "react";
import { ArrowUp, Mic, Paperclip, Slash } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function ChatComposer({
  onSend,
  disabled,
  onAttach,
}: {
  onSend: (question: string) => void;
  disabled?: boolean;
  onAttach?: () => void;
}) {
  const [value, setValue] = useState("");
  const [listeningHint, setListeningHint] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  function submit() {
    const q = value.trim();
    if (!q || disabled) return;
    onSend(q);
    setValue("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  }

  function insertSlash() {
    setValue((v) => (v.startsWith("/") ? v : `/${v}`));
    textareaRef.current?.focus();
  }

  return (
    <div className="border-t border-line bg-white/90 backdrop-blur-sm">
      <div className="mx-auto w-full max-w-4xl px-4 py-4">
        <div
          className={cn(
            "composer-shell rounded-2xl border border-line bg-white px-3 pb-2.5 pt-3 shadow-soft",
          )}
        >
          <textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => {
              setValue(e.target.value);
              const el = e.target;
              el.style.height = "auto";
              el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
            }}
            placeholder="Ask anything about your documents…"
            className="max-h-40 min-h-[56px] w-full resize-none bg-transparent px-1.5 text-[15px] leading-relaxed text-ink outline-none placeholder:text-muted-foreground"
            rows={2}
            disabled={disabled}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
          />
          <div className="mt-1 flex items-center justify-between gap-2">
            <div className="flex items-center gap-0.5">
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="h-9 w-9 rounded-xl text-slate hover:bg-mist hover:text-ink"
                onClick={onAttach}
                aria-label="Attach document"
                title="Attach / upload"
              >
                <Paperclip className="h-4 w-4" />
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className={cn(
                  "h-9 w-9 rounded-xl text-slate hover:bg-mist hover:text-ink",
                  listeningHint && "bg-signal-soft text-signal-deep",
                )}
                onClick={() => {
                  setListeningHint(true);
                  setTimeout(() => setListeningHint(false), 1200);
                }}
                aria-label="Voice input"
                title="Voice (coming soon)"
              >
                <Mic className="h-4 w-4" />
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="h-9 w-9 rounded-xl text-slate hover:bg-mist hover:text-ink"
                onClick={insertSlash}
                aria-label="Commands"
                title="Slash commands"
              >
                <Slash className="h-4 w-4" />
              </Button>
            </div>
            <Button
              type="button"
              size="icon"
              className="btn-gradient h-10 w-10 rounded-full disabled:opacity-40"
              onClick={submit}
              disabled={disabled || !value.trim()}
              aria-label="Send"
            >
              <ArrowUp className="h-4.5 w-4.5 h-[18px] w-[18px]" />
            </Button>
          </div>
        </div>
        <p className="mt-2.5 flex items-center justify-center gap-1.5 text-[11px] text-muted-foreground">
          <span className="inline-block h-1.5 w-1.5 rounded-full bg-signal" />
          Your data stays private. Veritas never trains on your documents.
        </p>
      </div>
    </div>
  );
}
