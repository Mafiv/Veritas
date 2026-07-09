"""Embedding service with OpenAI + deterministic mock fallback."""

from __future__ import annotations

import hashlib
import math
import struct
from typing import Sequence

import httpx

from app.core.config import get_settings


def _mock_embedding(text: str, dims: int) -> list[float]:
    """Deterministic pseudo-embedding from text hash — useful for local/dev/tests."""
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    # Expand hash stream
    values: list[float] = []
    seed = digest
    while len(values) < dims:
        for i in range(0, len(seed) - 3, 4):
            raw = struct.unpack(">I", seed[i : i + 4])[0]
            values.append((raw / 0xFFFFFFFF) * 2.0 - 1.0)
            if len(values) >= dims:
                break
        seed = hashlib.sha256(seed + text.encode("utf-8")).digest()
    # L2 normalize
    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return [v / norm for v in values]


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


class Embedder:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if self.settings.use_mock_llm or not self.settings.openai_api_key:
            return [
                _mock_embedding(t, self.settings.embedding_dimensions) for t in texts
            ]
        return await self._openai_embed(texts)

    async def embed_query(self, text: str) -> list[float]:
        vectors = await self.embed_texts([text])
        return vectors[0]

    async def _openai_embed(self, texts: list[str]) -> list[list[float]]:
        headers = {
            "Authorization": f"Bearer {self.settings.openai_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.settings.embedding_model,
            "input": texts,
            "dimensions": self.settings.embedding_dimensions,
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self.settings.openai_base_url}/embeddings",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            # Ensure order by index
            items = sorted(data["data"], key=lambda x: x["index"])
            return [item["embedding"] for item in items]
