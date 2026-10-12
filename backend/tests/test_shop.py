import asyncio
import json
import os
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import httpx
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app.config import settings
from app.db import initialize, connection, engine_for
from app.main import app
from app import commerce
from app.agents.tool_agent import execute_tool, propose, confirm_action
from app.chat import prepare_conversation
from app.knowledge_base.retriever import retrieve


class ShopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.original_path = settings.database_path
        cls.original_url = settings.database_url
        cls.original_mode = settings.ai_mode
        cls.original_seed = settings.seed_demo
        settings.ai_mode = "demo"
        settings.seed_demo = True

    @classmethod
    def tearDownClass(cls):
        settings.database_path = cls.original_path
        settings.database_url = cls.original_url
        settings.ai_mode = cls.original_mode
        settings.seed_demo = cls.original_seed
        cls.temp.cleanup()

    def setUp(self):
        settings.database_path = os.path.join(
            self.temp.name, self._testMethodName + ".db"
        )
        settings.database_url = "sqlite:///" + settings.database_path.replace("\\", "/")
        self.mysql_database = None
        if os.environ.get("MYSQL_TEST_URL"):
            from sqlalchemy.engine import make_url
            from sqlalchemy import create_engine

            self.mysql_database = "shiwu_test_" + os.urandom(6).hex()
            self.mysql_server = create_engine(
                make_url(os.environ["MYSQL_TEST_URL"])._replace(database=None),
                hide_parameters=True,
            )
            with self.mysql_server.begin() as conn:
                conn.exec_driver_sql(
                    f"CREATE DATABASE {self.mysql_database} CHARACTER SET utf8mb4"
                )
            settings.database_url = (
                make_url(os.environ["MYSQL_TEST_URL"])
                .set(database=self.mysql_database)
                .render_as_string(hide_password=False)
            )
        initialize()
        self.client = TestClient(app)
        auth = self.client.post(
            "/api/auth/login",
            json={"email": "demo@shop.local", "password": "Demo12345!"},
        ).json()
        self.client.headers["Authorization"] = "Bearer " + auth["token"]

    def tearDown(self):
        self.client.close()
        engine_for(settings.database_url).dispose()
        if self.mysql_database:
            # Only the random database created by this test can be removed.
            assert (
                self.mysql_database.startswith("shiwu_test_")
                and self.mysql_database[11:].isalnum()
            )
            with self.mysql_server.begin() as conn:
                conn.exec_driver_sql(f"DROP DATABASE {self.mysql_database}")
            self.mysql_server.dispose()

    def register_other(self):
        client = TestClient(app)
        r = client.post(
            "/api/auth/register",
            json={
                "name": "Other",
                "email": "other@example.com",
                "password": "Other12345!",
            },
        )
        self.assertEqual(r.status_code, 201)
        client.headers["Authorization"] = "Bearer " + r.json()["token"]
        return client, r.json()["user"]["id"]

    def checkout(self, key="test-key-123"):
        self.client.put("/api/cart", json={"product_id": "P001", "quantity": 1})
        r = self.client.post(
            "/api/orders",
            json={"address": "测试收货地址，不发生配送", "request_key": key},
        )
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()

    def new_conversation(self):
        return self.client.post("/api/chat", json={"message": "你好"}).json()[
            "conversation_id"
        ]

    def test_auth_and_logout(self):
        self.assertEqual(TestClient(app).get("/api/orders").status_code, 401)
        self.assertEqual(self.client.get("/api/auth/me").json()["id"], "demo-user")
        self.client.post("/api/auth/logout")
        self.assertEqual(self.client.get("/api/cart").status_code, 401)

    def test_registration_cannot_assign_admin(self):
        other, _ = self.register_other()
        self.assertEqual(other.get("/api/admin/overview").status_code, 403)
        r = other.post(
            "/api/auth/register",
            json={
                "name": "Fake",
                "email": "fake@example.com",
                "password": "Fake12345!",
                "role": "admin",
            },
        )
        self.assertEqual(r.status_code, 422)

    def test_bad_login(self):
        self.assertEqual(
            self.client.post(
                "/api/auth/login",
                json={"email": "demo@shop.local", "password": "wrong"},
            ).status_code,
            401,
        )

    def test_search_supports_product_id_and_specs(self):
        self.assertEqual(
            self.client.get("/api/products", params={"q": "P001"}).json()[0]["id"],
            "P001",
        )
        self.assertEqual(
            self.client.get("/api/products", params={"q": "macOS"}).json()[0]["id"],
            "P002",
        )

    def test_cart_totals_integer_cents(self):
        r = self.client.put("/api/cart", json={"product_id": "P003", "quantity": 1})
        self.assertEqual(r.json()["total_cents"], 9700)
        self.client.put("/api/cart", json={"product_id": "P003", "quantity": 2})
        self.assertEqual(self.client.get("/api/cart").json()["shipping_cents"], 0)

    def test_quantity_schema_and_inventory(self):
        for q in (0, -1, 100, 1.5, "1", True):
            self.assertEqual(
                self.client.put(
                    "/api/cart", json={"product_id": "P001", "quantity": q}
                ).status_code,
                422,
            )
        self.assertEqual(
            self.client.put(
                "/api/cart", json={"product_id": "P001", "quantity": 25}
            ).status_code,
            409,
        )

    def test_order_idempotency_and_price_snapshot(self):
        before = self.client.get("/api/products/P001").json()["stock"]
        first = self.checkout()
        second = self.client.post(
            "/api/orders",
            json={"address": "测试收货地址，不发生配送", "request_key": "test-key-123"},
        ).json()
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(
            self.client.get("/api/products/P001").json()["stock"], before - 1
        )
        self.assertEqual(first["items"][0]["price_cents"], 29900)
        self.assertEqual(self.client.get("/api/cart").json()["items"], [])

    def test_reused_key_cannot_change_payload(self):
        self.checkout()
        r = self.client.post(
            "/api/orders",
            json={"address": "另一个收货地址", "request_key": "test-key-123"},
        )
        self.assertEqual(r.status_code, 409)

    def test_order_cancel_releases_stock_once(self):
        before = self.client.get("/api/products/P001").json()["stock"]
        order = self.checkout()
        for _ in range(2):
            self.assertEqual(
                self.client.post(f"/api/orders/{order['id']}/cancel").status_code, 200
            )
        self.assertEqual(self.client.get("/api/products/P001").json()["stock"], before)

    def test_paid_order_cannot_cancel(self):
        order = self.checkout()
        self.client.post(f"/api/orders/{order['id']}/pay")
        self.assertEqual(
            self.client.post(f"/api/orders/{order['id']}/cancel").status_code, 409
        )

    def test_cross_user_order_isolation(self):
        order = self.checkout()
        other, _ = self.register_other()
        for path in ("", "/pay", "/cancel", "/receive"):
            r = (
                other.get(f"/api/orders/{order['id']}")
                if not path
                else other.post(f"/api/orders/{order['id']}{path}")
            )
            self.assertEqual(r.status_code, 404)
        self.assertEqual(
            other.post(
                "/api/tickets", json={"order_id": order["id"], "reason": "售后测试"}
            ).status_code,
            404,
        )

    def test_tool_scope_and_schema(self):
        result = execute_tool(
            "query_orders", {"order_id": "ORD-DEMO"}, "unrelated-user", "irrelevant"
        )
        self.assertIn("error", result)
        result = execute_tool(
            "query_orders",
            {"order_id": "ORD-DEMO", "user_id": "demo-user"},
            "unrelated-user",
            "irrelevant",
        )
        self.assertIn("error", result)
        self.assertIn("error", execute_tool("refund", {}, "demo-user", "irrelevant"))

    def test_transaction_rollback_when_second_item_out_of_stock(self):
        self.client.put("/api/cart", json={"product_id": "P001", "quantity": 1})
        self.client.put("/api/cart", json={"product_id": "P002", "quantity": 1})
        with connection(write=True) as conn:
            conn.execute("UPDATE products SET stock=0 WHERE id='P002'")
        before = self.client.get("/api/products/P001").json()["stock"]
        r = self.client.post(
            "/api/orders",
            json={"address": "测试收货地址", "request_key": "rollback-key"},
        )
        self.assertEqual(r.status_code, 409)
        self.assertEqual(self.client.get("/api/products/P001").json()["stock"], before)
        self.assertEqual(len(self.client.get("/api/cart").json()["items"]), 2)

    def test_two_buyers_cannot_oversell_last_item(self):
        _, other_id = self.register_other()
        with connection(write=True) as conn:
            conn.execute("UPDATE products SET stock=1 WHERE id='P001'")
        commerce.set_cart("demo-user", "P001", 1)
        commerce.set_cart(other_id, "P001", 1)

        def buy(uid):
            try:
                return commerce.create_order(uid, "测试并发收货地址", "last-item-key")[
                    "id"
                ]
            except HTTPException as exc:
                return exc.status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(buy, ["demo-user", other_id]))
        self.assertEqual(sum(isinstance(x, str) for x in results), 1)
        self.assertIn(409, results)
        self.assertEqual(self.client.get("/api/products/P001").json()["stock"], 0)

    def test_action_requires_confirmation_and_is_idempotent(self):
        r = self.client.post("/api/chat", json={"message": "把 P001 加入购物车"}).json()
        action = r["actions"][0]
        self.assertEqual(self.client.get("/api/cart").json()["items"], [])
        for _ in range(2):
            r = self.client.post(
                f"/api/actions/{action['id']}/confirm", json={"confirmed": True}
            )
            self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.client.get("/api/cart").json()["items"][0]["quantity"], 1)

    def test_rejected_action_does_not_mutate(self):
        r = self.client.post("/api/chat", json={"message": "把 P001 加入购物车"}).json()
        action = r["actions"][0]
        self.client.post(
            f"/api/actions/{action['id']}/confirm", json={"confirmed": False}
        )
        self.client.post(
            f"/api/actions/{action['id']}/confirm", json={"confirmed": True}
        )
        self.assertEqual(self.client.get("/api/cart").json()["items"], [])

    def test_action_owner_and_expiry(self):
        r = self.client.post("/api/chat", json={"message": "把 P001 加入购物车"}).json()
        action = r["actions"][0]
        other, _ = self.register_other()
        self.assertEqual(
            other.post(
                f"/api/actions/{action['id']}/confirm", json={"confirmed": True}
            ).status_code,
            404,
        )
        with connection(write=True) as conn:
            conn.execute(
                "UPDATE pending_actions SET expires_at=? WHERE id=?",
                (time.time() - 1, action["id"]),
            )
        self.assertEqual(
            self.client.post(
                f"/api/actions/{action['id']}/confirm", json={"confirmed": True}
            ).status_code,
            409,
        )

    def test_confirmation_rechecks_order_state(self):
        order = self.checkout()
        cid = self.new_conversation()
        action = propose("demo-user", cid, "cancel_order", {"order_id": order["id"]})
        self.client.post(f"/api/orders/{order['id']}/pay")
        r = self.client.post(
            f"/api/actions/{action['id']}/confirm", json={"confirmed": True}
        )
        self.assertEqual(r.status_code, 409)
        self.assertEqual(
            self.client.get(f"/api/orders/{order['id']}").json()["status"], "paid"
        )

    def test_multi_turn_order_reference_and_history_restore(self):
        first = self.client.post("/api/chat", json={"message": "查询 ORD-DEMO"}).json()
        second = self.client.post(
            "/api/chat",
            json={
                "message": "这单现在到哪了",
                "conversation_id": first["conversation_id"],
            },
        ).json()
        self.assertIn("ORD-DEMO", second["reply"])
        history = self.client.get(
            "/api/conversations/" + first["conversation_id"]
        ).json()["messages"]
        self.assertEqual(len(history), 4)
        self.assertEqual(history[-1]["content"], second["reply"])

    def test_conversation_isolation_and_serialization(self):
        cid = self.new_conversation()
        other, _ = self.register_other()
        self.assertEqual(other.get("/api/conversations/" + cid).status_code, 404)
        self.assertEqual(
            other.post(
                "/api/chat", json={"message": "你好", "conversation_id": cid}
            ).status_code,
            404,
        )
        prepare_conversation("demo-user", cid, "first pending")
        self.assertEqual(
            self.client.post(
                "/api/chat", json={"message": "second pending", "conversation_id": cid}
            ).status_code,
            409,
        )

    def test_sse_contains_live_steps_actions_and_final_message(self):
        r = self.client.post("/api/chat/stream", json={"message": "把 P001 加入购物车"})
        self.assertEqual(r.status_code, 200)
        events = [
            json.loads(line[6:])
            for line in r.text.splitlines()
            if line.startswith("data: ")
        ]
        names = [e["event"] for e in events]
        self.assertEqual(names[0], "conversation")
        self.assertLess(names.index("step"), names.index("action"))
        self.assertLess(names.index("action"), names.index("message"))
        self.assertEqual(names[-1], "done")
        self.assertEqual(self.client.get("/api/cart").json()["items"], [])

    def test_unknown_query_does_not_return_zero_score_documents(self):
        self.assertEqual(retrieve("zzzzzzzz"), [])
        self.assertEqual(retrieve("退货需要保持包装完整吗")[0]["id"], "returns")

    def test_after_sale_admin_workflow(self):
        r = self.client.post(
            "/api/tickets", json={"order_id": "ORD-DEMO", "reason": "左侧耳机无法连接"}
        )
        self.assertEqual(r.status_code, 201, r.text)
        ticket = r.json()
        duplicate = self.client.post(
            "/api/tickets", json={"order_id": "ORD-DEMO", "reason": "左侧耳机无法连接"}
        ).json()
        self.assertEqual(ticket["id"], duplicate["id"])
        admin = TestClient(app)
        auth = admin.post(
            "/api/auth/login",
            json={"email": "admin@shop.local", "password": "Demo12345!"},
        ).json()
        admin.headers["Authorization"] = "Bearer " + auth["token"]
        for state, resolution in [("processing", ""), ("resolved", "已安排演示换货")]:
            self.assertEqual(
                admin.put(
                    "/api/admin/tickets/" + ticket["id"],
                    json={"status": state, "resolution": resolution},
                ).status_code,
                200,
            )
        self.assertEqual(
            self.client.get("/api/tickets").json()[0]["status"], "resolved"
        )

    def test_admin_ship_and_customer_receive(self):
        order = self.checkout()
        self.client.post(f"/api/orders/{order['id']}/pay")
        self.assertEqual(
            self.client.post(f"/api/admin/orders/{order['id']}/ship").status_code, 403
        )
        admin = TestClient(app)
        auth = admin.post(
            "/api/auth/login",
            json={"email": "admin@shop.local", "password": "Demo12345!"},
        ).json()
        admin.headers["Authorization"] = "Bearer " + auth["token"]
        self.assertEqual(
            admin.post(f"/api/admin/orders/{order['id']}/ship").status_code, 200
        )
        self.assertEqual(
            self.client.post(f"/api/orders/{order['id']}/receive").json()["status"],
            "completed",
        )

    def test_llm_tool_loop_with_mocked_model(self):
        original = settings.ai_mode
        settings.ai_mode = "llm"
        calls = []

        async def fake(messages, tools, emit):
            calls.append(messages)
            if messages[-1]["role"] == "user":
                return {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "mock-call",
                            "type": "function",
                            "function": {
                                "name": "query_orders",
                                "arguments": '{"order_id":"ORD-DEMO"}',
                            },
                        }
                    ],
                }, {"prompt_tokens": 10, "completion_tokens": 4}
            self.assertEqual(messages[-1]["role"], "tool")
            emit({"event": "token", "data": {"content": "订单正在运输中"}})
            return {"role": "assistant", "content": "订单正在运输中"}, {
                "prompt_tokens": 20,
                "completion_tokens": 6,
            }

        try:
            with patch("app.agents.graph.call_llm", side_effect=fake):
                result = self.client.post(
                    "/api/chat", json={"message": "查订单"}
                ).json()
            self.assertEqual(result["llm_calls"], 2)
            self.assertEqual(result["tool_calls"], 1)
            with connection() as conn:
                record = conn.execute(
                    "SELECT * FROM ai_runs WHERE id=?", (result["run_id"],)
                ).fetchone()
            self.assertEqual(record["prompt_tokens"], 30)
            self.assertEqual(record["completion_tokens"], 10)
        finally:
            settings.ai_mode = original

    def test_llm_error_releases_conversation(self):
        original = settings.ai_mode
        settings.ai_mode = "llm"
        try:
            with self.assertLogs("app.chat", level="ERROR"):
                with patch(
                    "app.agents.graph.call_llm",
                    side_effect=RuntimeError("mock failure"),
                ):
                    r = self.client.post(
                        "/api/chat/stream", json={"message": "测试错误"}
                    )
            events = [
                json.loads(line[6:])
                for line in r.text.splitlines()
                if line.startswith("data: ")
            ]
            self.assertIn("error", [e["event"] for e in events])
            cid = events[0]["data"]["id"]
            with connection() as conn:
                self.assertEqual(
                    conn.execute(
                        "SELECT busy_until FROM conversations WHERE id=?", (cid,)
                    ).fetchone()[0],
                    0,
                )
        finally:
            settings.ai_mode = original


class LLMProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_streaming_fragments_and_usage(self):
        from app.agents.llm_client import call_llm

        original_key = settings.llm_api_key
        settings.llm_api_key = "test-key-not-real"
        chunks = [
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "call_1",
                                    "function": {
                                        "name": "query_orders",
                                        "arguments": '{"order_',
                                    },
                                }
                            ]
                        }
                    }
                ]
            },
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "function": {"arguments": 'id":"ORD-DEMO"}'},
                                }
                            ]
                        }
                    }
                ]
            },
            {"choices": [], "usage": {"prompt_tokens": 12, "completion_tokens": 6}},
        ]
        body = (
            "".join("data: " + json.dumps(c) + "\n\n" for c in chunks)
            + "data: [DONE]\n\n"
        )
        transport = httpx.MockTransport(lambda request: httpx.Response(200, text=body))
        client = httpx.AsyncClient(transport=transport)
        try:
            with patch("app.agents.llm_client.httpx.AsyncClient", return_value=client):
                result, usage = await call_llm(
                    [{"role": "user", "content": "test"}], [], lambda event: None
                )
            self.assertEqual(
                json.loads(result["tool_calls"][0]["function"]["arguments"]),
                {"order_id": "ORD-DEMO"},
            )
            self.assertEqual(usage["prompt_tokens"], 12)
        finally:
            settings.llm_api_key = original_key


if __name__ == "__main__":
    unittest.main()
