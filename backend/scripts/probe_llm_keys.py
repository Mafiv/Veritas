#!/usr/bin/env python3
"""Probe LLM/embedding keys. Prints only pass/fail — never secret values."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path


def load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        # File values win over empty Compose defaults for probing.
        os.environ[key] = value


async def main() -> int:
    env_path = Path(os.environ.get("PROBE_ENV_FILE", "/env/.env"))
    load_env_file(env_path)

    # Prefer process env already set by Compose
    from app.core.config import get_settings

    get_settings.cache_clear()
    s = get_settings()

    print("config.use_mock_llm =", s.use_mock_llm)
    print("config.llm_model =", s.llm_provider_model)
    print("config.has_github_key =", bool(s.github_api_key))
    print("config.has_openai_key =", bool(s.openai_api_key))
    print("config.has_gemini_key =", bool(s.gemini_api_key))
    print("config.has_anthropic_key =", bool(s.anthropic_api_key))

    from app.services.llm.client import LLMClient

    client = LLMClient()
    client.settings = s
    # Temporarily disable mock for the probe if keys exist
    if s.github_api_key or s.openai_api_key or s.gemini_api_key or s.anthropic_api_key:
        s.use_mock_llm = False

    print("--- chat ---")
    try:
        text = await client.complete(
            system="You are a connectivity probe.",
            user="Reply with exactly: OK",
            max_tokens=16,
            temperature=0,
        )
        print("chat_ok =", True)
        print("chat_reply =", repr((text or "")[:120]))
    except Exception as exc:
        print("chat_ok =", False)
        print("chat_error =", type(exc).__name__ + ":", str(exc)[:400])

    print("--- embeddings ---")
    from app.services.ingestion.embedder import Embedder

    embedder = Embedder()
    embedder.settings = s
    if not s.openai_api_key:
        print("embed_ok =", False)
        print("embed_error = OPENAI_API_KEY not set (embeddings fall back to mock)")
    else:
        # Ensure non-mock path
        s.use_mock_llm = False
        try:
            vectors = await embedder.embed_texts(["hello veritas"])
            dims = len(vectors[0]) if vectors else 0
            print("embed_ok =", True)
            print("embed_dims =", dims)
        except Exception as exc:
            print("embed_ok =", False)
            print("embed_error =", type(exc).__name__ + ":", str(exc)[:400])

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
