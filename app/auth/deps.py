"""FastAPI dependencies for identity and role checks."""

from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer

from app.auth.jwt import InvalidToken, decode_token

# Only sets the "Authorization: Bearer <token>" header format. The
# tokens are issued by this application, not by a third party.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


@dataclass(frozen=True)
class CurrentUser:
    """The caller, read from the verified token."""

    user_id: UUID
    tenant_id: UUID
    role: str


def get_current_user(token: str = Depends(oauth2_scheme)) -> CurrentUser:
    """Identify the caller. Never reads these from the request body."""
    try:
        payload = decode_token(token)
        return CurrentUser(
            user_id=UUID(payload["sub"]),
            tenant_id=UUID(payload["tenant_id"]),
            role=payload["role"],
        )
    except (InvalidToken, KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def require_role(*allowed: str):
    """Reject callers whose role is not one of allowed."""

    def check(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in allowed:
            raise HTTPException(status_code=403, detail="Not allowed")
        return user

    return check
