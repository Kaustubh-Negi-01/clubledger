"""Exercise actual outbox transactions with fake external transport, never send mail."""

import json
import io
import smtplib
import ssl
from urllib.error import HTTPError
import pytest
from clubledger.comms import service
from clubledger.comms import delivery
from tests.e2e.test_local_hardening import membership


def test_smtp_requires_validated_tls_and_fixed_provider(settings, monkeypatch):
    monkeypatch.setenv("CLUBLEDGER_MAIL_MODE", "brevo_smtp")
    monkeypatch.setenv("BREVO_SMTP_KEY", "test-smtp-only")
    monkeypatch.delenv("BREVO_SMTP_LOGIN", raising=False)
    with pytest.raises(delivery.MailConfigurationError):
        delivery.Settings.load()
    monkeypatch.setenv("BREVO_SMTP_LOGIN", "test@smtp-brevo.com")
    config = delivery.Settings.load()
    sent = []
    events = []

    class Client:
        def __init__(self, host, port, timeout):
            assert (host, port, timeout) == ("smtp-relay.brevo.com", 587, 8)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def ehlo(self):
            events.append("ehlo")

        def starttls(self, context):
            assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
            events.append("tls")

        def login(self, username, password):
            assert username == "test@smtp-brevo.com" and password == "test-smtp-only"
            assert "tls" in events
            events.append("login")

        def send_message(self, message):
            assert events[-1] == "login"
            sent.append(message)
            return {}

    monkeypatch.setattr(delivery.smtplib, "SMTP", Client)
    row = {
        "to_email": "reader@college.edu",
        "subject": "Renew",
        "body": "Renew at /join. Unsubscribe: /unsubscribe/token",
        "dedupe_key": "smtp1",
    }
    delivery.send_brevo_smtp(config, row)
    assert "https://clubledger-gold.vercel.app/join" in sent[0].get_content()
    assert sent[0]["To"] == "reader@college.edu"


def test_smtp_unknown_outcome_is_not_automatically_resent(
    db, make_user, settings, monkeypatch, clock
):
    monkeypatch.setenv("CLUBLEDGER_MAIL_MODE", "brevo_smtp")
    monkeypatch.setenv("BREVO_SMTP_KEY", "test-smtp-only")
    monkeypatch.setenv("BREVO_SMTP_LOGIN", "test@smtp-brevo.com")
    clock.set_now("2026-10-11T00:00:00Z")
    queued(db, make_user)
    db.execute(
        "UPDATE mail_outbox SET attempts=1,processed_at=?,last_error=?",
        (clock.now(), clock.now() + "|IN_FLIGHT"),
    )
    clock.set_now("2026-10-11T00:06:00Z")

    def forbidden(*args):
        pytest.fail("An uncertain SMTP attempt must never be sent again automatically")

    assert delivery.deliver_outbox(transport=forbidden, pace=False)["failed"] == 1
    assert (
        db.execute("SELECT last_error FROM mail_outbox").fetchone()[0]
        == "REVIEW_REQUIRED"
    )


def test_smtp_disconnect_requires_review(settings, monkeypatch):
    class Unavailable:
        def __init__(self, *args, **kwargs):
            raise smtplib.SMTPServerDisconnected("secret provider response")

    monkeypatch.setattr(delivery.smtplib, "SMTP", Unavailable)
    config = delivery.Settings(
        "test",
        "owner@gmail.com",
        "https://clubledger-gold.vercel.app",
        "brevo_smtp",
        "test@smtp-brevo.com",
    )
    with pytest.raises(delivery.DeliveryError) as failure:
        delivery.send_brevo_smtp(
            config,
            {
                "to_email": "reader@college.edu",
                "subject": "Test",
                "body": "text",
                "dedupe_key": "smtp2",
            },
        )
    assert failure.value.permanent and str(failure.value) == "SMTP_REVIEW_REQUIRED"


def test_brevo_uses_separate_server_key(settings, monkeypatch):
    monkeypatch.setenv("CLUBLEDGER_MAIL_MODE", "brevo")
    monkeypatch.delenv("BREVO_API_KEY", raising=False)
    with pytest.raises(delivery.MailConfigurationError):
        delivery.Settings.load()
    monkeypatch.setenv("BREVO_API_KEY", "brevo-test-only")
    config = delivery.Settings.load()
    assert config.provider == "brevo" and config.key == "brevo-test-only"


def test_brevo_request_and_duplicate_acceptance(settings, monkeypatch):
    config = delivery.Settings(
        "brevo-test-only",
        "owner@gmail.com",
        "https://clubledger-gold.vercel.app",
        "brevo",
    )
    row = {
        "to_email": "reader@college.edu",
        "subject": "Renewal",
        "body": "Renew at /join. Unsubscribe: /unsubscribe/token",
        "dedupe_key": "reminder-1",
    }
    requests = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, limit):
            return b'{"messageId":"provider-accepted"}'

    def fake_open(request, timeout):
        requests.append(request)
        return Response()

    monkeypatch.setattr(delivery, "urlopen", fake_open)
    assert delivery.send_brevo(config, row) == "provider-accepted"
    assert delivery.send_brevo(config, row) == "provider-accepted"
    payload = json.loads(requests[0].data)
    assert requests[0].full_url == "https://api.brevo.com/v3/smtp/email"
    assert requests[0].get_header("Api-key") == "brevo-test-only"
    assert payload["sender"]["email"] == "owner@gmail.com"
    assert payload["headers"] == json.loads(requests[1].data)["headers"]
    assert "https://clubledger-gold.vercel.app/join" in payload["textContent"]

    def duplicate(request, timeout):
        raise HTTPError(
            request.full_url,
            400,
            "duplicate",
            {},
            io.BytesIO(b'{"code":"duplicate_parameter"}'),
        )

    monkeypatch.setattr(delivery, "urlopen", duplicate)
    assert delivery.send_brevo(config, row) == "PREVIOUSLY_ACCEPTED"


def test_brevo_uncertain_attempt_stops_before_short_dedupe_window(
    db, make_user, settings, monkeypatch, clock
):
    monkeypatch.setenv("CLUBLEDGER_MAIL_MODE", "brevo")
    monkeypatch.setenv("BREVO_API_KEY", "brevo-test-only")
    clock.set_now("2026-10-11T00:00:00Z")
    queued(db, make_user)
    calls = []

    def uncertain(*args):
        calls.append(1)
        raise delivery.DeliveryError("PROVIDER_UNAVAILABLE")

    assert delivery.deliver_outbox(transport=uncertain, pace=False)["retrying"] == 1
    clock.set_now("2026-10-11T00:15:00Z")
    assert delivery.deliver_outbox(transport=uncertain, pace=False)["failed"] == 1
    assert len(calls) == 1
    assert (
        db.execute("SELECT last_error FROM mail_outbox").fetchone()[0]
        == "REVIEW_REQUIRED"
    )


@pytest.fixture
def settings(monkeypatch):
    monkeypatch.setenv("CLUBLEDGER_MAIL_MODE", "resend")
    monkeypatch.setenv("RESEND_API_KEY", "test-only")
    monkeypatch.setenv("CLUBLEDGER_MAIL_FROM", "club@verified.example.org")
    monkeypatch.setenv("CLUBLEDGER_SITE_URL", "https://clubledger-gold.vercel.app")


def queued(db, make_user, email="reader@college.edu"):
    author = make_user(email="email-author@college.edu")
    service.subscribe(db, email)
    item = service.create_announcement(
        db, author["id"], "Campus meeting", "Tomorrow at six"
    )
    service.publish(db, item)
    return item


def test_missing_provider_changes_nothing(db, make_user, monkeypatch):
    queued(db, make_user)
    monkeypatch.delenv("CLUBLEDGER_MAIL_MODE", raising=False)
    with pytest.raises(delivery.MailConfigurationError):
        delivery.deliver_outbox()
    row = db.execute("SELECT * FROM mail_outbox").fetchone()
    assert row["status"] == "QUEUED" and row["attempts"] == 0


def test_acceptance_is_once_and_network_runs_without_writer_lock(
    db, make_user, settings
):
    queued(db, make_user)
    sent = []

    def transport(config, row):
        # Can acquire a concurrent writer: external request holds no DB transaction.
        from clubledger.core.db import unit_of_work

        with unit_of_work() as other:
            other.execute("SELECT 1")
        sent.append(row["id"])
        return "provider-id"

    assert delivery.deliver_outbox(transport=transport, pace=False)["accepted"] == 1
    assert delivery.deliver_outbox(transport=transport, pace=False)["accepted"] == 0
    assert len(sent) == 1
    assert db.execute("SELECT status,attempts,last_error FROM mail_outbox").fetchone()[
        :
    ] == ("SENT", 1, None)
    assert db.execute("SELECT COUNT(*) FROM mail_capture").fetchone()[0] == 0


def test_unsubscribe_and_synthetic_recipients_never_reach_provider(
    db, make_user, settings
):
    queued(db, make_user)
    db.execute("UPDATE subscribers SET status='UNSUBSCRIBED'")
    author = db.execute(
        "SELECT id FROM users WHERE email='email-author@college.edu'"
    ).fetchone()[0]
    service.subscribe(db, "dataset00@demo.example")
    item = service.create_announcement(db, author, "Second", "Text")
    service.publish(db, item)

    def forbidden(*args):
        pytest.fail("An ineligible address reached the transport")

    result = delivery.deliver_outbox(transport=forbidden, pace=False)
    assert result["suppressed"] == 2
    assert {r[0] for r in db.execute("SELECT suppressed_reason FROM mail_outbox")} == {
        "UNSUBSCRIBED",
        "SYNTHETIC_ADDRESS",
    }


def test_retry_lease_three_attempts_and_sanitized_errors(
    db, make_user, settings, clock
):
    clock.set_now("2026-10-11T00:00:00Z")
    queued(db, make_user)

    def unavailable(*args):
        raise delivery.DeliveryError("PROVIDER_UNAVAILABLE")

    assert delivery.deliver_outbox(transport=unavailable, pace=False)["retrying"] == 1
    assert delivery.deliver_outbox(transport=unavailable, pace=False)["retrying"] == 0
    clock.set_now("2026-10-11T00:06:00Z")
    assert delivery.deliver_outbox(transport=unavailable, pace=False)["retrying"] == 1
    clock.set_now("2026-10-11T00:12:00Z")
    assert delivery.deliver_outbox(transport=unavailable, pace=False)["failed"] == 1
    assert db.execute("SELECT attempts FROM mail_outbox").fetchone()[0] == 3


def test_uncertain_attempt_is_not_replayed_outside_provider_window(
    db, make_user, settings, clock
):
    clock.set_now("2026-10-11T00:00:00Z")
    queued(db, make_user)
    db.execute(
        "UPDATE mail_outbox SET attempts=1,processed_at=?,last_error=?",
        (clock.now(), clock.now() + "|IN_FLIGHT"),
    )
    clock.set_now("2026-10-12T00:00:00Z")

    def forbidden(*args):
        pytest.fail("Unsafe replay outside idempotency window")

    assert delivery.deliver_outbox(transport=forbidden, pace=False)["failed"] == 1


def test_renewed_or_unsubscribed_reminders_are_suppressed(
    db, make_user, settings, clock
):
    clock.set_now("2027-07-01T18:30:00Z")
    user = make_user(email="renewal@college.edu")
    membership(db, user)
    assert service.send_reminders(db) == 1
    db.execute("UPDATE subscribers SET status='UNSUBSCRIBED'")
    assert (
        delivery.deliver_outbox(
            transport=lambda *args: pytest.fail("Opt-out ignored"), pace=False
        )["suppressed"]
        == 1
    )


def test_resend_absolute_links_and_stable_idempotency_header(settings, monkeypatch):
    requests = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, limit):
            return b'{"id":"accepted-id"}'

    def fake(request, timeout):
        requests.append(request)
        assert timeout == 8
        return Response()

    monkeypatch.setattr(delivery, "urlopen", fake)
    row = {
        "to_email": "reader@college.edu",
        "subject": "Reminder",
        "body": "Renew at /join.\nUnsubscribe: /unsubscribe/token",
        "dedupe_key": "unique-message",
    }
    config = delivery.Settings.load()
    assert delivery.send_resend(config, row) == "accepted-id"
    delivery.send_resend(config, row)
    assert (
        requests[0].headers["Idempotency-key"] == requests[1].headers["Idempotency-key"]
    )
    payload = json.loads(requests[0].data)
    assert "https://clubledger-gold.vercel.app/join" in payload["text"]
    assert "https://clubledger-gold.vercel.app/unsubscribe/token" in payload["text"]


def test_http_auth_failure_is_sanitized_and_permanent(settings, monkeypatch):
    def fail(*args, **kwargs):
        raise HTTPError(
            "https://api.resend.com/emails", 403, "secret response", {}, None
        )

    monkeypatch.setattr(delivery, "urlopen", fail)
    with pytest.raises(delivery.DeliveryError) as failure:
        delivery.send_resend(
            delivery.Settings.load(),
            {
                "body": "text",
                "dedupe_key": "key",
                "subject": "subject",
                "to_email": "reader@college.edu",
            },
        )
    assert failure.value.permanent
    assert str(failure.value) == "PROVIDER_HTTP_403"


def test_cron_auth_fails_closed_and_missing_provider_is_503(app_client, monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "x" * 40)
    monkeypatch.delenv("CLUBLEDGER_MAIL_MODE", raising=False)
    assert app_client.get("/internal/cron/mail").status_code == 401
    assert (
        app_client.get(
            "/internal/cron/mail", headers={"Authorization": "Bearer wrong"}
        ).status_code
        == 401
    )
    assert (
        app_client.get(
            "/internal/cron/mail", headers={"Authorization": "Bearer " + "x" * 40}
        ).status_code
        == 503
    )


def test_mail_status_requires_permission_and_shows_setup_state(
    app_client, make_user, login_as
):
    student = make_user(email="mail-student@college.edu")
    login_as(student)
    assert app_client.get("/admin/mail").status_code == 403
    admin = make_user(email="mail-admin@college.edu", roles=["admin"])
    login_as(admin)
    result = app_client.get("/admin/mail")
    assert result.status_code == 200
    assert "Email setup required" in result.text


def test_production_cannot_use_capture_as_delivery(db, monkeypatch):
    from clubledger.core.errors import DomainError

    monkeypatch.setenv("CLUBLEDGER_ENV", "prod")
    with pytest.raises(DomainError):
        service.process_mail_outbox(db)


def test_local_captures_are_not_reported_as_provider_acceptance(
    app_client, db, make_user, login_as
):
    queued(db, make_user)
    service.process_mail_outbox(db)
    admin = make_user(email="capture-auditor@college.edu", roles=["admin"])
    login_as(admin)
    page = app_client.get("/admin/mail")
    assert page.status_code == 200
    assert "Accepted: 0" in page.text
    assert "Captured locally" in page.text
