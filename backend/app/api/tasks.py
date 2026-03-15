"""REST API for Planned Tasks and E2B Desktop management."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.middleware.auth_middleware import AuthenticatedUser, get_current_user
from app.models.planned_task import TaskActionRequest, TaskCreateRequest, TaskEditRequest, TaskInputResponse
from app.services.task_orchestrator import get_task_orchestrator
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()

# ── Task CRUD ─────────────────────────────────────────────────────────


@router.get("/")
async def list_tasks(user: AuthenticatedUser = Depends(get_current_user)):  # noqa: B008
    """List all planned tasks for the authenticated user."""
    orchestrator = get_task_orchestrator()
    tasks = await orchestrator.list_tasks(user.uid)
    return {
        "tasks": [
            {
                "id": t.id,
                "title": t.title,
                "description": t.description[:200],
                "status": t.status.value,
                "step_count": len(t.steps),
                "progress": round(t.progress * 100, 1),
                "created_at": t.created_at.isoformat() if t.created_at else "",
                "updated_at": t.updated_at.isoformat() if t.updated_at else "",
            }
            for t in tasks
        ]
    }


@router.post("/")
async def create_task(
    body: TaskCreateRequest,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
):
    """Create a new planned task, decompose it into steps."""
    orchestrator = get_task_orchestrator()
    task = await orchestrator.create_task(user.uid, body.description)
    task = await orchestrator.plan_task(task)

    if body.auto_execute and task.steps:
        await orchestrator.start_execution(task)

    return {
        "id": task.id,
        "title": task.title,
        "status": task.status.value,
        "steps": [
            {
                "id": s.id,
                "title": s.title,
                "description": s.description,
                "persona_id": s.persona_id,
                "status": s.status.value,
            }
            for s in task.steps
        ],
    }


@router.get("/{task_id}")
async def get_task(task_id: str, user: AuthenticatedUser = Depends(get_current_user)):  # noqa: B008
    """Get full task detail with steps and outputs."""
    orchestrator = get_task_orchestrator()
    task = await orchestrator.get_task(user.uid, task_id)
    if not task:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Task not found")
    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "status": task.status.value,
        "progress": round(task.progress * 100, 1),
        "result_summary": task.result_summary,
        "e2b_desktop_id": task.e2b_desktop_id,
        "created_at": task.created_at.isoformat() if task.created_at else "",
        "updated_at": task.updated_at.isoformat() if task.updated_at else "",
        "steps": [
            {
                "id": s.id,
                "title": s.title,
                "description": s.description,
                "instruction": s.instruction,
                "persona_id": s.persona_id,
                "status": s.status.value,
                "output": s.output,
                "error": s.error,
                "depends_on": s.depends_on,
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "completed_at": s.completed_at.isoformat() if s.completed_at else None,
            }
            for s in task.steps
        ],
    }


@router.post("/{task_id}/execute")
async def execute_task(task_id: str, user: AuthenticatedUser = Depends(get_current_user)):  # noqa: B008
    """Start executing a planned task (after user confirms)."""
    orchestrator = get_task_orchestrator()
    task = await orchestrator.get_task(user.uid, task_id)
    if not task:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Task not found")
    await orchestrator.start_execution(task)
    return {"status": "running", "message": f"Task '{task.title}' execution started."}


@router.post("/{task_id}/action")
async def task_action(
    task_id: str,
    body: TaskActionRequest,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
):
    """Pause, resume, or cancel a task."""
    orchestrator = get_task_orchestrator()
    if body.action == "pause":
        ok = await orchestrator.pause_task(user.uid, task_id)
    elif body.action == "resume":
        ok = await orchestrator.resume_task(user.uid, task_id)
    elif body.action == "cancel":
        ok = await orchestrator.cancel_task(user.uid, task_id)
    else:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail=f"Unknown action: {body.action}")

    return {"success": ok, "action": body.action}


@router.delete("/{task_id}")
async def delete_task(task_id: str, user: AuthenticatedUser = Depends(get_current_user)):  # noqa: B008
    """Delete a planned task. Running tasks are cancelled first."""
    orchestrator = get_task_orchestrator()
    ok = await orchestrator.delete_task(user.uid, task_id)
    if not ok:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Task not found")
    return {"success": True}


@router.put("/{task_id}")
async def edit_task(
    task_id: str,
    body: TaskEditRequest,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
):
    """Edit task description and re-plan it. Running tasks cannot be edited."""
    orchestrator = get_task_orchestrator()
    task = await orchestrator.edit_task(user.uid, task_id, body.description)
    if not task:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="Task not found or cannot be edited while running")
    return {
        "id": task.id,
        "title": task.title,
        "status": task.status.value,
        "steps": [
            {
                "id": s.id,
                "title": s.title,
                "description": s.description,
                "persona_id": s.persona_id,
                "status": s.status.value,
            }
            for s in task.steps
        ],
    }


@router.post("/{task_id}/input/{input_id}")
async def provide_input(
    task_id: str,
    input_id: str,
    body: TaskInputResponse,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
):
    """Provide human input response for a waiting task step."""
    orchestrator = get_task_orchestrator()
    ok = await orchestrator.provide_input(user.uid, task_id, input_id, body.response)
    if not ok:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Task or input not found")
    return {"success": True}


# ── E2B Desktop Endpoints ─────────────────────────────────────────────


@router.get("/desktop/status")
async def desktop_status(user: AuthenticatedUser = Depends(get_current_user)):  # noqa: B008
    """Get the E2B Desktop sandbox status for the current user."""
    from app.services.e2b_desktop_service import get_e2b_desktop_service

    svc = get_e2b_desktop_service()
    info = await svc.get_desktop_info(user.uid)
    if not info:
        return {"status": "none", "message": "No active desktop sandbox."}
    return {
        "status": info.status.value,
        "sandbox_id": info.sandbox_id,
        "stream_url": info.stream_url,
    }


@router.post("/desktop/start")
async def start_desktop(user: AuthenticatedUser = Depends(get_current_user)):  # noqa: B008
    """Start an E2B Desktop sandbox for the current user."""
    from app.services.e2b_desktop_service import get_e2b_desktop_service

    svc = get_e2b_desktop_service()
    info = await svc.create_desktop(user.uid)
    return {
        "status": info.status.value,
        "sandbox_id": info.sandbox_id,
        "stream_url": info.stream_url,
    }


@router.post("/desktop/stop")
async def stop_desktop(user: AuthenticatedUser = Depends(get_current_user)):  # noqa: B008
    """Stop the E2B Desktop sandbox for the current user."""
    from app.services.e2b_desktop_service import get_e2b_desktop_service

    svc = get_e2b_desktop_service()
    destroyed = await svc.destroy_desktop(user.uid)
    return {"destroyed": destroyed}
