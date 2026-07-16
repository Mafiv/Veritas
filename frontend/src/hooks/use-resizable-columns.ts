"use client";

import { useCallback, useEffect, useState, type MouseEvent as ReactMouseEvent } from "react";

type Sizes = Record<string, number>;

function readStored(key: string, fallback: Sizes): Sizes {
  if (typeof window === "undefined") return fallback;
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw) as Sizes;
    return { ...fallback, ...parsed };
  } catch {
    return fallback;
  }
}

/**
 * Drag-to-resize column widths (px), persisted in localStorage.
 */
export function useResizableColumns(
  storageKey: string,
  defaults: Sizes,
  limits: Record<string, { min: number; max: number }>,
) {
  const [sizes, setSizes] = useState<Sizes>(() => readStored(storageKey, defaults));

  useEffect(() => {
    try {
      localStorage.setItem(storageKey, JSON.stringify(sizes));
    } catch {
      /* ignore quota */
    }
  }, [sizes, storageKey]);

  const startResize = useCallback(
    (
      key: string,
      event: ReactMouseEvent,
      options?: { /** When handle is on the left edge of the panel */ invert?: boolean },
    ) => {
      event.preventDefault();
      const startX = event.clientX;
      const startSize = sizes[key] ?? defaults[key];
      const invert = options?.invert ?? false;

      const onMove = (e: MouseEvent) => {
        const delta = e.clientX - startX;
        const limit = limits[key];
        const nextSize = Math.min(
          limit.max,
          Math.max(limit.min, startSize + (invert ? -delta : delta)),
        );
        setSizes((prev) => ({ ...prev, [key]: nextSize }));
      };

      const onUp = () => {
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
        window.removeEventListener("mousemove", onMove);
        window.removeEventListener("mouseup", onUp);
      };

      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
    },
    [sizes, defaults, limits],
  );

  return { sizes, startResize };
}
