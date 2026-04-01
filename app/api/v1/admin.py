"""Admin and health routes."""
from __future__ import annotations

from fastapi import APIRouter

from app.core.config import get_settings
from app.repositories.backtests import list_job_logs
from app.workers.jobs import job_status_snapshot


router = APIRouter(prefix="/v1/admin", tags=["admin"])


@router.get("/health")
def health() -> dict:
    settings = get_settings()
    return {
        "app": settings.app_name,
        "status": "ok",
        "openai_configured": bool(settings.openai_api_key),
        "active_jobs": job_status_snapshot(),
    }


@router.get("/jobs")
def jobs() -> dict:
    return {"active": job_status_snapshot(), "log": list_job_logs()}
