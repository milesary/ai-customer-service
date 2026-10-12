import asyncio
import json
import logging
import time
from fastapi import HTTPException
from app import commerce
from app.config import settings
from app.db import connection
from app.agents.graph import agent_graph
from app.service import active_handoff, get_conversation

logger = logging.getLogger(__name__)


def prepare_conversation(user_id, conversation_id, message):
    with connection(write=True) as conn:
        if conversation_id:
            get_conversation(conn, conversation_id, user_id)
            if active_handoff(conn, conversation_id):
                raise HTTPException(
                    409, "当前会话已转人工，处理完成后可继续使用 AI 客服"
                )
        else:
            conversation_id = commerce.identifier("CHAT")
            conn.execute(
                "INSERT INTO conversations VALUES (?,?,?,?,0)",
                (conversation_id, user_id, message[:30], commerce.now()),
            )
        updated = conn.execute(
            "UPDATE conversations SET busy_until=? WHERE id=? AND busy_until<?",
            (time.time() + 240, conversation_id, time.time()),
        )
        if updated.rowcount != 1:
            raise HTTPException(409, "此会话正在处理上一条消息")
        history = [
            dict(r)
            for r in conn.execute(
                "SELECT role,content,metadata FROM messages WHERE conversation_id=? ORDER BY id DESC LIMIT 16",
                (conversation_id,),
            )
        ][::-1]
        conn.execute(
            "INSERT INTO messages(conversation_id,role,content,metadata,created_at) VALUES (?,?,?,?,?)",
            (conversation_id, "user", message, "{}", commerce.now()),
        )
    return conversation_id, history


async def run_chat(user_id, conversation_id, message, history, emit):
    start = time.perf_counter()
    first_response_ms = None

    def measured_emit(event):
        nonlocal first_response_ms
        if (
            event["event"] == "token"
            and event["data"].get("content")
            and first_response_ms is None
        ):
            first_response_ms = round((time.perf_counter() - start) * 1000)
        emit(event)

    run_id = commerce.identifier("RUN")
    state = {
        "user_id": user_id,
        "conversation_id": conversation_id,
        "user_message": message,
        "history": history,
        "emit": measured_emit,
    }
    # Only the latest server-authored reply can carry an unfinished offline product draft.
    previous = next((m for m in reversed(history) if m["role"] == "assistant"), None)
    state["product_draft"] = (
        json.loads(previous.get("metadata", "{}")).get("product_draft")
        if previous
        else None
    )
    result = dict(state)
    status = "completed"
    emit(
        {
            "event": "conversation",
            "data": {"id": conversation_id, "mode": settings.ai_mode},
        }
    )
    try:
        async with asyncio.timeout(180):
            async for update in agent_graph.astream(
                state, stream_mode="updates", config={"recursion_limit": 12}
            ):
                for value in update.values():
                    result.update(value)
        elapsed = round((time.perf_counter() - start) * 1000)
        reply = result.get("final_response", "")
        metadata = {
            "sources": result.get("sources", []),
            "actions": result.get("actions", []),
            "products": result.get("products", []),
            "trace": result.get("trace", []),
            "elapsed_ms": elapsed,
            "llm_calls": result.get("llm_calls", 0),
            "tool_calls": result.get("tool_calls", 0),
            "run_id": run_id,
            "mode": settings.ai_mode,
            "first_response_ms": first_response_ms,
        }
        if result.get("product_draft") is not None:
            metadata["product_draft"] = result["product_draft"]
        with connection(write=True) as conn:
            conn.execute(
                "INSERT INTO messages(conversation_id,role,content,metadata,created_at) VALUES (?,?,?,?,?)",
                (
                    conversation_id,
                    "assistant",
                    reply,
                    json.dumps(metadata, ensure_ascii=False),
                    commerce.now(),
                ),
            )
        emit({"event": "message", "data": {"content": reply, **metadata}})
        return {"reply": reply, "conversation_id": conversation_id, **metadata}
    except asyncio.CancelledError:
        status = "cancelled"
        raise
    except Exception:
        status = "error"
        logger.exception("AI run failed: %s", run_id)
        emit(
            {
                "event": "error",
                "data": {
                    "message": "本次处理失败，请检查模型配置或稍后重试。",
                    "run_id": run_id,
                },
            }
        )
        return {
            "error": "本次处理失败",
            "run_id": run_id,
            "conversation_id": conversation_id,
        }
    finally:
        elapsed = round((time.perf_counter() - start) * 1000)
        with connection(write=True) as conn:
            conn.execute(
                "UPDATE conversations SET busy_until=0 WHERE id=?", (conversation_id,)
            )
            conn.execute(
                "INSERT INTO ai_runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    run_id,
                    user_id,
                    conversation_id,
                    settings.ai_mode,
                    elapsed,
                    result.get("llm_calls", 0),
                    result.get("tool_calls", 0),
                    result.get("prompt_tokens", 0),
                    result.get("completion_tokens", 0),
                    status,
                    json.dumps(result.get("trace", [])),
                    commerce.now(),
                ),
            )
            conn.execute(
                "INSERT INTO run_timings VALUES (?,?)", (run_id, first_response_ms)
            )
        emit({"event": "done", "data": {"run_id": run_id, "status": status}})


async def event_stream(user_id, conversation_id, message, history):
    queue = asyncio.Queue()
    task = asyncio.create_task(
        run_chat(user_id, conversation_id, message, history, queue.put_nowait)
    )
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=15)
            except asyncio.TimeoutError:
                if task.done():
                    await task
                    break
                yield ": keepalive\n\n"
                continue
            yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
            if event["event"] == "done":
                break
        await task
    finally:
        if not task.done():
            task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
