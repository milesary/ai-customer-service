"""Customer service context, handoff and auditable human handling."""

import json
import time
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from app import commerce
from app.db import connection


def ticket_dict(conn, row):
    ticket = dict(row)
    ticket.pop("active_order_id", None)
    detail = conn.execute(
        "SELECT * FROM ticket_details WHERE ticket_id=?", (row["id"],)
    ).fetchone()
    ticket.update(
        dict(detail)
        if detail
        else {
            "conversation_id": None,
            "category": "after_sale",
            "summary": row["reason"],
            "owner_id": None,
            "due_at": None,
            "updated_at": row["created_at"],
        }
    )
    owner = (
        conn.execute(
            "SELECT name FROM users WHERE id=?", (ticket["owner_id"],)
        ).fetchone()
        if ticket["owner_id"]
        else None
    )
    ticket["owner_name"] = owner["name"] if owner else None
    ticket["events"] = [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM ticket_events WHERE ticket_id=? ORDER BY created_at,id",
            (row["id"],),
        )
    ]
    return ticket


def list_tickets(user_id=None, ticket_id=None, conn=None):
    if conn is None:
        with connection() as c:
            return list_tickets(user_id, ticket_id, c)
    rows = conn.execute(
        """SELECT * FROM tickets WHERE (? IS NULL OR user_id=?) AND (? IS NULL OR id=?)
                           ORDER BY created_at DESC,id""",
        (user_id, user_id, ticket_id, ticket_id),
    ).fetchall()
    if ticket_id and not rows:
        raise HTTPException(404, "工单不存在")
    return [ticket_dict(conn, row) for row in rows]


def active_handoff(conn, conversation_id):
    row = conn.lock(
        """SELECT t.* FROM tickets t JOIN ticket_details d ON d.ticket_id=t.id
                          WHERE d.conversation_id=? AND d.category='handoff' AND t.status!='resolved'
                          ORDER BY t.created_at DESC LIMIT 1""",
        (conversation_id,),
    ).fetchone()
    return ticket_dict(conn, row) if row else None


def get_conversation(conn, conversation_id, user_id, allow_deleted=False):
    row = conn.lock(
        "SELECT * FROM conversations WHERE id=? AND user_id=?",
        (conversation_id, user_id),
    ).fetchone()
    if not row or (
        not allow_deleted
        and conn.execute(
            "SELECT conversation_id FROM conversation_deletions WHERE conversation_id=?",
            (conversation_id,),
        ).fetchone()
    ):
        raise HTTPException(404, "会话不存在或已删除")
    return row


def list_conversations(conn, user_id):
    return [
        dict(r)
        for r in conn.execute(
            """SELECT id,title,created_at FROM conversations
        WHERE user_id=? AND NOT EXISTS (SELECT 1 FROM conversation_deletions WHERE conversation_id=conversations.id)
        ORDER BY created_at DESC""",
            (user_id,),
        )
    ]


def delete_conversation(user_id, conversation_id):
    with connection(write=True) as conn:
        row = get_conversation(conn, conversation_id, user_id)
        if row["busy_until"] > time.time():
            raise HTTPException(409, "请等待当前回答完成后删除会话")
        if active_handoff(conn, conversation_id):
            raise HTTPException(409, "会话正在由人工处理，请等待工单完成后删除")
        # Retain links used by order, product and service audit records.
        conn.execute(
            "INSERT INTO conversation_deletions VALUES (?,?)",
            (conversation_id, commerce.now()),
        )
        conn.execute(
            "UPDATE pending_actions SET status='rejected' WHERE conversation_id=? AND status='pending'",
            (conversation_id,),
        )
    return {"ok": True}


def context(user_id):
    with connection() as conn:
        user = conn.execute(
            "SELECT id,name,email,role FROM users WHERE id=?", (user_id,)
        ).fetchone()
        if not user:
            raise HTTPException(404, "客户不存在")
        orders = [
            commerce.order_dict(conn, r)
            for r in conn.execute(
                "SELECT * FROM orders WHERE user_id=? ORDER BY created_at DESC",
                (user_id,),
            )
        ]
        conversations = list_conversations(conn, user_id)
        return {
            "customer": dict(user),
            "orders": orders,
            "tickets": list_tickets(user_id, conn=conn),
            "conversations": conversations,
        }


def add_event(conn, ticket_id, actor_id, kind, content):
    conn.execute(
        "INSERT INTO ticket_events VALUES (?,?,?,?,?,?)",
        (
            commerce.identifier("EVT"),
            ticket_id,
            actor_id,
            kind,
            content,
            commerce.now(),
        ),
    )


def attach_ticket(conn, ticket, user_id, conversation_id, category="after_sale"):
    if conn.execute(
        "SELECT ticket_id FROM ticket_details WHERE ticket_id=?", (ticket["id"],)
    ).fetchone():
        # Keep one conversation per case; never silently move an existing handoff.
        return ticket_dict(conn, ticket)
    lines = []
    if conversation_id:
        for row in conn.execute(
            "SELECT role,content,metadata FROM messages WHERE conversation_id=? ORDER BY id DESC LIMIT 8",
            (conversation_id,),
        ).fetchall()[::-1]:
            lines.append(
                ("客户" if row["role"] == "user" else "客服")
                + "："
                + row["content"][:240]
            )
            meta = json.loads(row["metadata"])
            if meta.get("sources"):
                lines.append(
                    "已参考：" + "、".join(s["title"] for s in meta["sources"])
                )
            if meta.get("trace"):
                lines.append(
                    "已执行工具："
                    + "、".join(
                        s["node"]
                        for s in meta["trace"]
                        if s["node"] not in ("retrieval", "assistant")
                    )
                )
    summary = "\n".join(lines) or ticket["reason"]
    due = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    conn.execute(
        "INSERT INTO ticket_details VALUES (?,?,?,?,?,?,?)",
        (ticket["id"], conversation_id, category, summary, None, due, commerce.now()),
    )
    add_event(conn, ticket["id"], user_id, "created", ticket["reason"])
    return ticket_dict(conn, ticket)


def handoff(
    user_id, conversation_id, reason, order_id=None, conn=None, from_confirmation=False
):
    if conn is None:
        with connection(write=True) as c:
            return handoff(user_id, conversation_id, reason, order_id, c)
    conversation = get_conversation(conn, conversation_id, user_id)
    if conversation["busy_until"] > time.time() and not from_confirmation:
        raise HTTPException(409, "请等待当前回答完成后转人工")
    previous = active_handoff(conn, conversation_id)
    if previous:
        return previous
    if order_id:
        commerce.get_order(conn, order_id, user_id)
    # Handoff is a service request, including unpaid order enquiries; separate from after-sale eligibility.
    existing = (
        conn.execute(
            "SELECT * FROM tickets WHERE user_id=? AND order_id=? AND status IN ('open','processing')",
            (user_id, order_id),
        ).fetchone()
        if order_id
        else None
    )
    ticket = (
        dict(existing)
        if existing
        else commerce.create_ticket(user_id, None, reason, conn)
    )
    if order_id and not existing:
        conn.execute(
            "UPDATE tickets SET order_id=? WHERE id=?", (order_id, ticket["id"])
        )
        ticket["order_id"] = order_id
    if existing:
        detail = conn.execute(
            "SELECT * FROM ticket_details WHERE ticket_id=?", (ticket["id"],)
        ).fetchone()
        if (
            detail
            and detail["conversation_id"]
            and detail["conversation_id"] != conversation_id
        ):
            raise HTTPException(409, "此订单已有另一会话关联的工单，请在售后页查看进度")
        if detail:
            conn.execute(
                "UPDATE ticket_details SET conversation_id=?,category=? WHERE ticket_id=?",
                (conversation_id, "handoff", ticket["id"]),
            )
            add_event(conn, ticket["id"], user_id, "handoff", reason)
    ticket = attach_ticket(conn, ticket, user_id, conversation_id, "handoff")
    conn.execute(
        "INSERT INTO messages(conversation_id,role,content,metadata,created_at) VALUES (?,?,?,?,?)",
        (
            conversation_id,
            "assistant",
            f"已转入人工队列，工单 {ticket['id']}。客服会收到本次对话摘要；请在这里查看处理进度。",
            json.dumps({"author": "service", "ticket_id": ticket["id"]}),
            commerce.now(),
        ),
    )
    # Pending model proposals cannot execute after ownership moves to a human.
    conn.execute(
        "UPDATE pending_actions SET status='rejected' WHERE conversation_id=? AND status='pending'",
        (conversation_id,),
    )
    return ticket


def lock_ticket(conn, ticket_id):
    detail = conn.execute(
        "SELECT conversation_id FROM ticket_details WHERE ticket_id=?", (ticket_id,)
    ).fetchone()
    # All service writers lock conversation before ticket, including customer messages.
    if detail and detail["conversation_id"]:
        conn.lock(
            "SELECT id FROM conversations WHERE id=?", (detail["conversation_id"],)
        ).fetchone()
    return conn.lock("SELECT * FROM tickets WHERE id=?", (ticket_id,)).fetchone()


def update_ticket(ticket_id, status, resolution, actor_id):
    with connection(write=True) as conn:
        row = lock_ticket(conn, ticket_id)
        if not row:
            raise HTTPException(404, "工单不存在")
        ticket = attach_ticket(conn, row, row["user_id"], None)
        if row["status"] == "resolved":
            if status != "resolved" or row["resolution"] != resolution:
                raise HTTPException(409, "已完成工单不可重新打开或修改结果")
            return ticket
        if ticket["owner_id"] and ticket["owner_id"] != actor_id:
            raise HTTPException(409, "此工单已由其他客服接单")
        if status == "resolved" and not resolution.strip():
            raise HTTPException(422, "请填写处理结果")
        conn.execute(
            "UPDATE tickets SET status=?,resolution=? WHERE id=?",
            (status, resolution, ticket_id),
        )
        conn.execute(
            "UPDATE ticket_details SET owner_id=?,updated_at=? WHERE ticket_id=?",
            (actor_id, commerce.now(), ticket_id),
        )
        add_event(conn, ticket_id, actor_id, status, resolution or "客服已接单")
        if status == "resolved" and ticket["conversation_id"]:
            conn.execute(
                "INSERT INTO messages(conversation_id,role,content,metadata,created_at) VALUES (?,?,?,?,?)",
                (
                    ticket["conversation_id"],
                    "assistant",
                    "工单处理完成：" + resolution + "。后续问题可继续向 AI 客服咨询。",
                    json.dumps({"author": "human", "ticket_id": ticket_id}),
                    commerce.now(),
                ),
            )
        return list_tickets(ticket_id=ticket_id, conn=conn)[0]


def human_reply(ticket_id, content, actor_id):
    if not content.strip():
        raise HTTPException(422, "回复不能为空")
    with connection(write=True) as conn:
        row = lock_ticket(conn, ticket_id)
        if not row:
            raise HTTPException(404, "工单不存在")
        ticket = ticket_dict(conn, row)
        if row["status"] != "processing" or ticket["owner_id"] != actor_id:
            raise HTTPException(409, "请先接单，已完成工单不可回复")
        add_event(conn, ticket_id, actor_id, "reply", content)
        if ticket["conversation_id"]:
            conn.execute(
                "INSERT INTO messages(conversation_id,role,content,metadata,created_at) VALUES (?,?,?,?,?)",
                (
                    ticket["conversation_id"],
                    "assistant",
                    content,
                    json.dumps({"author": "human", "ticket_id": ticket_id}),
                    commerce.now(),
                ),
            )
        conn.execute(
            "UPDATE ticket_details SET updated_at=? WHERE ticket_id=?",
            (commerce.now(), ticket_id),
        )
        return list_tickets(ticket_id=ticket_id, conn=conn)[0]


def fulfillment(order_id, stage, detail):
    with connection(write=True) as conn:
        order = commerce.get_order(conn, order_id)
        if order["status"] != "shipped":
            raise HTTPException(409, "只有已发货订单可更新配送节点")
        previous = order["fulfillment"][-1] if order["fulfillment"] else None
        if previous and previous["stage"] == "delivered":
            if stage == previous["stage"] and detail == previous["detail"]:
                return order
            raise HTTPException(409, "已送达订单不可回退配送节点")
        if previous and previous["stage"] == stage and previous["detail"] == detail:
            return order
        conn.execute(
            "INSERT INTO fulfillment_events VALUES (?,?,?,?,?)",
            (commerce.identifier("FUL"), order_id, stage, detail, commerce.now()),
        )
        return commerce.get_order(conn, order_id)


def conversation_history(conversation_id, user_id, allow_deleted=False):
    with connection() as conn:
        get_conversation(conn, conversation_id, user_id, allow_deleted)
        messages = []
        for m in conn.execute(
            "SELECT role,content,metadata FROM messages WHERE conversation_id=? ORDER BY id",
            (conversation_id,),
        ):
            metadata = json.loads(m["metadata"])
            for action in metadata.get("actions", []):
                a = conn.execute(
                    "SELECT status FROM pending_actions WHERE id=?", (action["id"],)
                ).fetchone()
                if a:
                    action["status"] = a["status"]
            messages.append({"role": m["role"], "content": m["content"], **metadata})
        return {
            "id": conversation_id,
            "messages": messages,
            "handoff": active_handoff(conn, conversation_id),
        }
