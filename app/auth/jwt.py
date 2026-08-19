"""Issue and verify JWTs.

The payload is signed, not encrypted — anyone holding the token can
read it. Never put a password or any secret in it.
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt

from app.config import JWT_ALGORITHM, JWT_EXPIRY_MINUTES, JWT_SECRET


class InvalidToken(Exception):
    """Token was missing, expired, forged, or malformed."""


def create_access_token(user_id: UUID, tenant_id: UUID, role: str) -> str:
    """Issue a signed token for this user."""
    if not JWT_SECRET:
        raise RuntimeError("JWT_SECRET is not set")

    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=JWT_EXPIRY_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """Verify a token and return its payload."""
    if not JWT_SECRET:
        raise RuntimeError("JWT_SECRET is not set")

    try:
        # algorithms is passed explicitly. Trusting the token's own alg
        # header is what lets an attacker present alg=none.
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise InvalidToken(str(exc)) from exc
