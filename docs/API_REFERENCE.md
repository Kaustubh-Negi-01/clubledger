# Actual HTTP endpoint reference

Extracted from route decorators in `backend/clubledger/api/`. Routes return HTML, redirects or JSON; they are all backend HTTP entry points. Dependency-based authentication is defined in the Python handler signature, and services enforce additional business rules.

| Method | URL | Source file | Handler |
| --- | --- | --- | --- |
| GET | `/admin/mail` | `backend/clubledger/api/comms.py` | `mail_status` |
| POST | `/admin/mail/process` | `backend/clubledger/api/comms.py` | `process_now` |
| GET | `/internal/cron/mail` | `backend/clubledger/api/comms.py` | `scheduled_mail` (server-only bearer authentication) |
| GET | `/auth/register` | `backend/clubledger/api/auth.py` | `get_register` |
| POST | `/auth/register` | `backend/clubledger/api/auth.py` | `post_register` |
| GET | `/auth/login` | `backend/clubledger/api/auth.py` | `get_login` |
| POST | `/auth/login` | `backend/clubledger/api/auth.py` | `post_login` |
| POST | `/auth/logout` | `backend/clubledger/api/auth.py` | `post_logout` |
| GET | `/me` | `backend/clubledger/api/auth.py` | `get_me` |
| GET | `/events` | `backend/clubledger/api/events.py` | `get_events_list` |
| GET | `/events/{event_id}` | `backend/clubledger/api/events.py` | `get_event_detail` |
| POST | `/events/{event_id}/hold` | `backend/clubledger/api/events.py` | `post_event_hold` |
| GET | `/tickets/{ticket_id}` | `backend/clubledger/api/events.py` | `get_ticket` |
| GET | `/checkin/{event_id}` | `backend/clubledger/api/events.py` | `get_checkin` |
| POST | `/checkin/{event_id}/scan` | `backend/clubledger/api/events.py` | `post_checkin_scan` |
| GET | `/admin/events/{event_id}/report` | `backend/clubledger/api/events.py` | `get_admin_event_report` |
| GET | `/expenses` | `backend/clubledger/api/expenses.py` | `list_expenses` |
| POST | `/expenses/new` | `backend/clubledger/api/expenses.py` | `post_create_expense` |
| POST | `/expenses/{expense_id}/receipt` | `backend/clubledger/api/expenses.py` | `post_upload_receipt` |
| GET | `/receipts/{receipt_id}` | `backend/clubledger/api/expenses.py` | `download_receipt` |
| POST | `/admin/expenses/{expense_id}/approve` | `backend/clubledger/api/expenses.py` | `post_approve_expense` |
| POST | `/admin/expenses/{expense_id}/reject` | `backend/clubledger/api/expenses.py` | `post_reject_expense` |
| POST | `/admin/expenses/{expense_id}/pay` | `backend/clubledger/api/expenses.py` | `post_pay_expense` |
| GET | `/join` | `backend/clubledger/api/membership.py` | `get_join` |
| POST | `/join` | `backend/clubledger/api/membership.py` | `post_join` |
| GET | `/members/card` | `backend/clubledger/api/membership.py` | `get_member_card` |
| GET | `/verify` | `backend/clubledger/api/membership.py` | `get_verify` |
| POST | `/verify/lookup` | `backend/clubledger/api/membership.py` | `post_verify_lookup` |
| GET | `/pay/{public_id}` | `backend/clubledger/api/payments.py` | `get_pay` |
| POST | `/pay/{public_id}/outcome` | `backend/clubledger/api/payments.py` | `post_pay_outcome` |
| POST | `/webhooks/payments` | `backend/clubledger/api/payments.py` | `post_payment_webhook` |
| GET | `/admin/payments` | `backend/clubledger/api/payments.py` | `get_admin_payments` |
| POST | `/admin/payments/{payment_id}/refund` | `backend/clubledger/api/payments.py` | `post_admin_refund` |
| POST | `/admin/payments/{payment_id}/fulfill` | `backend/clubledger/api/payments.py` | `post_admin_fulfill` |
| POST | `/admin/payment-events/{event_id}/resolve` | `backend/clubledger/api/payments.py` | `post_admin_resolve_receipt` |
| GET | `` | `backend/clubledger/api/reports.py` | `get_finance_dashboard` |
| GET | `/accounts/{code}` | `backend/clubledger/api/reports.py` | `get_account_drilldown` |
| GET | `/entries/{entry_id}` | `backend/clubledger/api/reports.py` | `get_entry_drilldown` |
| GET | `/integrity` | `backend/clubledger/api/reports.py` | `get_integrity_page` |
| GET | `/store` | `backend/clubledger/api/store.py` | `get_store_catalog` |
| GET | `/store/{product_id}` | `backend/clubledger/api/store.py` | `get_product_detail` |
| POST | `/store/reserve` | `backend/clubledger/api/store.py` | `post_store_reserve` |
| GET | `/me/orders` | `backend/clubledger/api/store.py` | `get_user_orders` |
| POST | `/store/orders/{order_id}/cancel` | `backend/clubledger/api/store.py` | `post_cancel_order` |
| POST | `/admin/store/orders/{order_id}/pickup` | `backend/clubledger/api/store.py` | `post_order_pickup` |
| GET | `/fundraisers/{fundraiser_id}/board` | `backend/clubledger/api/tasks.py` | `get_board` |
| PATCH | `/tasks/{task_id}/status` | `backend/clubledger/api/tasks.py` | `patch_task_status` |
| GET | `/dashboard` | `backend/clubledger/api/workspace.py` | `dashboard` |
| GET | `/announcements` | `backend/clubledger/api/workspace.py` | `announcements` |
| GET | `/announcements/{announcement_id}` | `backend/clubledger/api/workspace.py` | `announcement` |
| POST | `/subscribe` | `backend/clubledger/api/workspace.py` | `subscribe` |
| GET | `/unsubscribe/{token}` | `backend/clubledger/api/workspace.py` | `unsubscribe_page` |
| POST | `/unsubscribe/{token}` | `backend/clubledger/api/workspace.py` | `unsubscribe` |
| GET | `/admin/announcements` | `backend/clubledger/api/workspace.py` | `manage_announcements` |
| POST | `/admin/announcements` | `backend/clubledger/api/workspace.py` | `draft_announcement` |
| POST | `/admin/announcements/{announcement_id}/publish` | `backend/clubledger/api/workspace.py` | `publish` |
| GET | `/dev/mail` | `backend/clubledger/api/workspace.py` | `mail` |
| POST | `/dev/mail/process` | `backend/clubledger/api/workspace.py` | `process_mail` |
| POST | `/dev/mail/reminders` | `backend/clubledger/api/workspace.py` | `renewal_reminders` |
| GET | `/fundraisers` | `backend/clubledger/api/workspace.py` | `fundraisers` |
| POST | `/fundraisers` | `backend/clubledger/api/workspace.py` | `fundraiser_create` |
| GET | `/fundraisers/{fundraiser_id}/board` | `backend/clubledger/api/workspace.py` | `board` |
| POST | `/fundraisers/{fundraiser_id}/tasks` | `backend/clubledger/api/workspace.py` | `task_create` |
| POST | `/tasks/{task_id}/status` | `backend/clubledger/api/workspace.py` | `task_status` |
| GET | `/expenses` | `backend/clubledger/api/workspace.py` | `expenses` |
| GET | `/expenses/new` | `backend/clubledger/api/workspace.py` | `expense_new` |
| POST | `/expenses/submit` | `backend/clubledger/api/workspace.py` | `expense_submit` |
| GET | `/admin/checkin` | `backend/clubledger/api/workspace.py` | `checkin_events` |
| GET | `/admin/adjustments` | `backend/clubledger/api/workspace.py` | `adjustments` |
| POST | `/admin/adjustments` | `backend/clubledger/api/workspace.py` | `adjustment` |
| GET | `/admin/close` | `backend/clubledger/api/workspace.py` | `close_page` |
| POST | `/admin/close` | `backend/clubledger/api/workspace.py` | `close_period` |
| GET | `/snapshots/{snapshot_id}` | `backend/clubledger/api/workspace.py` | `snapshot` |
| POST | `/admin/settle` | `backend/clubledger/api/workspace.py` | `settlement` |
| POST | `/dev/advance-day` | `backend/clubledger/api/workspace.py` | `advance_demo` |
| POST | `/admin/expire` | `backend/clubledger/api/workspace.py` | `expiration` |
| GET | `/admin/handover` | `backend/clubledger/api/workspace.py` | `handover_page` |
| POST | `/admin/handover` | `backend/clubledger/api/workspace.py` | `handover` |
| GET | `/admin/members` | `backend/clubledger/api/workspace.py` | `members` |
| POST | `/admin/users/{user_id}/role` | `backend/clubledger/api/workspace.py` | `grant_role` |
| POST | `/admin/users/{user_id}/status` | `backend/clubledger/api/workspace.py` | `user_status` |
| GET | `/admin/events` | `backend/clubledger/api/workspace.py` | `events_admin` |
| POST | `/admin/events` | `backend/clubledger/api/workspace.py` | `event_create` |
| POST | `/admin/events/{event_id}/cancel` | `backend/clubledger/api/workspace.py` | `event_cancel` |
| GET | `/admin/store` | `backend/clubledger/api/workspace.py` | `inventory` |
| POST | `/admin/store/products` | `backend/clubledger/api/workspace.py` | `product_create` |
| POST | `/admin/store/variants/{variant_id}/restock` | `backend/clubledger/api/workspace.py` | `restock` |

FastAPI also exposes generated OpenAPI documentation at `/docs` and `/openapi.json`. These are framework-generated routes. `/` redirects to `/dashboard`, and `/static` serves frontend assets.

Existing routing note: the workspace HTML fundraiser-board route is registered before the tasks JSON handler for the same GET path. The browser currently receives the workspace HTML handler. The reorganization preserves this order rather than changing an API response during a folder move.
