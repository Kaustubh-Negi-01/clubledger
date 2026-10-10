"""Run the same first-slice and semester regressions against real PostgreSQL."""

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
