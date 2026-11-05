"""Account linking between Better Auth identities and Veritas users (real Postgres)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.auth import _provision_veritas_user
from app.core.exceptions import ConflictError, UnauthorizedError
from app.models.domain import User
from app.services.identity.linking import email_verified_from_claims, find_linked_user


async def _user(db: AsyncSession, *, auth_user_id: str | None = None) -> User:
    user = User(
        email=f"victim-{uuid.uuid4().hex[:8]}@example.com",
        full_name="Existing User",
        auth_user_id=auth_user_id,
    )
    db.add(user)
    await db.flush()
    return user


async def test_matches_by_auth_user_id_regardless_of_email(db: AsyncSession):
    user = await _user(db, auth_user_id="ba_1")
    found = await find_linked_user(
        db, auth_user_id="ba_1", email="changed@example.com", email_verified=False
    )
    assert found is not None and found.id == user.id


async def test_links_legacy_account_when_email_verified(db: AsyncSession):
    legacy = await _user(db)
    found = await find_linked_user(
        db, auth_user_id="ba_new", email=legacy.email.upper(), email_verified=True
    )
    assert found is not None and found.id == legacy.id
    assert legacy.auth_user_id == "ba_new"


async def test_refuses_to_link_legacy_account_with_unverified_email(db: AsyncSession):
    legacy = await _user(db)
    with pytest.raises(UnauthorizedError) as exc:
        await find_linked_user(
            db, auth_user_id="ba_attacker", email=legacy.email, email_verified=False
        )
    assert exc.value.code == "email_not_verified"
    assert legacy.auth_user_id is None


async def test_never_relinks_email_bound_to_another_identity(db: AsyncSession):
    owner = await _user(db, auth_user_id="ba_owner")
    with pytest.raises(ConflictError):
        await find_linked_user(db, auth_user_id="ba_other", email=owner.email, email_verified=True)
    assert owner.auth_user_id == "ba_owner"


async def test_unknown_identity_returns_none(db: AsyncSession):
    assert (
        await find_linked_user(
            db, auth_user_id="ba_x", email="nobody@example.com", email_verified=False
        )
        is None
    )


async def test_provision_creates_new_user_without_verification(db: AsyncSession):
    email = f"fresh-{uuid.uuid4().hex[:8]}@example.com"
    res = await _provision_veritas_user(
        db, auth_user_id="ba_fresh", email=email, full_name="Fresh", email_verified=False
    )
    assert res.created is True
    row = (await db.execute(select(User).where(User.email == email))).scalar_one()
    assert row.auth_user_id == "ba_fresh"


async def test_provision_does_not_hand_over_legacy_account(db: AsyncSession):
    legacy = await _user(db)
    with pytest.raises(UnauthorizedError):
        await _provision_veritas_user(
            db,
            auth_user_id="ba_attacker",
            email=legacy.email,
            full_name="Attacker",
            email_verified=False,
        )
    assert legacy.auth_user_id is None


def test_email_verified_claim_requires_literal_true():
    assert email_verified_from_claims({"emailVerified": True}) is True
    assert email_verified_from_claims({"email_verified": True}) is True
    assert email_verified_from_claims({"emailVerified": "true"}) is False
    assert email_verified_from_claims({}) is False
