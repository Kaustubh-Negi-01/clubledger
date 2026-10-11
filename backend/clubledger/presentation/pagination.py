"""Shared HTML pagination; filtering happens before the visible page is sliced."""

from math import ceil
from fastapi.templating import Jinja2Templates as BaseTemplates

PAGE_COLLECTIONS = {
    "members.html": "users",
    "manage_events.html": "events",
    "events/list.html": "events",
    "store/orders.html": "orders",
    "store/catalog.html": "products",
    "payments/admin_payments.html": "payments",
    "finance/index.html": "filtered_breakdown",
    "notifications.html": "notifications",
    "announcements.html": "announcements",
    "expenses.html": "expenses",
    "mail.html": "messages",
    "mail_status.html": "messages",
    "manage_announcements.html": "announcements",
    "fundraisers.html": "fundraisers",
    "adjustments.html": "entries",
    "handover.html": "records",
    "close.html": "snapshots",
    "inventory.html": "variants",
}


def paginate(request, rows, per_page=20):
    """Keep filters in navigation links and clamp invalid page numbers."""
    total = len(rows)
    pages = max(1, ceil(total / per_page))
    try:
        page = max(1, min(int(request.query_params.get("page", "1")), pages))
    except ValueError:
        page = 1
    start = (page - 1) * per_page
    return rows[start:start + per_page], {
        "page": page, "pages": pages, "total": total,
        "start": start + 1 if total else 0, "end": min(start + per_page, total),
        "previous": str(request.url.include_query_params(page=page - 1)) if page > 1 else None,
        "next": str(request.url.include_query_params(page=page + 1)) if page < pages else None,
    }


class Jinja2Templates(BaseTemplates):
    """Paginate full-page lists without changing JSON responses or dashboard previews."""

    def TemplateResponse(self, *args, **kwargs):
        context = kwargs.get("context")
        key = PAGE_COLLECTIONS.get(kwargs.get("name"))
        if key and context is not None and key in context:
            context = dict(context)
            context[key], context["pagination"] = paginate(kwargs["request"], context[key])
            kwargs["context"] = context
        return super().TemplateResponse(*args, **kwargs)
