"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { EmptyState } from "@/components/shared/empty-state";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type PlanTier, type UsageStats } from "@/lib/api-client";
import { useAppStore } from "@/lib/store";

export default function SettingsPage() {
  const user = useAppStore((s) => s.user);
  const setUser = useAppStore((s) => s.setUser);
  const [usage, setUsage] = useState<UsageStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const stats = await api.usage();
        setUsage(stats);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load usage");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  async function upgrade(plan: PlanTier) {
    try {
      const session = await api.checkout(plan);
      if (session.mock) {
        toast.success(`Upgraded to ${plan} (dev mock)`);
        const me = await api.me();
        setUser(me);
        const stats = await api.usage();
        setUsage(stats);
        return;
      }
      if (session.url) window.location.href = session.url;
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Checkout failed");
    }
  }

  return (
    <div className="mx-auto w-full max-w-3xl flex-1 px-4 py-8 md:px-8">
      <h1 className="font-display text-[28px] font-semibold tracking-tight text-ink">
        Settings
      </h1>
      <p className="mt-2 text-base text-slate">
        Profile, plan, and usage metering for your Veritas account.
      </p>

      <Card className="mt-8">
        <CardHeader>
          <CardTitle>Profile</CardTitle>
          <CardDescription>Account identity</CardDescription>
        </CardHeader>
        <CardContent className="space-y-1 text-sm">
          <p>
            <span className="text-muted-foreground">Name · </span>
            {user?.full_name}
          </p>
          <p>
            <span className="text-muted-foreground">Email · </span>
            {user?.email}
          </p>
          <p>
            <span className="text-muted-foreground">Plan · </span>
            <span className="font-semibold uppercase tracking-wide text-signal-deep">
              {user?.plan}
            </span>
          </p>
        </CardContent>
      </Card>

      <Card className="mt-6">
        <CardHeader>
          <CardTitle>Usage</CardTitle>
          <CardDescription>Metered against your current tier</CardDescription>
        </CardHeader>
        <CardContent>
          {loading && (
            <div className="space-y-3">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-2/3" />
            </div>
          )}
          {error && (
            <EmptyState title="Usage unavailable" description={error} />
          )}
          {usage && (
            <div className="space-y-5">
              <Meter
                label="Queries today"
                value={usage.queries_today}
                max={usage.queries_limit}
              />
              <Meter
                label="Documents"
                value={usage.documents_count}
                max={usage.documents_limit}
              />
              <Meter
                label="Workspaces"
                value={usage.workspaces_count}
                max={usage.workspaces_limit}
              />
              <p className="text-xs text-muted-foreground">
                {usage.chunks_total} total chunks indexed
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      <Card className="mt-6">
        <CardHeader>
          <CardTitle>Plans</CardTitle>
          <CardDescription>
            Free tier for exploration. Pro unlocks higher limits and premium retrieval.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-2">
          <PlanCard
            name="Pro"
            price="$29/mo"
            features={[
              "500 queries / day",
              "200 documents",
              "10 workspaces",
              "Cross-encoder reranking",
            ]}
            onSelect={() => upgrade("pro")}
            current={user?.plan === "pro"}
          />
          <PlanCard
            name="Team"
            price="$99/mo"
            features={[
              "5,000 queries / day",
              "2,000 documents",
              "100 workspaces",
              "Shared threads & admin",
            ]}
            onSelect={() => upgrade("team")}
            current={user?.plan === "team"}
          />
        </CardContent>
      </Card>
    </div>
  );
}

function Meter({
  label,
  value,
  max,
}: {
  label: string;
  value: number;
  max: number;
}) {
  const pct = Math.min(100, Math.round((value / Math.max(max, 1)) * 100));
  return (
    <div>
      <div className="mb-1.5 flex justify-between text-sm">
        <span className="text-ink-soft">{label}</span>
        <span className="font-mono text-xs text-muted-foreground">
          {value} / {max}
        </span>
      </div>
      <Progress value={pct} />
    </div>
  );
}

function PlanCard({
  name,
  price,
  features,
  onSelect,
  current,
}: {
  name: string;
  price: string;
  features: string[];
  onSelect: () => void;
  current?: boolean;
}) {
  return (
    <div className="rounded-xl border border-line bg-mist/40 p-4">
      <div className="flex items-baseline justify-between">
        <h3 className="font-display text-lg font-semibold text-ink">{name}</h3>
        <p className="text-sm font-medium text-signal-deep">{price}</p>
      </div>
      <ul className="mt-3 space-y-1.5 text-sm text-slate">
        {features.map((f) => (
          <li key={f}>· {f}</li>
        ))}
      </ul>
      <Button
        variant={current ? "outline" : "signal"}
        className="mt-4 w-full"
        disabled={current}
        onClick={onSelect}
      >
        {current ? "Current plan" : `Upgrade to ${name}`}
      </Button>
    </div>
  );
}
