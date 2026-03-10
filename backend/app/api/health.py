"""GET /health — Cloud Run healthcheck."""

import time

from fastapi import APIRouter

from app.config import settings

router = APIRouter()

_start_time = time.monotonic()


@router.get("/health")
async def health_check() -> dict:
    """Return service status, version, environment, and uptime."""
    uptime_seconds = round(time.monotonic() - _start_time, 2)
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "uptime_seconds": uptime_seconds,
    }
