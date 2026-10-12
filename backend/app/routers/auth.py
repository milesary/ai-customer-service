import hashlib

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError

from app import commerce
from app.db import connection
from app.models.schemas import LoginRequest, RegisterRequest
from app.security import (
    bearer,
    create_session,
    current_user,
    hash_password,
    verify_password,
)

router = APIRouter(tags=["身份认证"])


@router.post("/auth/register", status_code=201)
def register(req: RegisterRequest):
    uid = commerce.identifier("USER")
    try:
        with connection(write=True) as conn:
            conn.execute(
                "INSERT INTO users VALUES (?,?,?,?,?)",
                (
                    uid,
                    req.email.lower(),
                    req.name,
                    hash_password(req.password),
                    "customer",
                ),
            )
    except IntegrityError:
        raise HTTPException(409, "此邮箱已注册") from None
    return {
        "token": create_session(uid),
        "user": {
            "id": uid,
            "email": req.email.lower(),
            "name": req.name,
            "role": "customer",
        },
    }


@router.post("/auth/login")
def login(req: LoginRequest):
    with connection() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE email=?", (req.email.lower(),)
        ).fetchone()
    if not row or not verify_password(req.password, row["password_hash"]):
        raise HTTPException(401, "邮箱或密码不正确")
    user = {k: row[k] for k in ("id", "email", "name", "role")}
    return {"token": create_session(row["id"]), "user": user}


@router.get("/auth/me")
def me(user=Depends(current_user)):
    return user


@router.post("/auth/logout")
def logout(user=Depends(current_user), credentials=Depends(bearer)):
    with connection(write=True) as conn:
        conn.execute(
            "DELETE FROM sessions WHERE token_hash=?",
            (hashlib.sha256(credentials.credentials.encode()).hexdigest(),),
        )
    return {"ok": True}
