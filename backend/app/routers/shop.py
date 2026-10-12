from fastapi import APIRouter, Depends, HTTPException, Query

from app import commerce
from app.db import connection
from app.models.schemas import CartRequest, OrderRequest
from app.security import current_user

router = APIRouter(tags=["商品与订单"])


@router.get("/products")
def products(
    q: str = Query("", max_length=200), category: str = Query("", max_length=40)
):
    return commerce.products(q, category)


@router.get("/products/{product_id}")
def product(product_id: str):
    with connection() as conn:
        row = conn.execute(
            "SELECT * FROM products WHERE id=? AND active=1", (product_id,)
        ).fetchone()
    if not row:
        raise HTTPException(404, "商品不存在")
    return commerce.product_dict(row)


@router.get("/cart")
def cart(user=Depends(current_user)):
    return commerce.get_cart(user["id"])


@router.put("/cart")
def update_cart(req: CartRequest, user=Depends(current_user)):
    return commerce.set_cart(user["id"], req.product_id, req.quantity)


@router.delete("/cart/{product_id}")
def remove_cart(product_id: str, user=Depends(current_user)):
    with connection(write=True) as conn:
        commerce.lock_customer(conn, user["id"])
        conn.execute(
            "DELETE FROM cart WHERE user_id=? AND product_id=?",
            (user["id"], product_id),
        )
    return commerce.get_cart(user["id"])


@router.get("/orders")
def orders(user=Depends(current_user)):
    return commerce.list_orders(user["id"])


@router.post("/orders", status_code=201)
def checkout(req: OrderRequest, user=Depends(current_user)):
    return commerce.create_order(user["id"], req.address, req.request_key)


@router.get("/orders/{order_id}")
def order_detail(order_id: str, user=Depends(current_user)):
    with connection() as conn:
        return commerce.get_order(conn, order_id, user["id"])


@router.post("/orders/{order_id}/pay")
def pay(order_id: str, user=Depends(current_user)):
    return commerce.transition_order(order_id, "paid", user["id"])


@router.post("/orders/{order_id}/cancel")
def cancel(order_id: str, user=Depends(current_user)):
    return commerce.cancel_order(user["id"], order_id)


@router.post("/orders/{order_id}/receive")
def receive(order_id: str, user=Depends(current_user)):
    return commerce.transition_order(order_id, "completed", user["id"])
