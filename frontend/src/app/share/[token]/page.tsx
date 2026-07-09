"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { BrandMark } from "@/components/shared/brand";
import { API_BASE, type SharedLink } from "@/lib/api-client";

export default function PublicSharePage() {
  const params = useParams<{ token: string }>();
  const [link, setLink] = useState<SharedLink | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = params.token;
    if (!token) return;
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/share/${token}`);
        if (!res.ok) {
          const data = await res.json().catch(() => null);
          throw new Error(data?.error?.message || "Link unavailable");
        }
        setLink(await res.json());
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load share");
      }
    })();
  }, [params.token]);

  return (
    <div className="min-h-screen bg-paper px-6 py-16">
      <div className="mx-auto max-w-lg">
        <BrandMark size="md" />
        <h1 className="mt-10 font-display text-3xl font-semibold text-ink">
          Shared resource
        </h1>
        {error && <p className="mt-4 text-sm text-danger">{error}</p>}
        {link && (
          <div className="mt-6 rounded-2xl border border-line bg-white p-6 shadow-soft">
            <p className="text-sm text-slate">
              Type · <span className="font-medium text-ink">{link.resource_type}</span>
            </p>
            <p className="mt-2 font-mono text-xs text-muted-foreground break-all">
              {link.resource_id}
            </p>
            <p className="mt-4 text-xs text-muted-foreground">
              Views · {link.view_count}
              {link.expires_at
                ? ` · expires ${new Date(link.expires_at).toLocaleString()}`
                : ""}
            </p>
            <p className="mt-6 text-sm text-slate">
              Sign in to Veritas to open the full document or thread with citations.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
