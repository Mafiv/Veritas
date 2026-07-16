"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  ChevronLeft,
  ChevronRight,
  FileText,
  FolderOpen,
  LogOut,
  Menu,
  MessageSquare,
  Plus,
  Settings,
  Sparkles,
  Star,
} from "lucide-react";
import { useEffect, useState } from "react";
import { BrandMark } from "@/components/shared/brand";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { Separator } from "@/components/ui/separator";
import { api, setToken, type UsageStats } from "@/lib/api-client";
import { authClient } from "@/lib/auth-client";
import { useAppStore, useChatStore } from "@/lib/store";
import { cn } from "@/lib/utils";

const nav = [
  { href: "/chat", label: "Chat", icon: MessageSquare },
  { href: "/documents", label: "Documents", icon: FileText },
  { href: "/collections", label: "Collections", icon: Star },
  { href: "/settings", label: "Settings", icon: Settings },
];

function storageLabel(plan: string | undefined, chunks: number) {
  // Approximate storage from chunk count for the meter UI
  const usedMb = Math.max(0.1, chunks * 0.05);
  const limitGb =
    plan === "team" ? 100 : plan === "pro" ? 25 : 10;
  const usedGb = usedMb / 1024;
  return {
    usedLabel: usedGb >= 1 ? `${usedGb.toFixed(1)} GB` : `${usedMb.toFixed(1)} MB`,
    limitLabel: `${limitGb} GB`,
    pct: Math.min(100, Math.round((usedGb / limitGb) * 100) || Math.min(24, Math.round(usedMb / 10))),
  };
}

export function DashboardShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const {
    user,
    workspace,
    workspaces,
    sidebarCollapsed,
    setUser,
    setWorkspace,
    setWorkspaces,
    toggleSidebar,
  } = useAppStore();
  const resetChat = useChatStore((s) => s.reset);
  const [ready, setReady] = useState(false);
  const [usage, setUsage] = useState<UsageStats | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        // Refresh Better Auth JWT for FastAPI if we have a session cookie
        const { data } = await authClient.token();
        if (data?.token) setToken(data.token);

        const me = await api.me();
        if (cancelled) return;
        setUser(me);
        const ws = await api.listWorkspaces();
        setWorkspaces(ws);
        if (!workspace && ws[0]) setWorkspace(ws[0]);
        if (workspace && !ws.find((w) => w.id === workspace.id) && ws[0]) {
          setWorkspace(ws[0]);
        }
        try {
          const stats = await api.usage();
          if (!cancelled) setUsage(stats);
        } catch {
          /* usage optional for shell */
        }
      } catch {
        setToken(null);
        setUser(null);
        router.replace("/login");
        return;
      } finally {
        if (!cancelled) setReady(true);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function logout() {
    try {
      await authClient.signOut();
    } catch {
      /* ignore */
    }
    setToken(null);
    setUser(null);
    setWorkspace(null);
    setWorkspaces([]);
    resetChat();
    router.replace("/login");
  }

  async function createWorkspace() {
    const name = prompt("Workspace name");
    if (!name?.trim()) return;
    const ws = await api.createWorkspace({ name: name.trim() });
    const list = await api.listWorkspaces();
    setWorkspaces(list);
    setWorkspace(ws);
    resetChat();
  }

  if (!ready) {
    return (
      <div className="flex h-dvh items-center justify-center bg-paper">
        <div className="h-8 w-8 animate-pulse rounded-full bg-signal" />
      </div>
    );
  }

  const storage = storageLabel(user?.plan, usage?.chunks_total ?? 0);
  const initials = (user?.full_name || "U")
    .split(" ")
    .map((p) => p[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

  const sidebar = (collapsed: boolean, showDesktopToggle = false) => (
    <div className="relative flex h-full min-h-0 flex-col bg-white">
      {showDesktopToggle && (
        <button
          type="button"
          onClick={toggleSidebar}
          className="absolute top-5 z-20 hidden -right-3 h-6 w-6 items-center justify-center rounded-full border border-line bg-white text-slate shadow-soft transition hover:bg-mist hover:text-ink md:inline-flex"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? (
            <ChevronRight className="h-3.5 w-3.5" />
          ) : (
            <ChevronLeft className="h-3.5 w-3.5" />
          )}
        </button>
      )}
      <div
        className={cn(
          "flex shrink-0 items-center gap-2 py-5",
          collapsed ? "justify-center px-2" : "px-4",
        )}
      >
        {!collapsed && <BrandMark size="sm" />}
        {collapsed && (
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-ink text-xs font-bold text-white">
            V
          </span>
        )}
      </div>

      <div className={cn("min-h-0 flex-1 overflow-y-auto", collapsed ? "px-1.5" : "px-3")}>
        {!collapsed && (
          <p className="mb-2 px-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-slate">
            Workspace
          </p>
        )}
        <div className="space-y-1">
          {workspaces.map((w) => {
            const active = workspace?.id === w.id;
            return (
              <button
                key={w.id}
                type="button"
                title={w.name}
                onClick={() => {
                  setWorkspace(w);
                  resetChat();
                }}
                className={cn(
                  "nav-item flex w-full items-center rounded-xl text-left text-sm",
                  collapsed ? "justify-center px-0 py-2.5" : "gap-2.5 px-2.5 py-2",
                  active
                    ? "bg-signal-soft text-signal-deep font-semibold"
                    : "text-ink-soft hover:bg-mist",
                )}
              >
                <span
                  className={cn(
                    "flex h-7 w-7 shrink-0 items-center justify-center rounded-lg",
                    active ? "bg-white text-signal" : "bg-mist text-slate",
                  )}
                >
                  <FolderOpen className="h-3.5 w-3.5" />
                </span>
                {!collapsed && <span className="truncate">{w.name}</span>}
              </button>
            );
          })}
        </div>
        <button
          type="button"
          onClick={createWorkspace}
          title="New workspace"
          className={cn(
            "nav-item mt-1.5 flex w-full items-center rounded-xl text-sm text-slate hover:bg-mist hover:text-ink",
            collapsed ? "justify-center px-0 py-2.5" : "gap-2 px-2.5 py-2",
          )}
        >
          <Plus className="h-3.5 w-3.5" />
          {!collapsed && "New workspace"}
        </button>

        <Separator className={cn("my-4 w-auto", collapsed ? "mx-1" : "mx-0")} />

        <nav className="space-y-0.5">
          {nav.map((item) => {
            const active = pathname.startsWith(item.href);
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                title={item.label}
                className={cn(
                  "nav-item flex items-center rounded-xl text-sm font-medium",
                  collapsed ? "justify-center px-0 py-2.5" : "gap-2.5 px-3 py-2.5",
                  active
                    ? "nav-item-active bg-signal-soft/80 text-signal-deep"
                    : "text-ink-soft hover:bg-mist",
                )}
              >
                <Icon className="h-4 w-4 shrink-0" />
                {!collapsed && item.label}
              </Link>
            );
          })}
        </nav>
      </div>

      <div className={cn("shrink-0 space-y-3", collapsed ? "p-2" : "p-3")}>
        {!collapsed && (
          <div className="rounded-2xl border border-line bg-gradient-to-br from-white to-signal-soft/30 p-3.5">
            <div className="mb-2 flex items-center justify-between">
              <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate">
                Storage
              </p>
              <span className="text-[10px] font-medium text-signal-deep">
                {user?.plan || "free"}
              </span>
            </div>
            <Progress value={Math.max(8, storage.pct)} className="h-1.5" />
            <p className="mt-2 text-xs text-ink-soft">
              <span className="font-semibold text-ink">{storage.usedLabel}</span>
              {" / "}
              {storage.limitLabel} used
            </p>
            <Button
              size="sm"
              className="btn-gradient mt-3 h-8 w-full rounded-lg text-xs"
              onClick={() => router.push("/settings")}
            >
              <Sparkles className="h-3.5 w-3.5" />
              Upgrade plan
            </Button>
          </div>
        )}

        <div
          className={cn(
            "flex items-center rounded-xl",
            collapsed ? "flex-col gap-2 py-1" : "gap-2.5 px-1 py-1",
          )}
        >
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-ink text-xs font-semibold text-white">
            {initials}
          </div>
          {!collapsed && (
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium text-ink">{user?.full_name}</p>
              <p className="truncate text-[11px] text-muted-foreground">{user?.email}</p>
            </div>
          )}
          <button
            type="button"
            onClick={logout}
            className="rounded-lg p-2 text-slate hover:bg-mist hover:text-ink"
            aria-label="Sign out"
            title="Sign out"
          >
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );

  return (
    <div className="flex h-dvh overflow-hidden bg-paper">
      <aside
        className={cn(
          "relative hidden shrink-0 border-r border-line transition-[width] duration-200 ease-out md:block",
          sidebarCollapsed ? "w-[64px]" : "w-[240px]",
        )}
      >
        {sidebar(sidebarCollapsed, true)}
      </aside>

      <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
        <header className="flex shrink-0 items-center gap-3 border-b border-line bg-white px-4 py-3 md:hidden">
          <Sheet>
            <SheetTrigger asChild>
              <Button variant="outline" size="icon" aria-label="Open menu">
                <Menu className="h-4 w-4" />
              </Button>
            </SheetTrigger>
            <SheetContent side="left" className="w-[280px] p-0">
              <SheetHeader className="sr-only">
                <SheetTitle>Navigation</SheetTitle>
              </SheetHeader>
              {sidebar(false)}
            </SheetContent>
          </Sheet>
          <BrandMark size="sm" />
        </header>
        <main className="flex min-h-0 flex-1 flex-col overflow-hidden">{children}</main>
      </div>
    </div>
  );
}
