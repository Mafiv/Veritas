"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  FileText,
  LogOut,
  Menu,
  MessageSquare,
  Plus,
  Settings,
  LayoutGrid,
} from "lucide-react";
import { useEffect, useState } from "react";
import { BrandMark } from "@/components/shared/brand";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { Separator } from "@/components/ui/separator";
import { api, setToken } from "@/lib/api-client";
import { useAppStore, useChatStore } from "@/lib/store";
import { cn } from "@/lib/utils";

const nav = [
  { href: "/chat", label: "Chat", icon: MessageSquare },
  { href: "/documents", label: "Documents", icon: FileText },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function DashboardShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, workspace, workspaces, setUser, setWorkspace, setWorkspaces } =
    useAppStore();
  const resetChat = useChatStore((s) => s.reset);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const me = await api.me();
        if (cancelled) return;
        setUser(me);
        const ws = await api.listWorkspaces();
        setWorkspaces(ws);
        if (!workspace && ws[0]) setWorkspace(ws[0]);
        if (workspace && !ws.find((w) => w.id === workspace.id) && ws[0]) {
          setWorkspace(ws[0]);
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

  function logout() {
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
      <div className="flex min-h-screen items-center justify-center">
        <div className="h-8 w-8 animate-pulse rounded-full bg-signal" />
      </div>
    );
  }

  const sidebar = (
    <div className="flex h-full flex-col">
      <div className="px-4 py-5">
        <BrandMark size="sm" />
        <p className="mt-1 text-xs text-muted-foreground">
          Get answers, not approximations.
        </p>
      </div>

      <div className="px-3">
        <p className="mb-2 px-2 text-[10px] font-semibold uppercase tracking-wider text-slate">
          Workspace
        </p>
        <div className="space-y-1">
          {workspaces.map((w) => (
            <button
              key={w.id}
              type="button"
              onClick={() => {
                setWorkspace(w);
                resetChat();
              }}
              className={cn(
                "flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-sm transition",
                workspace?.id === w.id
                  ? "bg-ink text-white"
                  : "text-ink-soft hover:bg-mist",
              )}
            >
              <LayoutGrid className="h-3.5 w-3.5 shrink-0" />
              <span className="truncate">{w.name}</span>
            </button>
          ))}
        </div>
        <Button
          variant="ghost"
          size="sm"
          className="mt-2 w-full justify-start gap-2 text-slate"
          onClick={createWorkspace}
        >
          <Plus className="h-3.5 w-3.5" />
          New workspace
        </Button>
      </div>

      <Separator className="my-4" />

      <nav className="flex-1 space-y-1 px-3">
        {nav.map((item) => {
          const active = pathname.startsWith(item.href);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm font-medium transition",
                active
                  ? "bg-signal-soft text-signal-deep"
                  : "text-ink-soft hover:bg-mist",
              )}
            >
              <Icon className="h-4 w-4" />
              {item.label}
            </Link>
          );
        })}
      </nav>

      <div className="border-t border-line p-4">
        <p className="truncate text-sm font-medium text-ink">{user?.full_name}</p>
        <p className="truncate text-xs text-muted-foreground">{user?.email}</p>
        <p className="mt-1 text-[10px] uppercase tracking-wider text-signal-deep">
          {user?.plan} plan
        </p>
        <Button
          variant="ghost"
          size="sm"
          className="mt-2 w-full justify-start gap-2"
          onClick={logout}
        >
          <LogOut className="h-3.5 w-3.5" />
          Sign out
        </Button>
      </div>
    </div>
  );

  return (
    <div className="flex min-h-screen">
      <aside className="hidden w-64 shrink-0 border-r border-line bg-white/70 backdrop-blur md:block">
        {sidebar}
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-3 border-b border-line bg-white/70 px-4 py-3 backdrop-blur md:hidden">
          <Sheet>
            <SheetTrigger asChild>
              <Button variant="outline" size="icon" aria-label="Open menu">
                <Menu className="h-4 w-4" />
              </Button>
            </SheetTrigger>
            <SheetContent side="left" className="p-0">
              <SheetHeader className="sr-only">
                <SheetTitle>Navigation</SheetTitle>
              </SheetHeader>
              {sidebar}
            </SheetContent>
          </Sheet>
          <BrandMark size="sm" />
        </header>
        <main className="flex min-h-0 flex-1 flex-col">{children}</main>
      </div>
    </div>
  );
}
