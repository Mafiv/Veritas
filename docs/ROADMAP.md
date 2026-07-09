# Veritas roadmap

**Get answers, not approximations.**

| Phase | Focus | Status |
|-------|-------|--------|
| **1** | Normalized PostgreSQL schema (40 tables, Alembic `001`–`007`) | Done |
| **2** | Backend domain services & APIs (every table has a read/write path) | Done |
| **3** | Frontend wiring for Phase 2 APIs | Done (this branch) |
| **4** | Background jobs & delivery infra | Done (this branch) |
| **5** | Retrieval productionization hooks | Done (this branch) |
| **6** | Enterprise auth & compliance execution | Done (this branch) |
| **7** | Production hardening & docs | Done (this branch) |

---

## Phase 1 — Schema

See [`docs/SCHEMA.md`](SCHEMA.md). Domains: Identity, Documents, Knowledge Graph, Chat, Billing, Audit/Notifications, Enterprise.

## Phase 2 — Backend services

Services + endpoints for members, invitations, API keys, audit, ingestion jobs, document versions/permissions/collections/entities, chat citations/feedback/comments, billing plans/meters/invoices, notifications, shared links, webhooks.

## Phase 3 — Frontend wiring

- API client covers Phase 2/6 endpoints
- Documents: ingestion status polling, entities, reprocess, share links
- Collections: create + add documents
- Settings: team invites/roles, API keys, notifications, audit log, GDPR export
- Public `/share/[token]` page

## Phase 4 — Jobs & infra

- Celery beat: orphan cleanup, webhook delivery, usage meter rollup, retention purge
- SMTP email sender when `SMTP_HOST` is set (else console)
- Real orphan-file cleanup against DB storage paths

## Phase 5 — Retrieval

- Pluggable reranker (`lexical` default, optional `cross_encoder` via sentence-transformers)
- `USE_PGVECTOR` flag + setup SQL helper; embeddings remain JSON-portable by default
- `GET /health/retrieval` introspection

## Phase 6 — Compliance

- SSO connection upsert/list (config only — IdP login flow still external)
- Retention policy upsert + purge (soft-delete documents past retain window)
- GDPR / workspace export jobs with JSON download

## Phase 7 — Hardening

- This roadmap + README API table
- Unit tests for compliance / webhook delivery helpers
- Config knobs for SMTP, pgvector, reranker backend

## Still optional later

- Production IdP hardening (Authlib discovery cache, python3-saml XML validation)
- Breaking cleanup of legacy `users.plan` / JSON citation columns
- Real MiniLM weights in production images

## Domain 7 + SSO + pgvector (this branch)

- Notification preferences CRUD + preference-aware notify
- Webhook HMAC signing, retries, delivery list API, Celery beat service
- Collections delete + document list; chat `collection_id` scope
- Full OIDC/SAML login UI (mock IdP + real token exchange path)
- Alembic `008_pgvector` + dual-write/read hybrid search

