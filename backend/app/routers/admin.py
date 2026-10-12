from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from app import catalog, commerce, service
from app.db import connection
from app.models.schemas import (
    FulfillmentUpdate,
    HumanReply,
    ProductChanges,
    ProductCreate,
    ProductListingRequest,
    StockRequest,
    TicketUpdate,
)
from app.security import admin_user

router = APIRouter(tags=["管理工作台"])


@router.get("/admin/overview")
def overview(user=Depends(admin_user)):
    with connection() as conn:
        return {
            "orders": conn.execute("SELECT count(*) FROM orders").fetchone()[0],
            "revenue_cents": conn.execute(
                "SELECT coalesce(sum(total_cents),0) FROM orders WHERE status IN ('paid','shipped','completed')"
            ).fetchone()[0],
            "open_tickets": conn.execute(
                "SELECT count(*) FROM tickets WHERE status!='resolved'"
            ).fetchone()[0],
            "ai_runs": conn.execute("SELECT count(*) FROM ai_runs").fetchone()[0],
        }


@router.get("/admin/orders")
def admin_orders(user=Depends(admin_user)):
    return commerce.list_orders()


@router.post("/admin/orders/{order_id}/ship")
def ship(order_id: str, user=Depends(admin_user)):
    return commerce.transition_order(order_id, "shipped")


@router.put("/admin/products/{product_id}/stock")
def stock(product_id: str, req: StockRequest, user=Depends(admin_user)):
    catalog.update_product(user["id"], product_id, req.model_dump())
    return {"ok": True}


@router.post("/admin/products", status_code=201)
def create_product(req: ProductCreate, user=Depends(admin_user)):
    return catalog.create_product(user["id"], req.model_dump())


@router.get("/admin/products")
def admin_products(
    q: str = Query("", max_length=200),
    status: Literal["all", "listed", "unlisted"] = "all",
    category: str = Query("", max_length=40),
    user=Depends(admin_user),
):
    return commerce.products(q, category, status)


@router.get("/admin/products/{product_id}")
def admin_product(product_id: str, user=Depends(admin_user)):
    with connection() as conn:
        return catalog.get_product(conn, product_id)


@router.put("/admin/products/{product_id}/listing")
def product_listing(
    product_id: str, req: ProductListingRequest, user=Depends(admin_user)
):
    return catalog.set_listing(user["id"], product_id, req.active)


@router.patch("/admin/products/{product_id}")
def edit_product(product_id: str, req: ProductChanges, user=Depends(admin_user)):
    return catalog.update_product(
        user["id"], product_id, req.model_dump(exclude_unset=True)
    )


@router.get("/admin/product-events")
def product_events(user=Depends(admin_user)):
    return catalog.list_events()


@router.get("/admin/tickets")
def admin_tickets(user=Depends(admin_user)):
    return service.list_tickets()


@router.put("/admin/tickets/{ticket_id}")
def resolve(ticket_id: str, req: TicketUpdate, user=Depends(admin_user)):
    return service.update_ticket(ticket_id, req.status, req.resolution, user["id"])


@router.post("/admin/tickets/{ticket_id}/reply")
def reply(ticket_id: str, req: HumanReply, user=Depends(admin_user)):
    return service.human_reply(ticket_id, req.content, user["id"])


@router.get("/admin/customers")
def customers(user=Depends(admin_user)):
    with connection() as conn:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT id,name,email,role FROM users WHERE role='customer' ORDER BY name,id"
            )
        ]


@router.get("/admin/customers/{customer_id}")
def customer_context(customer_id: str, user=Depends(admin_user)):
    return service.context(customer_id)


@router.get("/admin/conversations/{conversation_id}")
def admin_conversation(conversation_id: str, user=Depends(admin_user)):
    with connection() as conn:
        row = conn.execute(
            "SELECT user_id FROM conversations WHERE id=?", (conversation_id,)
        ).fetchone()
    if not row:
        raise HTTPException(404, "会话不存在")
    return service.conversation_history(
        conversation_id, row["user_id"], allow_deleted=True
    )


@router.post("/admin/orders/{order_id}/fulfillment")
def update_fulfillment(order_id: str, req: FulfillmentUpdate, user=Depends(admin_user)):
    return service.fulfillment(order_id, req.stage, req.detail)


@router.get("/admin/ai-runs")
def ai_runs(user=Depends(admin_user)):
    with connection() as conn:
        return [
            dict(r)
            for r in conn.execute("""SELECT a.*,t.first_response_ms FROM ai_runs a
                    LEFT JOIN run_timings t ON t.run_id=a.id ORDER BY a.created_at DESC LIMIT 100""")
        ]
