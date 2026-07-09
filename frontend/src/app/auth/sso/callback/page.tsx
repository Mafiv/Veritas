"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { BrandMark } from "@/components/shared/brand";
import { api, setToken } from "@/lib/api-client";
import { useAppStore } from "@/lib/store";

export default function SsoCallbackPage() {
  const router = useRouter();
  const setUser = useAppStore((s) => s.setUser);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const hash = typeof window !== "undefined" ? window.location.hash.slice(1) : "";
    const params = new URLSearchParams(hash);
    const access = params.get("access_token");
    if (!access) {
      setError("Missing access token from identity provider");
      return;
    }
    (async () => {
      try {
        setToken(access);
        const me = await api.me();
        setUser(me);
        router.replace("/chat");
      } catch (err) {
        setError(err instanceof Error ? err.message : "SSO callback failed");
      }
    })();
  }, [router, setUser]);

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-paper px-6">
      <BrandMark size="md" />
      <p className="mt-8 text-sm text-slate">
        {error || "Completing SSO sign-in…"}
      </p>
    </div>
  );
}
