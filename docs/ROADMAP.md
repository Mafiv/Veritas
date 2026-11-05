# Veritas roadmap

## Done

| Area | What exists | Evidence |
|---|---|---|
| Retrieval | pgvector HNSW + Postgres FTS candidates scored with BM25, RRF fusion, lexical rerank, optional cross-encoder | `backend/evaluation/RESULTS.md`, `tests/integration/test_hybrid_search_pg.py` |
| Answering | Follow-up condensation, token-budgeted context, untrusted-source prompt, citation verification, abstention, retrieval trace | `tests/unit/test_orchestrator.py` |
| Ingestion | Celery worker, 202 uploads, size/type checks, contextual embeddings, best-effort enrichment | `tests/integration/test_api_flow.py`, `tests/unit/test_upload.py` |
| Security | Better Auth JWKS only, verified-email account linking, Redis rate limits, prod config validation, tenant-isolation sweep | `tests/integration/test_tenant_isolation.py`, `test_account_linking.py` |
| Quality gates | ruff, mypy (core), unit + integration tests, `alembic check`, retrieval eval regression gate, frontend lint/types/build | `.github/workflows/ci.yml` |

## Next

1. **Answer faithfulness eval**: an LLM judge for "is every claim supported by
   its cited source", run nightly with a real model.
2. **Evaluate HyDE and multi-query** with a real LLM, and enable them only if
   they beat their latency cost.
3. **A larger and more varied eval set** (PDFs with tables, longer documents),
   plus tuning of the hybrid fusion weights on it.
4. **Keyword stage at scale**: cap or sample candidates for very common terms,
   or evaluate a native BM25 index (e.g. ParadeDB `pg_search`).
5. **Frontend tests**: Vitest for the SSE parser and citation rendering, and a
   Playwright upload → ask → cite flow against mock mode.
6. **Observability**: OpenTelemetry spans per RAG stage, Prometheus metrics,
   token and cost tracking per message.
7. **Highlight cited passages** in the source viewer (store chunk character
   offsets).

## Not implemented (configuration only)

- SSO: connections can be stored, but there is no OIDC/SAML login flow.
- Retention policies: purge job exists; there is no UI.
- Knowledge-graph entities: extracted heuristically at ingestion, not used in retrieval.
