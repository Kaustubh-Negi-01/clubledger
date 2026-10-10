CREATE TABLE announcements (
 id INTEGER PRIMARY KEY, author_id INTEGER NOT NULL REFERENCES users(id), term_id INTEGER NOT NULL REFERENCES terms(id),
 title TEXT NOT NULL, body TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('DRAFT','PUBLISHED')),
 published_at TEXT, created_at TEXT NOT NULL, CHECK((status='PUBLISHED')=(published_at IS NOT NULL))
) STRICT;
CREATE TRIGGER immutable_announcements BEFORE UPDATE ON announcements WHEN OLD.status='PUBLISHED'
BEGIN SELECT RAISE(ABORT,'PUBLISHED_IMMUTABLE'); END;
CREATE TRIGGER preserve_announcements BEFORE DELETE ON announcements WHEN OLD.status='PUBLISHED'
BEGIN SELECT RAISE(ABORT,'PUBLISHED_IMMUTABLE'); END;
CREATE TABLE subscribers (
 id INTEGER PRIMARY KEY, email TEXT NOT NULL UNIQUE COLLATE NOCASE, user_id INTEGER REFERENCES users(id),
 status TEXT NOT NULL CHECK(status IN ('SUBSCRIBED','UNSUBSCRIBED')), unsub_token TEXT NOT NULL UNIQUE,
 subscribed_at TEXT NOT NULL, unsubscribed_at TEXT, created_at TEXT NOT NULL
) STRICT;
CREATE TABLE mail_outbox (
 id INTEGER PRIMARY KEY, dedupe_key TEXT NOT NULL UNIQUE, to_email TEXT NOT NULL, subject TEXT NOT NULL, body TEXT NOT NULL,
 kind TEXT NOT NULL CHECK(kind IN ('ANNOUNCEMENT','RENEW_30D','RENEW_7D','EXPIRED')),
 ref_table TEXT NOT NULL CHECK(ref_table IN ('announcements','memberships')), ref_id INTEGER NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('QUEUED','SENT','FAILED','SUPPRESSED')), suppressed_reason TEXT,
 attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT, processed_at TEXT, created_at TEXT NOT NULL,
 CHECK((status='SUPPRESSED')=(suppressed_reason IS NOT NULL))
) STRICT;
CREATE INDEX ix_outbox_status ON mail_outbox(status);
CREATE TABLE mail_capture (
 id INTEGER PRIMARY KEY, outbox_id INTEGER NOT NULL UNIQUE REFERENCES mail_outbox(id), to_email TEXT NOT NULL,
 subject TEXT NOT NULL, body TEXT NOT NULL, captured_at TEXT NOT NULL, created_at TEXT NOT NULL
) STRICT;
