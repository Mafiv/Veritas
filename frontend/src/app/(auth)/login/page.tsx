"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { toast } from "sonner";
import { BrandMark } from "@/components/shared/brand";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, setToken } from "@/lib/api-client";
import { useAppStore } from "@/lib/store";

export default function LoginPage() {
  const router = useRouter();
  const setUser = useAppStore((s) => s.setUser);
  const [loading, setLoading] = useState(false);
  const [ssoLoading, setSsoLoading] = useState(false);
  const [email, setEmail] = useState("");
  const [ssoHint, setSsoHint] = useState<string | null>(null);
  const [ssoEnforced, setSsoEnforced] = useState(false);

  async function onEmailBlur() {
    if (!email.includes("@")) return;
    try {
      const d = await api.ssoDiscover(email);
      if (d.sso_available) {
        setSsoHint(`SSO available via ${d.provider}`);
        setSsoEnforced(!!d.enforced);
      } else {
        setSsoHint(null);
        setSsoEnforced(false);
      }
    } catch {
      setSsoHint(null);
      setSsoEnforced(false);
    }
  }

  async function continueWithSso() {
    if (!email.includes("@")) {
      toast.error("Enter your work email first");
      return;
    }
    setSsoLoading(true);
    try {
      const start = await api.ssoStart({ email });
      window.location.href = start.authorize_url;
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "SSO start failed");
      setSsoLoading(false);
    }
  }

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (ssoEnforced) {
      await continueWithSso();
      return;
    }
    const form = new FormData(e.currentTarget);
    setLoading(true);
    try {
      const tokens = await api.login({
        email: String(form.get("email")),
        password: String(form.get("password")),
      });
      setToken(tokens.access_token);
      const me = await api.me();
      setUser(me);
      router.push("/chat");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center px-4">
      <div className="pointer-events-none absolute inset-0 veritas-grid opacity-40" />
      <div className="relative w-full max-w-md rounded-2xl border border-line bg-white/90 p-8 shadow-lift backdrop-blur">
        <BrandMark size="md" />
        <h1 className="mt-6 font-display text-2xl font-semibold text-ink">
          Welcome back
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Sign in to continue grounded research.
        </p>
        <form onSubmit={onSubmit} className="mt-6 space-y-4">
          <div className="space-y-2">
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              name="email"
              type="email"
              required
              autoComplete="email"
              placeholder="you@company.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              onBlur={onEmailBlur}
            />
            {ssoHint && (
              <p className="text-xs text-signal-deep">{ssoHint}</p>
            )}
          </div>
          {!ssoEnforced && (
            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                name="password"
                type="password"
                required={!ssoEnforced}
                autoComplete="current-password"
                minLength={8}
              />
            </div>
          )}
          {!ssoEnforced && (
            <Button type="submit" variant="signal" className="w-full" disabled={loading}>
              {loading ? "Signing in…" : "Sign in"}
            </Button>
          )}
        </form>

        <div className="my-5 flex items-center gap-3">
          <div className="h-px flex-1 bg-line" />
          <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
            or
          </span>
          <div className="h-px flex-1 bg-line" />
        </div>

        <Button
          type="button"
          variant="outline"
          className="w-full"
          disabled={ssoLoading}
          onClick={continueWithSso}
        >
          {ssoLoading ? "Redirecting…" : "Continue with SSO"}
        </Button>
        <p className="mt-2 text-center text-[11px] text-muted-foreground">
          OIDC / SAML / Google / Microsoft via your workspace connection
        </p>

        <p className="mt-6 text-center text-sm text-muted-foreground">
          New to Veritas?{" "}
          <Link href="/register" className="font-medium text-signal-deep hover:underline">
            Create an account
          </Link>
        </p>
      </div>
    </div>
  );
}
