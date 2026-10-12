import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from fastapi.testclient import TestClient
from fastapi import HTTPException
from tests import test_shop
from app.config import settings
from app.db import connection
from app.agents.tool_agent import execute_tool, confirm_action, tools_for


class CatalogTests(test_shop.ShopTests):
    def admin(self):
        client = TestClient(self.client.app)
        auth = client.post(
            "/api/auth/login",
            json={"email": "admin@shop.local", "password": "Demo12345!"},
        ).json()
        client.headers["Authorization"] = "Bearer " + auth["token"]
        return client

    def proposal(self, admin, message="把 P001 的库存改为 50 件"):
        result = admin.post("/api/chat", json={"message": message})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertTrue(result.json()["actions"], result.text)
        return result.json()["actions"][0]

    def test_manual_create_edit_audit_and_historical_price(self):
        admin = self.admin()
        new = {
            "id": "SKU-NEW",
            "name": "桌面新品",
            "category": "workspace",
            "price_cents": 10001,
            "stock": 9,
            "specs": {"颜色": "绿"},
        }
        result = admin.post("/api/admin/products", json=new)
        self.assertEqual(result.status_code, 201, result.text)
        self.assertEqual(
            self.client.get("/api/products", params={"q": "SKU-NEW"}).json()[0][
                "stock"
            ],
            9,
        )
        self.assertEqual(admin.post("/api/admin/products", json=new).status_code, 409)
        self.assertEqual(
            admin.patch(
                "/api/admin/products/P001",
                json={"name": "新耳机名称", "price_cents": 12345},
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.get("/api/orders/ORD-DEMO").json()["items"][0]["price_cents"],
            29900,
        )
        events = admin.get("/api/admin/product-events").json()
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["before_data"]["price_cents"], 29900)
        self.assertEqual(events[0]["after_data"]["price_cents"], 12345)
        self.assertIsNone(events[0]["action_id"])
        sku_action = self.proposal(admin, "把SKU-NEW的库存改为12件")
        self.assertEqual(sku_action["preview"]["after"]["stock"], 12)
        self.assertEqual(
            admin.post(
                f"/api/actions/{sku_action['id']}/confirm", json={"confirmed": True}
            ).status_code,
            200,
        )

    def test_buyer_cannot_manage_or_use_admin_tools(self):
        self.assertEqual(
            self.client.post(
                "/api/admin/products",
                json={
                    "id": "P007",
                    "name": "新品",
                    "category": "audio",
                    "price_cents": 99,
                    "stock": 1,
                },
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.patch(
                "/api/admin/products/P001", json={"stock": 50}
            ).status_code,
            403,
        )
        self.assertEqual(self.client.get("/api/admin/product-events").status_code, 403)
        cid = self.new_conversation()
        result = execute_tool(
            "propose_update_product",
            {"product_id": "P001", "changes": {"stock": 50}},
            "demo-user",
            cid,
        )
        self.assertIn("仅店铺管理员", result["error"])
        self.assertNotIn(
            "propose_update_product",
            [t["function"]["name"] for t in tools_for("customer")],
        )
        self.assertIn(
            "propose_update_product",
            [t["function"]["name"] for t in tools_for("admin")],
        )

    def test_ai_update_requires_confirmation_and_audits_once(self):
        admin = self.admin()
        before = self.client.get("/api/products/P001").json()["stock"]
        action = self.proposal(admin)
        self.assertEqual(action["preview"]["before"]["stock"], before)
        self.assertEqual(action["preview"]["after"]["stock"], 50)
        self.assertEqual(self.client.get("/api/products/P001").json()["stock"], before)
        self.assertEqual(admin.get("/api/admin/product-events").json(), [])
        self.assertEqual(
            self.client.post(
                f"/api/actions/{action['id']}/confirm", json={"confirmed": True}
            ).status_code,
            404,
        )
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(
                pool.map(
                    lambda _: confirm_action(action["id"], "demo-admin", True), range(2)
                )
            )
        self.assertEqual([r["status"] for r in results], ["confirmed", "confirmed"])
        self.assertEqual(self.client.get("/api/products/P001").json()["stock"], 50)
        events = admin.get("/api/admin/product-events").json()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["action_id"], action["id"])

    def test_rejection_and_expiry_do_not_write(self):
        admin = self.admin()
        action = self.proposal(admin)
        self.assertEqual(
            admin.post(
                f"/api/actions/{action['id']}/confirm", json={"confirmed": False}
            ).json()["status"],
            "rejected",
        )
        action = self.proposal(admin)
        with connection(write=True) as conn:
            conn.execute(
                "UPDATE pending_actions SET expires_at=0 WHERE id=?", (action["id"],)
            )
        self.assertEqual(
            admin.post(
                f"/api/actions/{action['id']}/confirm", json={"confirmed": True}
            ).status_code,
            409,
        )
        self.assertEqual(admin.get("/api/admin/product-events").json(), [])

    def test_changed_stock_blocks_stale_confirmation(self):
        admin = self.admin()
        action = self.proposal(admin, "把 P001 的售价改为 199.00")
        self.checkout()
        response = admin.post(
            f"/api/actions/{action['id']}/confirm", json={"confirmed": True}
        )
        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn("已变化", response.json()["detail"])
        self.assertEqual(
            self.client.get("/api/products/P001").json()["price_cents"], 29900
        )
        self.assertEqual(admin.get("/api/admin/product-events").json(), [])

    def test_confirmation_rechecks_admin_role(self):
        admin = self.admin()
        action = self.proposal(admin)
        with connection(write=True) as conn:
            conn.execute("UPDATE users SET role='customer' WHERE id='demo-admin'")
        with self.assertRaises(HTTPException) as exc:
            confirm_action(action["id"], "demo-admin", True)
        self.assertEqual(exc.exception.status_code, 403)

    def test_ai_creation_missing_fields_and_duplicate_race(self):
        admin = self.admin()
        missing = admin.post(
            "/api/chat", json={"message": "新增商品，名称 蓝牙耳机"}
        ).json()
        self.assertEqual(missing["actions"], [])
        self.assertIn("请补充", missing["reply"])
        action = self.proposal(
            admin,
            "新增商品，编号 P007，名称 蓝牙耳机，分类 audio，售价 199.00，库存 20",
        )
        self.assertEqual(self.client.get("/api/products/P007").status_code, 404)
        self.assertEqual(
            admin.post(
                f"/api/actions/{action['id']}/confirm", json={"confirmed": True}
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.get("/api/products/P007").json()["price_cents"], 19900
        )
        self.assertEqual(len(admin.get("/api/admin/product-events").json()), 1)
        cid = admin.post("/api/chat", json={"message": "你好"}).json()[
            "conversation_id"
        ]
        draft = {
            "id": "P008",
            "name": "另一商品",
            "category": "audio",
            "price_cents": 100,
            "stock": 5,
        }
        race = execute_tool("propose_create_product", draft, "demo-admin", cid)[
            "action"
        ]
        self.assertEqual(admin.post("/api/admin/products", json=draft).status_code, 201)
        self.assertEqual(
            admin.post(
                f"/api/actions/{race['id']}/confirm", json={"confirmed": True}
            ).status_code,
            409,
        )
        self.assertEqual(len(admin.get("/api/admin/product-events").json()), 2)

    def test_product_validation_and_restock_audit(self):
        admin = self.admin()
        for body in (
            {"stock": -1},
            {"stock": 1.1},
            {"name": "   "},
            {"category": "bad"},
            {"price_cents": 0},
            {"name": None},
            {"specs": {"x": "a" * 301}},
            {"restock_at": "2026-02-30"},
            {"active": 0},
            {},
        ):
            self.assertEqual(
                admin.patch("/api/admin/products/P001", json=body).status_code,
                422,
                body,
            )
        self.assertEqual(
            admin.put(
                "/api/admin/products/P001/stock",
                json={"stock": 10, "restock_at": "2026-11-01"},
            ).status_code,
            200,
        )
        action = self.proposal(admin, "把 P001 的补货日期改为 2026-11-15")
        self.assertEqual(
            admin.post(
                f"/api/actions/{action['id']}/confirm", json={"confirmed": True}
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.get("/api/products", params={"q": "P001"}).json()[0][
                "restock_at"
            ],
            "2026-11-15",
        )
        self.assertEqual(len(admin.get("/api/admin/product-events").json()), 2)
        invalid = admin.post(
            "/api/chat", json={"message": "把P001的库存改为50.5件"}
        ).json()
        self.assertEqual(invalid["actions"], [])
        self.assertIn("整数", invalid["reply"])

    def test_llm_admin_tool_loop_and_schema_uses_cents(self):
        admin = self.admin()
        settings.ai_mode = "llm"
        seen = []

        async def fake(messages, tools, emit):
            seen.append(tools)
            if messages[-1]["role"] == "user":
                return {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "mock",
                            "type": "function",
                            "function": {
                                "name": "propose_update_product",
                                "arguments": json.dumps(
                                    {
                                        "product_id": "P001",
                                        "changes": {"price_cents": 12001},
                                    }
                                ),
                            },
                        }
                    ],
                }, {}
            return {"role": "assistant", "content": "修改草稿已准备，请确认"}, {}

        try:
            with patch("app.agents.graph.call_llm", side_effect=fake):
                result = admin.post(
                    "/api/chat", json={"message": "修改耳机售价为120.01元"}
                ).json()
            self.assertIn(
                "propose_update_product", [t["function"]["name"] for t in seen[0]]
            )
            self.assertEqual(
                result["actions"][0]["preview"]["after"]["price_cents"], 12001
            )
            self.assertEqual(
                self.client.get("/api/products/P001").json()["price_cents"], 29900
            )
        finally:
            settings.ai_mode = "demo"

    def test_clothing_listing_intent_and_multi_turn_confirmation(self):
        admin = self.admin()
        first = admin.post("/api/chat", json={"message": "上新一个衣服商品"}).json()
        self.assertEqual(first["actions"], [])
        self.assertEqual(first["products"], [])
        self.assertIn("请补充", first["reply"])
        self.assertEqual(first["product_draft"]["分类"], "clothing")
        cid = first["conversation_id"]
        second = admin.post(
            "/api/chat",
            json={"message": "名称 纯棉T恤，售价 99.00", "conversation_id": cid},
        ).json()
        self.assertEqual(second["actions"], [])
        self.assertIn("编号、库存", second["reply"])
        restored = admin.get("/api/conversations/" + cid).json()["messages"][-1]
        self.assertEqual(restored["product_draft"]["名称"], "纯棉T恤")
        third = admin.post(
            "/api/chat",
            json={"message": "编号 CLO001，库存 20", "conversation_id": cid},
        ).json()
        self.assertEqual(third["actions"][0]["kind"], "create_product")
        preview = third["actions"][0]["preview"]["after"]
        self.assertEqual(
            (
                preview["category"],
                preview["image"],
                preview["price_cents"],
                preview["stock"],
            ),
            ("clothing", "shirt", 9900, 20),
        )
        self.assertEqual(self.client.get("/api/products/CLO001").status_code, 404)
        self.assertEqual(
            admin.post(
                f"/api/actions/{third['actions'][0]['id']}/confirm",
                json={"confirmed": True},
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.get("/api/products", params={"category": "clothing"}).json()[0][
                "name"
            ],
            "纯棉T恤",
        )
        # Completed drafts do not silently treat later field-only messages as another listing.
        later = admin.post(
            "/api/chat", json={"message": "编号 CLO002，库存 5", "conversation_id": cid}
        ).json()
        self.assertEqual(later["actions"], [])

    def test_empty_listing_draft_cancel_and_conversation_isolation(self):
        admin = self.admin()
        first = admin.post("/api/chat", json={"message": "上新一个商品"}).json()
        cid = first["conversation_id"]
        self.assertEqual(first["product_draft"], {})
        other = admin.post(
            "/api/chat",
            json={"message": "编号 CLO001，名称 T恤，分类 服装，售价 10，库存 1"},
        ).json()
        self.assertEqual(other["actions"], [])
        completed = admin.post(
            "/api/chat",
            json={
                "message": "编号 CLO001，名称 T恤，分类 服装，售价 10，库存 1",
                "conversation_id": cid,
            },
        ).json()
        self.assertEqual(len(completed["actions"]), 1)
        first = admin.post("/api/chat", json={"message": "上架一个衣服商品"}).json()
        cid = first["conversation_id"]
        cancelled = admin.post(
            "/api/chat", json={"message": "取消上新", "conversation_id": cid}
        ).json()
        self.assertIn("已取消", cancelled["reply"])
        self.assertNotIn("product_draft", cancelled)
        after = admin.post(
            "/api/chat",
            json={
                "message": "编号 CLO002，名称 T恤，售价 10，库存 1",
                "conversation_id": cid,
            },
        ).json()
        self.assertEqual(after["actions"], [])
        self.assertEqual(self.client.get("/api/products/CLO001").status_code, 404)

    def test_invalid_listing_fields_can_be_corrected_without_restarting(self):
        admin = self.admin()
        first = admin.post(
            "/api/chat",
            json={
                "message": "上新商品，编号 P001，名称 纯棉T恤，分类 服装，售价 99，库存 5"
            },
        ).json()
        self.assertEqual(first["actions"], [])
        self.assertIn("已存在", first["reply"])
        cid = first["conversation_id"]
        corrected = admin.post(
            "/api/chat", json={"message": "编号 CLO003", "conversation_id": cid}
        ).json()
        self.assertEqual(len(corrected["actions"]), 1)
        self.assertEqual(
            corrected["actions"][0]["preview"]["after"]["category"], "clothing"
        )

    def test_manual_listing_lifecycle_hidden_from_buyers_but_editable_by_admin(self):
        admin = self.admin()
        self.client.put("/api/cart", json={"product_id": "P001", "quantity": 1})
        self.assertEqual(
            admin.put(
                "/api/admin/products/P001/listing", json={"active": False}
            ).status_code,
            200,
        )
        self.assertEqual(self.client.get("/api/products/P001").status_code, 404)
        self.assertEqual(
            self.client.get("/api/products", params={"q": "P001"}).json(), []
        )
        self.assertEqual(
            self.client.put(
                "/api/cart", json={"product_id": "P001", "quantity": 1}
            ).status_code,
            404,
        )
        blocked = self.client.post(
            "/api/orders",
            json={"address": "测试收货地址", "request_key": "delisted-checkout"},
        )
        self.assertEqual(blocked.status_code, 409)
        self.assertIn("已下架", blocked.text)
        self.assertEqual(self.client.get("/api/cart").json()["items"][0]["active"], 0)
        self.assertEqual(
            len(admin.get("/api/admin/products", params={"status": "unlisted"}).json()),
            1,
        )
        self.assertEqual(admin.get("/api/admin/products/P001").json()["active"], 0)
        self.assertEqual(
            admin.patch(
                "/api/admin/products/P001", json={"stock": 11, "price_cents": 19901}
            ).status_code,
            200,
        )
        self.assertEqual(
            admin.put(
                "/api/admin/products/P001/listing", json={"active": True}
            ).status_code,
            200,
        )
        listed = self.client.get("/api/products/P001").json()
        self.assertEqual(
            (listed["active"], listed["stock"], listed["price_cents"]), (1, 11, 19901)
        )
        self.assertEqual(
            self.client.post(
                "/api/orders",
                json={"address": "测试收货地址", "request_key": "delisted-checkout"},
            ).status_code,
            201,
        )
        self.assertEqual(
            [e["kind"] for e in admin.get("/api/admin/product-events").json()],
            ["list", "update", "unlist"],
        )

    def test_ai_listing_queries_price_stock_and_restore_form_a_complete_flow(self):
        admin = self.admin()
        # Querying an unlisted status never prepares a listing change.
        query = admin.post("/api/chat", json={"message": "查询已下架商品"}).json()
        self.assertEqual(query["actions"], [])
        self.assertEqual(query["products"], [])
        action = self.proposal(admin, "下架 P001")
        self.assertEqual(action["kind"], "product_listing")
        self.assertEqual(action["preview"]["after"]["active"], 0)
        self.assertEqual(self.client.get("/api/products/P001").status_code, 200)
        self.assertEqual(
            admin.post(
                f"/api/actions/{action['id']}/confirm", json={"confirmed": True}
            ).status_code,
            200,
        )
        query = admin.post("/api/chat", json={"message": "查询已下架商品"}).json()
        self.assertEqual(query["products"][0]["id"], "P001")
        self.assertIn("已下架", query["reply"])
        for message in (
            "把 P001 的库存改为 20 件",
            "把 P001 的库存增加 5 件",
            "把 P001 的售价调整到 120.01",
        ):
            change = self.proposal(admin, message)
            self.assertEqual(
                admin.post(
                    f"/api/actions/{change['id']}/confirm", json={"confirmed": True}
                ).status_code,
                200,
            )
        self.assertEqual(admin.get("/api/admin/products/P001").json()["stock"], 25)
        action = self.proposal(admin, "重新上架 P001")
        self.assertEqual(action["kind"], "product_listing")
        self.assertEqual(
            admin.post(
                f"/api/actions/{action['id']}/confirm", json={"confirmed": True}
            ).status_code,
            200,
        )
        query = admin.post(
            "/api/chat", json={"message": "查询 P001 的库存和价格"}
        ).json()
        self.assertEqual(
            (query["products"][0]["stock"], query["products"][0]["price_cents"]),
            (25, 12001),
        )
        self.assertEqual(
            admin.post("/api/chat", json={"message": "查询一个不存在的名字"}).json()[
                "products"
            ],
            [],
        )

    def test_listing_permissions_expiry_stale_snapshot_and_repeated_confirmation(self):
        admin = self.admin()
        for path in ("/api/admin/products", "/api/admin/products/P001"):
            self.assertEqual(self.client.get(path).status_code, 403)
        self.assertEqual(
            self.client.put(
                "/api/admin/products/P001/listing", json={"active": False}
            ).status_code,
            403,
        )
        for tool, args in (
            ("query_admin_products", {}),
            ("propose_product_listing", {"product_id": "P001", "active": False}),
        ):
            self.assertIn(
                "error", execute_tool(tool, args, "demo-user", self.new_conversation())
            )
        self.assertEqual(
            admin.put(
                "/api/admin/products/P001/listing", json={"active": 1}
            ).status_code,
            422,
        )
        action = self.proposal(admin, "下架 P001")
        admin.patch("/api/admin/products/P001", json={"price_cents": 15000})
        self.assertEqual(
            admin.post(
                f"/api/actions/{action['id']}/confirm", json={"confirmed": True}
            ).status_code,
            409,
        )
        self.assertEqual(self.client.get("/api/products/P001").status_code, 200)
        action = self.proposal(admin, "下架 P001")
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(
                pool.map(
                    lambda _: confirm_action(action["id"], "demo-admin", True), range(2)
                )
            )
        self.assertEqual([r["status"] for r in results], ["confirmed", "confirmed"])
        self.assertEqual(
            len(
                [
                    e
                    for e in admin.get("/api/admin/product-events").json()
                    if e["kind"] == "unlist"
                ]
            ),
            1,
        )
        # A repeated manual request is also harmless and does not create another event.
        admin.put("/api/admin/products/P001/listing", json={"active": False})
        self.assertEqual(len(admin.get("/api/admin/product-events").json()), 2)

    def test_delisting_preserves_existing_order_payment_fulfillment_and_cancellation(
        self,
    ):
        admin = self.admin()
        order = self.checkout("before-delist-paid")
        second = self.checkout("before-delist-cancel")
        stock = admin.get("/api/admin/products/P001").json()["stock"]
        admin.put("/api/admin/products/P001/listing", json={"active": False})
        self.assertEqual(
            self.client.post(f"/api/orders/{order['id']}/pay").status_code, 200
        )
        self.assertEqual(
            admin.post(f"/api/admin/orders/{order['id']}/ship").status_code, 200
        )
        self.assertEqual(
            self.client.post(f"/api/orders/{order['id']}/receive").status_code, 200
        )
        self.assertEqual(
            self.client.post(f"/api/orders/{second['id']}/cancel").status_code, 200
        )
        hidden = admin.get("/api/admin/products/P001").json()
        self.assertEqual((hidden["active"], hidden["stock"]), (0, stock + 1))
        self.assertEqual(
            self.client.get(f"/api/orders/{order['id']}").json()["items"][0][
                "price_cents"
            ],
            29900,
        )

    def test_stock_delta_validation_and_llm_listing_protocol(self):
        admin = self.admin()
        cid = admin.post("/api/chat", json={"message": "你好"}).json()[
            "conversation_id"
        ]
        for args in (
            {"product_id": "P001", "stock_delta": -100000},
            {"product_id": "P001", "stock_delta": 2, "changes": {"stock": 20}},
        ):
            self.assertIn(
                "error", execute_tool("propose_update_product", args, "demo-admin", cid)
            )
        seen = []

        async def fake(messages, tools, emit):
            seen.append(tools)
            if messages[-1]["role"] == "user":
                return {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "mock-list",
                            "type": "function",
                            "function": {
                                "name": "propose_product_listing",
                                "arguments": json.dumps(
                                    {"product_id": "P001", "active": False}
                                ),
                            },
                        }
                    ],
                }, {}
            return {"role": "assistant", "content": "下架预览已准备，请确认"}, {}

        settings.ai_mode = "llm"
        try:
            with patch("app.agents.graph.call_llm", side_effect=fake):
                result = admin.post(
                    "/api/chat", json={"message": "暂时停售耳机"}
                ).json()
            self.assertIn(
                "propose_product_listing", [t["function"]["name"] for t in seen[0]]
            )
            action = result["actions"][0]
            self.assertEqual(action["preview"]["after"]["active"], 0)
            self.assertEqual(
                admin.post(
                    f"/api/actions/{action['id']}/confirm", json={"confirmed": True}
                ).status_code,
                200,
            )
        finally:
            settings.ai_mode = "demo"


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(
        CatalogTests(name) for name in CatalogTests.__dict__ if name.startswith("test_")
    )
