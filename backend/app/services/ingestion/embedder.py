"""Embedding providers: local ONNX (fastembed), OpenAI, and a deterministic mock.

The vector column is fixed-width (``vector(N)`` in Postgres), so every provider
must return exactly ``settings.embedding_dimensions`` floats. ``Embedder``
enforces that instead of letting a mismatch surface as a database error.
"""

from __future__ import annotations

import asyncio
import hashlib
import math
import struct
import threading
from collections.abc import Sequence
from typing import Any, Protocol

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import Settings, get_settings

OPENAI_BATCH_SIZE = 96


class EmbeddingDimensionError(RuntimeError):
    """Provider returned vectors that do not fit the configured vector column."""


class EmbeddingProvider(Protocol):
    name: str

    async def embed_passages(self, texts: list[str]) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]: ...


def _mock_embedding(text: str, dims: int) -> list[float]:
    """Deterministic pseudo-embedding from a text hash (tests / offline dev only).

    It has no semantic meaning: two paraphrases get unrelated vectors.
    """
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    values: list[float] = []
    seed = digest
    while len(values) < dims:
        for i in range(0, len(seed) - 3, 4):
            raw = struct.unpack(">I", seed[i : i + 4])[0]
            values.append((raw / 0xFFFFFFFF) * 2.0 - 1.0)
            if len(values) >= dims:
                break
        seed = hashlib.sha256(seed + text.encode("utf-8")).digest()
    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return [v / norm for v in values]


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    if a is None or b is None or len(a) == 0 or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


class MockEmbeddingProvider:
    name = "mock"

    def __init__(self, dims: int) -> None:
        self.dims = dims

    async def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return [_mock_embedding(t, self.dims) for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        return _mock_embedding(text, self.dims)


class LocalEmbeddingProvider:
    """fastembed (ONNX Runtime) — runs on CPU, no API key, reproducible.

    The model is loaded once per process and inference runs in a worker
    thread so it never blocks the event loop.
    """

    name = "local"
    _models: dict[str, Any] = {}
    _lock = threading.Lock()

    def __init__(self, model_name: str, cache_dir: str | None = None) -> None:
        self.model_name = model_name
        self.cache_dir = cache_dir or None

    def _model(self) -> Any:
        with self._lock:
            model = self._models.get(self.model_name)
            if model is None:
                from fastembed import TextEmbedding

                model = TextEmbedding(self.model_name, cache_dir=self.cache_dir)
                self._models[self.model_name] = model
            return model

    def _passages_sync(self, texts: list[str]) -> list[list[float]]:
        return [v.tolist() for v in self._model().passage_embed(texts)]

    def _query_sync(self, text: str) -> list[float]:
        # query_embed applies the model's retrieval instruction prefix (BGE-style).
        return next(iter(self._model().query_embed([text]))).tolist()

    async def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return await asyncio.to_thread(self._passages_sync, texts)

    async def embed_query(self, text: str) -> list[float]:
        return await asyncio.to_thread(self._query_sync, text)


class OpenAIEmbeddingProvider:
    name = "openai"

    def __init__(self, settings: Settings) -> None:
        if not settings.openai_api_key:
            raise RuntimeError("EMBEDDING_PROVIDER=openai requires OPENAI_API_KEY")
        self.settings = settings

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
        wait=wait_exponential(multiplier=0.5, max=8),
        stop=stop_after_attempt(4),
        reraise=True,
    )
    async def _request(self, client: httpx.AsyncClient, batch: list[str]) -> list[list[float]]:
        resp = await client.post(
            f"{self.settings.openai_base_url}/embeddings",
            headers={"Authorization": f"Bearer {self.settings.openai_api_key}"},
            json={
                "model": self.settings.embedding_model,
                "input": batch,
                # text-embedding-3-* supports shortening to the column width.
                "dimensions": self.settings.embedding_dimensions,
            },
        )
        resp.raise_for_status()
        items = sorted(resp.json()["data"], key=lambda x: x["index"])
        return [item["embedding"] for item in items]

    async def embed_passages(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        async with httpx.AsyncClient(timeout=60.0) as client:
            for start in range(0, len(texts), OPENAI_BATCH_SIZE):
                out.extend(await self._request(client, texts[start : start + OPENAI_BATCH_SIZE]))
        return out

    async def embed_query(self, text: str) -> list[float]:
        return (await self.embed_passages([text]))[0]


def build_provider(settings: Settings) -> EmbeddingProvider:
    if settings.embedding_provider == "mock":
        return MockEmbeddingProvider(settings.embedding_dimensions)
    if settings.embedding_provider == "openai":
        return OpenAIEmbeddingProvider(settings)
    return LocalEmbeddingProvider(settings.embedding_model, settings.model_cache_dir)


class Embedder:
    """Facade used by ingestion and retrieval; validates vector width."""

    def __init__(self, provider: EmbeddingProvider | None = None) -> None:
        self.settings = get_settings()
        self.provider = provider or build_provider(self.settings)

    @property
    def model_label(self) -> str:
        return f"{self.provider.name}:{self.settings.embedding_model}"

    def _check(self, vectors: list[list[float]]) -> list[list[float]]:
        expected = self.settings.embedding_dimensions
        for v in vectors:
            if len(v) != expected:
                raise EmbeddingDimensionError(
                    f"{self.model_label} returned {len(v)}-d vectors; "
                    f"the document_chunks.embedding column is vector({expected})"
                )
        return vectors

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return self._check(await self.provider.embed_passages(texts))

    async def embed_query(self, text: str) -> list[float]:
        return self._check([await self.provider.embed_query(text)])[0]
