"""Query transformations applied before retrieval.

- ``condense``: rewrite a follow-up ("and the second one?") into a standalone
  question using the conversation, so retrieval sees what the user means.
- ``expand_queries``: multi-query paraphrases (optional, off by default).
- ``hyde_embedding``: Hypothetical Document Embeddings (optional, off by default).

Expansion and HyDE each add an LLM round-trip before the first token; they are
enabled only if the evaluation harness shows they pay for that latency.
"""

from __future__ import annotations

from app.core.config import get_settings
from app.services.ingestion.embedder import Embedder
from app.services.llm.client import LLMClient
from app.services.monitoring.logger import get_logger

log = get_logger("veritas.query_rewriter")

CONDENSE_SYSTEM = (
    "You turn the user's latest message into a single standalone search query. "
    "Resolve pronouns and references using the conversation. Keep names, numbers "
    "and technical terms exactly. Output only the query, nothing else."
)


class QueryRewriter:
    def __init__(self, llm: LLMClient | None = None, embedder: Embedder | None = None):
        self.llm = llm or LLMClient()
        self.embedder = embedder or Embedder()
        self.settings = get_settings()

    async def condense(self, question: str, history: list[tuple[str, str]] | None) -> str:
        """Standalone version of ``question``; returns it unchanged without history."""
        prior = [(r, c) for r, c in (history or []) if r in ("user", "assistant")]
        if not prior or self.settings.use_mock_llm:
            return question
        transcript = "\n".join(f"{role.upper()}: {content[:600]}" for role, content in prior[-6:])
        try:
            text = await self.llm.complete(
                system=CONDENSE_SYSTEM,
                user=f"Conversation:\n{transcript}\n\nLatest message: {question}",
                max_tokens=120,
                temperature=0.0,
            )
        except Exception as exc:  # noqa: BLE001 - fall back to the raw question
            log.warning("query.condense_failed", error=str(exc))
            return question
        condensed = text.strip().strip('"').splitlines()[0].strip() if text.strip() else ""
        return condensed or question

    async def expand_queries(self, question: str, n: int = 3) -> list[str]:
        if not self.settings.enable_query_expansion:
            return [question]
        prompt = (
            f"Generate {n} alternative phrasings of the search query below. "
            f"Return one query per line, no numbering.\n\nQuery: {question}"
        )
        try:
            text = await self.llm.complete(
                system="You rewrite search queries to improve document retrieval recall.",
                user=prompt,
                max_tokens=200,
            )
        except Exception as exc:  # noqa: BLE001 - expansion is best-effort
            log.warning("query.expand_failed", error=str(exc))
            return [question]
        variants = [question]
        for line in (ln.strip(" -•\t") for ln in text.splitlines()):
            if line and line.lower() != question.lower() and line not in variants:
                variants.append(line)
            if len(variants) >= n + 1:
                break
        return variants

    async def hyde_embedding(self, question: str) -> list[float]:
        """Embed a hypothetical answer passage instead of the question."""
        hypo = await self.llm.complete(
            system=(
                "Write a short hypothetical passage that would answer the question. "
                "Do not say you are hypothesizing — write as if it were source text."
            ),
            user=question,
            max_tokens=250,
        )
        return await self.embedder.embed_query(hypo)
