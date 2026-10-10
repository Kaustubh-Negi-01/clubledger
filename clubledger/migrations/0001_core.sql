-- 0001_core.sql: Core authentication, sessions, terms, and schema migrations

CREATE TABLE users (
  id INTEGER PRIMARY KEY,
  email TEXT NOT NULL UNIQUE COLLATE NOCASE,
  name TEXT NOT NULL,
  password_hash TEXT NOT NULL,
  is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
  created_at TEXT NOT NULL
) STRICT;

CREATE TABLE roles (
  id INTEGER PRIMARY KEY,
  code TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL
) STRICT;

CREATE TABLE permissions (
  id INTEGER PRIMARY KEY,
  code TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL
) STRICT;

CREATE TABLE role_permissions (
  role_id INTEGER NOT NULL REFERENCES roles(id),
  permission_id INTEGER NOT NULL REFERENCES permissions(id),
  created_at TEXT NOT NULL,
  PRIMARY KEY (role_id, permission_id)
) STRICT;

CREATE TABLE user_roles (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  role_id INTEGER NOT NULL REFERENCES roles(id),
  granted_at TEXT NOT NULL,
  revoked_at TEXT,
  created_at TEXT NOT NULL
) STRICT;

CREATE UNIQUE INDEX ux_user_roles_live ON user_roles(user_id, role_id) WHERE revoked_at IS NULL;

CREATE TABLE sessions (
  id INTEGER PRIMARY KEY,
  token_hash TEXT NOT NULL UNIQUE,
  user_id INTEGER NOT NULL REFERENCES users(id),
  csrf_token TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  idle_expires_at TEXT NOT NULL,
  absolute_expires_at TEXT NOT NULL,
  revoked_at TEXT,
  created_at TEXT NOT NULL
) STRICT;

CREATE INDEX ix_sessions_user ON sessions(user_id);

CREATE TABLE terms (
  id INTEGER PRIMARY KEY,
  label TEXT NOT NULL UNIQUE,
  starts_at TEXT NOT NULL,
  ends_at TEXT,
  status TEXT NOT NULL CHECK (status IN ('OPEN','CLOSED')),
  closed_at TEXT,
  created_at TEXT NOT NULL,
  CHECK ((status = 'OPEN' AND ends_at IS NULL AND closed_at IS NULL)
      OR (status = 'CLOSED' AND ends_at IS NOT NULL AND closed_at IS NOT NULL AND ends_at > starts_at))
) STRICT;

CREATE UNIQUE INDEX ux_terms_one_open ON terms(status) WHERE status = 'OPEN';

CREATE TABLE audit_log (
  id INTEGER PRIMARY KEY,
  actor_user_id INTEGER REFERENCES users(id),
  action TEXT NOT NULL,
  entity TEXT NOT NULL,
  entity_id INTEGER,
  detail TEXT,
  created_at TEXT NOT NULL
) STRICT;

CREATE TABLE idempotency_keys (
  actor_user_id INTEGER NOT NULL REFERENCES users(id),
  action TEXT NOT NULL,
  key TEXT NOT NULL,
  request_hash TEXT NOT NULL,
  result_ref TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (actor_user_id, action, key)
) STRICT;

CREATE TABLE schema_migrations (
  number INTEGER PRIMARY KEY,
  filename TEXT NOT NULL,
  checksum TEXT NOT NULL,
  applied_at TEXT NOT NULL
) STRICT;
