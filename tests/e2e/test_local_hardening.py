"""Failure recovery and basic rendered accessibility on actual application routes."""
import sqlite3
import pytest
from bs4 import BeautifulSoup
from clubledger.core import clock
from clubledger.core.db import unit_of_work
from clubledger.core.errors import DomainError
from clubledger.comms import service as comms
from clubledger.close import service as close


@pytest.fixture(autouse=True)
def isolated_receipts(tmp_path, monkeypatch):
    monkeypatch.setenv('CLUBLEDGER_RECEIPTS_DIR',str(tmp_path/'receipts'))


def membership(conn, user, *, year='2026-27', starts='2026-07-31T18:30:00Z', expires='2027-07-31T18:30:00Z', status='ACTIVE'):
    plan = conn.execute('SELECT id FROM membership_plans LIMIT 1').fetchone()[0]
    return conn.execute('INSERT INTO memberships(user_id,plan_id,membership_year,status,starts_at,expires_at,member_code,qr_token,created_at) VALUES(?,?,?,?,?,?,?,?,?)',
                        (user['id'],plan,year,status,starts,expires,f'M-{user["id"]}-{year}',f'QR-{user["id"]}-{year}',clock.now())).lastrowid


@pytest.mark.req('MEM-06','pos')
def test_reminder_windows_deduplicate_and_expire(db, make_user, clock):
    clock.set_now('2027-07-01T18:30:00Z')
    member = make_user(email='reminder@college.edu')
    identifier = membership(db,member)
    assert comms.send_reminders(db)==1
    assert comms.send_reminders(db)==0
    assert comms.process_mail_outbox(db)==1
    clock.set_now('2027-07-24T18:30:00Z')
    assert comms.send_reminders(db)==1
    assert comms.process_mail_outbox(db)==1
    clock.set_now('2027-07-31T18:30:00Z')
    assert comms.send_reminders(db)==1
    assert comms.send_reminders(db)==0
    assert comms.process_mail_outbox(db)==1
    assert db.execute('SELECT status FROM memberships WHERE id=?',(identifier,)).fetchone()[0]=='EXPIRED'
    assert {row[0] for row in db.execute('SELECT kind FROM mail_outbox')}=={'RENEW_30D','RENEW_7D','EXPIRED'}
    assert db.execute('SELECT COUNT(*) FROM mail_capture').fetchone()[0]==3


@pytest.mark.req('MEM-06','neg')
def test_renewed_and_inactive_members_are_suppressed(db, make_user, clock):
    clock.set_now('2027-07-01T18:30:00Z')
    renewed = make_user(email='already-renewed@college.edu')
    inactive = make_user(email='inactive-reminder@college.edu')
    make_user(email='never-a-member@college.edu')
    membership(db,renewed)
    membership(db,inactive)
    assert comms.send_reminders(db)==2
    membership(db,renewed,year='2027-28',starts='2027-07-31T18:30:00Z',expires='2028-07-31T18:30:00Z',status='PENDING')
    db.execute('UPDATE users SET is_active=0 WHERE id=?',(inactive['id'],))
    comms.process_mail_outbox(db)
    assert {row[0] for row in db.execute('SELECT suppressed_reason FROM mail_outbox')}=={'MEMBERSHIP_RENEWED','USER_INACTIVE'}
    assert db.execute('SELECT COUNT(*) FROM mail_capture').fetchone()[0]==0


@pytest.mark.req('COM-04','neg')
def test_mail_retries_stop_after_three_failures_without_disclosing_error(db, make_user, monkeypatch):
    author=make_user(email='retry-author@college.edu')
    comms.subscribe(db,'retry-reader@college.edu')
    item=comms.create_announcement(db,author['id'],'Retry','Body')
    comms.publish(db,item)
    def unavailable(*args):
        raise OSError('private credential must never be persisted')
    monkeypatch.setattr(comms,'_capture',unavailable)
    for attempt in range(1,4):
        assert comms.process_mail_outbox(db)==1
        row=db.execute('SELECT * FROM mail_outbox').fetchone()
        assert row['attempts']==attempt
        assert row['status']==('FAILED' if attempt==3 else 'QUEUED')
        assert row['last_error']=='OSError'
    assert comms.process_mail_outbox(db)==0
    assert db.execute('SELECT COUNT(*) FROM mail_capture').fetchone()[0]==0


@pytest.mark.req('CLS-03','neg')
def test_failure_after_snapshot_rolls_back_entire_close(db, make_user, clock):
    clock.set_now('2026-09-01T10:00:00Z')
    actor=make_user(email='close-rollback@college.edu',roles=['admin'])
    db.execute("CREATE TRIGGER inject_term_failure BEFORE INSERT ON terms WHEN NEW.id<>1 BEGIN SELECT RAISE(ABORT,'injected'); END")
    with pytest.raises(sqlite3.IntegrityError):
        with unit_of_work() as conn:
            close.run_close(conn,1,actor['id'])
    assert db.execute('SELECT COUNT(*) FROM close_snapshots').fetchone()[0]==0
    assert db.execute('SELECT COUNT(*) FROM close_checks').fetchone()[0]==0
    assert db.execute("SELECT status FROM terms WHERE id=1").fetchone()[0]=='OPEN'
    assert db.execute('SELECT COUNT(*) FROM terms').fetchone()[0]==1


@pytest.mark.req('CLS-07','neg')
def test_handover_cannot_remove_sole_admin_by_moving_unrelated_role(db, make_user, clock):
    clock.set_now('2026-09-01T10:00:00Z')
    outgoing=make_user(email='sole-admin@college.edu',roles=['admin','events'])
    incoming=make_user(email='handover-recipient@college.edu')
    with unit_of_work() as conn: close.run_close(conn,1,outgoing['id'])
    original=[tuple(row) for row in db.execute('SELECT * FROM user_roles')]
    with pytest.raises(DomainError):
        with unit_of_work() as conn: close.run_handover(conn,1,outgoing['id'],incoming['id'],['events'])
    assert original==[tuple(row) for row in db.execute('SELECT * FROM user_roles')]
    assert db.execute('SELECT COUNT(*) FROM officer_handover').fetchone()[0]==0


@pytest.mark.req('CLS-08','neg')
def test_three_closes_remain_contiguous_and_preserve_memberships(db, make_user, clock):
    clock.set_now('2026-09-01T10:00:00Z')
    actor=make_user(email='three-periods@college.edu',roles=['admin'])
    membership(db,actor)
    original=[tuple(row) for row in db.execute('SELECT * FROM memberships')]
    for index, instant in enumerate(['2026-09-02T10:00:00Z','2026-09-03T10:00:00Z','2026-09-04T10:00:00Z'],1):
        clock.set_now(instant)
        with unit_of_work() as conn: close.run_close(conn,index,actor['id'])
    terms=db.execute('SELECT * FROM terms ORDER BY id').fetchall()
    assert len(terms)==4 and terms[-1]['status']=='OPEN'
    assert all(a['ends_at']==b['starts_at'] for a,b in zip(terms,terms[1:]))
    assert original==[tuple(row) for row in db.execute('SELECT * FROM memberships')]


@pytest.mark.req('UXA-01','pos')
def test_rendered_pages_have_titles_landmarks_headings_and_labels(app_client, make_user, make_event, login_as):
    admin=make_user(email='markup-audit@college.edu',roles=['admin'])
    event=make_event()
    login_as(admin)
    paths=['/auth/login','/auth/register','/dashboard','/join','/members/card','/verify','/events',f'/events/{event["id"]}',f'/checkin/{event["id"]}',f'/admin/events/{event["id"]}/report','/store','/me/orders','/fundraisers','/expenses','/announcements','/admin/events','/admin/checkin','/admin/members','/admin/store','/admin/payments','/admin/announcements','/dev/mail','/admin/close','/admin/handover','/admin/adjustments','/finance','/finance/integrity']
    for path in paths:
        response=app_client.get(path,headers={'Accept':'text/html'})
        assert response.status_code==200,(path,response.text)
        html=BeautifulSoup(response.text,'html.parser')
        assert html.title and html.title.get_text(strip=True),path
        assert html.html.get('lang')=='en',path
        assert len(html.find_all('h1'))==1,path
        assert html.find('main') and html.find('nav',attrs={'aria-label':'Main navigation'}),path
        ids=[element['id'] for element in html.find_all(id=True)]
        assert len(ids)==len(set(ids)),f'duplicate element IDs on {path}'
        for control in html.find_all(['input','select','textarea']):
            if control.get('type') in ('hidden','submit','button'): continue
            labelled=control.get('aria-label') or control.get('aria-labelledby') or control.find_parent('label') or (control.get('id') and html.find('label',attrs={'for':control['id']}))
            assert labelled,f'unlabelled {control.get("name")} on {path}'
        for image in html.find_all('img'):
            assert image.has_attr('alt'),path


def test_json_board_and_expenses_remain_available(app_client, db, make_user, login_as):
    user=make_user(email='json-workflows@college.edu',roles=['admin'])
    login_as(user)
    from clubledger.tasks.service import create_fundraiser
    fundraiser=create_fundraiser(db,term_id=1,title='JSON board',goal_paise=10000,status='ACTIVE')
    assert app_client.get(f'/fundraisers/{fundraiser}/board',headers={'Accept':'application/json'}).json()['tasks']==[]
    assert app_client.get('/expenses',headers={'Accept':'application/json'}).json()=={'expenses':[]}


@pytest.mark.req('AUTH-06','pos')
@pytest.mark.req('AUTH-06','neg')
def test_deactivation_revokes_sessions_reactivation_does_not_restore_them(app_client, db, make_user, login_as):
    from clubledger.core.auth import load_session
    user=make_user(email='disable-me@college.edu')
    admin=make_user(email='disable-admin@college.edu',roles=['admin'])
    old_cookie,_=login_as(user)
    _,csrf=login_as(admin)
    for action in ['deactivate','reactivate']:
        response=app_client.post(f'/admin/users/{user["id"]}/status',data={'csrf_token':csrf,'action':action},follow_redirects=False)
        assert response.status_code==303
        assert load_session(db,old_cookie) is None
    response=app_client.post(f'/admin/users/{admin["id"]}/status',data={'csrf_token':csrf,'action':'deactivate'})
    assert response.status_code==422
    assert db.execute('SELECT is_active FROM users WHERE id=?',(admin['id'],)).fetchone()[0]==1


@pytest.mark.req('AUTH-12','pos')
@pytest.mark.req('AUTH-12','neg')
def test_login_throttle_returns_retry_after_and_recovers(app_client, clock):
    from clubledger.core.ratelimit import reset_rate_limits
    reset_rate_limits()
    clock.set_now('2026-09-01T10:00:00Z')
    from bs4 import BeautifulSoup
    token=BeautifulSoup(app_client.get('/auth/login').text,'html.parser').find('input',attrs={'name':'csrf_token'})['value']
    data={'email':'throttled@college.edu','password':'wrong-but-long','csrf_token':token}
    for _ in range(5): assert app_client.post('/auth/login',data=data).status_code==401
    response=app_client.post('/auth/login',data=data)
    assert response.status_code==429 and int(response.headers['Retry-After'])>0
    clock.set_now('2026-09-01T10:01:01Z')
    assert app_client.post('/auth/login',data=data).status_code==401


def test_defined_text_color_tokens_have_sufficient_contrast():
    def luminance(value):
        colors=[int(value[i:i+2],16)/255 for i in (1,3,5)]
        linear=[c/12.92 if c<=.04045 else ((c+.055)/1.055)**2.4 for c in colors]
        return sum(c*w for c,w in zip(linear,[.2126,.7152,.0722]))
    from pathlib import Path
    import re
    css=(Path(__file__).parents[2]/'clubledger/web/static/app.css').read_text(encoding='utf-8')
    tokens=dict(re.findall(r'--([a-z]+):(#[0-9a-f]{6})',css))
    pairs=[(tokens['ink'],tokens['canvas']),(tokens['muted'],tokens['surface']),(tokens['green'],tokens['surface']),(tokens['surface'],tokens['ink']),(tokens['ink'],tokens['yellow']),(tokens['danger'],'#fff3f4'),('#ffffff',tokens['green'])]
    for foreground,background in pairs:
        a,b=sorted([luminance(foreground),luminance(background)])
        assert (b+.05)/(a+.05)>=4.5,(foreground,background)


@pytest.mark.req('JNL-10','pos')
@pytest.mark.req('JNL-10','neg')
def test_finance_income_is_per_period_while_cash_carries_forward(app_client, db, make_user, login_as, clock):
    import json
    from clubledger.journal.service import post_entry
    from clubledger.core.types import Line
    clock.set_now('2026-09-01T10:00:00Z')
    admin=make_user(email='period-finance@college.edu',roles=['admin'])
    post_entry(db,term_id=1,entry_date=clock.now(),source_type='adjustment',source_id=1,source_event='income-test',memo='Test period income',lines=[Line('1000',10000,0),Line('4000',0,10000)])
    with unit_of_work() as conn: identifier=close.run_close(conn,1,admin['id'])
    original=db.execute('SELECT * FROM close_snapshots WHERE id=?',(identifier,)).fetchone()
    # Deliberately post at the exact same timestamp as the preceding close.
    entry=post_entry(db,term_id=2,entry_date=clock.now(),source_type='adjustment',source_id=2,source_event='income-test',memo='New period income',lines=[Line('1000',5000,0),Line('4000',0,5000)])
    assert entry>original['watermark_entry_id']
    login_as(admin)
    for period,expected_income in [(1,10000),(2,5000)]:
        response=app_client.get(f'/finance?period_id={period}',headers={'Accept':'application/json'}).json()
        assert response['cash_summary']['cash_on_hand']==15000
        assert next(row['net_paise'] for row in response['breakdown'] if row['account_code']=='4000')==expected_income
        drill=app_client.get(f'/finance/accounts/4000?period_id={period}',headers={'Accept':'application/json'}).json()
        assert drill['total_paise']==expected_income
    clock.set_now('2026-09-02T10:00:00Z')
    with unit_of_work() as conn: second=close.run_close(conn,2,admin['id'])
    totals=json.loads(db.execute('SELECT totals_json FROM close_snapshots WHERE id=?',(second,)).fetchone()[0])
    income=next(row for row in totals['accounts'] if row['code']=='4000')
    cash=next(row for row in totals['accounts'] if row['code']=='1000')
    assert income['opening']==0 and income['movement']==income['closing']==5000
    assert cash['opening']==10000 and cash['movement']==5000 and cash['closing']==15000
    assert original['totals_json']==db.execute('SELECT totals_json FROM close_snapshots WHERE id=?',(identifier,)).fetchone()[0]


@pytest.mark.req('CMD-01','pos')
@pytest.mark.req('CMD-01','neg')
def test_local_commands_idempotent_and_reset_requires_exact_target(tmp_path, monkeypatch):
    from clubledger.cli import main
    from clubledger.core.db import connect
    target=(tmp_path/'commands.db').resolve()
    monkeypatch.setenv('CLUBLEDGER_ENV','test')
    monkeypatch.setenv('CLUBLEDGER_DB_PATH',str(target))
    def counts():
        conn=connect(str(target))
        try:
            return {name:conn.execute('SELECT COUNT(*) FROM "'+name+'"').fetchone()[0] for name in ['users','terms','products','tasks','announcements','mail_outbox','mail_capture','journal_entries']}
        finally: conn.close()
    for command in ['migrate','seed','expire-holds','send-reminders','process-mail','settle','check-integrity']:
        options=[command]+(['--demo'] if command=='seed' else [])
        assert main(options)==0
        before=counts()
        assert main(options)==0
        assert counts()==before
    assert main(['process-mail','--limit','0'])==1
    before=counts()
    assert main(['reset-db','--confirm',str(tmp_path/'wrong.db')])==1
    assert counts()==before
    assert main(['reset-db','--confirm',str(target)])==0
    assert list(tmp_path.glob('commands.db.backup-*'))
    assert counts()['users']==0
    monkeypatch.setenv('CLUBLEDGER_ENV','prod')
    monkeypatch.setenv('CLUBLEDGER_SIM_SECRET','test-only-production-config')
    assert main(['reset-db','--confirm',str(target)])==1
    assert main(['settle','--as-of','2026-09-01T10:00:00Z'])==1
