-- 0008_expenses.sql
-- Owner C
-- Expenses and Receipts schema per CONTRACT.md §1.8

CREATE TABLE expenses (
  id INTEGER PRIMARY KEY,
  submitter_id INTEGER NOT NULL REFERENCES users(id),
  term_id INTEGER NOT NULL REFERENCES terms(id),
  category_account_id INTEGER NOT NULL REFERENCES accounts(id),
  amount_paise INTEGER NOT NULL CHECK (amount_paise > 0),
  description TEXT NOT NULL,
  event_id INTEGER REFERENCES events(id),
  fundraiser_id INTEGER REFERENCES fundraisers(id),
  task_id INTEGER,
  status TEXT NOT NULL CHECK (status IN ('SUBMITTED','APPROVED','REJECTED','PAID','VOID')),
  decided_by INTEGER REFERENCES users(id),
  decided_at TEXT,
  decision_note TEXT,
  paid_by INTEGER REFERENCES users(id),
  paid_at TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY (task_id, fundraiser_id) REFERENCES tasks(id, fundraiser_id),
  CHECK (task_id IS NULL OR fundraiser_id IS NOT NULL)
) STRICT;

CREATE INDEX ix_expenses_status ON expenses(status);

CREATE TABLE receipts (
  id INTEGER PRIMARY KEY,
  uploader_id INTEGER NOT NULL REFERENCES users(id),
  expense_id INTEGER NOT NULL REFERENCES expenses(id),
  stored_name TEXT NOT NULL UNIQUE,
  original_name TEXT NOT NULL,
  mime TEXT NOT NULL CHECK (mime IN ('image/png','image/jpeg','application/pdf')),
  size_bytes INTEGER NOT NULL CHECK (size_bytes BETWEEN 1 AND 5242880),
  sha256 TEXT NOT NULL,
  created_at TEXT NOT NULL
) STRICT;

CREATE INDEX ix_receipts_expense ON receipts(expense_id);
