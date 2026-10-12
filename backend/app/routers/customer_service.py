from fastapi import APIRouter, Depends, HTTPException

from app import commerce, service
from app.db import connection
from app.models.schemas import HandoffRequest, HumanReply, TicketRequest
from app.security import current_user

router = APIRouter(tags=["客户服务"])


@router.get("/tickets")
def tickets(user=Depends(current_user)):
    return service.list_tickets(user["id"])


@router.post("/tickets", status_code=201)
def ticket(req: TicketRequest, user=Depends(current_user)):
    with connection(write=True) as conn:
        row = commerce.create_ticket(user["id"], req.order_id, req.reason, conn)
        return service.attach_ticket(conn, row, user["id"], None)


@router.get("/service/context")
def service_context(user=Depends(current_user)):
    return service.context(user["id"])


@router.post("/conversations/{conversation_id}/handoff")
def handoff(conversation_id: str, req: HandoffRequest, user=Depends(current_user)):
    return service.handoff(user["id"], conversation_id, req.reason, req.order_id)


@router.post("/conversations/{conversation_id}/messages")
def customer_message(conversation_id: str, req: HumanReply, user=Depends(current_user)):
    if not req.content.strip():
        raise HTTPException(422, "消息不能为空")
    with connection(write=True) as conn:
        service.get_conversation(conn, conversation_id, user["id"])
        ticket = service.active_handoff(conn, conversation_id)
        if not ticket:
            raise HTTPException(409, "此会话未转人工，请使用 AI 对话入口")
        conn.execute(
            "INSERT INTO messages(conversation_id,role,content,metadata,created_at) VALUES (?,?,?,?,?)",
            (conversation_id, "user", req.content, "{}", commerce.now()),
        )
        service.add_event(
            conn, ticket["id"], user["id"], "customer_message", req.content
        )
    return {"ok": True}


@router.get("/conversations")
def conversations(user=Depends(current_user)):
    with connection() as conn:
        return service.list_conversations(conn, user["id"])


@router.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: str, user=Depends(current_user)):
    return service.delete_conversation(user["id"], conversation_id)


@router.get("/conversations/{conversation_id}")
def conversation(conversation_id: str, user=Depends(current_user)):
    return service.conversation_history(conversation_id, user["id"])
