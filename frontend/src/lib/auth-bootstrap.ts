import { authClient } from "@/lib/auth-client";
import { api, setToken } from "@/lib/api-client";

async function syncApiToken() {
  const { data, error } = await authClient.token();
  if (error || !data?.token) {
    throw new Error(error?.message || "Failed to obtain API token");
  }
  setToken(data.token);
  return data.token;
}

/**
 * After Better Auth signup/login, obtain a JWT and ensure the Veritas user row
 * exists. Retries cover bootstrap-hook races and brief JWT issuance lag.
 */
export async function ensureVeritasSession(retries = 5, delayMs = 400) {
  let lastError: unknown;
  for (let i = 0; i < retries; i++) {
    try {
      await syncApiToken();
      await api.sync();
      return await api.me();
    } catch (err) {
      lastError = err;
      if (i + 1 < retries) {
        await new Promise((r) => setTimeout(r, delayMs * (i + 1)));
      }
    }
  }
  throw lastError instanceof Error
    ? lastError
    : new Error("Account provisioning timed out");
}
