"""Pytest fixtures — use in-memory SQLite for API tests when needed."""

import pytest


@pytest.fixture
def anyio_backend():
    return "asyncio"
