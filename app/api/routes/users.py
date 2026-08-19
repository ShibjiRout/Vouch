"""Admins adding colleagues to their own tenant."""

from fastapi import APIRouter, Depends, HTTPException
from psycopg import errors

from app.auth.deps import CurrentUser, require_role
from app.auth.passwords import hash_password
from app.db import postgres as db
from app.logging_config import get_logger
from app.models.schemas import AddUserRequest, UserOut

router = APIRouter(prefix="/users", tags=["users"])
log = get_logger(__name__)


@router.post("", response_model=UserOut, status_code=201)
def add_user(
    body: AddUserRequest,
    user: CurrentUser = Depends(require_role("admin")),
) -> UserOut:
    """Create a user inside the caller's tenant."""
    try:
        # tenant_id comes from the token, never from the body, so an
        # admin cannot add a user to someone else's company.
        row = db.fetch_one(
            "INSERT INTO users (tenant_id, email, password_hash, role) "
            "VALUES (%s, %s, %s, %s) RETURNING user_id, email, role, tenant_id",
            (user.tenant_id, body.email, hash_password(body.password), body.role),
        )
    except errors.UniqueViolation:
        raise HTTPException(status_code=409, detail="Email already registered")

    tenant = db.fetch_one(
        "SELECT name FROM tenants WHERE tenant_id = %s", (user.tenant_id,)
    )

    log.info("user added %s role=%s by=%s", row["user_id"], body.role, user.user_id)
    return UserOut(**row, tenant_name=tenant["name"])


@router.get("", response_model=list[UserOut])
def list_users(
    user: CurrentUser = Depends(require_role("admin")),
) -> list[UserOut]:
    """List everyone in the caller's tenant."""
    rows = db.fetch_all(
        "SELECT u.user_id, u.email, u.role, u.tenant_id, t.name AS tenant_name "
        "FROM users u JOIN tenants t ON t.tenant_id = u.tenant_id "
        "WHERE u.tenant_id = %s ORDER BY u.created_at",
        (user.tenant_id,),
    )
    return [UserOut(**row) for row in rows]
