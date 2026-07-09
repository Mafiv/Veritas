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
  return (
    <Link
      href="/"
      className={cn(
        "font-display font-bold tracking-tight text-ink inline-flex items-baseline gap-1",
        sizes[size],
        className,
      )}
    >
      Veritas
      <span className="inline-block h-2 w-2 rounded-full bg-signal translate-y-[-0.15em]" aria-hidden />
    </Link>
  );
}
