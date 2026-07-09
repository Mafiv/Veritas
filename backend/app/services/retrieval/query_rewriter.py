"""Query expansion and HyDE (Hypothetical Document Embeddings)."""

from __future__ import annotations

from app.core.config import get_settings
from app.services.ingestion.embedder import Embedder
from app.services.llm.client import LLMClient


class QueryRewriter:
    def __init__(self, llm: LLMClient | None = None, embedder: Embedder | None = None):
        self.llm = llm or LLMClient()
        self.embedder = embedder or Embedder()
        self.settings = get_settings()

    async def expand_queries(self, question: str, n: int = 3) -> list[str]:
        if not self.settings.enable_query_expansion:
            return [question]
        prompt = (
            "Generate {n} alternative phrasings of the search query below. "
            "Return one query per line, no numbering.\n\nQuery: {q}"
        ).format(n=n, q=question)
        text = await self.llm.complete(
            system="You rewrite search queries to improve document retrieval recall.",
            user=prompt,
            max_tokens=200,
        )
        lines = [ln.strip(" -•\t") for ln in text.splitlines() if ln.strip()]
        variants = [question]
        for line in lines:
            if line.lower() != question.lower() and line not in variants:
                variants.append(line)
            if len(variants) >= n + 1:
                break
        return variants[: n + 1]

    async def hyde_embedding(self, question: str) -> list[float]:
        """Generate a hypothetical answer and embed it for retrieval."""
        hypo = await self.llm.complete(
            system=(
                "Write a short hypothetical passage that would answer the question. "
                "Do not say you are hypothesizing — write as if it were source text."
            ),
            user=question,
            max_tokens=250,
        )
        return await self.embedder.embed_query(hypo)
