"""FastAPI entrypoint for STRATIX AI."""
from __future__ import annotations

from contextlib import asynccontextmanager
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import admin, auth, backtests, catalog, strategies, users
from app.core.config import get_settings
from app.core.database import init_db
from app.core.logging import get_logger
from app.repositories.users import ensure_demo_user


settings = get_settings()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    ensure_demo_user(settings.default_demo_user_email, settings.default_demo_user_password)
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid4())
    request.state.request_id = request_id
    started_at = perf_counter()
    response = await call_next(request)
    duration_ms = (perf_counter() - started_at) * 1000
    response.headers["x-request-id"] = request_id
    logger.info("%s %s status=%s duration_ms=%.2f", request.method, request.url.path, response.status_code, duration_ms)
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    request_id = getattr(request.state, "request_id", str(uuid4()))
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail, "request_id": request_id})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    request_id = getattr(request.state, "request_id", str(uuid4()))
    logger.warning("request_validation_failed request_id=%s path=%s errors=%s", request_id, request.url.path, exc.errors())
    return JSONResponse(status_code=422, content={"detail": "Invalid request payload", "errors": exc.errors(), "request_id": request_id})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", str(uuid4()))
    logger.error(
        "unhandled_exception request_id=%s path=%s",
        request_id,
        request.url.path,
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return JSONResponse(status_code=500, content={"detail": "Internal server error", "request_id": request_id})


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
