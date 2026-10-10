"""Run the same first-slice and semester regressions against real PostgreSQL."""


def test_cloud_signed_out_boundary_and_demo_hints(app_client, monkeypatch):
    monkeypatch.setenv("CLUBLEDGER_ENV", "prod")
    monkeypatch.setenv("CLUBLEDGER_DEMO_ACCOUNTS", "1")
    for path in ("/events", "/store", "/announcements"):
        response = app_client.get(path, follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/auth/login"
        assert (
            app_client.get(path, headers={"Accept": "application/json"}).status_code
            == 401
        )
    login = app_client.get("/auth/login")
    assert login.status_code == 200
    assert "student@skyline.edu" in login.text
    assert "DemoPassword123!" in login.text


from tests.e2e.test_first_slice import (
    test_first_vertical_slice_happy_path,
    test_first_vertical_slice_failed_dues_negative_flow,
    test_regression_capacity_race_and_late_payment_unfulfilled,
    test_regression_ticket_cancellation_and_exact_journal_reversal,
    test_regression_repeated_notifications_no_effect,
    test_regression_csrf_and_foreign_ownership_blocks,
    test_regression_duplicate_and_wrong_event_checkin,
)
from tests.e2e.test_complete_workspace import (
    test_all_student_sections_are_reachable,
    test_admin_screens_and_mail_permissions,
    test_full_semester_merch_expense_settlement_close_handover,
    test_receipt_upload_csrf_mime_and_ownership,
    test_snapshot_immutable_and_handover_before_close_blocked,
)
from tests.e2e.test_payment_feedback import (
    test_ticket_checkout_keeps_real_booking_details_and_outcomes,
)

from tests.e2e.test_failed_purchase_retry import (
    test_failed_membership_can_retry_without_false_membership,
    test_failed_merch_releases_stock_once_and_retry_succeeds,
    test_failed_ticket_releases_last_seat,
)

from tests.e2e.test_refund_navigation import (
    test_refund_returns_all_payments_without_hiding_other_refunds,
)
from tests.unit.test_demo_dataset import (
    test_large_demo_append_preserves_existing_data_and_is_repeat_safe,
)
