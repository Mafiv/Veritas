"""LLM client with LiteLLM multi-provider support + mock fallback."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import httpx
import litellm

from app.core.config import get_settings

_PROVIDER_API_KEYS: dict[str, str] = {
    "openai": "openai_api_key",
    "gemini": "gemini_api_key",
    "github": "github_api_key",
    "anthropic": "anthropic_api_key",
}

# GitHub Models OpenAI-compatible endpoint (LiteLLM mishandles gpt-5 max tokens).
_GITHUB_MODELS_URL = "https://models.github.ai/inference/chat/completions"


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
            if self._provider_name(resolved_model) == "github":
                return await self._github_complete(
                    model=resolved_model,
                    system=system,
                    user=user,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )

            response = await litellm.acompletion(
                **self._completion_kwargs(
                    model=resolved_model,
                    system=system,
                    user=user,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    stream=False,
                )
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
            if self._provider_name(resolved_model) == "github":
                # GitHub Models streaming via SSE; fall back to chunked complete for reliability.
                text = await self._github_complete(
                    model=resolved_model,
                    system=system,
                    user=user,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                for token in _tokenize_words(text):
                    yield token
                return

            response = await litellm.acompletion(
                **self._completion_kwargs(
                    model=resolved_model,
                    system=system,
                    user=user,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    stream=True,
                )
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

    async def _github_complete(
        self,
        *,
        model: str,
        system: str,
        user: str,
        max_tokens: int,
        temperature: float,
    ) -> str:
        api_key = self.settings.github_api_key
        # GitHub Models accepts openai/<name> or bare model ids.
        api_model = model.split("/", 1)[-1]
        if not api_model.startswith("openai/"):
            # Prefer openai/ prefix used by GitHub Models catalog
            if api_model.startswith(("gpt-", "o1", "o3", "o4")):
                api_model = f"openai/{api_model}"

        body: dict[str, Any] = {
            "model": api_model,
            "messages": self._build_messages(system=system, user=user),
        }
        # gpt-5 / o-series require max_completion_tokens and often reject temperature
        if self._uses_max_completion_tokens(model):
            # Reasoning models spend tokens before visible output — keep a floor.
            body["max_completion_tokens"] = max(max_tokens, 256)
        else:
            body["max_tokens"] = max_tokens
            body["temperature"] = temperature

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/vnd.github+json",
        }
        # Free GitHub Models tiers rate-limit aggressively; retry a few times.
        max_attempts = 4
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                last_error = ""
                for attempt in range(max_attempts):
                    resp = await client.post(_GITHUB_MODELS_URL, headers=headers, json=body)
                    if resp.status_code == 429:
                        retry_after = resp.headers.get("retry-after")
                        try:
                            delay = float(retry_after) if retry_after else 0.0
                        except ValueError:
                            delay = 0.0
                        delay = max(delay, 1.5 * (2**attempt))
                        last_error = resp.text[:400]
                        if attempt + 1 >= max_attempts:
                            break
                        await asyncio.sleep(min(delay, 20.0))
                        continue
                    if resp.status_code >= 400:
                        raise LLMProviderError(
                            f"GitHub Models HTTP {resp.status_code}: {resp.text[:400]}"
                        )
                    data = resp.json()
                    content = data.get("choices", [{}])[0].get("message", {}).get("content")
                    if not content:
                        raise LLMProviderError(
                            f"Empty response from GitHub Models model '{api_model}'"
                        )
                    return content
                raise LLMProviderError(
                    "GitHub Models rate limit exceeded (HTTP 429). "
                    "Wait a minute, or set ENABLE_HYDE=false and "
                    "ENABLE_QUERY_EXPANSION=false to use fewer requests, "
                    "or enable paid GitHub Models / use another provider. "
                    f"Details: {last_error}"
                )
        except LLMProviderError:
            raise
        except Exception as exc:
            raise LLMProviderError(f"GitHub Models request failed: {exc}") from exc

    def _completion_kwargs(
        self,
        *,
        model: str,
        system: str,
        user: str,
        max_tokens: int,
        temperature: float,
        stream: bool,
    ) -> dict:
        kwargs: dict = {
            "model": model,
            "messages": self._build_messages(system=system, user=user),
            "stream": stream,
            "api_key": self._api_key_for_model(model) or None,
            "drop_params": True,
        }
        if self._uses_max_completion_tokens(model):
            kwargs["max_completion_tokens"] = max_tokens
            if not self._is_reasoning_model(model):
                kwargs["temperature"] = temperature
        else:
            kwargs["max_tokens"] = max_tokens
            kwargs["temperature"] = temperature
        return kwargs

    def _api_key_for_model(self, model: str) -> str:
        provider = self._provider_name(model)
        attr = _PROVIDER_API_KEYS.get(provider, "")
        return getattr(self.settings, attr, "") if attr else ""

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

    @staticmethod
    def _model_name(model: str) -> str:
        return model.split("/", 1)[-1].lower()

    @classmethod
    def _is_reasoning_model(cls, model: str) -> bool:
        name = cls._model_name(model)
        return name.startswith(("o1", "o3", "o4", "gpt-5"))

    @classmethod
    def _uses_max_completion_tokens(cls, model: str) -> bool:
        """GitHub/OpenAI gpt-5 and o-series reject max_tokens."""
        name = cls._model_name(model)
        return name.startswith(("gpt-5", "o1", "o3", "o4"))

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
