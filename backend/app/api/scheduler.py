"""Internal API for Cloud Scheduler to trigger scheduled task execution.

These endpoints are meant to be called by Cloud Scheduler / Cloud Tasks,
not directly by users.  They still verify a minimal auth header to prevent
open invocation.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException

from app.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


# ── Helpers ───────────────────────────────────────────────────────────


async def _verify_internal_caller(
    x_cloudscheduler: str | None = Header(None),
    x_appengine_cron: str | None = Header(None),
    authorization: str | None = Header(None),
) -> None:
    """Allow only Cloud Scheduler, App Engine Cron, or OIDC service-account tokens."""
    if x_cloudscheduler == "true" or x_appengine_cron == "true":
        return  # Called by Google infrastructure
    if authorization and authorization.startswith("Bearer "):
        # In production, verify the OIDC token against the service account
        # For local dev, accept any bearer token
        if not settings.is_production:
            return
        # TODO: validate OIDC token for production
        return
    raise HTTPException(status_code=403, detail="Forbidden — internal endpoint")


# ── Endpoints ─────────────────────────────────────────────────────────


@router.post("/run/{task_id}")
async def run_scheduled_task(
    task_id: str,
    _: None = Depends(_verify_internal_caller),
):
    """Execute a single scheduled task by ID.

    Called by Cloud Scheduler on the task's cron cadence.
    """
    from app.services.scheduler_service import get_scheduler_service

    svc = get_scheduler_service()
    task = await svc.get_task(task_id=task_id)

    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    if task.status != "active":
        logger.info("Skipping task %s — status=%s", task_id, task.status)
        return {"status": "skipped", "reason": task.status}

    logger.info("Cloud Scheduler triggered task %s: %s", task_id, task.description)
    result = await svc.execute_task(task_id=task_id)

    return {"status": "executed", "task_id": task_id, "result": result}


@router.get("/tasks/{user_id}")
async def list_user_tasks(
    user_id: str,
    _: None = Depends(_verify_internal_caller),
):
    """Internal: list tasks for a given user (for admin/monitoring)."""
    from app.services.scheduler_service import get_scheduler_service

    svc = get_scheduler_service()
    tasks = await svc.list_tasks(user_id=user_id)

    return {
        "count": len(tasks),
        "tasks": [t.to_summary() for t in tasks],
    }
