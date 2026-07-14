This is the Veritas frontend (Next.js App Router).

## Environment

Create a local env file from the example:

```bash
cp .env.example .env.local
```

Required variables:

- `NEXT_PUBLIC_API_URL` (default: `http://localhost:8000/api/v1`)
- `BETTER_AUTH_SECRET`, `BETTER_AUTH_URL`, `DATABASE_URL`
- `INTERNAL_AUTH_BOOTSTRAP_SECRET` (must match backend)

Optional Google OAuth:

- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`
- `NEXT_PUBLIC_GOOGLE_AUTH_ENABLED=true`
- Redirect URI: `http://localhost:3000/api/auth/callback/google`

Apply Better Auth tables once:

```bash
# from repo with docker Postgres running:
docker exec -i veritas-db-1 psql -U veritas -d veritas < scripts/create-better-auth-tables.sql
```

Integration note:

- Backend `FRONTEND_URL`, `CORS_ORIGINS`, and `BETTER_AUTH_URL` should match your frontend origin.

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.
