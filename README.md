# Veritas

**Get answers, not approximations.**

Veritas is a RAG-based “Chat with your data” SaaS platform. Upload PDFs, Notion exports, Markdown, or plain text — then ask questions and receive grounded, citation-backed answers.

## Architecture

- **Frontend** — Next.js (App Router), Tailwind, shadcn-style primitives, Zustand
- **API** — FastAPI with JWT auth, workspaces, documents, streaming chat, Stripe billing
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

Set `USE_MOCK_LLM=true` (default) to run without an OpenAI key. Set `OPENAI_API_KEY` and `USE_MOCK_LLM=false` for real embeddings/chat.

### 3. Frontend

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

### Full stack via Docker

```bash
docker compose up --build
```

- App: http://localhost:3000  
- API docs: http://localhost:8000/docs  

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
| POST | `/api/v1/auth/register` | Create account + personal workspace |
| POST | `/api/v1/auth/login` | JWT login |
| GET | `/api/v1/workspaces` | List workspaces |
| POST | `/api/v1/workspaces/{id}/documents` | Upload document |
| POST | `/api/v1/workspaces/{id}/chat/stream` | SSE grounded Q&A |
| GET | `/api/v1/billing/usage` | Plan usage meters |
| POST | `/api/v1/billing/checkout` | Stripe (or mock) upgrade |

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
