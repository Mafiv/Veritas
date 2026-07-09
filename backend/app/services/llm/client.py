"""LLM client with OpenAI + mock streaming fallback."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.core.config import get_settings


class LLMClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 800,
        temperature: float = 0.2,
        model: str | None = None,
    ) -> str:
        if self.settings.use_mock_llm or not self.settings.openai_api_key:
            return self._mock_complete(system=system, user=user)
        try:
            return await self._openai_chat(
                system=system,
                user=user,
                max_tokens=max_tokens,
                temperature=temperature,
                model=model or self.settings.chat_model,
            )
        except Exception:
            # Automatic model fallback
            try:
                return await self._openai_chat(
                    system=system,
                    user=user,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    model=self.settings.chat_fallback_model,
                )
            except Exception:
                return self._mock_complete(system=system, user=user)

    async def stream(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 1200,
        temperature: float = 0.2,
    ) -> AsyncIterator[str]:
        if self.settings.use_mock_llm or not self.settings.openai_api_key:
            text = self._mock_complete(system=system, user=user)
            for token in _tokenize_words(text):
                yield token
                await asyncio.sleep(0.02)
            return

        headers = {
            "Authorization": f"Bearer {self.settings.openai_api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self.settings.chat_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{self.settings.openai_base_url}/chat/completions",
                headers=headers,
                json=payload,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        delta = chunk["choices"][0]["delta"].get("content")
                        if delta:
                            yield delta
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue

    async def _openai_chat(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int,
        temperature: float,
        model: str,
    ) -> str:
        headers = {
            "Authorization": f"Bearer {self.settings.openai_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(
                f"{self.settings.openai_base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    def _mock_complete(self, *, system: str, user: str) -> str:
        # Extract context blocks if present for grounded mock answers
        if "Sources:" in user or "Context:" in user:
            # Produce a citation-aware answer
            citations = []
            for i in range(1, 6):
                if f"[{i}]" in user:
                    citations.append(i)
            cite = "".join(f"[{i}]" for i in citations[:3]) or "[1]"
            question = user.split("Question:")[-1].strip() if "Question:" in user else user
            return (
                f"Based on the provided source material{cite}, here is a grounded answer "
                f"to your question.\n\n"
                f"**Answer:** The documents indicate relevant information addressing: "
                f"{question[:180].strip()}\n\n"
                f"Key points drawn from the retrieved passages{cite}:\n"
                f"- The source material directly supports this conclusion.\n"
                f"- Supporting details appear in the cited excerpts above.\n\n"
                f"If you need more specificity, ask a follow-up about a particular section."
            )
        if "alternative phrasings" in system.lower() or "rewrite" in system.lower():
            base = user.split("Query:")[-1].strip()
            return f"{base}\n{base} details\noverview of {base}\n{base} summary"
        if "hypothetical" in system.lower():
            return (
                f"This document discusses the topic in detail. "
                f"It covers key facts, definitions, and conclusions related to: {user[:200]}"
            )
        if "suggest" in system.lower() and "question" in system.lower():
            return (
                "What are the main findings?\n"
                "Who are the key stakeholders mentioned?\n"
                "What timelines or deadlines appear?\n"
                "What risks or limitations are discussed?\n"
                "How do the conclusions relate to the stated goals?"
            )
        if "summar" in system.lower():
            snippet = user[:400].replace("\n", " ")
            return f"Summary: {snippet}..."
        return f"Veritas response: {user[:500]}"


def _tokenize_words(text: str) -> list[str]:
    parts: list[str] = []
    buf = ""
    for ch in text:
        buf += ch
        if ch in " \n":
            parts.append(buf)
            buf = ""
    if buf:
        parts.append(buf)
    return parts
