"""Shared pytest configuration."""

import os

# Unit tests must never download models or call providers.
os.environ.setdefault("EMBEDDING_PROVIDER", "mock")
os.environ.setdefault("USE_MOCK_LLM", "true")
os.environ.setdefault("RERANKER_BACKEND", "lexical")

import pytest  # noqa: E402


@pytest.fixture
def anyio_backend():
    return "asyncio"
