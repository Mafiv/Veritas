"""Bearer token verification: only Better Auth (asymmetric) JWTs are accepted."""

from __future__ import annotations

import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.security import HTTPAuthorizationCredentials
from starlette.requests import Request

from app.api import deps
from app.core import better_auth
from app.core.config import get_settings
from app.core.exceptions import UnauthorizedError

ISSUER = get_settings().better_auth_url.rstrip("/")


@pytest.fixture
def signing_key(monkeypatch: pytest.MonkeyPatch) -> Ed25519PrivateKey:
    """Stand in for the JWKS endpoint with a locally generated Ed25519 key."""
    key = Ed25519PrivateKey.generate()
    client = SimpleNamespace(
        get_signing_key_from_jwt=lambda _token: SimpleNamespace(key=key.public_key())
    )
    monkeypatch.setattr(better_auth, "_jwk_client", lambda: client)
    return key


def _claims(**extra) -> dict:
    now = int(time.time())
    return {"sub": "ba_1", "iss": ISSUER, "aud": ISSUER, "iat": now, "exp": now + 300, **extra}


def _request() -> Request:
    return Request({"type": "http", "headers": [], "state": {}})


def test_accepts_eddsa_token_from_jwks(signing_key: Ed25519PrivateKey):
    token = jwt.encode(_claims(email="a@example.com"), signing_key, algorithm="EdDSA")
    assert better_auth.verify_better_auth_jwt(token)["sub"] == "ba_1"


def test_rejects_hs256_token_signed_with_app_secret(signing_key: Ed25519PrivateKey):
    """The removed legacy path: a token forged with SECRET_KEY must not work."""
    forged = jwt.encode(
        {**_claims(), "type": "access"}, get_settings().secret_key, algorithm="HS256"
    )
    with pytest.raises(UnauthorizedError):
        better_auth.verify_better_auth_jwt(forged)


async def test_get_current_user_has_no_hs256_fallback(
    signing_key: Ed25519PrivateKey, monkeypatch: pytest.MonkeyPatch
):
    async def _must_not_resolve(*_a, **_k):
        raise AssertionError("user lookup must not run for a rejected token")

    monkeypatch.setattr(deps, "_resolve_user_from_better_auth", _must_not_resolve)
    forged = jwt.encode(
        {**_claims(), "type": "access"}, get_settings().secret_key, algorithm="HS256"
    )
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=forged)
    with pytest.raises(UnauthorizedError):
        await deps.get_current_user(_request(), db=None, credentials=creds)  # type: ignore[arg-type]


def test_rejects_wrong_audience(signing_key: Ed25519PrivateKey):
    token = jwt.encode(_claims(aud="https://evil.example"), signing_key, algorithm="EdDSA")
    with pytest.raises(UnauthorizedError):
        better_auth.verify_better_auth_jwt(token)
