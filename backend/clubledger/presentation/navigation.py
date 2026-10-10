# In plain English: Defines the sidebar links in one readable list; permissions decide which links appear.
"""Human-readable navigation labels and URLs, shared by the page layout."""

# Everyday pages available from the student menu.
MAIN_NAVIGATION = [
    ("/dashboard", "Overview"),
    ("/join", "Membership"),
    ("/events", "Events & tickets"),
    ("/store", "Club store"),
    ("/me/orders", "My orders"),
    ("/fundraisers", "Fundraisers & tasks"),
    ("/expenses", "Expenses"),
    ("/announcements", "Announcements"),
]

# Officer links include the permission required to display them.
# Hiding a link is not authorization: backend routes also enforce permissions.
OPERATIONS_NAVIGATION = [
    ("finance.view", "/finance", "Financial ledger"),
    ("events.manage", "/admin/events", "Manage events"),
    ("members.verify", "/verify", "Verify membership"),
    ("events.checkin", "/admin/checkin", "Door check-in"),
    ("members.manage", "/admin/members", "Members & roles"),
    ("store.manage", "/admin/store", "Inventory & pickup"),
    ("payments.admin", "/admin/payments", "Payments & refunds"),
    ("comms.publish", "/admin/announcements", "Publish updates"),
    ("comms.mail_viewer", "/dev/mail", "Local mail capture"),
    ("close.run", "/admin/adjustments", "Prior-period corrections"),
    ("close.run", "/admin/close", "Semester close"),
    ("handover.run", "/admin/handover", "Officer handover"),
]
