"use client";

import type { MouseEvent as ReactMouseEvent } from "react";
import { cn } from "@/lib/utils";

export function ResizeHandle({
  onMouseDown,
  className,
}: {
  onMouseDown: (e: ReactMouseEvent) => void;
  className?: string;
}) {
  return (
    <div
      role="separator"
      aria-orientation="vertical"
      tabIndex={0}
      onMouseDown={onMouseDown}
      className={cn(
        "group relative z-10 w-1.5 shrink-0 cursor-col-resize bg-line transition-colors hover:bg-signal/35 active:bg-signal/50",
        className,
      )}
    >
      <span className="pointer-events-none absolute inset-y-0 left-1/2 w-3 -translate-x-1/2" />
      <span className="pointer-events-none absolute top-1/2 left-1/2 h-7 w-[3px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-ink/15 transition group-hover:h-10 group-hover:bg-signal group-active:bg-signal" />
    </div>
  );
}
