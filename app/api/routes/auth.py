"""Register, login, and the current user."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from psycopg import errors

from app.auth.deps import CurrentUser, get_current_user
from app.auth.jwt import create_access_token
from app.auth.passwords import hash_password, verify_password
from app.db import postgres as db
from app.logging_config import get_logger
from app.models.schemas import RegisterRequest, TokenResponse, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])
log = get_logger(__name__)


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(body: RegisterRequest) -> TokenResponse:
    """Create a tenant and its first user, who becomes admin."""
    tenant_name = body.tenant_name or body.email.split("@")[-1]

    try:
        # One transaction — a failed user insert must not leave an
        # orphan tenant behind.
        with db.transaction() as cur:
            cur.execute(
                "INSERT INTO tenants (name) VALUES (%s) RETURNING tenant_id",
                (tenant_name,),
            )
            tenant_id = cur.fetchone()["tenant_id"]

            cur.execute(
                "INSERT INTO users (tenant_id, email, password_hash, role) "
                "VALUES (%s, %s, %s, 'admin') RETURNING user_id",
                (tenant_id, body.email, hash_password(body.password)),
            )
            user_id = cur.fetchone()["user_id"]

    except errors.UniqueViolation:
        # Do not SELECT first to check. Two simultaneous signups both
        # pass that check and one fails here anyway.
        raise HTTPException(status_code=409, detail="Email already registered")

    log.info("registered user=%s tenant=%s", user_id, tenant_id)
    return TokenResponse(
        access_token=create_access_token(user_id, tenant_id, "admin")
    )


@router.post("/login", response_model=TokenResponse)
def login(form: OAuth2PasswordRequestForm = Depends()) -> TokenResponse:
    """Exchange email and password for a token."""
    email = form.username.strip().lower()

    row = db.fetch_one(
        "SELECT user_id, tenant_id, password_hash, role, is_active "
        "FROM users WHERE email = %s",
        (email,),
    )

    # Same response whether the email is unknown, the password is
    # wrong, or the account is disabled.
    if (
        row is None
        or not row["is_active"]
        or not verify_password(form.password, row["password_hash"])
    ):
        log.info("failed login for %s", email)
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    db.execute(
        "UPDATE users SET last_login_at = now() WHERE user_id = %s",
        (row["user_id"],),
    )

    log.info("login user=%s tenant=%s", row["user_id"], row["tenant_id"])
    return TokenResponse(
        access_token=create_access_token(
            row["user_id"], row["tenant_id"], row["role"]
        )
    )


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser = Depends(get_current_user)) -> UserOut:
    """Return the caller and their tenant."""
    row = db.fetch_one(
        "SELECT u.user_id, u.email, u.role, t.tenant_id, t.name AS tenant_name "
        "FROM users u JOIN tenants t ON t.tenant_id = u.tenant_id "
        "WHERE u.user_id = %s AND u.tenant_id = %s",
        (user.user_id, user.tenant_id),
    )
    if row is None:
        raise HTTPException(status_code=404)
    return UserOut(**row)
