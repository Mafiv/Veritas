# Veritas

**Get answers, not approximations.**

Veritas is a RAG-based “Chat with your data” SaaS platform. Upload PDFs, Notion exports, Markdown, or plain text — then ask questions and receive grounded, citation-backed answers.

## Architecture

- **Frontend** — Next.js (App Router), Tailwind, shadcn-style primitives, Zustand
- **API** — FastAPI with Better Auth (Next.js) + JWKS JWT verification, workspaces, documents, streaming chat, Stripe billing
- **Retrieval** — Hybrid vector + BM25 search, Reciprocal Rank Fusion, HyDE, query expansion, cross-encoder-style reranking
- **Data** — PostgreSQL (+ pgvector-ready), Redis, local/S3 object storage, Celery workers

```
Client (Next.js) → FastAPI → Ingestion / RAG Engine / Billing
                           → PostgreSQL · Redis · Object Storage
                           → Celery (embeddings, cleanup)
```

## Quick start

### Prerequisites

- Python 3.11+
- Node.js 20+
- Docker (optional, for Postgres/Redis)

### 1. Infrastructure

```bash
docker compose up -d db redis
```

Or point `DATABASE_URL` / `REDIS_URL` at existing services.

### 2. Backend

```bash
cd backend
cp .env.example .env
pip install -e ".[dev]"
# For local SQLite-free Postgres:
# DATABASE_URL=postgresql+asyncpg://veritas:veritas@localhost:5432/veritas
uvicorn app.main:app --reload --port 8000
```

Set `USE_MOCK_LLM=true` (default) to run without any LLM API keys. Set `USE_MOCK_LLM=false` and configure a provider for real chat completions (embeddings still use `OPENAI_API_KEY` separately).

### Switching LLM providers

Chat completions are routed through [LiteLLM](https://docs.litellm.ai/). Switch providers by changing `LLM_MODEL` and the matching API key in `backend/.env` — no code changes required.

| Provider | `LLM_MODEL` example | API key env var |
|----------|-------------------|-----------------|
| OpenAI | `openai/gpt-4o` | `OPENAI_API_KEY` |
| Google Gemini | `gemini/gemini-1.5-pro` | `GEMINI_API_KEY` |
| GitHub Models | `github/gpt-4o-mini` | `GITHUB_API_KEY` (GitHub PAT; free tier, rate-limited — good for local testing) |
| Anthropic | `anthropic/claude-sonnet-4-6` | `ANTHROPIC_API_KEY` |

```bash
# Example: Gemini
LLM_MODEL=gemini/gemini-1.5-pro
GEMINI_API_KEY=your-key-here
USE_MOCK_LLM=false
```

### 3. Authentication (Better Auth)

Login/register are owned by **Better Auth** in the Next.js app (email/password + optional Google OAuth). FastAPI verifies Better Auth JWTs via JWKS and keeps Veritas `users` / workspaces / API keys.

1. Copy env files and set a shared bootstrap secret (same value in both):

```bash
# backend/.env
BETTER_AUTH_URL=http://localhost:3000
INTERNAL_AUTH_BOOTSTRAP_SECRET=change-me-bootstrap-secret

# frontend/.env.local
BETTER_AUTH_SECRET=change-me-to-a-long-random-secret
BETTER_AUTH_URL=http://localhost:3000
DATABASE_URL=postgresql://veritas:veritas@localhost:5432/veritas
INTERNAL_AUTH_BOOTSTRAP_SECRET=change-me-bootstrap-secret
NEXT_PUBLIC_BETTER_AUTH_URL=http://localhost:3000
```

2. Apply DB schemas:

```bash
cd backend && alembic upgrade head
cd ../frontend && npm run db:push
```

3. Optional Google OAuth — create credentials in Google Cloud Console with redirect URI:

`http://localhost:3000/api/auth/callback/google`

Then set `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `NEXT_PUBLIC_GOOGLE_AUTH_ENABLED=true` in `frontend/.env.local`.

### 4. Frontend

```bash
cd frontend
cp .env.example .env.local
npm install
npm run db:push
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

### Full stack via Docker

Runs Postgres, Redis, migrations (Alembic + Better Auth tables), API, and frontend dev server:

```bash
# Optional: copy shared secrets for compose variable substitution
cp .env.docker.example .env

# First run builds images (~2–5 min). Later runs are much faster:
docker compose up

# Rebuild only when dependencies or Dockerfiles change:
docker compose up --build

# Background jobs (embeddings, etc.) — optional:
docker compose --profile worker up

# Production-style Next.js build (slower):
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build
```

- App: http://localhost:3000  
- API docs: http://localhost:8000/docs  

Compose sets Docker-internal URLs automatically (`BETTER_AUTH_INTERNAL_URL`, `INTERNAL_API_URL`). Browser-facing URLs stay `http://localhost:3000` and `http://localhost:8000`.

To reset the database: `docker compose down -v` (destroys Postgres volume).

## Key features

| Area | Capabilities |
|------|----------------|
| Ingestion | PDF / MD / Notion HTML / DOCX / text, semantic chunking, summaries, suggested questions |
| Retrieval | Hybrid search, RRF, HyDE, multi-query expansion, reranking |
| Chat | SSE streaming, inline citations, conversation memory, feedback |
| Workspaces | Multi-tenant workspaces, Owner/Editor/Viewer roles |
| Billing | Stripe checkout + webhooks, free/pro/team quotas, usage metering |

## Design system (frontend)

Opinionated **archival ink + signal teal** identity — Space Grotesk (display) + Source Sans 3 (body). Tokens live in `frontend/src/app/globals.css` (`--ink`, `--signal`, spacing/radius/shadow scales). Not default zinc shadcn, not cream/serif, not purple neon.

## API overview

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/auth/bootstrap` | Provision user + personal workspace (Better Auth hook, internal secret) |
| POST | `/api/v1/auth/sync` | Provision/link user from a Better Auth JWT (rate-limited per IP) |
| GET | `/api/v1/auth/me` | Current user |
| GET | `/api/v1/workspaces` | List workspaces |
| GET/POST/PATCH/DELETE | `/api/v1/workspaces/{id}/members` | Member management (owner) |
| POST | `/api/v1/workspaces/{id}/invitations` | Invite by email |
| POST | `/api/v1/invitations/{token}/accept` | Accept invitation |
| POST | `/api/v1/workspaces/{id}/api-keys` | Create workspace API key (`vtk_…`) |
| POST | `/api/v1/workspaces/{id}/documents` | Upload document (+ ingestion job) |
| GET | `/api/v1/workspaces/{id}/documents/{doc}/status` | Ingestion job status |
| GET | `/api/v1/workspaces/{id}/documents/{doc}/versions` | Document versions |
| GET | `/api/v1/workspaces/{id}/documents/{doc}/questions` | Suggested questions |
| GET | `/api/v1/workspaces/{id}/documents/{doc}/entities` | Extracted entities |
| GET/POST | `/api/v1/workspaces/{id}/collections` | Document collections |
| POST | `/api/v1/workspaces/{id}/chat/stream` | SSE grounded Q&A |
| POST | `/api/v1/workspaces/{id}/threads/{tid}/comments` | Thread comments |
| GET | `/api/v1/workspaces/{id}/audit-logs` | Audit log (owner) |
| GET | `/api/v1/notifications` | In-app notifications |
| GET | `/api/v1/billing/plans` | Plans from DB |
| GET | `/api/v1/billing/usage` | Plan usage meters |
| GET | `/api/v1/billing/invoices` | Local invoice history |
| POST | `/api/v1/billing/checkout` | Stripe (or mock) upgrade |
| POST | `/api/v1/workspaces/{id}/shared-links` | Expiring share links |
| POST | `/api/v1/workspaces/{id}/webhooks` | Outbound webhooks (owner) |
| PUT | `/api/v1/workspaces/{id}/sso` | SSO connection config (owner) |
| PUT | `/api/v1/workspaces/{id}/retention-policies` | Retention policy upsert |
| POST | `/api/v1/exports` | GDPR / workspace export job |
| GET | `/health/retrieval` | Retrieval / pgvector introspection |

Product phases (schema → services → UI → jobs → retrieval → compliance → hardening) are documented in [`docs/ROADMAP.md`](docs/ROADMAP.md).

## Tests

```bash
cd backend
pytest tests/unit -q
```

```bash
cd frontend
npm run build
```

## Project layout

```
backend/app/          FastAPI app, services, tasks
frontend/src/app/     Next.js routes (landing, auth, dashboard)
docker-compose.yml    db, redis, api, worker, frontend
docs/SCHEMA.md        PostgreSQL 3NF schema (40 tables) + Alembic guide
```

## Database schema

See [`docs/SCHEMA.md`](docs/SCHEMA.md) for the full 40-table ERD, soft-delete policy, and domain migrations (`alembic upgrade head`).

## License

MIT
