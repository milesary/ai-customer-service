import hashlib
import hmac
import secrets
import time
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from app.config import settings
from app.db import connection

bearer = HTTPBearer(auto_error=False)


def hash_password(password):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), 260_000
    ).hex()
    return f"{salt}${digest}"


def verify_password(password, encoded):
    salt, digest = encoded.split("$", 1)
    actual = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), 260_000
    ).hex()
    return hmac.compare_digest(actual, digest)


def create_session(user_id):
    token = secrets.token_urlsafe(32)
    with connection(write=True) as conn:
        conn.execute("DELETE FROM sessions WHERE expires_at < ?", (time.time(),))
        conn.execute(
            "INSERT INTO sessions VALUES (?,?,?)",
            (
                hashlib.sha256(token.encode()).hexdigest(),
                user_id,
                time.time() + settings.session_hours * 3600,
            ),
        )
    return token


def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if not credentials:
        raise HTTPException(401, "请先登录")
    with connection() as conn:
        user = conn.execute(
            """SELECT u.id,u.email,u.name,u.role FROM sessions s JOIN users u ON u.id=s.user_id
                              WHERE s.token_hash=? AND s.expires_at>?""",
            (hashlib.sha256(credentials.credentials.encode()).hexdigest(), time.time()),
        ).fetchone()
    if not user:
        raise HTTPException(401, "登录已过期，请重新登录")
    return dict(user)


def admin_user(user=Depends(current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "需要店铺管理员权限")
    return user
