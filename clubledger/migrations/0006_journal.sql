-- 0006_journal.sql
-- Owner C
-- Journal schema: accounts, journal_entries, journal_lines, triggers and chart of accounts seed

CREATE TABLE accounts (
  id INTEGER PRIMARY KEY,
  code TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  type TEXT NOT NULL CHECK (type IN ('ASSET','LIABILITY','INCOME','EXPENSE')),
  created_at TEXT NOT NULL
) STRICT;

CREATE TABLE journal_entries (
  id INTEGER PRIMARY KEY,
  term_id INTEGER NOT NULL REFERENCES terms(id),
  entry_date TEXT NOT NULL,
  source_type TEXT NOT NULL CHECK (source_type IN ('payment','payment_event','expense','adjustment')),
  source_id INTEGER NOT NULL,
  source_event TEXT NOT NULL,
  memo TEXT,
  status TEXT NOT NULL CHECK (status IN ('DRAFT','POSTED')),
  posted_at TEXT,
  reverses_entry_id INTEGER REFERENCES journal_entries(id),
  adjusts_term_id INTEGER REFERENCES terms(id),
  created_at TEXT NOT NULL,
  UNIQUE (source_type, source_id, source_event),
  CHECK ((status = 'POSTED') = (posted_at IS NOT NULL)),
  CHECK (adjusts_term_id IS NULL OR adjusts_term_id <> term_id),
  CHECK (adjusts_term_id IS NULL OR source_type = 'adjustment'),
  CHECK (source_event NOT LIKE '%_reversal' OR reverses_entry_id IS NOT NULL)
) STRICT;

CREATE INDEX ix_entries_term ON journal_entries(term_id, entry_date);
CREATE INDEX ix_entries_asof ON journal_entries(status, entry_date);
CREATE INDEX ix_entries_source ON journal_entries(source_type, source_id);
CREATE UNIQUE INDEX ux_entries_reversal ON journal_entries(reverses_entry_id) WHERE reverses_entry_id IS NOT NULL;

CREATE TABLE journal_lines (
  id INTEGER PRIMARY KEY,
  entry_id INTEGER NOT NULL REFERENCES journal_entries(id),
  account_id INTEGER NOT NULL REFERENCES accounts(id),
  debit_paise INTEGER NOT NULL DEFAULT 0 CHECK (debit_paise >= 0),
  credit_paise INTEGER NOT NULL DEFAULT 0 CHECK (credit_paise >= 0),
  created_at TEXT NOT NULL,
  CHECK ((debit_paise = 0) <> (credit_paise = 0))
) STRICT;

CREATE INDEX ix_lines_entry ON journal_lines(entry_id);
CREATE INDEX ix_lines_account ON journal_lines(account_id);

-- Triggers

-- 1. trg_entry_insert_draft_only:
-- status must be 'DRAFT' (direct INSERT of POSTED aborts)
-- term_id must reference a term with status='OPEN' (abort with TERM_CLOSED otherwise)
-- adjusts_term_id if set must reference a term with status='CLOSED'
CREATE TRIGGER trg_entry_insert_draft_only
BEFORE INSERT ON journal_entries
FOR EACH ROW
BEGIN
  SELECT CASE
    WHEN NEW.status <> 'DRAFT' THEN
      RAISE(ABORT, 'Direct INSERT of POSTED entry is not allowed')
    WHEN (SELECT status FROM terms WHERE id = NEW.term_id) <> 'OPEN' THEN
      RAISE(ABORT, 'TERM_CLOSED')
    WHEN NEW.adjusts_term_id IS NOT NULL AND (SELECT status FROM terms WHERE id = NEW.adjusts_term_id) <> 'CLOSED' THEN
      RAISE(ABORT, 'adjusts_term_id must reference a CLOSED term')
  END;
END;

-- 2. trg_entry_adjusts_term_check:
-- BEFORE UPDATE OF adjusts_term_id ON journal_entries
-- adjusts_term_id if set must reference a term with status='CLOSED'
CREATE TRIGGER trg_entry_adjusts_term_check
BEFORE UPDATE OF adjusts_term_id ON journal_entries
FOR EACH ROW
WHEN NEW.adjusts_term_id IS NOT NULL
BEGIN
  SELECT CASE
    WHEN (SELECT status FROM terms WHERE id = NEW.adjusts_term_id) <> 'CLOSED' THEN
      RAISE(ABORT, 'adjusts_term_id must reference a CLOSED term')
  END;
END;

-- 3. trg_entry_post_check:
-- BEFORE UPDATE OF status ON journal_entries WHEN NEW.status = 'POSTED'
-- OLD.status must be 'DRAFT'
-- line count >= 2
-- Σdebit = Σcredit and > 0
-- term_id must still be 'OPEN'
-- adjusts_term_id if set must still reference a term with status='CLOSED'
CREATE TRIGGER trg_entry_post_check
BEFORE UPDATE OF status ON journal_entries
FOR EACH ROW
WHEN NEW.status = 'POSTED'
BEGIN
  SELECT CASE
    WHEN OLD.status <> 'DRAFT' THEN
      RAISE(ABORT, 'Only DRAFT entries can be transitioned to POSTED')
    WHEN (SELECT status FROM terms WHERE id = NEW.term_id) <> 'OPEN' THEN
      RAISE(ABORT, 'TERM_CLOSED')
    WHEN NEW.adjusts_term_id IS NOT NULL AND (SELECT status FROM terms WHERE id = NEW.adjusts_term_id) <> 'CLOSED' THEN
      RAISE(ABORT, 'adjusts_term_id must reference a CLOSED term')
    WHEN (SELECT COUNT(*) FROM journal_lines WHERE entry_id = NEW.id) < 2 THEN
      RAISE(ABORT, 'Posted entry must have at least 2 lines')
    WHEN (SELECT COALESCE(SUM(debit_paise), 0) FROM journal_lines WHERE entry_id = NEW.id) <>
         (SELECT COALESCE(SUM(credit_paise), 0) FROM journal_lines WHERE entry_id = NEW.id) THEN
      RAISE(ABORT, 'Debits and credits must balance')
    WHEN (SELECT COALESCE(SUM(debit_paise), 0) FROM journal_lines WHERE entry_id = NEW.id) <= 0 THEN
      RAISE(ABORT, 'Total amount must be greater than zero')
  END;
END;

-- 4. trg_entry_immutable_posted:
-- BEFORE UPDATE or DELETE WHEN OLD.status = 'POSTED' -> always abort
CREATE TRIGGER trg_entry_immutable_posted_update
BEFORE UPDATE ON journal_entries
FOR EACH ROW
WHEN OLD.status = 'POSTED'
BEGIN
  SELECT RAISE(ABORT, 'POSTED journal entries are immutable');
END;

CREATE TRIGGER trg_entry_immutable_posted_delete
BEFORE DELETE ON journal_entries
FOR EACH ROW
WHEN OLD.status = 'POSTED'
BEGIN
  SELECT RAISE(ABORT, 'POSTED journal entries cannot be deleted');
END;

-- 5. trg_entry_term_fixed:
-- BEFORE UPDATE OF term_id, source_type, source_id, source_event, reverses_entry_id ON journal_entries -> abort
CREATE TRIGGER trg_entry_term_fixed
BEFORE UPDATE OF term_id, source_type, source_id, source_event, reverses_entry_id ON journal_entries
FOR EACH ROW
BEGIN
  SELECT RAISE(ABORT, 'Key entry fields cannot be modified');
END;

-- 6. trg_line_insert_draft_only:
-- parent entry must exist and be DRAFT
CREATE TRIGGER trg_line_insert_draft_only
BEFORE INSERT ON journal_lines
FOR EACH ROW
BEGIN
  SELECT CASE
    WHEN (SELECT status FROM journal_entries WHERE id = NEW.entry_id) IS NULL THEN
      RAISE(ABORT, 'Parent journal entry does not exist')
    WHEN (SELECT status FROM journal_entries WHERE id = NEW.entry_id) <> 'DRAFT' THEN
      RAISE(ABORT, 'Lines can only be inserted into DRAFT entries')
  END;
END;

-- 7. trg_line_update_blocked:
-- abort if old parent or new parent is POSTED; entry_id may never change
CREATE TRIGGER trg_line_update_blocked
BEFORE UPDATE ON journal_lines
FOR EACH ROW
BEGIN
  SELECT CASE
    WHEN NEW.entry_id <> OLD.entry_id THEN
      RAISE(ABORT, 'entry_id cannot be changed')
    WHEN (SELECT status FROM journal_entries WHERE id = OLD.entry_id) = 'POSTED' THEN
      RAISE(ABORT, 'Cannot update lines of a POSTED entry')
    WHEN (SELECT status FROM journal_entries WHERE id = NEW.entry_id) = 'POSTED' THEN
      RAISE(ABORT, 'Cannot move lines into a POSTED entry')
  END;
END;

-- 8. trg_line_delete_draft_only:
-- abort if parent is POSTED
CREATE TRIGGER trg_line_delete_draft_only
BEFORE DELETE ON journal_lines
FOR EACH ROW
BEGIN
  SELECT CASE
    WHEN (SELECT status FROM journal_entries WHERE id = OLD.entry_id) = 'POSTED' THEN
      RAISE(ABORT, 'Cannot delete lines from a POSTED entry')
  END;
END;

-- Seed fixed chart of accounts (CONTRACT §1.6)
INSERT INTO accounts (code, name, type, created_at) VALUES
  ('1000', 'Cash on Hand/Bank', 'ASSET', '1970-01-01T00:00:00Z'),
  ('1100', 'Payment Clearing', 'ASSET', '1970-01-01T00:00:00Z'),
  ('2000', 'Unfulfilled Payments Obligation', 'LIABILITY', '1970-01-01T00:00:00Z'),
  ('2100', 'Reimbursements Payable', 'LIABILITY', '1970-01-01T00:00:00Z'),
  ('4000', 'Dues Income', 'INCOME', '1970-01-01T00:00:00Z'),
  ('4100', 'Ticket Income', 'INCOME', '1970-01-01T00:00:00Z'),
  ('4200', 'Merchandise Income', 'INCOME', '1970-01-01T00:00:00Z'),
  ('5000', 'Events Expense', 'EXPENSE', '1970-01-01T00:00:00Z'),
  ('5010', 'Merch Stock Expense', 'EXPENSE', '1970-01-01T00:00:00Z'),
  ('5020', 'Fundraiser Expense', 'EXPENSE', '1970-01-01T00:00:00Z'),
  ('5090', 'Other Expense', 'EXPENSE', '1970-01-01T00:00:00Z');
