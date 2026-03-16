"""User-facing REST API for scheduled/cron tasks.

These endpoints let the dashboard UI create, list, pause, resume, and
delete scheduled tasks.  They authenticate via the standard Firebase
bearer token (same as other user-facing APIs).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.middleware.auth_middleware import AuthenticatedUser, get_current_user
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


# ── Request / Response models ─────────────────────────────────────────


class ScheduledTaskCreate(BaseModel):
    description: str
    schedule: str  # cron expression or NLP like "daily", "every monday"
    action: str = "run_agent_query"
    action_params: dict | None = None
    notify_channel: str = ""
    notify_recipient: str = ""


class ScheduledTaskAction(BaseModel):
    action: str  # "pause" | "resume"


# ── Endpoints ─────────────────────────────────────────────────────────


@router.get("/")
async def list_scheduled_tasks(
    user: AuthenticatedUser = Depends(get_current_user),
):
    """List all scheduled tasks for the authenticated user."""
    from app.services.scheduler_service import get_scheduler_service

    svc = get_scheduler_service()
    tasks = await svc.list_tasks(user.uid)
    return {"tasks": [t.to_summary() for t in tasks]}


@router.post("/")
async def create_scheduled_task(
    body: ScheduledTaskCreate,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Create a new scheduled/cron task."""
    from app.services.scheduler_service import get_scheduler_service

    svc = get_scheduler_service()
    task = await svc.create_task(
        user_id=user.uid,
        description=body.description,
        action=body.action,
        action_params=body.action_params or {},
        schedule=body.schedule,
        notify_rule=None,
    )
    return task.to_summary()


@router.get("/{task_id}")
async def get_scheduled_task(
    task_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Get a single scheduled task by ID."""
    from app.services.scheduler_service import get_scheduler_service

    svc = get_scheduler_service()
    task = await svc.get_task(user.uid, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Scheduled task not found")
    return task.to_summary()


@router.get("/{task_id}/history")
async def get_execution_history(
    task_id: str,
    limit: int = 20,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Return recent execution records for a scheduled task."""
    from google.cloud import firestore as gc_firestore

    from app.services.scheduler_service import get_scheduler_service

    svc = get_scheduler_service()
    # Ensure user owns this task
    task = await svc.get_task(user.uid, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Scheduled task not found")

    # Read from executions subcollection
    coll_ref = (
        svc.db.collection("scheduled_tasks")
        .document(task_id)
        .collection("executions")
    )
    docs = coll_ref.order_by("executed_at", direction=gc_firestore.Query.DESCENDING).limit(limit).stream()
    executions = []
    for doc in docs:
        d = doc.to_dict()
        executions.append({
            "id": doc.id,
            "status": "success" if d.get("success") else "failed",
            "result": d.get("output", ""),
            "error": d.get("output", "") if not d.get("success") else None,
            "started_at": d["executed_at"].isoformat() if d.get("executed_at") else None,
            "run_count": d.get("run_count"),
        })
    return {"executions": executions}


@router.post("/{task_id}/action")
async def scheduled_task_action(
    task_id: str,
    body: ScheduledTaskAction,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Pause or resume a scheduled task."""
    from app.services.scheduler_service import get_scheduler_service

    svc = get_scheduler_service()
    if body.action == "pause":
        result = await svc.pause_task(user.uid, task_id)
    elif body.action == "resume":
        result = await svc.resume_task(user.uid, task_id)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {body.action}")
    if not result:
        raise HTTPException(status_code=404, detail="Scheduled task not found")
    return result.to_summary()


@router.delete("/{task_id}")
async def delete_scheduled_task(
    task_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Delete a scheduled task."""
    from app.services.scheduler_service import get_scheduler_service

    svc = get_scheduler_service()
    ok = await svc.delete_task(user.uid, task_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Scheduled task not found")
    return {"success": True}
