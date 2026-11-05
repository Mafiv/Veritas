"""Production settings must refuse insecure defaults."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import DEFAULT_SECRET_KEY, Settings

SECURE = {
    "app_env": "production",
    "secret_key": "x" * 48,
    "internal_auth_bootstrap_secret": "y" * 32,
    "debug": False,
    "use_mock_llm": False,
}


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **{**SECURE, **overrides})  # type: ignore[arg-type]


def test_secure_production_config_loads() -> None:
    assert _settings().app_env == "production"


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"secret_key": DEFAULT_SECRET_KEY}, "SECRET_KEY"),
        ({"secret_key": "short"}, "SECRET_KEY"),
        ({"internal_auth_bootstrap_secret": ""}, "INTERNAL_AUTH_BOOTSTRAP_SECRET"),
        ({"debug": True}, "DEBUG"),
        ({"use_mock_llm": True}, "USE_MOCK_LLM"),
    ],
)
def test_insecure_production_config_is_rejected(override: dict, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        _settings(**override)


def test_development_allows_defaults() -> None:
    s = Settings(_env_file=None, app_env="development")  # type: ignore[call-arg]
    assert s.secret_key == DEFAULT_SECRET_KEY
