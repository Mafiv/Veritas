"""Password hashing helpers.

Authentication tokens are issued by Better Auth and verified in
``app.core.better_auth``; this module no longer mints or decodes JWTs.
"""

from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)
