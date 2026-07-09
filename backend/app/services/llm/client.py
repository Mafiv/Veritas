"""LLM client with LiteLLM multi-provider support + mock fallback."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import litellm

from app.core.config import get_settings

_PROVIDER_API_KEYS: dict[str, str] = {
    "openai": "openai_api_key",
    "gemini": "gemini_api_key",
    "github": "github_api_key",
    "anthropic": "anthropic_api_key",
}


class LLMProviderError(RuntimeError):
    """Raised when an LLM provider is misconfigured or the call fails."""


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
        if self.settings.use_mock_llm:
            return self._mock_complete(system=system, user=user)

        resolved_model = model or self.settings.llm_provider_model
        self._ensure_provider_configured(resolved_model)

        try:
            response = await litellm.acompletion(
                model=resolved_model,
                messages=self._build_messages(system=system, user=user),
                max_tokens=max_tokens,
                temperature=temperature,
            )
            content = response.choices[0].message.content
            if content is None:
                provider = self._provider_name(resolved_model)
                raise LLMProviderError(
                    f"Empty response from provider '{provider}' model '{resolved_model}'"
                )
            return content
        except LLMProviderError:
            raise
        except Exception as exc:
            provider = self._provider_name(resolved_model)
            raise LLMProviderError(
                f"LLM call failed for provider '{provider}' model '{resolved_model}': {exc}"
            ) from exc

    async def stream(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 1200,
        temperature: float = 0.2,
    ) -> AsyncIterator[str]:
        if self.settings.use_mock_llm:
            text = self._mock_complete(system=system, user=user)
            for token in _tokenize_words(text):
                yield token
                await asyncio.sleep(0.02)
            return

        resolved_model = self.settings.llm_provider_model
        self._ensure_provider_configured(resolved_model)

        try:
            response = await litellm.acompletion(
                model=resolved_model,
                messages=self._build_messages(system=system, user=user),
                max_tokens=max_tokens,
                temperature=temperature,
                stream=True,
            )
            async for chunk in response:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        except LLMProviderError:
            raise
        except Exception as exc:
            provider = self._provider_name(resolved_model)
            raise LLMProviderError(
                f"LLM stream failed for provider '{provider}' model '{resolved_model}': {exc}"
            ) from exc

    @staticmethod
    def _build_messages(*, system: str, user: str) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

    @staticmethod
    def _provider_name(model: str) -> str:
        if "/" in model:
            return model.split("/", 1)[0].lower()
        return "openai"

    def _ensure_provider_configured(self, model: str) -> None:
        provider = self._provider_name(model)
        settings_attr = _PROVIDER_API_KEYS.get(provider)
        if settings_attr is None:
            supported = ", ".join(sorted(_PROVIDER_API_KEYS))
            raise LLMProviderError(
                f"Unsupported LLM provider '{provider}' in model '{model}'. "
                f"Supported providers: {supported}"
            )

        api_key = getattr(self.settings, settings_attr, "")
        if not api_key:
            env_var = settings_attr.upper()
            raise LLMProviderError(
                f"Missing API key for provider '{provider}' (model '{model}'). "
                f"Set {env_var} in the environment."
            )

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
