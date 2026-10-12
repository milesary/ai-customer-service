"""Business contract checks, also runnable against MYSQL_TEST_URL."""

from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
from tests import test_shop
from app.db import connection
from app.agents.tool_agent import confirm_action


class ServiceTests(test_shop.ShopTests):
    def admin(self):
        client = TestClient(self.client.app)
        auth = client.post(
            "/api/auth/login",
            json={"email": "admin@shop.local", "password": "Demo12345!"},
        ).json()
        client.headers["Authorization"] = "Bearer " + auth["token"]
        return client

    def transfer(self, order_id=None):
        cid = self.new_conversation()
        result = self.client.post(
            f"/api/conversations/{cid}/handoff",
            json={"reason": "耳机故障，需要人工确认换货方案", "order_id": order_id},
        )
        self.assertEqual(result.status_code, 200, result.text)
        return cid, result.json()

    def test_handoff_human_reply_completion_and_ai_resume(self):
        cid, ticket = self.transfer("ORD-DEMO")
        duplicate = self.client.post(
            f"/api/conversations/{cid}/handoff",
            json={"reason": "重复转人工", "order_id": "ORD-DEMO"},
        ).json()
        self.assertEqual(ticket["id"], duplicate["id"])
        self.assertIn("客户：", ticket["summary"])
        self.assertEqual(
            self.client.post(
                "/api/chat", json={"message": "继续问", "conversation_id": cid}
            ).status_code,
            409,
        )
        self.assertEqual(
            self.client.post(
                f"/api/conversations/{cid}/messages",
                json={"content": "我已经重置耳机，仍无法连接"},
            ).status_code,
            200,
        )
        admin = self.admin()
        self.assertEqual(
            admin.post(
                f"/api/admin/tickets/{ticket['id']}/reply", json={"content": "先检查"}
            ).status_code,
            409,
        )
        self.assertEqual(
            admin.put(
                f"/api/admin/tickets/{ticket['id']}",
                json={"status": "processing", "resolution": ""},
            ).status_code,
            200,
        )
        self.assertEqual(
            admin.post(
                f"/api/admin/tickets/{ticket['id']}/reply",
                json={"content": "已查看订单，正在核实换货条件"},
            ).status_code,
            200,
        )
        messages = self.client.get("/api/conversations/" + cid).json()["messages"]
        self.assertEqual(messages[-1]["author"], "human")
        self.assertEqual(
            admin.put(
                f"/api/admin/tickets/{ticket['id']}",
                json={"status": "resolved", "resolution": "已安排模拟换货"},
            ).status_code,
            200,
        )
        self.assertIsNone(
            self.client.get("/api/conversations/" + cid).json()["handoff"]
        )
        resumed = self.client.post(
            "/api/chat",
            json={"message": "查询我的售后处理进度", "conversation_id": cid},
        )
        self.assertEqual(resumed.status_code, 200, resumed.text)
        self.assertIn("已安排模拟换货", resumed.json()["reply"])
        self.assertEqual(
            admin.put(
                f"/api/admin/tickets/{ticket['id']}",
                json={"status": "processing", "resolution": ""},
            ).status_code,
            409,
        )

    def test_customer_context_and_admin_permissions(self):
        other, _ = self.register_other()
        self.assertEqual(other.get("/api/service/context").json()["orders"], [])
        for path in ("/api/admin/customers", "/api/admin/customers/demo-user"):
            self.assertEqual(other.get(path).status_code, 403)
        cid, ticket = self.transfer()
        self.assertEqual(
            other.post(
                f"/api/conversations/{cid}/handoff", json={"reason": "非法转人工"}
            ).status_code,
            404,
        )
        self.assertEqual(
            other.post(
                f"/api/conversations/{cid}/messages", json={"content": "非法消息"}
            ).status_code,
            404,
        )
        self.assertEqual(
            other.post(
                f"/api/admin/tickets/{ticket['id']}/reply", json={"content": "非法回复"}
            ).status_code,
            403,
        )
        context = self.admin().get("/api/admin/customers/demo-user").json()
        self.assertNotIn("password_hash", context["customer"])
        self.assertEqual(context["tickets"][0]["conversation_id"], cid)

    def test_handoff_rejects_pending_writes_and_busy_conversation(self):
        response = self.client.post(
            "/api/chat", json={"message": "把 P001 加入购物车"}
        ).json()
        cid = response["conversation_id"]
        self.client.post(
            f"/api/conversations/{cid}/handoff", json={"reason": "需要人工确认商品"}
        )
        result = self.client.post(
            f"/api/actions/{response['actions'][0]['id']}/confirm",
            json={"confirmed": True},
        )
        self.assertEqual(result.json()["status"], "rejected")
        self.assertEqual(self.client.get("/api/cart").json()["items"], [])
        cid = self.new_conversation()
        with connection(write=True) as conn:
            conn.execute(
                "UPDATE conversations SET busy_until=? WHERE id=?", (9999999999, cid)
            )
        self.assertEqual(
            self.client.post(
                f"/api/conversations/{cid}/handoff", json={"reason": "正在生成时接管"}
            ).status_code,
            409,
        )

    def test_model_handoff_confirmation_and_ticket_scope(self):
        response = self.client.post("/api/chat", json={"message": "帮我转人工"}).json()
        self.assertEqual(response["actions"][0]["kind"], "handoff")
        self.assertEqual(self.client.get("/api/tickets").json(), [])
        result = self.client.post(
            f"/api/actions/{response['actions'][0]['id']}/confirm",
            json={"confirmed": True},
        )
        self.assertEqual(result.json()["status"], "confirmed")
        other, _ = self.register_other()
        self.assertEqual(
            other.post("/api/chat", json={"message": "查询我的售后处理进度"}).json()[
                "reply"
            ],
            "你目前没有售后或转人工工单。",
        )

    def test_fulfillment_restocks_and_state_constraints(self):
        admin = self.admin()
        result = admin.post(
            "/api/admin/orders/ORD-DEMO/fulfillment",
            json={"stage": "delivered", "detail": "模拟包裹已送达收货点"},
        )
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(
            admin.post(
                "/api/admin/orders/ORD-DEMO/fulfillment",
                json={"stage": "transit", "detail": "回退到运输中"},
            ).status_code,
            409,
        )
        response = self.client.post(
            "/api/chat", json={"message": "查询 ORD-DEMO 的物流"}
        ).json()
        self.assertIn("已送达", response["reply"])
        self.assertEqual(
            admin.put(
                "/api/admin/products/P001/stock",
                json={"stock": 0, "restock_at": "2026-13-32"},
            ).status_code,
            422,
        )
        self.assertEqual(
            admin.put(
                "/api/admin/products/P001/stock",
                json={"stock": 0, "restock_at": "2026-11-01"},
            ).status_code,
            200,
        )
        response = self.client.post(
            "/api/chat", json={"message": "耳机什么时候补货"}
        ).json()
        self.assertIn("2026-11-01", response["reply"])
        other, _ = self.register_other()
        self.assertEqual(
            other.post(
                "/api/admin/orders/ORD-DEMO/fulfillment",
                json={"stage": "delivered", "detail": "非法更新节点"},
            ).status_code,
            403,
        )

    def test_after_sale_linked_to_conversation(self):
        response = self.client.post(
            "/api/chat", json={"message": "订单 ORD-DEMO 的耳机无法连接，帮我申请售后"}
        ).json()
        action = response["actions"][0]
        self.client.post(
            f"/api/actions/{action['id']}/confirm", json={"confirmed": True}
        )
        ticket = self.client.get("/api/tickets").json()[0]
        self.assertEqual(ticket["conversation_id"], response["conversation_id"])
        self.assertIn("耳机无法连接", ticket["summary"])
        self.assertTrue(ticket["due_at"])

    def test_concurrent_confirmation_is_idempotent(self):
        response = self.client.post(
            "/api/chat", json={"message": "把 P001 加入购物车"}
        ).json()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(
                pool.map(
                    lambda _: confirm_action(
                        response["actions"][0]["id"], "demo-user", True
                    ),
                    range(2),
                )
            )
        self.assertEqual([r["status"] for r in results], ["confirmed", "confirmed"])
        self.assertEqual(self.client.get("/api/cart").json()["items"][0]["quantity"], 1)

    def test_run_timing_and_trace_recorded(self):
        result = self.client.post("/api/chat", json={"message": "查询我的订单"}).json()
        self.assertIsNotNone(result["first_response_ms"])
        self.assertLessEqual(result["first_response_ms"], result["elapsed_ms"])
        runs = self.admin().get("/api/admin/ai-runs").json()
        self.assertEqual(runs[0]["first_response_ms"], result["first_response_ms"])
        self.assertIn("elapsed_ms", result["trace"][2])

    def test_delete_conversation_hides_history_and_rejects_pending_actions(self):
        result = self.client.post(
            "/api/chat", json={"message": "把 P001 加入购物车"}
        ).json()
        cid = result["conversation_id"]
        action = result["actions"][0]["id"]
        orders = self.client.get("/api/orders").json()
        runs = self.admin().get("/api/admin/ai-runs").json()
        self.assertEqual(
            self.client.delete("/api/conversations/" + cid).status_code, 200
        )
        self.assertNotIn(
            cid, [c["id"] for c in self.client.get("/api/conversations").json()]
        )
        self.assertNotIn(
            cid,
            [
                c["id"]
                for c in self.client.get("/api/service/context").json()["conversations"]
            ],
        )
        self.assertEqual(self.client.get("/api/conversations/" + cid).status_code, 404)
        self.assertEqual(
            self.client.post(
                "/api/chat", json={"message": "继续", "conversation_id": cid}
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                f"/api/conversations/{cid}/handoff", json={"reason": "已删除会话转人工"}
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                f"/api/conversations/{cid}/messages", json={"content": "旧页面消息"}
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                f"/api/actions/{action}/confirm", json={"confirmed": True}
            ).json()["status"],
            "rejected",
        )
        self.assertEqual(self.client.get("/api/cart").json()["items"], [])
        self.assertEqual(self.client.get("/api/orders").json(), orders)
        self.assertEqual(self.admin().get("/api/admin/ai-runs").json(), runs)
        self.assertEqual(
            self.admin().get("/api/admin/conversations/" + cid).status_code, 200
        )

    def test_delete_conversation_requires_ownership_and_authentication(self):
        cid = self.new_conversation()
        other, _ = self.register_other()
        self.assertEqual(
            TestClient(self.client.app).delete("/api/conversations/" + cid).status_code,
            401,
        )
        self.assertEqual(other.delete("/api/conversations/" + cid).status_code, 404)
        self.assertEqual(
            self.admin().delete("/api/conversations/" + cid).status_code, 404
        )
        self.assertEqual(
            self.client.delete("/api/conversations/missing").status_code, 404
        )
        self.assertEqual(self.client.get("/api/conversations/" + cid).status_code, 200)

    def test_delete_conversation_blocks_busy_and_active_handoff(self):
        cid = self.new_conversation()
        with connection(write=True) as conn:
            conn.execute(
                "UPDATE conversations SET busy_until=? WHERE id=?", (9999999999, cid)
            )
        self.assertEqual(
            self.client.delete("/api/conversations/" + cid).status_code, 409
        )
        with connection(write=True) as conn:
            conn.execute("UPDATE conversations SET busy_until=0 WHERE id=?", (cid,))
        transferred = self.client.post(
            f"/api/conversations/{cid}/handoff",
            json={"reason": "删除保护测试，需要人工处理"},
        ).json()
        self.assertEqual(
            self.client.delete("/api/conversations/" + cid).status_code, 409
        )
        agent = self.admin()
        agent.put(
            f"/api/admin/tickets/{transferred['id']}",
            json={"status": "processing", "resolution": ""},
        )
        agent.put(
            f"/api/admin/tickets/{transferred['id']}",
            json={"status": "resolved", "resolution": "处理完成"},
        )
        tickets = self.client.get("/api/tickets").json()
        self.assertEqual(
            self.client.delete("/api/conversations/" + cid).status_code, 200
        )
        self.assertEqual(self.client.get("/api/tickets").json(), tickets)
        self.assertEqual(agent.get("/api/admin/conversations/" + cid).status_code, 200)


def load_tests(loader, tests, pattern):
    # Reuse fixtures while running the original commerce tests only in test_shop.
    import unittest

    return unittest.TestSuite(
        ServiceTests(name) for name in ServiceTests.__dict__ if name.startswith("test_")
    )
