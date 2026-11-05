"""Shared pytest configuration."""

import os
import tempfile

# Unit tests must never download models or call providers.
os.environ.setdefault("EMBEDDING_PROVIDER", "mock")
os.environ.setdefault("USE_MOCK_LLM", "true")
os.environ.setdefault("RERANKER_BACKEND", "lexical")
os.environ.setdefault("LOCAL_STORAGE_PATH", tempfile.mkdtemp(prefix="veritas-test-"))
os.environ.setdefault("INGEST_INLINE", "true")

import pytest  # noqa: E402


@pytest.fixture
def anyio_backend():
    return "asyncio"
