"""Token and identifier generation utilities."""

import hashlib
import secrets
import uuid


def generate_token(nbytes: int = 32) -> str:
    """Generate a cryptographically secure random hex token."""
    return secrets.token_hex(nbytes)


def hash_token(raw_token: str) -> str:
    """Compute SHA-256 hex digest of a token."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def generate_csrf_token() -> str:
    """Generate a CSRF token."""
    return secrets.token_hex(32)


def generate_idempotency_key() -> str:
    """Generate a UUID4 string for idempotency keys."""
    return str(uuid.uuid4())


def generate_public_id(prefix: str = "pay_") -> str:
    """Generate an opaque public ID."""
    return f"{prefix}{secrets.token_urlsafe(16)}"
