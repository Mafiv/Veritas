import Link from "next/link";
import { cn } from "@/lib/utils";

export function BrandMark({
  className,
  size = "md",
}: {
  className?: string;
  size?: "sm" | "md" | "lg";
}) {
  const sizes = {
    sm: "text-lg",
    md: "text-2xl",
    lg: "text-5xl md:text-6xl lg:text-7xl",
  };
  const mark = {
    sm: "h-7 w-7",
    md: "h-9 w-9",
    lg: "h-14 w-14",
  };

  return (
    <Link
      href="/"
      className={cn(
        "font-display font-bold tracking-tight text-ink inline-flex items-center gap-2",
        sizes[size],
        className,
      )}
    >
      <span
        className={cn(
          "inline-flex items-center justify-center rounded-xl bg-gradient-to-br from-signal to-signal-deep text-white shadow-soft",
          mark[size],
        )}
        aria-hidden
      >
        <svg viewBox="0 0 24 24" className="h-[55%] w-[55%]" fill="none">
          <path
            d="M12 3l7 3v5.5c0 4.4-2.9 8.3-7 9.5-4.1-1.2-7-5.1-7-9.5V6l7-3z"
            fill="currentColor"
            opacity="0.25"
          />
          <path
            d="M12 3l7 3v5.5c0 4.4-2.9 8.3-7 9.5-4.1-1.2-7-5.1-7-9.5V6l7-3z"
            stroke="currentColor"
            strokeWidth="1.6"
          />
          <path
            d="M8.5 12.2l2.2 2.2 4.8-4.8"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </span>
      Veritas
    </Link>
  );
}
