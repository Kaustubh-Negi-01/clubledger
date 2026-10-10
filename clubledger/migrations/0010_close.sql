CREATE TABLE close_snapshots (
 id INTEGER PRIMARY KEY, term_id INTEGER NOT NULL UNIQUE REFERENCES terms(id), taken_at TEXT NOT NULL,
 taken_by INTEGER NOT NULL REFERENCES users(id), watermark_entry_id INTEGER NOT NULL,
 totals_json TEXT NOT NULL, content_sha256 TEXT NOT NULL, created_at TEXT NOT NULL
) STRICT;
CREATE TRIGGER immutable_snapshot_update BEFORE UPDATE ON close_snapshots BEGIN SELECT RAISE(ABORT,'SNAPSHOT_IMMUTABLE'); END;
CREATE TRIGGER immutable_snapshot_delete BEFORE DELETE ON close_snapshots BEGIN SELECT RAISE(ABORT,'SNAPSHOT_IMMUTABLE'); END;
CREATE TABLE close_checks (
 id INTEGER PRIMARY KEY, term_id INTEGER NOT NULL REFERENCES terms(id), code TEXT NOT NULL,
 passed INTEGER NOT NULL CHECK(passed IN (0,1)), detail TEXT, evaluated_at TEXT NOT NULL, created_at TEXT NOT NULL
) STRICT;
CREATE TABLE officer_handover (
 id INTEGER PRIMARY KEY, term_id INTEGER NOT NULL UNIQUE REFERENCES terms(id),
 from_user_id INTEGER NOT NULL REFERENCES users(id), to_user_id INTEGER NOT NULL REFERENCES users(id),
 notes TEXT, role_changes_json TEXT NOT NULL, completed_at TEXT NOT NULL, created_at TEXT NOT NULL
) STRICT;
