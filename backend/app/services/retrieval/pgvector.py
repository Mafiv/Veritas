"""Runtime description of the retrieval stack (served by GET /health/retrieval)."""

from __future__ import annotations

from typing import Any

from app.core.config import get_settings


def describe_vector_strategy() -> dict[str, Any]:
    settings = get_settings()
    return {
        "vector_store": "postgres/pgvector",
        "vector_index": "hnsw (vector_cosine_ops, m=16, ef_construction=64)",
        "hnsw_ef_search": settings.hnsw_ef_search,
        "keyword_index": "gin on generated tsvector ('english')",
        "fusion": "weighted reciprocal rank fusion (k=60)",
        "candidates_per_index": settings.retrieval_candidates,
        "embedding_provider": settings.embedding_provider,
        "embedding_model": settings.embedding_model,
        "embedding_dimensions": settings.embedding_dimensions,
    }
