-- 0007_tasks.sql
-- Owner C
-- Fundraisers and Tasks schema per CONTRACT.md §1.7

CREATE TABLE fundraisers (
  id INTEGER PRIMARY KEY,
  term_id INTEGER NOT NULL REFERENCES terms(id),
  title TEXT NOT NULL,
  goal_paise INTEGER CHECK (goal_paise IS NULL OR goal_paise > 0),
  status TEXT NOT NULL CHECK (status IN ('PLANNING','ACTIVE','DONE','CANCELLED')),
  created_at TEXT NOT NULL
) STRICT;

CREATE TABLE tasks (
  id INTEGER PRIMARY KEY,
  fundraiser_id INTEGER NOT NULL REFERENCES fundraisers(id),
  title TEXT NOT NULL,
  owner_user_id INTEGER REFERENCES users(id),
  due_at TEXT,
  status TEXT NOT NULL CHECK (status IN ('TODO','DOING','DONE','BLOCKED')),
  created_at TEXT NOT NULL,
  UNIQUE (id, fundraiser_id)
) STRICT;
