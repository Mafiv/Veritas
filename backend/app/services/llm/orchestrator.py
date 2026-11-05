"""RAG orchestrator — retrieval + grounded answer generation."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import AsyncIterator
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.schemas import Citation
from app.services.ingestion.embedder import Embedder
from app.services.llm.client import LLMClient
from app.services.retrieval.hybrid_search import HybridSearcher, ScoredChunk
from app.services.retrieval.query_rewriter import QueryRewriter
from app.services.retrieval.reranker import build_reranker

SYSTEM_PROMPT = """You are Veritas, a precise research assistant.
Answer ONLY using the provided source excerpts.
Every factual claim must include an inline citation like [1], [2] matching the source numbers.
If the sources do not contain enough information, say so clearly.
Be concise, structured, and never invent facts not present in the sources."""


@dataclass
class RAGResult:
    answer: str
    citations: list[Citation]
    latency_ms: float
    retrieved_count: int


class RAGOrchestrator:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.embedder = Embedder()
        self.searcher = HybridSearcher(self.embedder)
        self.rewriter = QueryRewriter(embedder=self.embedder)
        self.reranker = build_reranker()
        self.llm = LLMClient()

    async def retrieve(
        self,
        db: AsyncSession,
        *,
        workspace_id: UUID,
        question: str,
        document_ids: list[UUID] | None = None,
        use_hyde: bool = True,
        use_rerank: bool = True,
    ) -> list[ScoredChunk]:
        query_embedding = None
        if use_hyde and self.settings.enable_hyde:
            try:
                query_embedding = await self.rewriter.hyde_embedding(question)
            except Exception:
                query_embedding = await self.embedder.embed_query(question)
        else:
            query_embedding = await self.embedder.embed_query(question)

        # Multi-query expansion — merge unique chunks by id
        queries = await self.rewriter.expand_queries(question, n=3)
        seen: dict[UUID, ScoredChunk] = {}
        for q in queries:
            emb = query_embedding if q == question else await self.embedder.embed_query(q)
            hits = await self.searcher.search(
                db,
                workspace_id=workspace_id,
                query=q,
                query_embedding=emb,
                document_ids=document_ids,
            )
            for hit in hits:
                existing = seen.get(hit.chunk.id)
                if existing is None or hit.score > existing.score:
                    seen[hit.chunk.id] = hit

        candidates = sorted(seen.values(), key=lambda x: x.score, reverse=True)
        candidates = candidates[: self.settings.retrieval_top_k]

        if use_rerank and self.settings.enable_reranker and candidates:
            candidates = await self.reranker.rerank(
                question, candidates, top_k=self.settings.rerank_top_k
            )
        else:
            candidates = candidates[: self.settings.rerank_top_k]
        return candidates

    def build_citations(self, scored: list[ScoredChunk]) -> list[Citation]:
        citations: list[Citation] = []
        for i, s in enumerate(scored, start=1):
            snippet = s.chunk.content.strip().replace("\n", " ")
            if len(snippet) > 280:
                snippet = snippet[:277] + "..."
            citations.append(
                Citation(
                    chunk_id=s.chunk.id,
                    document_id=s.document.id,
                    document_name=s.document.original_filename,
                    page_number=s.chunk.page_number,
                    heading=s.chunk.heading,
                    snippet=snippet,
                    score=round(s.score, 4),
                    citation_index=i,
                )
            )
        return citations

    def build_prompt(
        self,
        question: str,
        scored: list[ScoredChunk],
        history: list[tuple[str, str]] | None = None,
    ) -> str:
        context_blocks = []
        for i, s in enumerate(scored, start=1):
            header = f"[{i}] {s.document.original_filename}"
            if s.chunk.page_number:
                header += f" (p.{s.chunk.page_number})"
            if s.chunk.heading:
                header += f" — {s.chunk.heading}"
            context_blocks.append(f"{header}\n{s.chunk.content}")

        history_block = ""
        if history:
            turns = []
            for role, content in history[-6:]:
                turns.append(f"{role.upper()}: {content}")
            history_block = "Conversation so far:\n" + "\n".join(turns) + "\n\n"

        sources = "\n\n".join(context_blocks) if context_blocks else "(No sources retrieved)"
        return (
            f"{history_block}"
            f"Sources:\n{sources}\n\n"
            f"Question: {question}\n\n"
            "Answer with inline citations [n] referring to the sources above."
        )

    async def answer(
        self,
        db: AsyncSession,
        *,
        workspace_id: UUID,
        question: str,
        document_ids: list[UUID] | None = None,
        history: list[tuple[str, str]] | None = None,
        use_hyde: bool = True,
        use_rerank: bool = True,
    ) -> RAGResult:
        started = time.perf_counter()
        scored = await self.retrieve(
            db,
            workspace_id=workspace_id,
            question=question,
            document_ids=document_ids,
            use_hyde=use_hyde,
            use_rerank=use_rerank,
        )
        citations = self.build_citations(scored)
        prompt = self.build_prompt(question, scored, history)
        answer = await self.llm.complete(system=SYSTEM_PROMPT, user=prompt)
        latency = (time.perf_counter() - started) * 1000
        return RAGResult(
            answer=answer,
            citations=citations,
            latency_ms=latency,
            retrieved_count=len(scored),
        )

    async def stream_answer(
        self,
        db: AsyncSession,
        *,
        workspace_id: UUID,
        question: str,
        document_ids: list[UUID] | None = None,
        history: list[tuple[str, str]] | None = None,
        use_hyde: bool = True,
        use_rerank: bool = True,
    ) -> AsyncIterator[dict]:
        """Yield SSE-friendly event dicts: citations, token, done."""
        started = time.perf_counter()
        scored = await self.retrieve(
            db,
            workspace_id=workspace_id,
            question=question,
            document_ids=document_ids,
            use_hyde=use_hyde,
            use_rerank=use_rerank,
        )
        citations = self.build_citations(scored)
        yield {
            "event": "citations",
            "data": {"citations": [c.model_dump(mode="json") for c in citations]},
        }

        prompt = self.build_prompt(question, scored, history)
        full = ""
        async for token in self.llm.stream(system=SYSTEM_PROMPT, user=prompt):
            full += token
            yield {"event": "token", "data": {"token": token}}

        latency = (time.perf_counter() - started) * 1000
        yield {
            "event": "done",
            "data": {
                "answer": full,
                "citations": [c.model_dump(mode="json") for c in citations],
                "latency_ms": latency,
                "retrieved_count": len(scored),
            },
        }
