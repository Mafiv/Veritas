import { betterAuth } from "better-auth";
import { drizzleAdapter } from "better-auth/adapters/drizzle";
import { nextCookies } from "better-auth/next-js";
import { jwt } from "better-auth/plugins";
import { db } from "@/lib/db";
import * as schema from "@/lib/db/schema";

const betterAuthUrl = process.env.BETTER_AUTH_URL || "http://localhost:3000";
const apiBase =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
const bootstrapSecret = process.env.INTERNAL_AUTH_BOOTSTRAP_SECRET || "";
const googleClientId = process.env.GOOGLE_CLIENT_ID || "";
const googleClientSecret = process.env.GOOGLE_CLIENT_SECRET || "";

async function bootstrapVeritasUser(user: {
  id: string;
  email: string;
  name: string;
  image?: string | null;
}) {
  if (!bootstrapSecret) {
    console.warn(
      "[auth] INTERNAL_AUTH_BOOTSTRAP_SECRET missing — skipping Veritas user sync",
    );
    return;
  }
  try {
    const res = await fetch(`${apiBase}/auth/bootstrap`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Internal-Secret": bootstrapSecret,
      },
      body: JSON.stringify({
        auth_user_id: user.id,
        email: user.email,
        full_name: user.name || user.email.split("@")[0],
        avatar_url: user.image || null,
      }),
    });
    if (!res.ok) {
      const text = await res.text();
      console.error("[auth] bootstrap failed", res.status, text);
    }
  } catch (err) {
    console.error("[auth] bootstrap request error", err);
  }
}

export const auth = betterAuth({
  database: drizzleAdapter(db, {
    provider: "pg",
    schema: {
      user: schema.user,
      session: schema.session,
      account: schema.account,
      verification: schema.verification,
      jwks: schema.jwks,
    },
  }),
  baseURL: betterAuthUrl,
  secret: process.env.BETTER_AUTH_SECRET,
  emailAndPassword: {
    enabled: true,
    minPasswordLength: 8,
  },
  socialProviders: {
    ...(googleClientId && googleClientSecret
      ? {
          google: {
            clientId: googleClientId,
            clientSecret: googleClientSecret,
          },
        }
      : {}),
  },
  databaseHooks: {
    user: {
      create: {
        after: async (user) => {
          await bootstrapVeritasUser(user);
        },
      },
    },
  },
  plugins: [
    jwt({
      jwt: {
        issuer: betterAuthUrl,
        audience: betterAuthUrl,
        expirationTime: "24h",
        definePayload: ({ user }) => ({
          id: user.id,
          email: user.email,
          name: user.name,
          image: user.image,
        }),
      },
    }),
    nextCookies(),
  ],
});

export type Session = typeof auth.$Infer.Session;
