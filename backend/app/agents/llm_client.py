"""Asynchronous OpenAI-compatible SSE client, including fragmented tool calls."""

import asyncio
import json
import httpx
from app.config import settings


async def call_llm(messages, tools, emit):
    if not settings.llm_api_key:
        raise RuntimeError("LLM 模式需要配置 LLM_API_KEY")
    body = {
        "model": settings.llm_model,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 1200,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if tools:
        body.update(tools=tools, tool_choice="auto")
    result = {"role": "assistant", "content": ""}
    calls = {}
    usage = {}
    # Retry only before any response is emitted; never replay partially executed output.
    for attempt in range(2):
        received = False
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(45, connect=10)
            ) as client:
                async with client.stream(
                    "POST",
                    settings.llm_base_url.rstrip("/") + "/chat/completions",
                    headers={"Authorization": f"Bearer {settings.llm_api_key}"},
                    json=body,
                ) as response:
                    if response.status_code >= 400:
                        if (
                            response.status_code in (429, 502, 503, 504)
                            and attempt == 0
                        ):
                            await asyncio.sleep(0.5)
                            continue
                        raise RuntimeError(
                            f"模型服务返回 HTTP {response.status_code}，请检查模型配置"
                        )
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        raw = line[5:].strip()
                        if raw == "[DONE]":
                            break
                        if not raw:
                            continue
                        received = True
                        data = json.loads(raw)
                        if data.get("error"):
                            raise RuntimeError("模型服务报告流式请求失败")
                        if data.get("usage"):
                            usage = data["usage"]
                        for choice in data.get("choices", []):
                            delta = choice.get("delta", {})
                            if delta.get("content"):
                                result["content"] += delta["content"]
                                emit(
                                    {
                                        "event": "token",
                                        "data": {"content": delta["content"]},
                                    }
                                )
                            for tc in delta.get("tool_calls", []):
                                item = calls.setdefault(
                                    tc["index"],
                                    {
                                        "id": "",
                                        "type": "function",
                                        "function": {"name": "", "arguments": ""},
                                    },
                                )
                                if tc.get("id"):
                                    item["id"] += tc["id"]
                                for key in ("name", "arguments"):
                                    item["function"][key] += tc.get("function", {}).get(
                                        key, ""
                                    )
            if calls:
                result["tool_calls"] = [calls[k] for k in sorted(calls)]
                result["content"] = result["content"] or None
            if not calls and not result["content"]:
                raise RuntimeError("模型返回了空响应")
            return result, usage
        except (httpx.TimeoutException, httpx.ConnectError):
            if received or attempt:
                raise RuntimeError("模型请求超时或连接失败，请稍后重试") from None
            await asyncio.sleep(0.5)
    raise RuntimeError("模型服务暂不可用")
