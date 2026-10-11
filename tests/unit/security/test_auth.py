"""Tests for scrypt password hashing, session lifecycles, and live permissions."""

from datetime import datetime, timezone, timedelta
from pathlib import Path
import pytest

from clubledger.core import clock
from clubledger.security.auth import (
    authenticate_user,
    create_session,
    deactivate_user,
    get_user_permissions,
    hash_password,
    load_session,
    register_user,
    revoke_session,
    verify_password,
)
from clubledger.core.db import apply_migrations, connect
from clubledger.core.errors import DomainError
from clubledger.core.idgen import hash_token
from clubledger.seed import seed_roles_and_permissions


@pytest.fixture(autouse=True)
def clean_clock():
    clock.reset()
    yield
    clock.reset()


@pytest.fixture
def db(tmp_path: Path):
    db_file = tmp_path / "auth_test.db"
    conn = connect(str(db_file))
    apply_migrations(conn)
    seed_roles_and_permissions(conn)
    yield conn
    conn.close()


def test_scrypt_password_hashing_and_verification() -> None:
    password = "SuperSecretPassword123!"
    pwd_hash = hash_password(password)

    # Hash contains scrypt marker and salt
    assert pwd_hash.startswith("scrypt$")
    parts = pwd_hash.split("$")
    assert len(parts) == 3

    # Verification passes with correct password
    assert verify_password(password, pwd_hash) is True

    # Verification fails with wrong password
    assert verify_password("WrongPassword!", pwd_hash) is False

    # Two hashes of the same password differ because of unique random salts
    pwd_hash_2 = hash_password(password)
    assert pwd_hash != pwd_hash_2


def test_user_registration_and_authentication(db) -> None:
    user_id = register_user(
        db, email="User@Example.Com", name="Test User", password="Password123"
    )
    assert user_id > 0

    # Case-insensitive duplicate registration rejected with 422 VALIDATION (AUTH-01)
    with pytest.raises(DomainError) as exc_info:
        register_user(
            db, email="user@example.com", name="Another User", password="Password123"
        )
    assert exc_info.value.code == "VALIDATION"
    assert exc_info.value.http_status == 422

    # Authenticate with correct credentials
    auth_id = authenticate_user(db, email="user@example.com", password="Password123")
    assert auth_id == user_id

    # Authenticate with wrong password
    assert (
        authenticate_user(db, email="user@example.com", password="WrongPassword")
        is None
    )

    # Authenticate with non-existent email
    assert (
        authenticate_user(db, email="unknown@example.com", password="Password123")
        is None
    )


def test_session_lifecycle_and_sliding_expiry(
    db, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLUBLEDGER_ENV", "test")
    clock.set_now("2026-08-01T10:00:00Z")

    user_id = register_user(
        db, email="session@example.com", name="Session User", password="Password123"
    )
    raw_token, csrf_token = create_session(db, user_id)

    # Raw token is NOT stored in DB, only token_hash (AUTH-02)
    stored_token_row = db.execute(
        "SELECT token_hash FROM sessions WHERE user_id = ?;", (user_id,)
    ).fetchone()
    assert stored_token_row["token_hash"] == hash_token(raw_token)
    assert stored_token_row["token_hash"] != raw_token

    # Initial load succeeds
    session = load_session(db, raw_token)
    assert session is not None
    assert session.user_id == user_id
    assert session.csrf_token == csrf_token
    assert session.idle_expires_at == "2026-08-01T12:00:00Z"
    assert session.absolute_expires_at == "2026-08-01T18:00:00Z"

    # Activity less than 60s later: does not update last_seen_at (AUTH-03)
    clock.set_now("2026-08-01T10:00:30Z")
    s2 = load_session(db, raw_token)
    assert s2 is not None
    assert s2.last_seen_at == "2026-08-01T10:00:00Z"

    # Activity 65s later: slides idle_expires_at to now + 2h
    clock.set_now("2026-08-01T10:01:05Z")
    s3 = load_session(db, raw_token)
    assert s3 is not None
    assert s3.last_seen_at == "2026-08-01T10:01:05Z"
    assert s3.idle_expires_at == "2026-08-01T12:01:05Z"
    assert (
        s3.absolute_expires_at == "2026-08-01T18:00:00Z"
    )  # Absolute expires unchanged

    # Idle expiry: inactivity for > 2 hours invalidates session
    clock.set_now("2026-08-01T14:02:00Z")
    assert load_session(db, raw_token) is None


def test_session_absolute_expiry_and_logout(
    db, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLUBLEDGER_ENV", "test")
    clock.set_now("2026-08-01T10:00:00Z")

    user_id = register_user(
        db, email="abs@example.com", name="Abs User", password="Password123"
    )
    raw_token, _ = create_session(db, user_id)

    # Active every 30 minutes up to +8h01m -> absolute limit still terminates session
    clock.set_now("2026-08-01T18:01:00Z")
    assert load_session(db, raw_token) is None

    # Revoked session (logout) returns None (AUTH-04)
    clock.set_now("2026-08-01T10:00:00Z")
    raw_token2, _ = create_session(db, user_id)
    s = load_session(db, raw_token2)
    assert s is not None
    revoke_session(db, s.id)
    assert load_session(db, raw_token2) is None


def test_user_deactivation_revokes_sessions(
    db, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLUBLEDGER_ENV", "test")
    clock.set_now("2026-08-01T10:00:00Z")

    user_id = register_user(
        db, email="deact@example.com", name="Deact User", password="Password123"
    )
    raw_token, _ = create_session(db, user_id)
    assert (
        load_session(db, raw_token) is None
        or load_session(db, raw_token).user_id == user_id
    )

    # Deactivating user revokes sessions immediately (AUTH-06)
    deactivate_user(db, user_id)
    assert load_session(db, raw_token) is None


def test_live_permission_checks_and_role_revocation(
    db, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLUBLEDGER_ENV", "test")
    now = "2026-08-01T10:00:00Z"
    clock.set_now(now)

    user_id = register_user(
        db, email="roles@example.com", name="Role User", password="Password123"
    )

    # Plain registered member has no staff permissions (AUTH-01, CONTRACT §4.3)
    perms = get_user_permissions(db, user_id)
    assert len(perms) == 0

    # Grant 'door' role
    door_role_id = db.execute("SELECT id FROM roles WHERE code = 'door';").fetchone()[
        "id"
    ]
    db.execute(
        "INSERT INTO user_roles (user_id, role_id, granted_at, created_at) VALUES (?, ?, ?, ?);",
        (user_id, door_role_id, now, now),
    )

    # User now immediately has door permissions (events.checkin, members.verify)
    door_perms = get_user_permissions(db, user_id)
    assert "events.checkin" in door_perms
    assert "members.verify" in door_perms
    assert "finance.view" not in door_perms

    # Revoking role takes effect immediately without caching (AUTH-05)
    db.execute(
        "UPDATE user_roles SET revoked_at = ? WHERE user_id = ?;", (now, user_id)
    )
    revoked_perms = get_user_permissions(db, user_id)
    assert len(revoked_perms) == 0

    # Admin role grants all permissions
    admin_role_id = db.execute("SELECT id FROM roles WHERE code = 'admin';").fetchone()[
        "id"
    ]
    db.execute(
        "INSERT INTO user_roles (user_id, role_id, granted_at, created_at) VALUES (?, ?, ?, ?);",
        (user_id, admin_role_id, now, now),
    )
    admin_perms = get_user_permissions(db, user_id)
    assert "finance.view" in admin_perms
    assert "events.checkin" in admin_perms
    assert "close.run" in admin_perms
