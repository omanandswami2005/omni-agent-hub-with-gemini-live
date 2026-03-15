"""Planned Task ADK tools — task planning & human-in-the-loop for agents.

Replaces the old synchronous plan_task tool with an async, persistent,
Firestore-backed task system. Agents can:
  - Create and plan tasks (returns immediately, runs in background)
  - Check task status and progress
  - Request human input (confirmation, choice, text)
  - Get task results

These tools are available to the root agent and all personas.
"""

from __future__ import annotations

from google.adk.tools import FunctionTool
from google.adk.tools.tool_context import ToolContext

from app.models.planned_task import InputType
from app.services.task_orchestrator import get_task_orchestrator
from app.utils.logging import get_logger

logger = get_logger(__name__)


# ── Task Creation & Planning ──────────────────────────────────────────


async def create_planned_task(
    description: str,
    auto_execute: bool = False,
    tool_context: ToolContext | None = None,
) -> dict:
    """Create a new planned task from a complex user request.

    Decomposes the request into actionable steps via AI, stores them in the
    database, and optionally starts execution immediately.

    Call this when the user request clearly needs MULTIPLE steps or specialists.
    The task runs asynchronously — the user can continue chatting while it executes.

    Args:
        description: The full user request to decompose into a task plan.
        auto_execute: If True, start executing immediately after planning.
                     If False, wait for user confirmation first.
        tool_context: Injected by ADK.

    Returns:
        Task info with ID, planned steps, and status.
    """
    user_id = (tool_context.user_id if tool_context else None) or "unknown"
    orchestrator = get_task_orchestrator()

    # Create and plan
    task = await orchestrator.create_task(user_id, description)
    task = await orchestrator.plan_task(task)

    if auto_execute and task.steps:
        await orchestrator.start_execution(task)

    return {
        "task_id": task.id,
        "title": task.title,
        "status": task.status.value,
        "steps": [
            {
                "id": s.id,
                "title": s.title,
                "persona": s.persona_id,
                "status": s.status.value,
            }
            for s in task.steps
        ],
        "message": (
            f"Task planned with {len(task.steps)} steps. "
            + ("Execution started." if auto_execute else "Awaiting user confirmation to start.")
        ),
    }


async def execute_planned_task(
    task_id: str,
    tool_context: ToolContext | None = None,
) -> dict:
    """Start executing a planned task that's awaiting confirmation.

    Call this after the user reviews and confirms a task plan.

    Args:
        task_id: The ID of the task to execute.
        tool_context: Injected by ADK.

    Returns:
        Updated task status.
    """
    user_id = (tool_context.user_id if tool_context else None) or "unknown"
    orchestrator = get_task_orchestrator()

    task = await orchestrator.get_task(user_id, task_id)
    if not task:
        return {"error": f"Task {task_id} not found."}

    await orchestrator.start_execution(task)
    return {
        "task_id": task.id,
        "status": "running",
        "message": f"Task '{task.title}' is now executing {len(task.steps)} steps in the background.",
    }


# ── Task Status & Results ─────────────────────────────────────────────


async def get_task_status(
    task_id: str,
    tool_context: ToolContext | None = None,
) -> dict:
    """Check the current status and progress of a planned task.

    Args:
        task_id: The ID of the task to check.
        tool_context: Injected by ADK.

    Returns:
        Current task status, progress percentage, and step statuses.
    """
    user_id = (tool_context.user_id if tool_context else None) or "unknown"
    orchestrator = get_task_orchestrator()

    task = await orchestrator.get_task(user_id, task_id)
    if not task:
        return {"error": f"Task {task_id} not found."}

    return {
        "task_id": task.id,
        "title": task.title,
        "status": task.status.value,
        "progress": round(task.progress * 100, 1),
        "steps": [
            {
                "id": s.id,
                "title": s.title,
                "status": s.status.value,
                "output": s.output[:500] if s.output else "",
                "error": s.error,
            }
            for s in task.steps
        ],
        "result_summary": task.result_summary,
    }


async def list_planned_tasks(
    tool_context: ToolContext | None = None,
) -> dict:
    """List all planned tasks for the current user.

    Args:
        tool_context: Injected by ADK.

    Returns:
        List of tasks with their status and progress.
    """
    user_id = (tool_context.user_id if tool_context else None) or "unknown"
    orchestrator = get_task_orchestrator()

    tasks = await orchestrator.list_tasks(user_id)
    return {
        "tasks": [
            {
                "id": t.id,
                "title": t.title,
                "status": t.status.value,
                "progress": round(t.progress * 100, 1),
                "step_count": len(t.steps),
                "created_at": t.created_at.isoformat() if t.created_at else "",
            }
            for t in tasks[:20]  # Limit to 20 most recent
        ],
        "total": len(tasks),
    }


# ── Task Actions ──────────────────────────────────────────────────────


async def pause_planned_task(
    task_id: str,
    tool_context: ToolContext | None = None,
) -> dict:
    """Pause a running task.

    Args:
        task_id: The task to pause.
        tool_context: Injected by ADK.

    Returns:
        Updated status.
    """
    user_id = (tool_context.user_id if tool_context else None) or "unknown"
    ok = await get_task_orchestrator().pause_task(user_id, task_id)
    return {"paused": ok, "message": "Task paused." if ok else "Cannot pause this task."}


async def resume_planned_task(
    task_id: str,
    tool_context: ToolContext | None = None,
) -> dict:
    """Resume a paused task.

    Args:
        task_id: The task to resume.
        tool_context: Injected by ADK.

    Returns:
        Updated status.
    """
    user_id = (tool_context.user_id if tool_context else None) or "unknown"
    ok = await get_task_orchestrator().resume_task(user_id, task_id)
    return {"resumed": ok, "message": "Task resumed." if ok else "Cannot resume this task."}


async def cancel_planned_task(
    task_id: str,
    tool_context: ToolContext | None = None,
) -> dict:
    """Cancel a running or paused task.

    Args:
        task_id: The task to cancel.
        tool_context: Injected by ADK.

    Returns:
        Updated status.
    """
    user_id = (tool_context.user_id if tool_context else None) or "unknown"
    ok = await get_task_orchestrator().cancel_task(user_id, task_id)
    return {"cancelled": ok, "message": "Task cancelled." if ok else "Cannot cancel this task."}


# ── Human-in-the-Loop ─────────────────────────────────────────────────


async def ask_user_confirmation(
    question: str,
    task_id: str = "",
    step_id: str = "",
    tool_context: ToolContext | None = None,
) -> dict:
    """Ask the user a yes/no confirmation question.

    This pauses exec and waits for the user's response.

    Args:
        question: The yes/no question to ask.
        task_id: Associated task ID (if within a task).
        step_id: Associated step ID (if within a step).
        tool_context: Injected by ADK.

    Returns:
        The user's response ('yes' or 'no').
    """
    user_id = (tool_context.user_id if tool_context else None) or "unknown"
    orchestrator = get_task_orchestrator()

    if task_id:
        task = await orchestrator.get_task(user_id, task_id)
        if task:
            step = orchestrator._get_step(task, step_id) if step_id else task.current_step
            if step:
                response = await orchestrator.request_input(
                    task, step, prompt=question, input_type=InputType.CONFIRMATION
                )
                return {"response": response, "confirmed": response.lower() in ("yes", "y", "true", "1")}

    # Fallback: publish as standalone input request via event bus
    return await _standalone_input_request(user_id, question, InputType.CONFIRMATION)


async def ask_user_choice(
    question: str,
    options: list[str],
    task_id: str = "",
    step_id: str = "",
    tool_context: ToolContext | None = None,
) -> dict:
    """Ask the user to choose from multiple options.

    Args:
        question: The question to ask.
        options: List of choices for the user.
        task_id: Associated task ID.
        step_id: Associated step ID.
        tool_context: Injected by ADK.

    Returns:
        The user's selected option.
    """
    user_id = (tool_context.user_id if tool_context else None) or "unknown"
    orchestrator = get_task_orchestrator()

    if task_id:
        task = await orchestrator.get_task(user_id, task_id)
        if task:
            step = orchestrator._get_step(task, step_id) if step_id else task.current_step
            if step:
                response = await orchestrator.request_input(
                    task, step, prompt=question, input_type=InputType.CHOICE, options=options
                )
                return {"response": response}

    return await _standalone_input_request(user_id, question, InputType.CHOICE, options=options)


async def ask_user_text(
    question: str,
    task_id: str = "",
    step_id: str = "",
    tool_context: ToolContext | None = None,
) -> dict:
    """Ask the user for free-form text input.

    Args:
        question: What to ask the user.
        task_id: Associated task ID.
        step_id: Associated step ID.
        tool_context: Injected by ADK.

    Returns:
        The user's text response.
    """
    user_id = (tool_context.user_id if tool_context else None) or "unknown"
    orchestrator = get_task_orchestrator()

    if task_id:
        task = await orchestrator.get_task(user_id, task_id)
        if task:
            step = orchestrator._get_step(task, step_id) if step_id else task.current_step
            if step:
                response = await orchestrator.request_input(
                    task, step, prompt=question, input_type=InputType.TEXT
                )
                return {"response": response}

    return await _standalone_input_request(user_id, question, InputType.TEXT)


# ── Helpers ───────────────────────────────────────────────────────────


async def _standalone_input_request(
    user_id: str,
    prompt: str,
    input_type: InputType,
    options: list[str] | None = None,
) -> dict:
    """Publish a standalone input request (not tied to a running task)."""
    import asyncio
    import json
    import time
    from uuid import uuid4

    from app.services.event_bus import get_event_bus

    input_id = uuid4().hex[:10]
    event = json.dumps({
        "type": "task_input_required",
        "task_id": "",
        "input": {
            "id": input_id,
            "step_id": "",
            "input_type": input_type.value,
            "prompt": prompt,
            "options": options or [],
        },
        "timestamp": time.time(),
    })

    bus = get_event_bus()
    await bus.publish(user_id, event)

    # Wait for response via orchestrator's pending inputs
    orchestrator = get_task_orchestrator()
    future: asyncio.Future[str] = asyncio.get_event_loop().create_future()
    orchestrator._pending_inputs[input_id] = future

    try:
        response = await asyncio.wait_for(future, timeout=300)
        return {"response": response}
    except TimeoutError:
        return {"error": "User did not respond in time."}
    finally:
        orchestrator._pending_inputs.pop(input_id, None)


# ── Tool Registration ─────────────────────────────────────────────────

_TASK_TOOLS: list[FunctionTool] | None = None


def get_planned_task_tools() -> list[FunctionTool]:
    """Return all planned task management tools."""
    global _TASK_TOOLS
    if _TASK_TOOLS is None:
        _TASK_TOOLS = [
            FunctionTool(create_planned_task),
            FunctionTool(execute_planned_task),
            FunctionTool(get_task_status),
            FunctionTool(list_planned_tasks),
            FunctionTool(pause_planned_task),
            FunctionTool(resume_planned_task),
            FunctionTool(cancel_planned_task),
        ]
    return _TASK_TOOLS


_HITL_TOOLS: list[FunctionTool] | None = None


def get_human_input_tools() -> list[FunctionTool]:
    """Return human-in-the-loop input tools."""
    global _HITL_TOOLS
    if _HITL_TOOLS is None:
        _HITL_TOOLS = [
            FunctionTool(ask_user_confirmation),
            FunctionTool(ask_user_choice),
            FunctionTool(ask_user_text),
        ]
    return _HITL_TOOLS
