"""Admins adding, listing, and removing colleagues in their own tenant."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from psycopg import errors

from app.auth.deps import CurrentUser, require_role
from app.auth.passwords import hash_password
from app.db import postgres as db
from app.logging_config import get_logger
from app.models.schemas import AddUserRequest, UserOut
from app.services.purge import purge_thread

router = APIRouter(prefix="/users", tags=["users"])
log = get_logger(__name__)

# added_by is a self-reference, so the join is users to users. LEFT,
# because it is NULL for whoever registered the tenant and for anyone
# whose adder has since been removed.
USER_ROWS = (
    "SELECT u.user_id, u.email, u.role, u.tenant_id, u.created_at, "
    "       t.name AS tenant_name, a.email AS added_by_email "
    "FROM users u "
    "JOIN tenants t ON t.tenant_id = u.tenant_id "
    "LEFT JOIN users a ON a.user_id = u.added_by "
)


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
            "INSERT INTO users (tenant_id, email, password_hash, role, added_by) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING user_id",
            (
                user.tenant_id,
                body.email,
                hash_password(body.password),
                body.role,
                user.user_id,
            ),
        )
    except errors.UniqueViolation:
        raise HTTPException(status_code=409, detail="Email already registered")

    log.info("user added %s role=%s by=%s", row["user_id"], body.role, user.user_id)
    return UserOut(
        **db.fetch_one(USER_ROWS + "WHERE u.user_id = %s", (row["user_id"],))
    )


@router.get("", response_model=list[UserOut])
def list_users(
    user: CurrentUser = Depends(require_role("admin")),
) -> list[UserOut]:
    """List everyone in the caller's tenant, and who added them."""
    rows = db.fetch_all(
        USER_ROWS + "WHERE u.tenant_id = %s ORDER BY u.created_at",
        (user.tenant_id,),
    )
    return [UserOut(**row) for row in rows]


@router.delete("/{user_id}", status_code=204)
def remove_user(
    user_id: UUID,
    user: CurrentUser = Depends(require_role("admin")),
) -> None:
    """Remove a colleague, and everything in their chats."""
    # Scoped lookup, not fetch-then-check. 404 rather than 403 so the
    # response says nothing about whether the id exists elsewhere.
    row = db.fetch_one(
        "SELECT user_id FROM users WHERE user_id = %s AND tenant_id = %s",
        (user_id, user.tenant_id),
    )
    if row is None:
        raise HTTPException(status_code=404, detail="User not found")

    if user_id == user.user_id:
        # Removing yourself can leave a tenant with no admin, and
        # nobody able to make one.
        raise HTTPException(status_code=400, detail="You cannot remove yourself")

    # Their chats go with them. created_by is ON DELETE SET NULL, so
    # dropping the user alone would leave chats nobody can reach, with
    # their chunks and messages still stored.
    threads = db.fetch_all(
        "SELECT thread_id FROM threads WHERE created_by = %s AND tenant_id = %s",
        (user_id, user.tenant_id),
    )
    for thread in threads:
        purge_thread(user.tenant_id, thread["thread_id"])

    # Explicit, for the same reason. ON DELETE CASCADE from threads
    # takes the document rows.
    db.execute(
        "DELETE FROM threads WHERE created_by = %s AND tenant_id = %s",
        (user_id, user.tenant_id),
    )

    # added_by on anyone this person added becomes NULL, which is the
    # right answer — the column records who, not a live account.
    db.execute(
        "DELETE FROM users WHERE user_id = %s AND tenant_id = %s",
        (user_id, user.tenant_id),
    )
    log.info("user removed %s chats=%s by=%s", user_id, len(threads), user.user_id)
