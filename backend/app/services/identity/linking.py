"""Map a Better Auth identity onto a Veritas user, safely.

Rules:
1. A user whose ``auth_user_id`` matches the token subject is always that user.
2. Otherwise, an existing user with the same email is linked only if it has no
   ``auth_user_id`` yet (an account created before Better Auth) **and** the
   identity provider says the email is verified. Without that check, anyone
   could register an unverified Better Auth account with a victim's address and
   inherit the victim's workspaces.
3. An email already bound to a *different* ``auth_user_id`` is never relinked.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, UnauthorizedError
from app.models.domain import User


def email_verified_from_claims(claims: dict[str, Any]) -> bool:
    """Better Auth JWT payload uses ``emailVerified``; accept the OIDC spelling too."""
    value = claims.get("emailVerified", claims.get("email_verified"))
    return value is True


async def find_linked_user(
    db: AsyncSession,
    *,
    auth_user_id: str,
    email: str,
    email_verified: bool,
) -> User | None:
    """Return the Veritas user for this identity, linking by email if allowed.

    Returns ``None`` when no Veritas user exists yet (caller may provision one).
    Raises when an account exists for the email but must not be linked.
    """
    if not auth_user_id:
        raise UnauthorizedError("Token missing subject")
    email = email.lower()

    by_id = (
        await db.execute(select(User).where(User.auth_user_id == auth_user_id))
    ).scalar_one_or_none()
    if by_id is not None:
        return by_id

    if not email:
        return None

    by_email = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if by_email is None:
        return None

    if by_email.auth_user_id:
        # Bound to a different identity. Never relink silently.
        raise ConflictError(
            "This email is already linked to another sign-in account",
            code="account_link_conflict",
        )
    if not email_verified:
        raise UnauthorizedError(
            "Verify your email address to link it to your existing Veritas account",
            code="email_not_verified",
        )

    by_email.auth_user_id = auth_user_id
    await db.flush()
    return by_email
