"use client";

import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { EmptyState } from "@/components/shared/empty-state";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import {
  api,
  type ApiKey,
  type AuditLog,
  type ExportJob,
  type Invitation,
  type Member,
  type Notification,
  type PlanTier,
  type UsageStats,
  type WorkspaceRole,
} from "@/lib/api-client";
import { useAppStore } from "@/lib/store";

export default function SettingsPage() {
  const user = useAppStore((s) => s.user);
  const workspace = useAppStore((s) => s.workspace);
  const setUser = useAppStore((s) => s.setUser);
  const [usage, setUsage] = useState<UsageStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [members, setMembers] = useState<Member[]>([]);
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [apiKeys, setApiKeys] = useState<ApiKey[]>([]);
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([]);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [exports, setExports] = useState<ExportJob[]>([]);

  const [inviteEmail, setInviteEmail] = useState("");
  const [keyName, setKeyName] = useState("");
  const [newKeySecret, setNewKeySecret] = useState<string | null>(null);

  const loadWorkspaceAdmin = useCallback(async () => {
    if (!workspace) return;
    try {
      const [m, inv, keys, logs, notifs, ex] = await Promise.all([
        api.listMembers(workspace.id).catch(() => []),
        api.listInvitations(workspace.id).catch(() => []),
        api.listApiKeys(workspace.id).catch(() => []),
        api.listAuditLogs(workspace.id).catch(() => []),
        api.listNotifications().catch(() => []),
        api.listExportJobs().catch(() => []),
      ]);
      setMembers(m);
      setInvitations(inv);
      setApiKeys(keys);
      setAuditLogs(logs);
      setNotifications(notifs);
      setExports(ex);
    } catch {
      /* owner-only sections may 403 for viewers */
    }
  }, [workspace]);

  useEffect(() => {
    (async () => {
      try {
        const stats = await api.usage();
        setUsage(stats);
        await loadWorkspaceAdmin();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load usage");
      } finally {
        setLoading(false);
      }
    })();
  }, [loadWorkspaceAdmin]);

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

  async function sendInvite() {
    if (!workspace || !inviteEmail.trim()) return;
    try {
      await api.createInvitation(workspace.id, {
        email: inviteEmail.trim(),
        role: "viewer",
      });
      setInviteEmail("");
      toast.success("Invitation sent");
      await loadWorkspaceAdmin();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Invite failed");
    }
  }

  async function changeRole(userId: string, role: WorkspaceRole) {
    if (!workspace) return;
    try {
      await api.updateMemberRole(workspace.id, userId, role);
      toast.success("Role updated");
      await loadWorkspaceAdmin();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Update failed");
    }
  }

  async function createKey() {
    if (!workspace || !keyName.trim()) return;
    try {
      const key = await api.createApiKey(workspace.id, { name: keyName.trim() });
      setNewKeySecret(key.secret || null);
      setKeyName("");
      toast.success("API key created — copy it now");
      await loadWorkspaceAdmin();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Key create failed");
    }
  }

  async function requestExport() {
    try {
      const job = await api.createExportJob({
        job_type: "gdpr_user_export",
        workspace_id: workspace?.id,
      });
      toast.success(`Export ${job.status}`);
      await loadWorkspaceAdmin();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Export failed");
    }
  }

  async function markAllRead() {
    try {
      await api.markAllNotificationsRead();
      await loadWorkspaceAdmin();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed");
    }
  }

  return (
    <div className="mx-auto w-full max-w-3xl flex-1 overflow-y-auto px-4 py-8 md:px-8">
      <h1 className="font-display text-[28px] font-semibold tracking-tight text-ink">
        Settings
      </h1>
      <p className="mt-2 text-base text-slate">
        Profile, team, API keys, billing, and compliance for your Veritas workspace.
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
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle>Notifications</CardTitle>
            <CardDescription>In-app feed</CardDescription>
          </div>
          <Button variant="outline" size="sm" onClick={markAllRead}>
            Mark all read
          </Button>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          {notifications.length === 0 && (
            <p className="text-muted-foreground">No notifications yet.</p>
          )}
          {notifications.slice(0, 8).map((n) => (
            <div
              key={n.id}
              className={`rounded-lg border border-line px-3 py-2 ${n.read_at ? "opacity-60" : ""}`}
            >
              <p className="font-medium text-ink">{n.title}</p>
              {n.body && <p className="text-xs text-slate">{n.body}</p>}
            </div>
          ))}
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
            </div>
          )}
          {error && <EmptyState title="Usage unavailable" description={error} />}
          {usage && (
            <div className="space-y-5">
              <Meter label="Queries today" value={usage.queries_today} max={usage.queries_limit} />
              <Meter label="Documents" value={usage.documents_count} max={usage.documents_limit} />
              <Meter label="Workspaces" value={usage.workspaces_count} max={usage.workspaces_limit} />
              <p className="text-xs text-muted-foreground">
                {usage.chunks_total} total chunks indexed
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      <Card className="mt-6">
        <CardHeader>
          <CardTitle>Team</CardTitle>
          <CardDescription>Members and invitations for {workspace?.name}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex gap-2">
            <Input
              placeholder="colleague@company.com"
              value={inviteEmail}
              onChange={(e) => setInviteEmail(e.target.value)}
            />
            <Button onClick={sendInvite}>Invite</Button>
          </div>
          <ul className="space-y-2 text-sm">
            {members.map((m) => (
              <li key={m.id} className="flex items-center justify-between gap-2">
                <span>
                  {m.full_name}{" "}
                  <span className="text-muted-foreground">({m.email})</span>
                </span>
                <select
                  className="rounded-md border border-line bg-white px-2 py-1 text-xs"
                  value={m.role}
                  onChange={(e) => changeRole(m.user_id, e.target.value as WorkspaceRole)}
                  disabled={m.role === "owner"}
                >
                  <option value="owner">owner</option>
                  <option value="editor">editor</option>
                  <option value="viewer">viewer</option>
                </select>
              </li>
            ))}
          </ul>
          {invitations.length > 0 && (
            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate">
                Pending invites
              </p>
              <ul className="space-y-1 text-sm text-ink-soft">
                {invitations.map((i) => (
                  <li key={i.id}>
                    {i.email} · {i.role} · {i.status}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </CardContent>
      </Card>

      <Card className="mt-6">
        <CardHeader>
          <CardTitle>API keys</CardTitle>
          <CardDescription>Workspace-scoped keys (`vtk_…`)</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex gap-2">
            <Input
              placeholder="Key name"
              value={keyName}
              onChange={(e) => setKeyName(e.target.value)}
            />
            <Button onClick={createKey}>Create</Button>
          </div>
          {newKeySecret && (
            <p className="rounded-lg bg-mist px-3 py-2 font-mono text-xs break-all">
              {newKeySecret}
            </p>
          )}
          <ul className="space-y-1 text-sm">
            {apiKeys.map((k) => (
              <li key={k.id} className="flex justify-between">
                <span>
                  {k.name} · <span className="font-mono text-xs">{k.key_prefix}…</span>
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={async () => {
                    if (!workspace) return;
                    await api.revokeApiKey(workspace.id, k.id);
                    await loadWorkspaceAdmin();
                  }}
                >
                  Revoke
                </Button>
              </li>
            ))}
          </ul>
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
            features={["500 queries / day", "200 documents", "10 workspaces"]}
            onSelect={() => upgrade("pro")}
            current={user?.plan === "pro"}
          />
          <PlanCard
            name="Team"
            price="$99/mo"
            features={["5,000 queries / day", "2,000 documents", "100 workspaces"]}
            onSelect={() => upgrade("team")}
            current={user?.plan === "team"}
          />
        </CardContent>
      </Card>

      <Card className="mt-6">
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle>Data export</CardTitle>
            <CardDescription>GDPR / workspace JSON export</CardDescription>
          </div>
          <Button variant="outline" size="sm" onClick={requestExport}>
            Request export
          </Button>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          {exports.length === 0 && (
            <p className="text-muted-foreground">No export jobs yet.</p>
          )}
          {exports.slice(0, 5).map((e) => (
            <div key={e.id} className="flex justify-between gap-2">
              <span>
                {e.job_type} · {e.status}
              </span>
              {e.download_url && (
                <a
                  className="text-signal-deep underline"
                  href={`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1"}${e.download_url}`}
                >
                  Download
                </a>
              )}
            </div>
          ))}
        </CardContent>
      </Card>

      <Card className="mt-6">
        <CardHeader>
          <CardTitle>SSO</CardTitle>
          <CardDescription>
            OIDC / SAML / Google / Microsoft for this workspace (owners)
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <SsoSettings workspaceId={workspace?.id} />
        </CardContent>
      </Card>

      <Card className="mt-6">
        <CardHeader>
          <CardTitle>Webhooks</CardTitle>
          <CardDescription>Outbound event URLs (owners)</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <WebhookSettings workspaceId={workspace?.id} />
        </CardContent>
      </Card>

      <Card className="mt-6">
        <CardHeader>
          <CardTitle>Notification preferences</CardTitle>
          <CardDescription>In-app and email channels</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <NotificationPrefs />
        </CardContent>
      </Card>

      <Card className="mt-6 mb-10">
        <CardHeader>
          <CardTitle>Audit log</CardTitle>
          <CardDescription>Recent workspace actions (owners)</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2 text-xs">
          {auditLogs.length === 0 && (
            <p className="text-muted-foreground">No audit entries or insufficient role.</p>
          )}
          {auditLogs.slice(0, 12).map((a) => (
            <div key={a.id} className="flex justify-between gap-3 border-b border-line/60 py-1.5">
              <span className="font-medium text-ink">{a.action}</span>
              <span className="text-muted-foreground">
                {new Date(a.created_at).toLocaleString()}
              </span>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}

function SsoSettings({ workspaceId }: { workspaceId?: string }) {
  const [provider, setProvider] = useState("oidc");
  const [domains, setDomains] = useState("");
  const [issuer, setIssuer] = useState("");
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const [enforced, setEnforced] = useState(false);
  const [rows, setRows] = useState<
    Awaited<ReturnType<typeof api.listSsoConnections>>
  >([]);

  useEffect(() => {
    if (!workspaceId) return;
    api.listSsoConnections(workspaceId).then(setRows).catch(() => setRows([]));
  }, [workspaceId]);

  if (!workspaceId) return <p className="text-muted-foreground">Select a workspace.</p>;

  return (
    <div className="space-y-3">
      <div className="grid gap-2 sm:grid-cols-2">
        <select
          className="rounded-md border border-line bg-white px-2 py-2 text-sm"
          value={provider}
          onChange={(e) => setProvider(e.target.value)}
        >
          <option value="oidc">oidc</option>
          <option value="saml">saml</option>
          <option value="google">google</option>
          <option value="microsoft">microsoft</option>
        </select>
        <Input
          placeholder="Domains (comma-separated)"
          value={domains}
          onChange={(e) => setDomains(e.target.value)}
        />
        <Input
          placeholder="Issuer URL"
          value={issuer}
          onChange={(e) => setIssuer(e.target.value)}
        />
        <Input
          placeholder="Client ID"
          value={clientId}
          onChange={(e) => setClientId(e.target.value)}
        />
        <Input
          placeholder="Client secret"
          type="password"
          value={clientSecret}
          onChange={(e) => setClientSecret(e.target.value)}
        />
        <label className="flex items-center gap-2 text-xs">
          <input
            type="checkbox"
            checked={enforced}
            onChange={(e) => setEnforced(e.target.checked)}
          />
          Enforce SSO (block password login)
        </label>
      </div>
      <Button
        size="sm"
        onClick={async () => {
          try {
            await api.upsertSsoConnection(workspaceId, {
              provider,
              issuer_url: issuer || undefined,
              client_id: clientId || undefined,
              client_secret: clientSecret || undefined,
              domains: domains
                .split(",")
                .map((d) => d.trim())
                .filter(Boolean),
              is_enforced: enforced,
            });
            toast.success("SSO connection saved");
            setRows(await api.listSsoConnections(workspaceId));
          } catch (err) {
            toast.error(err instanceof Error ? err.message : "SSO save failed");
          }
        }}
      >
        Save SSO
      </Button>
      <ul className="space-y-1 text-xs text-ink-soft">
        {rows.map((r) => (
          <li key={r.id}>
            {r.provider} · {(r.domains || []).join(", ")} ·{" "}
            {r.is_enforced ? "enforced" : "optional"}
          </li>
        ))}
      </ul>
    </div>
  );
}

function WebhookSettings({ workspaceId }: { workspaceId?: string }) {
  const [url, setUrl] = useState("");
  const [secretOnce, setSecretOnce] = useState<string | null>(null);
  const [rows, setRows] = useState<
    Awaited<ReturnType<typeof api.listWebhooks>>
  >([]);

  useEffect(() => {
    if (!workspaceId) return;
    api.listWebhooks(workspaceId).then(setRows).catch(() => setRows([]));
  }, [workspaceId]);

  if (!workspaceId) return <p className="text-muted-foreground">Select a workspace.</p>;

  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        <Input
          placeholder="https://hooks.example.com/veritas"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
        />
        <Button
          size="sm"
          onClick={async () => {
            try {
              const ep = await api.createWebhook(workspaceId, {
                url,
                event_types: ["document.ready", "document.failed"],
              });
              setSecretOnce(ep.secret || null);
              setUrl("");
              toast.success("Webhook created — copy the secret now");
              setRows(await api.listWebhooks(workspaceId));
            } catch (err) {
              toast.error(err instanceof Error ? err.message : "Create failed");
            }
          }}
        >
          Add
        </Button>
      </div>
      {secretOnce && (
        <p className="rounded-lg bg-mist px-3 py-2 font-mono text-xs break-all">
          {secretOnce}
        </p>
      )}
      <ul className="space-y-1 text-xs">
        {rows.map((w) => (
          <li key={w.id} className="flex justify-between gap-2">
            <span className="truncate">
              {w.url} · {(w.event_types || []).join(", ")}
            </span>
            <Button
              variant="ghost"
              size="sm"
              onClick={async () => {
                await api.deleteWebhook(workspaceId, w.id);
                setRows(await api.listWebhooks(workspaceId));
              }}
            >
              Delete
            </Button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function NotificationPrefs() {
  const [prefs, setPrefs] = useState<
    Awaited<ReturnType<typeof api.listNotificationPreferences>>
  >([]);

  useEffect(() => {
    api.listNotificationPreferences().then(setPrefs).catch(() => setPrefs([]));
  }, []);

  if (prefs.length === 0) {
    return <p className="text-muted-foreground">No preferences loaded.</p>;
  }

  return (
    <ul className="space-y-2">
      {prefs.map((p) => (
        <li key={p.id} className="flex items-center justify-between gap-2">
          <span>
            {p.event_type} · {p.channel}
          </span>
          <input
            type="checkbox"
            checked={p.enabled}
            onChange={async (e) => {
              const updated = await api.updateNotificationPreference({
                event_type: p.event_type,
                channel: p.channel,
                enabled: e.target.checked,
              });
              setPrefs((prev) =>
                prev.map((x) => (x.id === updated.id ? updated : x)),
              );
            }}
          />
        </li>
      ))}
    </ul>
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
