"""Scheduler Plugin — Create, manage, and delete scheduled/cron tasks.

Provides ADK tools for the agent to schedule recurring tasks, one-shot
reminders, daily news digests, periodic research emails, and more.

Leverages Google Cloud Scheduler (recurring) and Cloud Tasks (one-shot).
"""

from __future__ import annotations

from google.adk.tools import FunctionTool
from google.adk.tools.tool_context import ToolContext

from app.models.plugin import (
    PluginCategory,
    PluginKind,
    PluginManifest,
    ToolSummary,
)

# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

MANIFEST = PluginManifest(
    id="scheduler",
    name="Task Scheduler",
    description="Schedule recurring and one-shot tasks: daily news emails, "
    "periodic reminders, research reports, cron jobs, and more. "
    "Integrates with Cloud Scheduler and Courier for delivery.",
    version="0.1.0",
    author="Omni Hub Team",
    category=PluginCategory.PRODUCTIVITY,
    kind=PluginKind.NATIVE,
    icon="clock",
    tags=["productivity", "scheduling", "cron"],
    module="app.plugins.scheduler_plugin",
    factory="get_tools",
    tools_summary=[
        ToolSummary(
            name="create_scheduled_task",
            description="Schedule a recurring or one-shot task with optional notification",
        ),
        ToolSummary(
            name="list_scheduled_tasks",
            description="List all scheduled tasks for the user",
        ),
        ToolSummary(
            name="delete_scheduled_task",
            description="Delete/cancel a scheduled task",
        ),
        ToolSummary(
            name="pause_scheduled_task",
            description="Pause a scheduled task without deleting it",
        ),
        ToolSummary(
            name="resume_scheduled_task",
            description="Resume a paused scheduled task",
        ),
    ],
)


# ---------------------------------------------------------------------------
# Cron expression helpers
# ---------------------------------------------------------------------------

_NLP_TO_CRON = {
    "every minute": "* * * * *",
    "every 5 minutes": "*/5 * * * *",
    "every 15 minutes": "*/15 * * * *",
    "every 30 minutes": "*/30 * * * *",
    "every hour": "0 * * * *",
    "hourly": "0 * * * *",
    "daily": "0 9 * * *",
    "every day": "0 9 * * *",
    "every morning": "0 8 * * *",
    "every evening": "0 18 * * *",
    "every night": "0 21 * * *",
    "weekly": "0 9 * * MON",
    "every week": "0 9 * * MON",
    "every monday": "0 9 * * MON",
    "every tuesday": "0 9 * * TUE",
    "every wednesday": "0 9 * * WED",
    "every thursday": "0 9 * * THU",
    "every friday": "0 9 * * FRI",
    "every saturday": "0 9 * * SAT",
    "every sunday": "0 9 * * SUN",
    "monthly": "0 9 1 * *",
    "every month": "0 9 1 * *",
}


def _parse_schedule(schedule: str) -> tuple[str, str]:
    """Parse a schedule string into (cron_expression, schedule_type).

    Accepts either:
    - A cron expression (e.g., '0 9 * * MON')
    - Natural language (e.g., 'every monday', 'daily', 'every 5 minutes')
    """
    lower = schedule.strip().lower()

    # Check NLP shortcuts
    for nlp, cron in _NLP_TO_CRON.items():
        if nlp in lower:
            return cron, "cron"

    # Check if it looks like a cron expression (5 space-separated fields)
    parts = schedule.strip().split()
    if len(parts) == 5 and all(
        any(c.isdigit() or c in "*/-,MONTUEWEDTHUFRISATSUN" for c in p.upper())
        for p in parts
    ):
        return schedule.strip(), "cron"

    # Default: treat as description, schedule daily at 9am
    return "0 9 * * *", "cron"


# ---------------------------------------------------------------------------
# Tool context helper — get user_id from ADK tool context
# ---------------------------------------------------------------------------

def _get_user_id(tool_context=None) -> str:
    """Extract user_id from ADK tool context."""
    if tool_context and hasattr(tool_context, "state"):
        return tool_context.state.get("user_id", "default_user")
    return "default_user"


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


async def create_scheduled_task(
    description: str,
    schedule: str,
    action: str = "run_agent_query",
    notify_channel: str = "",
    notify_recipient: str = "",
    action_params: str = "",
    tool_context: ToolContext | None = None,
) -> dict:
    """Schedule a recurring or one-shot task.

    Args:
        description: What the task does (e.g., "Send daily news summary to email").
        schedule: When to run. Accepts cron expressions ('0 9 * * MON') or
            natural language ('daily', 'every monday', 'every 5 minutes').
        action: Action type: 'run_agent_query', 'send_email', 'send_notification',
            'fetch_and_summarize', 'run_shell_command'.
        notify_channel: Optional notification channel: 'email', 'log'. Empty = no notification.
        notify_recipient: Recipient for notifications (email address, etc.).
        action_params: JSON string of additional parameters for the action.
            For 'send_email': {"to": "...", "subject": "...", "body": "..."}
            For 'run_agent_query': {"query": "..."}
            For 'fetch_and_summarize': {"url": "..."}

    Returns:
        A dict with task details including ID and schedule.
    """
    import json

    from app.services.scheduler_service import get_scheduler_service

    svc = get_scheduler_service()

    cron_expr, schedule_type = _parse_schedule(schedule)

    # Parse action_params from JSON string
    params = {}
    if action_params:
        try:
            params = json.loads(action_params)
        except json.JSONDecodeError:
            params = {"query": action_params}

    # For run_agent_query without explicit query, use the description
    if action == "run_agent_query" and "query" not in params:
        params["query"] = description

    # Build notification rule
    notify_rule = None
    if notify_channel:
        notify_rule = {
            "channel": notify_channel,
            "recipient": notify_recipient,
            "condition": "always",
            "message": "Scheduled task result: {output}",
            "title": description,
        }

    task = await svc.create_task(
        user_id=_get_user_id(tool_context),
        description=description,
        action=action,
        schedule=cron_expr,
        schedule_type=schedule_type,
        action_params=params,
        notify_rule=notify_rule,
    )

    return {
        "success": True,
        "task_id": task.id,
        "description": task.description,
        "schedule": task.schedule,
        "schedule_type": task.schedule_type,
        "action": task.action,
        "status": task.status,
        "notify": f"Will notify via {notify_channel}" if notify_channel else "No notification configured",
        "message": f"Scheduled '{description}' with cron '{cron_expr}'",
    }


async def list_scheduled_tasks(tool_context: ToolContext | None = None) -> dict:
    """List all scheduled tasks for the current user.

    Returns:
        A dict with the list of scheduled tasks.
    """
    from app.services.scheduler_service import get_scheduler_service

    svc = get_scheduler_service()
    tasks = await svc.list_tasks(user_id=_get_user_id(tool_context))

    return {
        "count": len(tasks),
        "tasks": [t.to_summary() for t in tasks],
    }


async def delete_scheduled_task(task_id: str, tool_context: ToolContext | None = None) -> dict:
    """Delete/cancel a scheduled task.

    Args:
        task_id: The ID of the scheduled task to delete.

    Returns:
        A dict confirming deletion.
    """
    from app.services.scheduler_service import get_scheduler_service

    svc = get_scheduler_service()
    deleted = await svc.delete_task(user_id=_get_user_id(tool_context), task_id=task_id)

    return {
        "success": deleted,
        "task_id": task_id,
        "message": f"Task {task_id} deleted." if deleted else f"Task {task_id} not found.",
    }


async def pause_scheduled_task(task_id: str, tool_context: ToolContext | None = None) -> dict:
    """Pause a scheduled task without deleting it.

    Args:
        task_id: The ID of the scheduled task to pause.

    Returns:
        A dict confirming the task is paused.
    """
    from app.services.scheduler_service import get_scheduler_service

    svc = get_scheduler_service()
    task = await svc.pause_task(user_id=_get_user_id(tool_context), task_id=task_id)

    if task:
        return {"success": True, "task_id": task_id, "status": "paused"}
    return {"success": False, "error": f"Task {task_id} not found"}


async def resume_scheduled_task(task_id: str, tool_context: ToolContext | None = None) -> dict:
    """Resume a paused scheduled task.

    Args:
        task_id: The ID of the scheduled task to resume.

    Returns:
        A dict confirming the task is resumed.
    """
    from app.services.scheduler_service import get_scheduler_service

    svc = get_scheduler_service()
    task = await svc.resume_task(user_id=_get_user_id(tool_context), task_id=task_id)

    if task:
        return {"success": True, "task_id": task_id, "status": "active"}
    return {"success": False, "error": f"Task {task_id} not found"}


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_tools() -> list[FunctionTool]:
    return [
        FunctionTool(create_scheduled_task),
        FunctionTool(list_scheduled_tasks),
        FunctionTool(delete_scheduled_task),
        FunctionTool(pause_scheduled_task),
        FunctionTool(resume_scheduled_task),
    ]
