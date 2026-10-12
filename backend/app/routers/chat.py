import asyncio

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.agents.tool_agent import confirm_action
from app.chat import event_stream, prepare_conversation, run_chat
from app.models.schemas import ChatRequest, ConfirmRequest
from app.security import current_user

router = APIRouter(tags=["AI 对话"])


@router.post("/chat")
async def chat(req: ChatRequest, user=Depends(current_user)):
    cid, history = await asyncio.to_thread(
        prepare_conversation, user["id"], req.conversation_id, req.message
    )
    result = await run_chat(user["id"], cid, req.message, history, lambda event: None)
    if "error" in result:
        raise HTTPException(502, result["error"])
    return result


@router.post("/chat/stream")
async def chat_stream(req: ChatRequest, user=Depends(current_user)):
    cid, history = await asyncio.to_thread(
        prepare_conversation, user["id"], req.conversation_id, req.message
    )
    return StreamingResponse(
        event_stream(user["id"], cid, req.message, history),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/actions/{action_id}/confirm")
def confirm(action_id: str, req: ConfirmRequest, user=Depends(current_user)):
    return confirm_action(action_id, user["id"], req.confirmed)
