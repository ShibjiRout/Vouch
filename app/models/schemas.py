"""Request and response shapes for the API."""

import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.auth.passwords import MAX_PASSWORD_BYTES, MIN_PASSWORD_LENGTH

# Deliberately loose. Without email sending there is no way to check
# deliverability, so this only catches obvious typos.
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class RegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=MIN_PASSWORD_LENGTH)
    tenant_name: str | None = None

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not EMAIL_RE.match(value):
            raise ValueError("Not a valid email address")
        return value

    @field_validator("password")
    @classmethod
    def fits_bcrypt(cls, value: str) -> str:
        # bcrypt truncates at 72 bytes, and bytes is not characters.
        if len(value.encode()) > MAX_PASSWORD_BYTES:
            raise ValueError(f"Password must be under {MAX_PASSWORD_BYTES} bytes")
        return value


class AddUserRequest(BaseModel):
    """An admin adding a colleague to their own tenant."""

    email: str
    password: str = Field(min_length=MIN_PASSWORD_LENGTH)
    role: str = "member"

    _valid_email = field_validator("email")(RegisterRequest.valid_email.__func__)
    _fits_bcrypt = field_validator("password")(RegisterRequest.fits_bcrypt.__func__)

    @field_validator("role")
    @classmethod
    def known_role(cls, value: str) -> str:
        if value not in ("admin", "member"):
            raise ValueError("Role must be admin or member")
        return value


# Login takes form fields, not JSON, so the /docs Authorize button
# works. FastAPI's OAuth2PasswordRequestForm supplies the shape —
# note its field is called "username", and holds the email.


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    user_id: UUID
    email: str
    role: str
    tenant_id: UUID
    tenant_name: str


# ---------------------------------------------------------------
# Threads
# ---------------------------------------------------------------


class ThreadCreate(BaseModel):
    title: str | None = None


class ThreadOut(BaseModel):
    thread_id: UUID
    title: str | None
    created_at: datetime
    last_msg_at: datetime | None


# ---------------------------------------------------------------
# Documents
# ---------------------------------------------------------------


class DocumentOut(BaseModel):
    document_id: UUID
    thread_id: UUID
    filename: str
    status: str
    chunk_count: int
    page_count: int | None
    error_message: str | None
    created_at: datetime
