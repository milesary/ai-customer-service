import json
import time
from fastapi import HTTPException
from app import commerce, service, catalog
from app.db import connection
from app.models.schemas import (
    SearchArgs,
    OrderArgs,
    CartRequest,
    CancelArgs,
    TicketArgs,
    TicketQuery,
    HandoffRequest,
    ProductCreate,
    ProductEditArgs,
    ProductListingArgs,
    AdminProductQuery,
)
from app.knowledge_base.retriever import retrieve

TOOL_MODELS = {
    "search_products": (
        SearchArgs,
        "按商品编号、名称或规格关键词搜索；query填写一个关键词，空查询列出全部商品",
    ),
    "query_orders": (OrderArgs, "查询当前用户订单；空编号列出该用户订单"),
    "query_tickets": (
        TicketQuery,
        "查询当前用户售后或转人工工单、处理记录及进度；空编号列出全部工单",
    ),
    "search_knowledge": (SearchArgs, "检索店铺政策和商品说明，回答须标注来源"),
    "propose_add_to_cart": (CartRequest, "建议添加商品到购物车，必须用户确认后执行"),
    "propose_cancel_order": (CancelArgs, "建议取消当前用户的待支付订单，必须确认"),
    "propose_create_ticket": (TicketArgs, "建议创建当前用户售后工单，必须确认"),
    "propose_handoff": (
        HandoffRequest,
        "建议将当前会话转人工，并附上已查资料和对话摘要；必须用户确认",
    ),
    "propose_create_product": (
        ProductCreate,
        "管理员专用：新增商品草稿，编号、名称、分类、价格（分）和库存必须由管理员提供；缺少时追问。必须管理员确认后执行",
    ),
    "propose_update_product": (
        ProductEditArgs,
        "管理员专用：修改商品名称、分类、描述、价格（分）、库存、规格、示意图或补货日期；只填写明确要求修改的字段。changes.stock为修改后的绝对可售数量；增加/减少库存使用stock_delta（增量，可负），不能同时传两者。必须确认",
    ),
    "query_admin_products": (
        AdminProductQuery,
        "管理员专用：按编号、名称、规格、分类与上架状态查询商品，包含已下架商品。status=all/ listed/ unlisted；查询不需要确认",
    ),
    "propose_product_listing": (
        ProductListingArgs,
        "管理员专用：将已有商品上架（active=true）或下架（active=false）。保留历史订单，不删除商品。必须确认",
    ),
}
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": name,
            "description": desc,
            "parameters": model.model_json_schema(),
        },
    }
    for name, (model, desc) in TOOL_MODELS.items()
]
ADMIN_TOOLS = {
    "propose_create_product",
    "propose_update_product",
    "query_admin_products",
    "propose_product_listing",
}


def tools_for(role):
    return [
        t for t in TOOLS if role == "admin" or t["function"]["name"] not in ADMIN_TOOLS
    ]


def action_dict(row):
    result = dict(row)
    result["payload"] = json.loads(result["payload"])
    result["result"] = json.loads(result["result"]) if result["result"] else None
    if "_after" in result["payload"]:
        result["preview"] = {
            "before": result["payload"].get("_before"),
            "after": result["payload"]["_after"],
        }
    return result


def propose(user_id, conversation_id, kind, args):
    summary = ""
    with connection(write=True) as conn:
        if kind in ("create_product", "update_product", "product_listing"):
            catalog.require_admin(conn, user_id)
            if kind == "create_product":
                args = ProductCreate.model_validate(args).model_dump()
                if conn.execute(
                    "SELECT id FROM products WHERE id=?", (args["id"],)
                ).fetchone():
                    raise HTTPException(409, "商品编号已存在，请使用其他编号")
                summary = f"新增并上架商品 {args['id']} · {args['name']}"
                args = {**args, "_before": None, "_after": {**args, "active": 1}}
            else:
                before = catalog.get_product(conn, args["product_id"], lock=True)
                if kind == "product_listing":
                    changes = {"active": int(args["active"])}
                else:
                    data = dict(args.get("changes", {}))
                    if args.get("stock_delta") is not None:
                        if "stock" in data:
                            raise HTTPException(422, "不能同时指定库存绝对值和增量")
                        data["stock"] = before["stock"] + args["stock_delta"]
                    try:
                        changes = catalog.changes_data(data)
                    except ValueError:
                        raise HTTPException(
                            422, "修改值超出范围，请检查价格和库存"
                        ) from None
                if kind == "product_listing" and before["active"] == changes["active"]:
                    raise HTTPException(
                        409, "商品已经" + ("上架" if args["active"] else "下架")
                    )
                verb = (
                    ("上架" if args["active"] else "下架")
                    if kind == "product_listing"
                    else "修改"
                )
                summary = f"{verb}商品 {before['id']} · {before['name']}"
                args = {
                    "product_id": args["product_id"],
                    **(
                        {"active": bool(changes["active"])}
                        if kind == "product_listing"
                        else {"changes": changes}
                    ),
                    "_before": before,
                    "_after": {**before, **changes},
                }
        elif kind == "add_to_cart":
            p = conn.execute(
                "SELECT * FROM products WHERE id=? AND active=1", (args["product_id"],)
            ).fetchone()
            if not p:
                raise HTTPException(404, "商品不存在")
            if args["quantity"] > p["stock"]:
                raise HTTPException(409, "库存不足")
            summary = f"添加 {args['quantity']} 件 {p['name']} 到购物车"
        elif kind == "cancel_order":
            order = commerce.get_order(conn, args["order_id"], user_id)
            if order["status"] != "pending_payment":
                raise HTTPException(409, "仅待支付订单可取消")
            summary = f"取消订单 {order['id']}，释放预留库存"
        elif kind == "handoff":
            if args["order_id"]:
                commerce.get_order(conn, args["order_id"], user_id)
            summary = f"转人工处理：{args['reason'][:70]}"
        else:
            if args["order_id"]:
                order = commerce.get_order(conn, args["order_id"], user_id)
                if order["status"] not in ("paid", "shipped", "completed"):
                    raise HTTPException(409, "该订单无法申请售后")
            summary = f"创建售后工单：{args['reason'][:70]}"
        payload = json.dumps(args, ensure_ascii=False, sort_keys=True)
        previous = conn.execute(
            "SELECT * FROM pending_actions WHERE user_id=? AND conversation_id=? AND kind=? AND payload=? AND status='pending' AND expires_at>?",
            (user_id, conversation_id, kind, payload, time.time()),
        ).fetchone()
        if previous:
            return action_dict(previous)
        action_id = commerce.identifier("ACT")
        conn.execute(
            "INSERT INTO pending_actions VALUES (?,?,?,?,?,?,?,?,?)",
            (
                action_id,
                user_id,
                conversation_id,
                kind,
                payload,
                summary,
                "pending",
                None,
                time.time() + 600,
            ),
        )
        return action_dict(
            conn.execute(
                "SELECT * FROM pending_actions WHERE id=?", (action_id,)
            ).fetchone()
        )


def execute_tool(name, args, user_id, conversation_id):
    if name not in TOOL_MODELS:
        return {"error": "未知工具"}
    try:
        parsed = (
            TOOL_MODELS[name][0]
            .model_validate(args)
            .model_dump(exclude_unset=name == "propose_update_product")
        )
    except ValueError:
        return {"error": "工具参数不符合 schema，请补全正确参数"}
    try:
        if name in ADMIN_TOOLS:
            with connection() as conn:
                catalog.require_admin(conn, user_id)
        if name == "search_products":
            return {"products": commerce.products(parsed["query"])}
        if name == "query_admin_products":
            return {
                "products": commerce.products(
                    parsed["query"], parsed["category"], parsed["status"]
                )
            }
        if name == "query_orders":
            if parsed["order_id"]:
                with connection() as conn:
                    return {
                        "orders": [
                            commerce.get_order(conn, parsed["order_id"], user_id)
                        ]
                    }
            return {"orders": commerce.list_orders(user_id)}
        if name == "search_knowledge":
            return {"sources": retrieve(parsed["query"])}
        if name == "query_tickets":
            return {"tickets": service.list_tickets(user_id, parsed["ticket_id"])}
        return {
            "action": propose(
                user_id, conversation_id, name.removeprefix("propose_"), parsed
            )
        }
    except HTTPException as exc:
        return {"error": exc.detail}


def confirm_action(action_id, user_id, confirmed):
    with connection(write=True) as conn:
        # Lock the conversation first to serialize confirmation against handoff and AI runs.
        action = conn.execute(
            "SELECT conversation_id FROM pending_actions WHERE id=? AND user_id=?",
            (action_id, user_id),
        ).fetchone()
        if action:
            conversation = conn.lock(
                "SELECT busy_until FROM conversations WHERE id=?",
                (action["conversation_id"],),
            ).fetchone()
            if conversation["busy_until"] > time.time():
                raise HTTPException(409, "请等待当前回答完成后确认")
        row = conn.lock(
            "SELECT * FROM pending_actions WHERE id=? AND user_id=?",
            (action_id, user_id),
        ).fetchone()
        if not row:
            raise HTTPException(404, "确认操作不存在")
        if row["status"] != "pending":
            return action_dict(row)
        if row["expires_at"] < time.time():
            raise HTTPException(409, "确认已过期，请重新发起")
        result = None
        if confirmed:
            args = json.loads(row["payload"])
            if row["kind"] == "create_product":
                result = catalog.create_product(
                    user_id,
                    {k: v for k, v in args.items() if not k.startswith("_")},
                    conn,
                    action_id,
                )
            elif row["kind"] == "update_product":
                result = catalog.update_product(
                    user_id,
                    args["product_id"],
                    args["changes"],
                    conn,
                    action_id,
                    args["_before"],
                )
            elif row["kind"] == "product_listing":
                result = catalog.set_listing(
                    user_id,
                    args["product_id"],
                    args["active"],
                    conn,
                    action_id,
                    args["_before"],
                )
            elif row["kind"] == "add_to_cart":
                result = commerce.set_cart(
                    user_id, args["product_id"], args["quantity"], conn, add=True
                )
            elif row["kind"] == "cancel_order":
                result = commerce.cancel_order(user_id, args["order_id"], conn)
            elif row["kind"] == "create_ticket":
                result = commerce.create_ticket(
                    user_id, args["order_id"], args["reason"], conn
                )
                result = service.attach_ticket(
                    conn, result, user_id, row["conversation_id"]
                )
            elif row["kind"] == "handoff":
                result = service.handoff(
                    user_id,
                    row["conversation_id"],
                    args["reason"],
                    args["order_id"],
                    conn,
                    from_confirmation=True,
                )
            else:
                raise HTTPException(409, "不支持此操作")
        status = "confirmed" if confirmed else "rejected"
        conn.execute(
            "UPDATE pending_actions SET status=?,result=? WHERE id=?",
            (status, json.dumps(result, ensure_ascii=False), action_id),
        )
        conn.execute(
            "INSERT INTO messages(conversation_id,role,content,metadata,created_at) VALUES (?,?,?,?,?)",
            (
                row["conversation_id"],
                "assistant",
                f"用户{'确认并执行' if confirmed else '拒绝'}了操作：{row['summary']}",
                json.dumps({"action_id": action_id, "status": status}),
                commerce.now(),
            ),
        )
        return action_dict(
            conn.execute(
                "SELECT * FROM pending_actions WHERE id=?", (action_id,)
            ).fetchone()
        )
