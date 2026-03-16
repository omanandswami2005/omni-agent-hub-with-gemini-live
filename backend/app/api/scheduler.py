"""Internal API for Cloud Scheduler to trigger scheduled task execution.

These endpoints are meant to be called by Cloud Scheduler / Cloud Tasks,
not directly by users.  They still verify a minimal auth header to prevent
open invocation.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from google.cloud import firestore

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
        if not settings.is_production:
            return  # Accept any bearer token in dev
        # Validate OIDC token in production
        token = authorization.removeprefix("Bearer ").strip()
        if await _verify_oidc_token(token):
            return
        raise HTTPException(status_code=401, detail="Invalid OIDC token")
    raise HTTPException(status_code=403, detail="Forbidden — internal endpoint")


async def _verify_oidc_token(token: str) -> bool:
    """Validate a Google OIDC token against the expected service account."""
    try:
        from google.auth.transport import requests as google_requests
        from google.oauth2 import id_token

        claims = id_token.verify_oauth2_token(
            token,
            google_requests.Request(),
            audience=settings.BACKEND_URL or None,
        )
        # Verify the email claim matches our scheduler service account
        email = claims.get("email", "")
        expected_sa = settings.SCHEDULER_SA_EMAIL
        if expected_sa and email != expected_sa:
            logger.warning("oidc_email_mismatch", expected=expected_sa, got=email)
            return False
        return True
    except Exception:
        logger.warning("oidc_token_validation_failed", exc_info=True)
        return False


# ── Endpoints ─────────────────────────────────────────────────────────


@router.post("/run/{task_id}")
async def run_scheduled_task(
    task_id: str,
    request: Request,
    _: None = Depends(_verify_internal_caller),
):
    """Execute a single scheduled task by ID.

    Called by Cloud Scheduler on the task's cron cadence.
    Supports idempotency via ``execution_id`` in the request body.
    """
    from app.services.scheduler_service import get_scheduler_service

    # Extract optional execution_id for idempotency
    execution_id = ""
    try:
        body = await request.json()
        execution_id = body.get("execution_id", "")
    except Exception:
        pass

    svc = get_scheduler_service()
    task = await svc.get_task_by_id(task_id=task_id)

    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    if task.status != "active":
        logger.info("Skipping task %s — status=%s", task_id, task.status)
        return {"status": "skipped", "reason": task.status}

    logger.info("Cloud Scheduler triggered task %s: %s", task_id, task.description)
    result = await svc.execute_task(task_id=task_id, execution_id=execution_id)

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


@router.get("/health")
async def scheduler_health():
    """Health check for the scheduler subsystem.

    Returns basic stats: whether the cron runner is active and task counts.
    Used by monitoring, load balancer health checks, and Cloud Run probes.
    """
    from app.services.scheduler_service import get_scheduler_service

    svc = get_scheduler_service()
    try:
        active_count = 0
        failed_count = 0
        for doc in svc.db.collection("scheduled_tasks").where(
            filter=firestore.FieldFilter("status", "in", ["active", "failed"])
        ).stream():
            data = doc.to_dict()
            if data.get("status") == "active":
                active_count += 1
            else:
                failed_count += 1
        return {
            "status": "healthy",
            "cron_runner_active": svc._cron_running,
            "active_tasks": active_count,
            "failed_tasks": failed_count,
        }
    except Exception as exc:
        return {"status": "degraded", "error": str(exc)}
