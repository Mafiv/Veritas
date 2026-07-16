"""Verify Better Auth JWTs via remote JWKS (EdDSA)."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import httpx
import jwt
from jwt import PyJWKClient

from app.core.config import get_settings
from app.core.exceptions import UnauthorizedError


def _jwks_base_url() -> str:
    settings = get_settings()
    internal = settings.better_auth_internal_url.strip()
    return (internal or settings.better_auth_url).rstrip("/")


@lru_cache
def _jwk_client() -> PyJWKClient:
    base = _jwks_base_url()
    return PyJWKClient(f"{base}/api/auth/jwks", cache_keys=True, lifespan=3600)


def clear_jwks_cache() -> None:
    _jwk_client.cache_clear()


def verify_better_auth_jwt(token: str) -> dict[str, Any]:
    """Validate a Better Auth JWT and return claims.

    Better Auth JWT plugin signs with EdDSA (Ed25519) by default and sets
    issuer/audience to the Better Auth base URL.
    """
    settings = get_settings()
    issuer = settings.better_auth_url.rstrip("/")
    try:
        client = _jwk_client()
        signing_key = client.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["EdDSA", "ES256", "RS256"],
            audience=issuer,
            issuer=issuer,
            options={"require": ["exp", "sub"]},
        )
        return claims
    except UnauthorizedError:
        raise
    except Exception as exc:
        # Distinguish network/JWKS failures from bad tokens for clearer errors
        if isinstance(exc, (httpx.HTTPError, jwt.PyJWKClientError)):
            raise UnauthorizedError(f"Unable to verify Better Auth token: {exc}") from exc
        raise UnauthorizedError("Invalid or expired Better Auth token") from exc
