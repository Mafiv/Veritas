"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { toast } from "sonner";
import { BrandMark } from "@/components/shared/brand";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { authClient } from "@/lib/auth-client";
import { api, setToken } from "@/lib/api-client";
import { useAppStore } from "@/lib/store";

async function syncApiToken() {
  const { data, error } = await authClient.token();
  if (error || !data?.token) {
    throw new Error(error?.message || "Failed to obtain API token");
  }
  setToken(data.token);
  return data.token;
}

export default function LoginPage() {
  const router = useRouter();
  const setUser = useAppStore((s) => s.setUser);
  const [loading, setLoading] = useState(false);
  const googleEnabled = Boolean(process.env.NEXT_PUBLIC_GOOGLE_AUTH_ENABLED === "true");

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    setLoading(true);
    try {
      const { error } = await authClient.signIn.email({
        email: String(form.get("email")),
        password: String(form.get("password")),
      });
      if (error) {
        throw new Error(error.message || "Login failed");
      }
      await syncApiToken();
      await api.sync();
      const me = await api.me();
      setUser(me);
      router.push("/chat");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  async function onGoogle() {
    setLoading(true);
    try {
      await authClient.signIn.social({
        provider: "google",
        callbackURL: "/callback?next=/chat",
      });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Google sign-in failed");
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
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="password">Password</Label>
            <Input
              id="password"
              name="password"
              type="password"
              required
              autoComplete="current-password"
              minLength={8}
            />
          </div>
          <Button type="submit" variant="signal" className="w-full" disabled={loading}>
            {loading ? "Signing in…" : "Sign in"}
          </Button>
        </form>
        {googleEnabled && (
          <>
            <div className="my-4 flex items-center gap-3 text-xs text-muted-foreground">
              <span className="h-px flex-1 bg-line" />
              or
              <span className="h-px flex-1 bg-line" />
            </div>
            <Button
              type="button"
              variant="outline"
              className="w-full"
              disabled={loading}
              onClick={onGoogle}
            >
              Continue with Google
            </Button>
          </>
        )}
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
