"""FastAPI entrypoint for STRATIX AI."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import admin, auth, backtests, catalog, strategies, users
from app.core.config import get_settings
from app.core.database import init_db
from app.repositories.users import ensure_demo_user


settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    init_db()
    ensure_demo_user(settings.default_demo_user_email, settings.default_demo_user_password)


@app.get("/")
def root() -> dict:
    return {
        "name": settings.app_name,
        "status": "ok",
        "docs": "/docs",
        "openai_model_primary": settings.openai_model_primary,
    }


app.include_router(auth.router)
app.include_router(users.router)
app.include_router(catalog.router)
app.include_router(strategies.router)
app.include_router(backtests.router)
app.include_router(admin.router)
