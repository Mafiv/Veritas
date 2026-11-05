"""Hybrid retrieval: pgvector HNSW + Postgres full-text candidates scored with BM25, fused with RRF.

Both rankings run inside Postgres and return a bounded candidate list
(``settings.retrieval_candidates`` each), so query cost no longer grows with
the size of the workspace. Only the fused top-k rows are loaded as ORM objects.

``BM25Index`` is kept as a small in-memory reference implementation; the
evaluation harness uses it to reproduce the pre-pgvector baseline.
"""

from __future__ import annotations

import math
import re
import time
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import Text, cast, func, select, text
from sqlalchemy.dialects.postgresql import TSQUERY
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.domain import Document, DocumentChunk
from app.services.ingestion.embedder import Embedder

SearchMode = Literal["hybrid", "vector", "keyword"]


@dataclass
class ScoredChunk:
    chunk: DocumentChunk
    document: Document
    score: float
    vector_score: float = 0.0  # cosine similarity (1 - cosine distance)
    keyword_score: float = 0.0  # BM25 over GIN-matched candidates


TOKEN_RE = re.compile(r"[a-z0-9]+", re.I)


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in TOKEN_RE.findall(text)]


class BM25Index:
    """In-memory Okapi BM25 (reference / eval baseline only, O(corpus) per query)."""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.docs: list[list[str]] = []
        self.doc_lens: list[int] = []
        self.df: Counter[str] = Counter()
        self.avgdl = 0.0
        self.N = 0

    def fit(self, corpus: list[str]) -> None:
        self.docs = [tokenize(doc) for doc in corpus]
        self.doc_lens = [len(d) for d in self.docs]
        self.N = len(self.docs)
        self.avgdl = sum(self.doc_lens) / self.N if self.N else 0.0
        self.df = Counter()
        for doc in self.docs:
            for term in set(doc):
                self.df[term] += 1

    def score(self, query: str) -> list[float]:
        q_terms = tokenize(query)
        scores = [0.0] * self.N
        if not self.N or not q_terms:
            return scores
        for i, doc in enumerate(self.docs):
            tf = Counter(doc)
            dl = self.doc_lens[i] or 1
            s = 0.0
            for term in q_terms:
                if term not in tf:
                    continue
                n_qi = self.df.get(term, 0)
                idf = math.log(1 + (self.N - n_qi + 0.5) / (n_qi + 0.5))
                freq = tf[term]
                denom = freq + self.k1 * (1 - self.b + self.b * dl / (self.avgdl or 1))
                s += idf * (freq * (self.k1 + 1)) / denom
            scores[i] = s
        return scores


def reciprocal_rank_fusion(
    ranked_lists: Sequence[Sequence[Any]],
    *,
    k: int = 60,
    weights: Sequence[float] | None = None,
) -> dict[Any, float]:
    """Merge ranked lists of ids via weighted RRF: sum(w / (k + rank))."""
    scores: dict[Any, float] = defaultdict(float)
    weights = weights or [1.0] * len(ranked_lists)
    for weight, ranking in zip(weights, ranked_lists):
        for rank, item in enumerate(ranking):
            scores[item] += weight * (1.0 / (k + rank + 1))
    return dict(scores)


def keyword_tsquery(query: str) -> Any:
    """OR-semantics tsquery from free text.

    ``plainto_tsquery`` ANDs every term, which almost never matches a natural
    language question in full. We keep its stemming/stop-word handling and
    swap ``&`` for ``|`` so any matching term contributes, ranked by
    ``ts_rank_cd``.
    """
    plain = cast(func.plainto_tsquery("english", query), Text)
    return func.to_tsquery("english", func.replace(plain, "&", "|"))


STATS_TTL_SECONDS = 60.0
_STATS_CACHE: dict[UUID, tuple[float, int, float]] = {}
_TSV_ENTRY = re.compile(r"'((?:[^']|'')+)'(?::([0-9A-D,]+))?")


def _quote(lexeme: str) -> str:
    return "'" + lexeme.replace("'", "''") + "'"


def _term_frequencies(tsv_text: str, lexemes: list[str]) -> dict[str, int]:
    """Occurrences of each query lexeme, read from a tsvector's text form."""
    wanted = set(lexemes)
    out: dict[str, int] = {}
    for match in _TSV_ENTRY.finditer(tsv_text):
        lexeme = match.group(1).replace("''", "'")
        if lexeme in wanted:
            positions = match.group(2)
            out[lexeme] = len(positions.split(",")) if positions else 1
    return out


class HybridSearcher:
    def __init__(self, embedder: Embedder | None = None):
        self.embedder = embedder or Embedder()
        self.settings = get_settings()

    def _scope(self, stmt: Any, workspace_id: UUID, document_ids: list[UUID] | None) -> Any:
        live_docs = select(Document.id).where(
            Document.workspace_id == workspace_id, Document.deleted_at.is_(None)
        )
        stmt = stmt.where(DocumentChunk.workspace_id == workspace_id).where(
            DocumentChunk.document_id.in_(live_docs)
        )
        if document_ids is not None:
            stmt = stmt.where(DocumentChunk.document_id.in_(document_ids))
        return stmt

    async def vector_candidates(
        self,
        db: AsyncSession,
        *,
        workspace_id: UUID,
        query_embedding: Sequence[float],
        document_ids: list[UUID] | None,
        limit: int,
    ) -> list[tuple[UUID, float]]:
        """Top-N chunk ids by cosine similarity via the HNSW index."""
        # Filtered HNSW scans can return fewer than LIMIT rows when the filter
        # is selective (small workspace in a big table). pgvector >= 0.8 keeps
        # scanning the graph until enough rows pass the filter.
        await db.execute(text(f"SET LOCAL hnsw.ef_search = {int(self.settings.hnsw_ef_search)}"))
        await db.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))
        distance = DocumentChunk.embedding.cosine_distance(list(query_embedding))
        stmt = select(DocumentChunk.id, distance.label("distance")).where(
            DocumentChunk.embedding.is_not(None)
        )
        stmt = self._scope(stmt, workspace_id, document_ids).order_by(distance).limit(limit)
        rows = (await db.execute(stmt)).all()
        return [(row.id, 1.0 - float(row.distance)) for row in rows]

    async def keyword_candidates(
        self,
        db: AsyncSession,
        *,
        workspace_id: UUID,
        query: str,
        document_ids: list[UUID] | None,
        limit: int,
    ) -> list[tuple[UUID, float]]:
        """Top-N chunk ids by Okapi BM25, with candidates from the GIN index.

        Postgres' ``ts_rank_cd`` has no IDF, so frequent words weigh as much as
        rare ones (it scored R@5 0.78 vs 0.90 for BM25 in our eval). We keep
        Postgres for candidate generation (``@@`` on the GIN index) and score
        those candidates with BM25 using per-term document frequencies, which
        are cheap GIN-backed counts for just the query's lexemes.
        """
        lexemes = await self._query_lexemes(db, query)
        if not lexemes:
            return []
        tsq = keyword_tsquery(query)
        pool = select(
            DocumentChunk.id,
            cast(DocumentChunk.content_tsv, Text).label("tsv"),
            DocumentChunk.token_count,
        ).where(DocumentChunk.content_tsv.op("@@")(tsq))
        pool = (
            self._scope(pool, workspace_id, document_ids)
            .order_by(func.ts_rank_cd(DocumentChunk.content_tsv, tsq, 1).desc(), DocumentChunk.id)
            .limit(max(limit * 4, 200))
        )
        rows = (await db.execute(pool)).all()
        if not rows:
            return []

        n_docs, avgdl = await self._workspace_stats(db, workspace_id)
        df = await self._document_frequencies(db, workspace_id, lexemes)
        k1, b = 1.2, 0.75
        idf = {
            t: math.log(1 + (n_docs - df.get(t, 0) + 0.5) / (df.get(t, 0) + 0.5)) for t in lexemes
        }
        scored: list[tuple[UUID, float]] = []
        for row in rows:
            tf = _term_frequencies(row.tsv, lexemes)
            dl = max(1, row.token_count or 1)
            score = sum(
                idf[t] * f * (k1 + 1) / (f + k1 * (1 - b + b * dl / avgdl)) for t, f in tf.items()
            )
            scored.append((row.id, score))
        scored.sort(key=lambda x: (-x[1], str(x[0])))
        return scored[:limit]

    @staticmethod
    async def _query_lexemes(db: AsyncSession, query: str) -> list[str]:
        """Query terms after Postgres' own english stemming/stop-words (same as the index)."""
        arr = func.tsvector_to_array(func.to_tsvector("english", query))
        return list((await db.execute(select(arr))).scalar_one() or [])

    async def _workspace_stats(self, db: AsyncSession, workspace_id: UUID) -> tuple[int, float]:
        """(chunk count, mean chunk length) — cached briefly; only BM25 normalisation uses it."""
        cached = _STATS_CACHE.get(workspace_id)
        if cached and cached[0] > time.monotonic():
            return cached[1], cached[2]
        n, avgdl = (
            await db.execute(
                select(func.count(), func.avg(DocumentChunk.token_count)).where(
                    DocumentChunk.workspace_id == workspace_id
                )
            )
        ).one()
        stats = (int(n or 0), float(avgdl or 1.0))
        _STATS_CACHE[workspace_id] = (time.monotonic() + STATS_TTL_SECONDS, *stats)
        return stats

    @staticmethod
    async def _document_frequencies(
        db: AsyncSession, workspace_id: UUID, lexemes: list[str]
    ) -> dict[str, int]:
        cols = [
            func.count()
            .filter(DocumentChunk.content_tsv.op("@@")(cast(func.quote_literal(t), TSQUERY)))
            .label(f"t{i}")
            for i, t in enumerate(lexemes)
        ]
        row = (
            await db.execute(
                select(*cols).where(
                    DocumentChunk.workspace_id == workspace_id,
                    DocumentChunk.content_tsv.op("@@")(
                        func.to_tsquery("simple", " | ".join(_quote(t) for t in lexemes))
                    ),
                )
            )
        ).one()
        return {t: int(row[i]) for i, t in enumerate(lexemes)}

    async def search(
        self,
        db: AsyncSession,
        *,
        workspace_id: UUID,
        query: str,
        query_embedding: Sequence[float] | None = None,
        document_ids: list[UUID] | None = None,
        top_k: int | None = None,
        mode: SearchMode = "hybrid",
    ) -> list[ScoredChunk]:
        top_k = top_k or self.settings.retrieval_top_k
        if document_ids is not None and not document_ids:
            return []
        n = max(self.settings.retrieval_candidates, top_k)

        vector_hits: list[tuple[UUID, float]] = []
        keyword_hits: list[tuple[UUID, float]] = []
        if mode in ("hybrid", "vector"):
            if query_embedding is None:
                query_embedding = await self.embedder.embed_query(query)
            vector_hits = await self.vector_candidates(
                db,
                workspace_id=workspace_id,
                query_embedding=query_embedding,
                document_ids=document_ids,
                limit=n,
            )
        if mode in ("hybrid", "keyword"):
            keyword_hits = await self.keyword_candidates(
                db, workspace_id=workspace_id, query=query, document_ids=document_ids, limit=n
            )

        vector_scores = dict(vector_hits)
        keyword_scores = dict(keyword_hits)
        if mode == "vector":
            fused = vector_scores
        elif mode == "keyword":
            fused = keyword_scores
        else:
            fused = reciprocal_rank_fusion(
                [[cid for cid, _ in vector_hits], [cid for cid, _ in keyword_hits]],
                weights=[self.settings.hybrid_vector_weight, self.settings.hybrid_bm25_weight],
            )
        ranked = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)[:top_k]
        if not ranked:
            return []

        ids = [cid for cid, _ in ranked]
        rows = (
            await db.execute(
                select(DocumentChunk, Document)
                .join(Document, Document.id == DocumentChunk.document_id)
                .where(DocumentChunk.id.in_(ids))
            )
        ).all()
        by_id = {chunk.id: (chunk, doc) for chunk, doc in rows}

        results: list[ScoredChunk] = []
        for cid, score in ranked:
            if cid not in by_id:
                continue
            chunk, doc = by_id[cid]
            results.append(
                ScoredChunk(
                    chunk=chunk,
                    document=doc,
                    score=score,
                    vector_score=vector_scores.get(cid, 0.0),
                    keyword_score=keyword_scores.get(cid, 0.0),
                )
            )
        return results
