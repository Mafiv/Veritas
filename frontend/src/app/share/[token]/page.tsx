"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { BrandMark } from "@/components/shared/brand";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { API_BASE, type SharePreview } from "@/lib/api-client";

export default function PublicSharePage() {
  const params = useParams<{ token: string }>();
  const [link, setLink] = useState<SharePreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [needsPassword, setNeedsPassword] = useState(false);

  async function load(pw?: string) {
    const token = params.token;
    if (!token) return;
    setError(null);
    try {
      const qs = pw ? `?password=${encodeURIComponent(pw)}` : "";
      const res = await fetch(`${API_BASE}/share/${token}${qs}`);
      if (!res.ok) {
        const data = await res.json().catch(() => null);
        const msg = data?.error?.message || "Link unavailable";
        if (String(msg).toLowerCase().includes("password")) {
          setNeedsPassword(true);
        }
        throw new Error(msg);
      }
      setLink(await res.json());
      setNeedsPassword(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load share");
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.token]);

  const preview = link?.preview || {};

  return (
    <div className="min-h-screen bg-paper px-6 py-16">
      <div className="mx-auto max-w-lg">
        <BrandMark size="md" />
        <h1 className="mt-10 font-display text-3xl font-semibold text-ink">
          Shared resource
        </h1>

        {needsPassword && (
          <div className="mt-6 rounded-2xl border border-line bg-white p-6 shadow-soft">
            <p className="text-sm text-slate">This link is password protected.</p>
            <Input
              className="mt-3"
              type="password"
              placeholder="Share password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <Button className="mt-3" onClick={() => load(password)}>
              Unlock
            </Button>
          </div>
        )}

        {error && !needsPassword && <p className="mt-4 text-sm text-danger">{error}</p>}

        {link && (
          <div className="mt-6 rounded-2xl border border-line bg-white p-6 shadow-soft">
            <p className="text-sm text-slate">
              Type ·{" "}
              <span className="font-medium text-ink">{link.resource_type}</span>
            </p>
            {typeof preview.title === "string" && (
              <h2 className="mt-3 font-display text-xl font-semibold text-ink">
                {preview.title}
              </h2>
            )}
            {typeof preview.summary === "string" && preview.summary && (
              <p className="mt-3 text-sm leading-relaxed text-slate">{preview.summary}</p>
            )}
            {typeof preview.description === "string" && preview.description && (
              <p className="mt-3 text-sm text-slate">{preview.description}</p>
            )}
            {Array.isArray(preview.suggested_questions) &&
              preview.suggested_questions.length > 0 && (
                <ul className="mt-4 space-y-1.5 text-sm text-ink-soft">
                  {(preview.suggested_questions as string[]).map((q) => (
                    <li key={q}>· {q}</li>
                  ))}
                </ul>
              )}
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
