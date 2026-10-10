import hashlib
import json

from clubledger.core import clock
from clubledger.core.errors import DomainError
from clubledger.reports.service import balance, movement, check_integrity


def checklist(conn, term_id):
    term = conn.execute('SELECT * FROM terms WHERE id=?', (term_id,)).fetchone()
    if not term or term['status'] != 'OPEN':
        raise DomainError('TERM_CLOSED', 409)
    checks = []
    def add(code, title, passed, detail):
        checks.append(dict(code=code, title=title, passed=bool(passed), detail=str(detail)))
    payments = conn.execute("SELECT COUNT(*) FROM payments WHERE status IN ('CREATED','PENDING') OR (status='SUCCEEDED' AND fulfillment='UNFULFILLED')").fetchone()[0]
    receipts = conn.execute("SELECT COUNT(*) FROM payment_events WHERE outcome='UNAPPLIED_RECEIPT' AND resolution IS NULL").fetchone()[0]
    add('payments', 'Resolve pending and unapplied payments', payments+receipts == 0, f'{payments} pending/unfulfilled payments; {receipts} unapplied receipts')
    expenses = conn.execute("SELECT COUNT(*) FROM expenses WHERE status IN ('SUBMITTED','APPROVED')").fetchone()[0]
    add('expenses', 'Complete expense reimbursements', expenses == 0, f'{expenses} unfinished expenses')
    holds = conn.execute("SELECT COUNT(*) FROM ticket_holds WHERE status='HELD'").fetchone()[0]
    orders = conn.execute("SELECT COUNT(*) FROM merch_orders WHERE status='RESERVED'").fetchone()[0]
    add('reservations', 'Clear ticket and merchandise reservations', holds+orders == 0, f'{holds} holds; {orders} reservations')
    drafts = conn.execute("SELECT COUNT(*) FROM journal_entries WHERE term_id=? AND status<>'POSTED'", (term_id,)).fetchone()[0]
    integrity = check_integrity(conn)
    add('journal', 'Balance and reconcile the journal', drafts == 0 and integrity['passed'], f'{drafts} draft entries; integrity: {integrity["passed"]}')
    obligations = balance(conn, '2000') + balance(conn, '2100')
    add('obligations', 'Clear payment and reimbursement obligations', balance(conn, '2000') == 0 and balance(conn, '2100') == 0, f'{obligations} paise outstanding')
    clearing = balance(conn, '1100')
    add('settlement', 'Settle received payments to cash', clearing == 0, f'{clearing} paise in clearing; settlement is T+1')
    missing = conn.execute("SELECT COUNT(*) FROM expenses e WHERE status='PAID' AND NOT EXISTS(SELECT 1 FROM receipts r WHERE r.expense_id=e.id)").fetchone()[0]
    add('receipts', 'Attach every paid expense receipt', missing == 0, f'{missing} missing receipts')
    add('time', 'Close after the period starts', clock.now() > term['starts_at'], f'Period started {term["starts_at"]}')
    return checks


def run_close(conn, term_id, actor_id):
    if not conn.in_transaction:
        raise RuntimeError('Close requires an outer BEGIN IMMEDIATE transaction.')
    checks = checklist(conn, term_id)
    failed = [row['title'] for row in checks if not row['passed']]
    if failed:
        raise DomainError('CLOSE_BLOCKED', 409, '; '.join(failed))
    term = conn.execute('SELECT * FROM terms WHERE id=?', (term_id,)).fetchone()
    now = clock.now()
    watermark = conn.execute("SELECT COALESCE(MAX(id),0) FROM journal_entries WHERE status='POSTED'").fetchone()[0]
    accounts = []
    for account in conn.execute('SELECT code,name,type AS kind FROM accounts ORDER BY code'):
        value = balance(conn, account['code'], watermark_id=watermark)
        change = movement(conn, account['code'], term_id)
        signed = change.debit_paise-change.credit_paise if account['kind'] in ('ASSET','EXPENSE') else change.credit_paise-change.debit_paise
        if account['kind'] in ('INCOME','EXPENSE'):
            value = signed
        accounts.append(dict(code=account['code'], name=account['name'], kind=account['kind'], opening=value-signed, movement=signed, closing=value))
    totals = dict(term_id=term_id, label=term['label'], watermark_entry_id=watermark, accounts=accounts,
                  payments=conn.execute('SELECT COUNT(*) FROM payments WHERE term_id=?', (term_id,)).fetchone()[0],
                  sources=[dict(row) for row in conn.execute("SELECT e.source_type,COUNT(DISTINCT e.id) AS entries,SUM(l.debit_paise) AS debit_paise,SUM(l.credit_paise) AS credit_paise FROM journal_entries e JOIN journal_lines l ON l.entry_id=e.id WHERE e.term_id=? AND e.status='POSTED' AND e.id<=? GROUP BY e.source_type",(term_id,watermark))],
                  events=[dict(row) for row in conn.execute('SELECT event_id,COUNT(*) AS tickets,SUM(price_paise) AS gross_paise FROM tickets WHERE payment_id IN (SELECT id FROM payments WHERE term_id=?) GROUP BY event_id', (term_id,))])
    raw = json.dumps(totals, sort_keys=True, separators=(',', ':'))
    snapshot = conn.execute('INSERT INTO close_snapshots(term_id,taken_at,taken_by,watermark_entry_id,totals_json,content_sha256,created_at) VALUES(?,?,?,?,?,?,?)',
                            (term_id, now, actor_id, watermark, raw, hashlib.sha256(raw.encode()).hexdigest(), now)).lastrowid
    for row in checks:
        conn.execute('INSERT INTO close_checks(term_id,code,passed,detail,evaluated_at,created_at) VALUES(?,?,1,?,?,?)', (term_id, row['code'], row['detail'], now, now))
    conn.execute("UPDATE terms SET status='CLOSED',ends_at=?,closed_at=? WHERE id=?", (now, now, term_id))
    conn.execute("INSERT INTO terms(label,starts_at,status,created_at) VALUES(?,?,'OPEN',?)", (f'Period {term_id+1} · {now[:10]}', now, now))
    conn.execute("INSERT INTO audit_log(actor_user_id,action,entity,entity_id,detail,created_at) VALUES(?,'close','terms',?,?,?)", (actor_id, term_id, raw, now))
    return snapshot


def run_handover(conn, term_id, from_user_id, to_user_id, role_codes, notes=''):
    if not conn.in_transaction:
        raise RuntimeError('Handover requires an outer BEGIN IMMEDIATE transaction.')
    term = conn.execute("SELECT 1 FROM terms t JOIN close_snapshots s ON s.term_id=t.id WHERE t.id=? AND t.status='CLOSED'", (term_id,)).fetchone()
    if not term:
        raise DomainError('VALIDATION', 422, 'Close the period before officer handover.')
    if from_user_id == to_user_id or not role_codes:
        raise DomainError('VALIDATION', 422, 'Choose two different officers and at least one role.')
    if conn.execute('SELECT 1 FROM officer_handover WHERE term_id=?', (term_id,)).fetchone():
        raise DomainError('VALIDATION', 422, 'This period already has a handover record.')
    if not conn.execute('SELECT 1 FROM users WHERE id=? AND is_active=1', (to_user_id,)).fetchone():
        raise DomainError('VALIDATION', 422, 'The receiving officer must be active.')
    now = clock.now()
    roles = []
    for code in set(role_codes):
        role = conn.execute('SELECT r.id FROM roles r JOIN user_roles ur ON ur.role_id=r.id WHERE r.code=? AND ur.user_id=? AND ur.revoked_at IS NULL', (code, from_user_id)).fetchone()
        if not role:
            raise DomainError('VALIDATION', 422, 'The outgoing officer does not hold every selected role.')
        roles.append(role['id'])
    for role in roles:
        conn.execute('UPDATE user_roles SET revoked_at=? WHERE user_id=? AND role_id=? AND revoked_at IS NULL', (now, from_user_id, role))
        if not conn.execute('SELECT 1 FROM user_roles WHERE user_id=? AND role_id=? AND revoked_at IS NULL', (to_user_id, role)).fetchone():
            conn.execute('INSERT INTO user_roles(user_id,role_id,granted_at,created_at) VALUES(?,?,?,?)', (to_user_id, role, now, now))
    if not conn.execute("SELECT 1 FROM user_roles ur JOIN roles r ON r.id=ur.role_id JOIN users u ON u.id=ur.user_id WHERE r.code='admin' AND ur.revoked_at IS NULL AND u.is_active=1 AND u.id<>?", (from_user_id,)).fetchone():
        raise DomainError('VALIDATION', 422, 'At least one active admin must remain.')
    conn.execute('UPDATE sessions SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL', (now, from_user_id))
    changes = json.dumps(sorted(set(role_codes)))
    result = conn.execute('INSERT INTO officer_handover(term_id,from_user_id,to_user_id,notes,role_changes_json,completed_at,created_at) VALUES(?,?,?,?,?,?,?)', (term_id, from_user_id, to_user_id, notes, changes, now, now)).lastrowid
    conn.execute("INSERT INTO audit_log(actor_user_id,action,entity,entity_id,detail,created_at) VALUES(?,'handover','terms',?,?,?)", (to_user_id, term_id, changes, now))
    return result
