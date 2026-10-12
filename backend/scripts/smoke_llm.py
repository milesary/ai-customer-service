"""Opt-in live model check using only fictional seed data and a temporary database."""

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import settings
from app.db import initialize
from app.chat import prepare_conversation, run_chat


async def main():
    if not settings.llm_api_key:
        raise SystemExit("Configure LLM_API_KEY in backend/.env first.")
    original = (settings.database_url, settings.ai_mode, settings.seed_demo)
    records = []
    try:
        with tempfile.TemporaryDirectory() as temp:
            settings.database_url = "sqlite:///" + os.path.join(
                temp, "live-check.db"
            ).replace("\\", "/")
            settings.ai_mode = "llm"
            settings.seed_demo = True
            initialize()
            for question, expected in [
                ("查询 ORD-DEMO 的订单状态", "query_orders"),
                ("把 P001 加入购物车", "propose_add_to_cart"),
            ]:
                cid, history = prepare_conversation("demo-user", None, question)
                events = []
                result = await run_chat(
                    "demo-user",
                    cid,
                    question,
                    history,
                    lambda event: events.append(event["event"]),
                )
                ok = "error" not in result and any(
                    t["node"] == expected and t.get("ok")
                    for t in result.get("trace", [])
                )
                if expected.startswith("propose_"):
                    ok = (
                        ok
                        and bool(result.get("actions"))
                        and all(a["status"] == "pending" for a in result["actions"])
                    )
                records.append(
                    {
                        "expected_tool": expected,
                        "passed": ok,
                        "llm_calls": result.get("llm_calls", 0),
                        "tool_calls": result.get("tool_calls", 0),
                        "token_events": events.count("token"),
                        "trace": result.get("trace", []),
                    }
                )
    finally:
        from app.db import engine_for

        engine_for(settings.database_url).dispose()
        settings.database_url, settings.ai_mode, settings.seed_demo = original
    print(json.dumps(records, indent=2))
    if not all(r["passed"] for r in records):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
