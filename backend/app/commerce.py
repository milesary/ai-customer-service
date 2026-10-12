import json
import secrets
from datetime import datetime, timezone
from fastapi import HTTPException
from app.db import connection


def now():
    return datetime.now(timezone.utc).isoformat()


def identifier(prefix):
    return f"{prefix}-{secrets.token_hex(5).upper()}"


def product_dict(row):
    result = dict(row)
    result["specs"] = json.loads(result["specs"])
    return result


def lock_customer(conn, user_id):
    conn.lock("SELECT id FROM users WHERE id=?", (user_id,)).fetchone()


def products(query="", category="", status="listed"):
    with connection() as conn:
        rows = conn.execute(
            """SELECT p.*,r.expected_at AS restock_at FROM products p
                               LEFT JOIN restock_plans r ON r.product_id=p.id WHERE (?='all' OR active=?) AND (?='' OR category=?)
                               AND (?='' OR p.id LIKE ? OR name LIKE ? OR description LIKE ? OR specs LIKE ?) ORDER BY p.id""",
            (
                status,
                0 if status == "unlisted" else 1,
                category,
                category,
                query,
                f"%{query}%",
                f"%{query}%",
                f"%{query}%",
                f"%{query}%",
            ),
        ).fetchall()
    return [product_dict(r) for r in rows]


def get_cart(user_id, conn=None):
    if conn is None:
        with connection() as c:
            return get_cart(user_id, c)
    items = [
        product_dict(r)
        for r in conn.execute(
            """SELECT p.*,c.quantity FROM cart c JOIN products p ON p.id=c.product_id
                                                    WHERE c.user_id=? ORDER BY p.id""",
            (user_id,),
        ).fetchall()
    ]
    subtotal = sum(i["price_cents"] * i["quantity"] for i in items)
    shipping = 800 if 0 < subtotal < 9900 else 0
    return {
        "items": items,
        "subtotal_cents": subtotal,
        "shipping_cents": shipping,
        "total_cents": subtotal + shipping,
    }


def set_cart(user_id, product_id, quantity, conn=None, add=False):
    if conn is None:
        with connection(write=True) as c:
            return set_cart(user_id, product_id, quantity, c, add)
    lock_customer(conn, user_id)
    row = conn.lock(
        "SELECT * FROM products WHERE id=? AND active=1", (product_id,)
    ).fetchone()
    if not row:
        raise HTTPException(404, "商品不存在")
    if add:
        existing = conn.execute(
            "SELECT quantity FROM cart WHERE user_id=? AND product_id=?",
            (user_id, product_id),
        ).fetchone()
        quantity += existing["quantity"] if existing else 0
    if not 1 <= quantity <= min(row["stock"], 99):
        raise HTTPException(409, "库存不足或数量超过上限")
    if conn.execute(
        "SELECT quantity FROM cart WHERE user_id=? AND product_id=?",
        (user_id, product_id),
    ).fetchone():
        conn.execute(
            "UPDATE cart SET quantity=? WHERE user_id=? AND product_id=?",
            (quantity, user_id, product_id),
        )
    else:
        conn.execute("INSERT INTO cart VALUES (?,?,?)", (user_id, product_id, quantity))
    return get_cart(user_id, conn)


def order_dict(conn, row):
    order = dict(row)
    order["items"] = [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM order_items WHERE order_id=?", (row["id"],)
        )
    ]
    order["fulfillment"] = [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM fulfillment_events WHERE order_id=? ORDER BY created_at,id",
            (row["id"],),
        )
    ]
    return order


def get_order(conn, order_id, user_id=None):
    row = conn.lock(
        "SELECT * FROM orders WHERE id=? AND (? IS NULL OR user_id=?)",
        (order_id, user_id, user_id),
    ).fetchone()
    if not row:
        raise HTTPException(404, "订单不存在")
    return order_dict(conn, row)


def list_orders(user_id=None):
    with connection() as conn:
        rows = conn.execute(
            "SELECT * FROM orders WHERE (? IS NULL OR user_id=?) ORDER BY created_at DESC",
            (user_id, user_id),
        ).fetchall()
        return [order_dict(conn, r) for r in rows]


def create_order(user_id, address, request_key):
    with connection(write=True) as conn:
        lock_customer(conn, user_id)
        previous = conn.execute(
            "SELECT * FROM orders WHERE user_id=? AND request_key=?",
            (user_id, request_key),
        ).fetchone()
        if previous:
            if previous["address"] != address:
                raise HTTPException(409, "同一请求编号不能用于不同订单")
            return order_dict(conn, previous)
        # Read price and listing status after locking products in a stable order.
        ids = conn.execute(
            "SELECT product_id FROM cart WHERE user_id=? ORDER BY product_id",
            (user_id,),
        ).fetchall()
        for item in ids:
            conn.lock(
                "SELECT id FROM products WHERE id=?", (item["product_id"],)
            ).fetchone()
        cart = get_cart(user_id, conn)
        if not cart["items"]:
            raise HTTPException(409, "购物车为空")
        order_id = identifier("ORD")
        for item in cart["items"]:
            if not item["active"]:
                raise HTTPException(409, f"{item['name']} 已下架，请先移出购物车")
            result = conn.execute(
                "UPDATE products SET stock=stock-? WHERE id=? AND active=1 AND stock>=?",
                (item["quantity"], item["id"], item["quantity"]),
            )
            if result.rowcount != 1:
                raise HTTPException(409, f"{item['name']} 库存不足，请调整购物车")
        conn.execute(
            "INSERT INTO orders VALUES (?,?,?,?,?,?,?)",
            (
                order_id,
                user_id,
                "pending_payment",
                cart["total_cents"],
                address,
                now(),
                request_key,
            ),
        )
        for item in cart["items"]:
            conn.execute(
                "INSERT INTO order_items VALUES (?,?,?,?,?)",
                (
                    order_id,
                    item["id"],
                    item["name"],
                    item["price_cents"],
                    item["quantity"],
                ),
            )
        conn.execute("DELETE FROM cart WHERE user_id=?", (user_id,))
        return get_order(conn, order_id, user_id)


def cancel_order(user_id, order_id, conn=None):
    if conn is None:
        with connection(write=True) as c:
            return cancel_order(user_id, order_id, c)
    order = get_order(conn, order_id, user_id)
    if order["status"] == "cancelled":
        return order
    if order["status"] != "pending_payment":
        raise HTTPException(409, "仅待支付订单可取消，已支付订单请申请售后")
    for item in order["items"]:
        conn.execute(
            "UPDATE products SET stock=stock+? WHERE id=?",
            (item["quantity"], item["product_id"]),
        )
    conn.execute("UPDATE orders SET status='cancelled' WHERE id=?", (order_id,))
    return get_order(conn, order_id, user_id)


def transition_order(order_id, target, user_id=None):
    allowed = {"paid": "pending_payment", "shipped": "paid", "completed": "shipped"}
    with connection(write=True) as conn:
        order = get_order(conn, order_id, user_id)
        if order["status"] == target:
            return order
        if order["status"] != allowed[target]:
            raise HTTPException(409, "当前订单状态不支持此操作")
        conn.execute("UPDATE orders SET status=? WHERE id=?", (target, order_id))
        if target in ("shipped", "completed"):
            conn.execute(
                "INSERT INTO fulfillment_events VALUES (?,?,?,?,?)",
                (
                    identifier("FUL"),
                    order_id,
                    target,
                    "模拟出库，已交付配送" if target == "shipped" else "买家已确认收货",
                    now(),
                ),
            )
        return get_order(conn, order_id, user_id)


def create_ticket(user_id, order_id, reason, conn=None):
    if conn is None:
        with connection(write=True) as c:
            return create_ticket(user_id, order_id, reason, c)
    if order_id:
        order = get_order(conn, order_id, user_id)
        if order["status"] not in ("paid", "shipped", "completed"):
            raise HTTPException(409, "该订单尚未支付或已取消，无法申请售后")
        previous = conn.execute(
            "SELECT * FROM tickets WHERE user_id=? AND order_id=? AND status IN ('open','processing')",
            (user_id, order_id),
        ).fetchone()
        if previous:
            return dict(previous)
    tid = identifier("TK")
    conn.execute(
        "INSERT INTO tickets(id,user_id,order_id,reason,status,resolution,created_at) VALUES (?,?,?,?,?,?,?)",
        (tid, user_id, order_id, reason, "open", "", now()),
    )
    return dict(conn.execute("SELECT * FROM tickets WHERE id=?", (tid,)).fetchone())
