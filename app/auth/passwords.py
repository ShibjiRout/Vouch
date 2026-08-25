"""Password hashing with bcrypt."""

import bcrypt

# bcrypt silently truncates at 72 bytes, so reject longer up front
# rather than let two different passwords hash the same.
MAX_PASSWORD_BYTES = 72
MIN_PASSWORD_LENGTH = 8


def hash_password(password: str) -> str:
    """Hash a password for storage."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    """Check a password against its stored hash."""
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False
