-- Remember which notices each account has read. Business records remain the source.
CREATE TABLE notification_reads (
 id INTEGER PRIMARY KEY,
 user_id INTEGER NOT NULL REFERENCES users(id),
 notification_key TEXT NOT NULL CHECK(length(notification_key) BETWEEN 1 AND 120),
 read_at TEXT NOT NULL,
 UNIQUE(user_id, notification_key)
) STRICT;
