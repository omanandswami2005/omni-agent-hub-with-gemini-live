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
    return task.to_dict()


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


@router.get("/{task_id}/history")
async def get_execution_history(
    task_id: str,
    limit: int = 20,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Get execution history for a scheduled task."""
    from google.cloud import firestore as fs

    from app.services.scheduler_service import get_scheduler_service

    svc = get_scheduler_service()
    task = await svc.get_task(user.uid, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Scheduled task not found")

    # Read from the executions subcollection
    docs = (
        svc.db.collection("scheduled_tasks")
        .document(task_id)
        .collection("executions")
        .order_by("started_at", direction=fs.Query.DESCENDING)
        .limit(limit)
        .stream()
    )
    history = []
    for doc in docs:
        data = doc.to_dict()
        history.append({
            "id": doc.id,
            "started_at": data.get("started_at").isoformat() if data.get("started_at") else None,
            "completed_at": data.get("completed_at").isoformat() if data.get("completed_at") else None,
            "status": data.get("status", "unknown"),
            "result": (data.get("result") or "")[:500],
            "error": data.get("error", ""),
        })
    return {"task_id": task_id, "executions": history}
