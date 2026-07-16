"""Unit tests for LiteLLM-backed LLMClient."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.config import Settings, get_settings
from app.services.llm.client import LLMClient, LLMProviderError


def _settings(**overrides) -> Settings:
    defaults = {
        "use_mock_llm": False,
        "llm_provider_model": "openai/gpt-4o-mini",
        "openai_api_key": "sk-test",
    }
    defaults.update(overrides)
    return Settings(**defaults)


def _patch_settings(monkeypatch: pytest.MonkeyPatch, **overrides) -> None:
    get_settings.cache_clear()
    monkeypatch.setattr(
        "app.services.llm.client.get_settings",
        lambda: _settings(**overrides),
    )


@pytest.mark.asyncio
async def test_mock_llm_bypasses_litellm(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fail_acompletion(*_args, **_kwargs):
        raise AssertionError("litellm.acompletion must not be called when USE_MOCK_LLM=true")

    _patch_settings(monkeypatch, use_mock_llm=True)
    monkeypatch.setattr("app.services.llm.client.litellm.acompletion", fail_acompletion)

    llm = LLMClient()
    result = await llm.complete(system="answer", user="hello")
    assert isinstance(result, str)
    assert result


@pytest.mark.asyncio
async def test_complete_uses_litellm(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_settings(monkeypatch)

    async def fake_acompletion(**kwargs):
        assert kwargs["model"] == "openai/gpt-4o-mini"
        assert kwargs["messages"] == [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "user prompt"},
        ]
        assert kwargs["max_tokens"] == 800
        assert kwargs["temperature"] == 0.2
        assert kwargs.get("drop_params") is True
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="Hello from LLM"))]
        )

    monkeypatch.setattr("app.services.llm.client.litellm.acompletion", fake_acompletion)

    llm = LLMClient()
    result = await llm.complete(system="system prompt", user="user prompt")
    assert result == "Hello from LLM"


@pytest.mark.asyncio
async def test_stream_yields_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_settings(monkeypatch)

    async def fake_acompletion(**kwargs):
        assert kwargs["stream"] is True

        async def _stream():
            for token in ("Hello", " world"):
                yield SimpleNamespace(
                    choices=[SimpleNamespace(delta=SimpleNamespace(content=token))]
                )

        return _stream()

    monkeypatch.setattr("app.services.llm.client.litellm.acompletion", fake_acompletion)

    llm = LLMClient()
    tokens: list[str] = []
    async for token in llm.stream(system="system", user="user"):
        tokens.append(token)

    assert tokens == ["Hello", " world"]


@pytest.mark.asyncio
async def test_missing_api_key_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_settings(
        monkeypatch,
        llm_provider_model="gemini/gemini-1.5-pro",
        openai_api_key="",
        gemini_api_key="",
    )

    llm = LLMClient()
    with pytest.raises(LLMProviderError, match="Missing API key for provider 'gemini'"):
        await llm.complete(system="system", user="user")


@pytest.mark.asyncio
async def test_github_provider_uses_direct_http(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_settings(
        monkeypatch,
        llm_provider_model="github/gpt-5-mini",
        github_api_key="ghp_test",
        openai_api_key="",
    )

    class FakeResponse:
        status_code = 200
        text = "{}"

        def json(self):
            return {
                "choices": [{"message": {"content": "OK from GitHub"}, "finish_reason": "stop"}]
            }

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, headers=None, json=None):
            assert "models.github.ai" in url
            assert json["model"] == "openai/gpt-5-mini"
            assert "max_completion_tokens" in json
            assert "max_tokens" not in json
            return FakeResponse()

    monkeypatch.setattr("app.services.llm.client.httpx.AsyncClient", FakeClient)

    llm = LLMClient()
    result = await llm.complete(system="system", user="user", max_tokens=64)
    assert result == "OK from GitHub"


@pytest.mark.asyncio
async def test_litellm_failure_raises_provider_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_settings(monkeypatch)

    async def fail_acompletion(**_kwargs):
        raise RuntimeError("upstream timeout")

    monkeypatch.setattr("app.services.llm.client.litellm.acompletion", fail_acompletion)

    llm = LLMClient()
    with pytest.raises(LLMProviderError, match="provider 'openai' model 'openai/gpt-4o-mini'"):
        await llm.complete(system="system", user="user")
