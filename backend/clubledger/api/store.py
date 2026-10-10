# In plain English: Serves merchandise pages and handles reservations, cancellation and pickup.
"""Store and merchandise routes per CONTRACT.md §12."""

import json
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from clubledger.config import get_db_path
from clubledger.core import idgen
from clubledger.core.auth import (
    COOKIE_SESSION,
    get_current_session,
    get_user_permissions,
    load_session,
    require_perm,
    verify_csrf,
)
from clubledger.core.db import connect, unit_of_work
from clubledger.core.errors import DomainError
from clubledger.core.types import CartItem, Session
from clubledger.store.service import (
    MERCH_PURPOSE_HANDLER,
    cancel_order,
    mark_picked_up,
    reserve_cart,
)

router = APIRouter(tags=["store"])

from clubledger.paths import TEMPLATES_DIR

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def get_optional_session(request: Request) -> Session | None:
    """Resolve session if present, otherwise return None for public routes."""
    raw_token = request.cookies.get(COOKIE_SESSION)
    if not raw_token:
        return None
    try:
        conn = connect(get_db_path())
        try:
            return load_session(conn, raw_token)
        finally:
            conn.close()
    except Exception:
        return None


def require_store_manage_or_pickup(
    session: Session = Depends(get_current_session),
) -> Session:
    """Dependency: verify caller holds store.manage or store.pickup permission."""
    conn = connect(get_db_path())
    try:
        perms = get_user_permissions(conn, session.user_id)
        if "store.manage" not in perms and "store.fulfill" not in perms:
            raise DomainError(
                "FORBIDDEN", 403, "Missing store.manage or store.pickup permission"
            )
        return session
    finally:
        conn.close()


@router.get("/store", response_class=HTMLResponse)
def get_store_catalog(request: Request) -> Response:
    """Public catalog showing active products and available stock per size (STO-01)."""
    session = get_optional_session(request)
    conn = connect(get_db_path())
    try:
        products = conn.execute(
            "SELECT id, name, description, base_price_paise FROM products WHERE is_active = 1 ORDER BY id ASC;"
        ).fetchall()

        catalog_data = []
        for p in products:
            variants = conn.execute(
                "SELECT id, sku, size, physical_qty, reserved_qty, "
                "       (physical_qty - reserved_qty) AS available_qty "
                "FROM variants WHERE product_id = ? ORDER BY id ASC;",
                (p["id"],),
            ).fetchall()

            catalog_data.append(
                {
                    "id": p["id"],
                    "name": p["name"],
                    "description": p["description"],
                    "base_price_paise": p["base_price_paise"],
                    "base_price_inr": f"{p['base_price_paise'] / 100:.2f}",
                    "variants": [
                        {
                            "id": v["id"],
                            "sku": v["sku"],
                            "size": v["size"],
                            "available_qty": v["available_qty"],
                        }
                        for v in variants
                    ],
                }
            )

        return templates.TemplateResponse(
            request=request,
            name="store/catalog.html",
            context={
                "session": session,
                "products": catalog_data,
            },
        )
    finally:
        conn.close()


@router.get("/store/{product_id}", response_class=HTMLResponse)
def get_product_detail(request: Request, product_id: int) -> Response:
    """Public product detail page."""
    session = get_optional_session(request)
    conn = connect(get_db_path())
    try:
        product = conn.execute(
            "SELECT id, name, description, base_price_paise, is_active FROM products WHERE id = ?;",
            (product_id,),
        ).fetchone()

        if not product or not product["is_active"]:
            raise DomainError("NOT_FOUND", 404, "Product not found or inactive")

        variants = conn.execute(
            "SELECT id, sku, size, physical_qty, reserved_qty, "
            "       (physical_qty - reserved_qty) AS available_qty "
            "FROM variants WHERE product_id = ? ORDER BY id ASC;",
            (product_id,),
        ).fetchall()

        idemp_key = idgen.generate_idempotency_key() if session else None
        csrf_tok = session.csrf_token if session else None

        return templates.TemplateResponse(
            request=request,
            name="store/detail.html",
            context={
                "session": session,
                "csrf_token": csrf_tok,
                "idempotency_key": idemp_key,
                "product": product,
                "price_inr": f"{product['base_price_paise'] / 100:.2f}",
                "variants": variants,
            },
        )
    finally:
        conn.close()


@router.post("/store/reserve")
def post_store_reserve(
    request: Request,
    idempotency_key: Annotated[str, Form(...)],
    csrf_token: Annotated[str, Form(...)],
    variant_id: Annotated[int | None, Form()] = None,
    qty: Annotated[int | None, Form()] = None,
    cart_json: Annotated[str | None, Form()] = None,
    session: Session = Depends(get_current_session),
) -> Response:
    """Reserve cart items and redirect to payment simulator (STO-02)."""
    verify_csrf(session, csrf_token)

    # Parse items either from single item form or JSON cart array
    items: list[CartItem] = []
    if cart_json:
        try:
            parsed = json.loads(cart_json)
            for it in parsed:
                items.append(
                    CartItem(variant_id=int(it["variant_id"]), qty=int(it["qty"]))
                )
        except Exception:
            raise DomainError("VALIDATION", 422, "Malformed cart_json format")
    elif variant_id is not None and qty is not None:
        items.append(CartItem(variant_id=variant_id, qty=qty))
    else:
        raise DomainError("VALIDATION", 422, "No items provided in cart")

    with unit_of_work() as conn:
        order, payment = reserve_cart(
            conn,
            user_id=session.user_id,
            items=items,
            idempotency_key=idempotency_key,
        )
        return RedirectResponse(url=f"/pay/{payment.public_id}", status_code=303)


@router.get("/me/orders", response_class=HTMLResponse)
def get_user_orders(
    request: Request,
    session: Session = Depends(get_current_session),
) -> Response:
    """View logged-in user's merchandise orders."""
    conn = connect(get_db_path())
    try:
        order_rows = conn.execute(
            "SELECT o.id, o.status, o.expires_at, o.total_paise, o.price_tier, o.payment_id, o.picked_up_at, o.created_at, p.status AS payment_status "
            "FROM merch_orders o LEFT JOIN payments p ON p.id=o.payment_id WHERE o.user_id = ? ORDER BY o.id DESC;",
            (session.user_id,),
        ).fetchall()

        orders_data = []
        for o in order_rows:
            items = conn.execute(
                "SELECT oi.qty, oi.unit_price_paise, v.size, p.name AS product_name "
                "FROM merch_order_items oi "
                "JOIN variants v ON oi.variant_id = v.id "
                "JOIN products p ON v.product_id = p.id "
                "WHERE oi.order_id = ?;",
                (o["id"],),
            ).fetchall()
            orders_data.append(
                {
                    "order": o,
                    "total_inr": f"{o['total_paise'] / 100:.2f}",
                    "order_items": items,
                    "items": items,
                }
            )

        return templates.TemplateResponse(
            request=request,
            name="store/orders.html",
            context={
                "session": session,
                "csrf_token": session.csrf_token,
                "orders": orders_data,
            },
        )
    finally:
        conn.close()


@router.post("/store/orders/{order_id}/cancel")
def post_cancel_order(
    request: Request,
    order_id: int,
    csrf_token: Annotated[str, Form(...)],
    session: Session = Depends(get_current_session),
) -> Response:
    """Cancel merchandise order by owner."""
    verify_csrf(session, csrf_token)
    with unit_of_work() as conn:
        order = conn.execute(
            "SELECT user_id FROM merch_orders WHERE id = ?;", (order_id,)
        ).fetchone()
        if not order:
            raise DomainError("NOT_FOUND", 404, "Order not found")
        if order["user_id"] != session.user_id:
            raise DomainError("FORBIDDEN", 403, "Access denied to order")

        cancel_order(conn, {"MERCH": MERCH_PURPOSE_HANDLER}, order_id, session.user_id)
        return RedirectResponse(url="/me/orders", status_code=303)


@router.post("/admin/store/orders/{order_id}/pickup")
def post_order_pickup(
    request: Request,
    order_id: int,
    csrf_token: Annotated[str, Form(...)],
    session: Session = Depends(require_store_manage_or_pickup),
) -> Response:
    """Staff pickup confirmation reducing physical and reserved stock (STO-07)."""
    verify_csrf(session, csrf_token)
    with unit_of_work() as conn:
        mark_picked_up(conn, order_id, staff_id=session.user_id)
        return RedirectResponse(url="/me/orders", status_code=303)
