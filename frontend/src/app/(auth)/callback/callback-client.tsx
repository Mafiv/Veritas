"use client";

import { useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { authClient } from "@/lib/auth-client";
import { api, setToken } from "@/lib/api-client";
import { useAppStore } from "@/lib/store";

/**
 * After Google OAuth, Better Auth redirects here with a session cookie.
 * Exchange session for a JWT and load the Veritas user before entering the app.
 */
export default function AuthCallbackClient() {
  const router = useRouter();
  const params = useSearchParams();
  const setUser = useAppStore((s) => s.setUser);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const next = params.get("next") || "/chat";
      try {
        const session = await authClient.getSession();
        if (!session.data?.session) {
          router.replace("/login");
          return;
        }
        const { data, error } = await authClient.token();
        if (error || !data?.token) {
          throw new Error(error?.message || "Failed to obtain API token");
        }
        setToken(data.token);
        await api.sync();
        let me = null;
        for (let i = 0; i < 5; i++) {
          try {
            me = await api.me();
            break;
          } catch {
            await new Promise((r) => setTimeout(r, 400));
          }
        }
        if (!me) throw new Error("Account provisioning timed out");
        if (!cancelled) {
          setUser(me);
          router.replace(next);
        }
      } catch {
        if (!cancelled) router.replace("/login");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [params, router, setUser]);

  return (
    <div className="flex min-h-screen items-center justify-center text-sm text-muted-foreground">
      Completing sign-in…
    </div>
  );
}
