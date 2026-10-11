# In plain English: Checks passwords, manages login sessions and determines user permissions.
"""Authentication, sessions, and permissions per CONTRACT.md §4, §13.3."""

from datetime import datetime, timezone, timedelta
import hashlib
import secrets
import sqlite3
from typing import Callable, Set

from fastapi import Depends, HTTPException, Request

from clubledger.config import get_db_path, get_env
from clubledger.core import clock
from clubledger.security.csrf import verify_csrf_token
from clubledger.core.db import connect
from clubledger.core.errors import DomainError
from clubledger.core.idgen import generate_csrf_token, generate_token, hash_token
from clubledger.core.types import Session


COOKIE_SESSION = "cl_session"


def _parse_utc(iso_str: str) -> datetime:
    if iso_str.endswith("Z"):
        return datetime.fromisoformat(iso_str[:-1]).replace(tzinfo=timezone.utc)
    dt = datetime.fromisoformat(iso_str)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _format_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- Passwords (stdlib scrypt per CONTRACT §1.1, G11) ---


def hash_password(password: str) -> str:
    """Hash password with hashlib.scrypt using per-user salt."""
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=16384, r=8, p=1)
    return f"scrypt${salt.hex()}${derived.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    """Verify password against stored scrypt hash."""
    try:
        scheme, salt_hex, hash_hex = password_hash.split("$", 2)
        if scheme != "scrypt":
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
        test = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=16384, r=8, p=1)
        return secrets.compare_digest(expected, test)
    except Exception:
        return False


# --- User Registration and Authentication ---


def register_user(
    conn: sqlite3.Connection, email: str, name: str, password: str
) -> int:
    """Register a new user. Raises DomainError('VALIDATION', 422) if duplicate email."""
    normalized_email = email.strip()
    if not normalized_email or "@" not in normalized_email:
        raise DomainError("VALIDATION", 422, "Invalid email address")
    if not name.strip():
        raise DomainError("VALIDATION", 422, "Name cannot be empty")
    if len(password) < 8:
        raise DomainError("VALIDATION", 422, "Password must be at least 8 characters")

    # Check case-insensitive duplicate
    existing = conn.execute(
        "SELECT id FROM users WHERE email = ? COLLATE NOCASE;", (normalized_email,)
    ).fetchone()
    if existing:
        raise DomainError("VALIDATION", 422, "Email already registered")

    pwd_hash = hash_password(password)
    now_iso = clock.now()
    cur = conn.execute(
        "INSERT INTO users (email, name, password_hash, is_active, created_at) "
        "VALUES (?, ?, ?, 1, ?);",
        (normalized_email, name.strip(), pwd_hash, now_iso),
    )
    return cur.lastrowid  # type: ignore[return-value]


def authenticate_user(
    conn: sqlite3.Connection, email: str, password: str
) -> int | None:
    """Authenticate user with email and password. Returns user_id if valid."""
    row = conn.execute(
        "SELECT id, password_hash, is_active FROM users WHERE email = ? COLLATE NOCASE;",
        (email.strip(),),
    ).fetchone()
    if not row or row["is_active"] != 1:
        return None

    if verify_password(password, row["password_hash"]):
        return row["id"]
    return None


def deactivate_user(conn: sqlite3.Connection, user_id: int) -> None:
    """Deactivate a user and revoke all their sessions in the same transaction (AUTH-06)."""
    now = clock.now()
    conn.execute("UPDATE users SET is_active = 0 WHERE id = ?;", (user_id,))
    conn.execute(
        "UPDATE sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL;",
        (now, user_id),
    )


# --- Sessions (CONTRACT §4.1, §13.3) ---


def create_session(conn: sqlite3.Connection, user_id: int) -> tuple[str, str]:
    """Create a new session row. Returns (raw_token, csrf_token)."""
    raw_token = generate_token(32)
    token_hash = hash_token(raw_token)
    csrf_token = generate_csrf_token()
    now_iso = clock.now()
    now_dt = _parse_utc(now_iso)

    idle_expires_at = _format_utc(now_dt + timedelta(hours=2))
    absolute_expires_at = _format_utc(now_dt + timedelta(hours=8))

    conn.execute(
        "INSERT INTO sessions ("
        "  token_hash, user_id, csrf_token, last_seen_at, idle_expires_at, "
        "  absolute_expires_at, created_at"
        ") VALUES (?, ?, ?, ?, ?, ?, ?);",
        (
            token_hash,
            user_id,
            csrf_token,
            now_iso,
            idle_expires_at,
            absolute_expires_at,
            now_iso,
        ),
    )
    return raw_token, csrf_token


def load_session(conn: sqlite3.Connection, raw_token: str) -> Session | None:
    """Validate and load session. Slides idle expiry if active (CONTRACT §4.1)."""
    if not raw_token:
        return None

    token_hash = hash_token(raw_token)
    row = conn.execute(
        "SELECT id, user_id, csrf_token, last_seen_at, idle_expires_at, "
        "       absolute_expires_at, revoked_at "
        "FROM sessions WHERE token_hash = ?;",
        (token_hash,),
    ).fetchone()
    if not row or row["revoked_at"] is not None:
        return None

    # Check user active status
    user_row = conn.execute(
        "SELECT is_active FROM users WHERE id = ?;", (row["user_id"],)
    ).fetchone()
    if not user_row or user_row["is_active"] != 1:
        # Revoke session if user deactivated
        conn.execute(
            "UPDATE sessions SET revoked_at = ? WHERE id = ?;", (clock.now(), row["id"])
        )
        return None

    current_iso = clock.now()
    if (
        current_iso >= row["idle_expires_at"]
        or current_iso >= row["absolute_expires_at"]
    ):
        return None

    last_seen_iso = row["last_seen_at"]
    idle_expires_iso = row["idle_expires_at"]

    # Sliding idle refresh: if now - last_seen_at >= 60 s, slide idle expiry
    now_dt = _parse_utc(current_iso)
    last_seen_dt = _parse_utc(last_seen_iso)
    if (now_dt - last_seen_dt).total_seconds() >= 60:
        abs_dt = _parse_utc(row["absolute_expires_at"])
        new_idle_dt = min(now_dt + timedelta(hours=2), abs_dt)
        new_idle_iso = _format_utc(new_idle_dt)
        last_seen_iso = current_iso
        idle_expires_iso = new_idle_iso
        conn.execute(
            "UPDATE sessions SET last_seen_at = ?, idle_expires_at = ? WHERE id = ?;",
            (last_seen_iso, idle_expires_iso, row["id"]),
        )

    return Session(
        id=row["id"],
        user_id=row["user_id"],
        csrf_token=row["csrf_token"],
        last_seen_at=last_seen_iso,
        idle_expires_at=idle_expires_iso,
        absolute_expires_at=row["absolute_expires_at"],
        revoked_at=None,
    )


def revoke_session(conn: sqlite3.Connection, session_id: int) -> None:
    """Revoke a session server-side."""
    conn.execute(
        "UPDATE sessions SET revoked_at = ? WHERE id = ?;", (clock.now(), session_id)
    )


def verify_csrf(session: Session, supplied: str) -> None:
    """Verify CSRF token for authenticated session."""
    verify_csrf_token(session.csrf_token, supplied)


# --- Permissions and Access Control (CONTRACT §4.1, §4.3) ---


def get_user_permissions(conn: sqlite3.Connection, user_id: int) -> Set[str]:
    """Resolve live permissions from the database. Admin role grants all permissions."""
    # Check if user has active admin role
    admin_row = conn.execute(
        "SELECT 1 FROM user_roles ur "
        "JOIN roles r ON ur.role_id = r.id "
        "WHERE ur.user_id = ? AND r.code = 'admin' AND ur.revoked_at IS NULL;",
        (user_id,),
    ).fetchone()
    if admin_row:
        # Return all permission codes in system
        all_perms = conn.execute("SELECT code FROM permissions;").fetchall()
        return {r["code"] for r in all_perms}

    rows = conn.execute(
        "SELECT DISTINCT p.code "
        "FROM permissions p "
        "JOIN role_permissions rp ON p.id = rp.permission_id "
        "JOIN user_roles ur ON rp.role_id = ur.role_id "
        "WHERE ur.user_id = ? AND ur.revoked_at IS NULL;",
        (user_id,),
    ).fetchall()
    return {r["code"] for r in rows}


def get_current_session(request: Request) -> Session:
    """Dependency: resolve authenticated session from cl_session cookie."""
    raw_token = request.cookies.get(COOKIE_SESSION)
    if not raw_token:
        raise DomainError("AUTH_REQUIRED", 401, "Authentication required")

    conn = connect(get_db_path())
    try:
        session = load_session(conn, raw_token)
        if not session:
            raise DomainError("AUTH_REQUIRED", 401, "Invalid or expired session")
        return session
    finally:
        conn.close()


def require_perm(code: str) -> Callable[[Session], Session]:
    """FastAPI Depends factory: verify current session holds the required live permission."""

    def _dependency(session: Session = Depends(get_current_session)) -> Session:
        conn = connect(get_db_path())
        try:
            perms = get_user_permissions(conn, session.user_id)
            if code not in perms:
                raise DomainError(
                    "FORBIDDEN", 403, f"Missing required permission: {code}"
                )
            return session
        finally:
            conn.close()

    return _dependency
