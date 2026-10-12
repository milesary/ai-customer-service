"""Shared manual/AI product writes, audited in the same transaction."""

import json
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException
from app import commerce
from app.db import connection
from app.models.schemas import ProductCreate, ProductChanges


def require_admin(conn, user_id):
    row = conn.execute("SELECT role FROM users WHERE id=?", (user_id,)).fetchone()
    if not row or row["role"] != "admin":
        raise HTTPException(403, "仅店铺管理员可以管理商品")


def get_product(conn, product_id, lock=False):
    query = "SELECT * FROM products WHERE id=?"
    row = (conn.lock if lock else conn.execute)(query, (product_id,)).fetchone()
    if not row:
        raise HTTPException(404, "商品不存在")
    product = commerce.product_dict(row)
    plan = conn.execute(
        "SELECT expected_at FROM restock_plans WHERE product_id=?", (product_id,)
    ).fetchone()
    product["restock_at"] = plan["expected_at"] if plan else None
    return product


def changes_data(data):
    changes = ProductChanges.model_validate(data).model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(422, "请提供至少一项商品修改")
    return changes


def audit(conn, user_id, product_id, kind, before, after, action_id):
    conn.execute(
        "INSERT INTO product_events VALUES (?,?,?,?,?,?,?,?)",
        (
            commerce.identifier("PE"),
            product_id,
            user_id,
            kind,
            json.dumps(before, ensure_ascii=False),
            json.dumps(after, ensure_ascii=False),
            action_id,
            commerce.now(),
        ),
    )


def save_plan(conn, product_id, restock_at):
    conn.execute("DELETE FROM restock_plans WHERE product_id=?", (product_id,))
    if restock_at:
        conn.execute(
            "INSERT INTO restock_plans VALUES (?,?,?)",
            (product_id, restock_at, commerce.now()),
        )


def create_product(user_id, data, conn=None, action_id=None):
    if conn is None:
        with connection(write=True) as c:
            return create_product(user_id, data, c, action_id)
    require_admin(conn, user_id)
    product = ProductCreate.model_validate(data).model_dump()
    try:
        conn.execute(
            "INSERT INTO products(id,name,category,description,price_cents,stock,image,specs,active) VALUES (?,?,?,?,?,?,?,?,1)",
            tuple(
                json.dumps(product[k], ensure_ascii=False)
                if k == "specs"
                else product[k]
                for k in (
                    "id",
                    "name",
                    "category",
                    "description",
                    "price_cents",
                    "stock",
                    "image",
                    "specs",
                )
            ),
        )
    except IntegrityError:
        raise HTTPException(409, "商品编号已存在，请使用其他编号") from None
    save_plan(conn, product["id"], product["restock_at"])
    after = get_product(conn, product["id"])
    audit(conn, user_id, product["id"], "create", None, after, action_id)
    return after


def update_product(user_id, product_id, data, conn=None, action_id=None, expected=None):
    if conn is None:
        with connection(write=True) as c:
            return update_product(user_id, product_id, data, c, action_id, expected)
    require_admin(conn, user_id)
    changes = changes_data(data)
    before = get_product(conn, product_id, lock=True)
    # Compare the proposal snapshot under the product lock, including live stock.
    if expected is not None and before != expected:
        raise HTTPException(409, "商品或库存已变化，请重新让 AI 生成操作预览")
    fields = {k: v for k, v in changes.items() if k != "restock_at"}
    if fields:
        conn.execute(
            "UPDATE products SET " + ",".join(k + "=?" for k in fields) + " WHERE id=?",
            tuple(
                json.dumps(v, ensure_ascii=False) if k == "specs" else v
                for k, v in fields.items()
            )
            + (product_id,),
        )
    if "restock_at" in changes:
        save_plan(conn, product_id, changes["restock_at"])
    after = get_product(conn, product_id)
    audit(conn, user_id, product_id, "update", before, after, action_id)
    return after


def list_events():
    with connection() as conn:
        rows = conn.execute("""SELECT e.*,u.name AS actor_name FROM product_events e JOIN users u ON u.id=e.actor_id
                               ORDER BY e.created_at DESC,e.id DESC LIMIT 50""").fetchall()
    return [
        {
            **r,
            "before_data": json.loads(r["before_data"]),
            "after_data": json.loads(r["after_data"]),
        }
        for r in rows
    ]


def set_listing(user_id, product_id, active, conn=None, action_id=None, expected=None):
    if conn is None:
        with connection(write=True) as c:
            return set_listing(user_id, product_id, active, c, action_id, expected)
    require_admin(conn, user_id)
    before = get_product(conn, product_id, lock=True)
    if expected is not None and before != expected:
        raise HTTPException(409, "商品或库存已变化，请重新让 AI 生成操作预览")
    if before["active"] == int(active):
        return before
    if active and (before["price_cents"] < 1 or not before["name"].strip()):
        raise HTTPException(422, "上架前请填写有效的商品名称和售价")
    conn.execute("UPDATE products SET active=? WHERE id=?", (int(active), product_id))
    after = get_product(conn, product_id)
    audit(
        conn,
        user_id,
        product_id,
        "list" if active else "unlist",
        before,
        after,
        action_id,
    )
    return after
