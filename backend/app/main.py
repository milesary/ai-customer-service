"""Application setup, lifecycle and health endpoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import initialize
from app.routers import admin, auth, chat, customer_service, shop


@asynccontextmanager
async def lifespan(app):
    initialize()
    yield


app = FastAPI(title="购物 AI 电商", version="2.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "ai_mode": settings.ai_mode,
        "payment_mode": "simulated",
        "database": "mysql"
        if settings.database_url.startswith("mysql")
        else "sqlite-test",
    }


for router in (
    auth.router,
    shop.router,
    customer_service.router,
    chat.router,
    admin.router,
):
    app.include_router(router, prefix="/api")
