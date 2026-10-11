"""Run the same ownership and read-state guarantees against real PostgreSQL."""

from tests.unit.test_notifications import (
    test_only_own_payment_outcomes_are_visible_and_readable,
    test_read_state_is_idempotent_per_user_and_new_outcome_is_unread,
    test_draft_announcements_are_hidden_and_unfulfilled_is_not_success,
)

__all__ = [
    "test_only_own_payment_outcomes_are_visible_and_readable",
    "test_read_state_is_idempotent_per_user_and_new_outcome_is_unread",
    "test_draft_announcements_are_hidden_and_unfulfilled_is_not_success",
]
