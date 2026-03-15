"""Scheduler Service — Firestore-backed cron/scheduled task management.

Stores scheduled tasks in Firestore and integrates with Google Cloud
Scheduler (recurring) and Cloud Tasks (one-shot delayed) for execution.

Firestore collection: ``scheduled_tasks/{task_id}``
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from uuid import uuid4

import httpx
from google.cloud import firestore

from app.config import settings
from app.services.event_bus import get_event_bus
from app.utils.logging import get_logger

logger = get_logger(__name__)

COLLECTION = "scheduled_tasks"


# ── Data model ────────────────────────────────────────────────────────


class ScheduledTask:
    """In-memory representation of a Firestore scheduled_task document."""

    def __init__(
        self,
        *,
        id: str = "",
        user_id: str = "",
        description: str = "",
        action: str = "",
        action_params: dict | None = None,
        schedule: str = "",
        schedule_type: str = "cron",
        notify_rule: dict | None = None,
        status: str = "active",
        last_run_at: datetime | None = None,
        next_run_at: datetime | None = None,
        run_count: int = 0,
        last_result: str = "",
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        cloud_scheduler_name: str = "",
        cloud_task_name: str = "",
    ) -> None:
        self.id = id or f"sched_{uuid4().hex[:12]}"
        self.user_id = user_id
        self.description = description
        self.action = action
        self.action_params = action_params or {}
        self.schedule = schedule
        self.schedule_type = schedule_type  # "cron" | "once" | "interval"
        self.notify_rule = notify_rule
        self.status = status  # "active" | "paused" | "completed" | "failed"
        self.last_run_at = last_run_at
        self.next_run_at = next_run_at
        self.run_count = run_count
        self.last_result = last_result
        self.created_at = created_at or datetime.now(UTC)
        self.updated_at = updated_at or datetime.now(UTC)
        self.cloud_scheduler_name = cloud_scheduler_name
        self.cloud_task_name = cloud_task_name

    def to_firestore(self) -> dict:
        return {
            "user_id": self.user_id,
            "description": self.description,
            "action": self.action,
            "action_params": self.action_params,
            "schedule": self.schedule,
            "schedule_type": self.schedule_type,
            "notify_rule": self.notify_rule,
            "status": self.status,
            "last_run_at": self.last_run_at,
            "next_run_at": self.next_run_at,
            "run_count": self.run_count,
            "last_result": self.last_result,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "cloud_scheduler_name": self.cloud_scheduler_name,
            "cloud_task_name": self.cloud_task_name,
        }

    @classmethod
    def from_firestore(cls, task_id: str, data: dict) -> ScheduledTask:
        return cls(
            id=task_id,
            user_id=data.get("user_id", ""),
            description=data.get("description", ""),
            action=data.get("action", ""),
            action_params=data.get("action_params") or {},
            schedule=data.get("schedule", ""),
            schedule_type=data.get("schedule_type", "cron"),
            notify_rule=data.get("notify_rule"),
            status=data.get("status", "active"),
            last_run_at=data.get("last_run_at"),
            next_run_at=data.get("next_run_at"),
            run_count=data.get("run_count", 0),
            last_result=data.get("last_result", ""),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            cloud_scheduler_name=data.get("cloud_scheduler_name", ""),
            cloud_task_name=data.get("cloud_task_name", ""),
        )

    def to_summary(self) -> dict:
        return {
            "id": self.id,
            "description": self.description,
            "schedule": self.schedule,
            "schedule_type": self.schedule_type,
            "status": self.status,
            "run_count": self.run_count,
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ── Service ───────────────────────────────────────────────────────────


class SchedulerService:
    """Manages scheduled tasks with Firestore persistence and Cloud Scheduler/Tasks integration."""

    def __init__(self, db: firestore.Client | None = None) -> None:
        self._db = db
        self._event_bus = get_event_bus()

    @property
    def db(self) -> firestore.Client:
        if self._db is None:
            self._db = firestore.Client(project=settings.GOOGLE_CLOUD_PROJECT or None)
        return self._db

    # ── CRUD ──────────────────────────────────────────────────────

    async def create_task(
        self,
        user_id: str,
        description: str,
        action: str,
        schedule: str,
        schedule_type: str = "cron",
        action_params: dict | None = None,
        notify_rule: dict | None = None,
    ) -> ScheduledTask:
        """Create a new scheduled task and optionally register with Cloud Scheduler."""
        task = ScheduledTask(
            user_id=user_id,
            description=description,
            action=action,
            action_params=action_params,
            schedule=schedule,
            schedule_type=schedule_type,
            notify_rule=notify_rule,
            status="active",
        )

        # Persist to Firestore
        self.db.collection(COLLECTION).document(task.id).set(task.to_firestore())

        # Try to register with Cloud Scheduler for recurring tasks
        if schedule_type == "cron":
            await self._register_cloud_scheduler(task)

        logger.info(
            "scheduled_task_created",
            task_id=task.id,
            user_id=user_id,
            schedule=schedule,
            action=action,
        )

        # Publish event for dashboard
        await self._publish_event(user_id, "task_scheduled", task.to_summary())

        return task

    async def get_task(self, user_id: str, task_id: str) -> ScheduledTask | None:
        snap = self.db.collection(COLLECTION).document(task_id).get()
        if not snap.exists:
            return None
        data = snap.to_dict()
        if data.get("user_id") != user_id:
            return None
        return ScheduledTask.from_firestore(task_id, data)

    async def list_tasks(self, user_id: str) -> list[ScheduledTask]:
        query = (
            self.db.collection(COLLECTION)
            .where(filter=firestore.FieldFilter("user_id", "==", user_id))
            .order_by("created_at", direction=firestore.Query.DESCENDING)
        )
        tasks = []
        for doc in query.stream():
            tasks.append(ScheduledTask.from_firestore(doc.id, doc.to_dict()))
        return tasks

    async def delete_task(self, user_id: str, task_id: str) -> bool:
        task = await self.get_task(user_id, task_id)
        if not task:
            return False

        # Delete from Cloud Scheduler if registered
        if task.cloud_scheduler_name:
            await self._delete_cloud_scheduler(task.cloud_scheduler_name)

        self.db.collection(COLLECTION).document(task_id).delete()
        logger.info("scheduled_task_deleted", task_id=task_id, user_id=user_id)
        await self._publish_event(user_id, "task_unscheduled", {"task_id": task_id})
        return True

    async def pause_task(self, user_id: str, task_id: str) -> ScheduledTask | None:
        task = await self.get_task(user_id, task_id)
        if not task:
            return None
        task.status = "paused"
        task.updated_at = datetime.now(UTC)
        self.db.collection(COLLECTION).document(task_id).set(task.to_firestore())
        if task.cloud_scheduler_name:
            await self._pause_cloud_scheduler(task.cloud_scheduler_name)
        return task

    async def resume_task(self, user_id: str, task_id: str) -> ScheduledTask | None:
        task = await self.get_task(user_id, task_id)
        if not task:
            return None
        task.status = "active"
        task.updated_at = datetime.now(UTC)
        self.db.collection(COLLECTION).document(task_id).set(task.to_firestore())
        if task.cloud_scheduler_name:
            await self._resume_cloud_scheduler(task.cloud_scheduler_name)
        return task

    # ── Task Execution (called by Cloud Scheduler/Tasks endpoint) ─────

    async def execute_task(self, task_id: str) -> dict:
        """Execute a scheduled task. Called by the internal trigger endpoint."""
        snap = self.db.collection(COLLECTION).document(task_id).get()
        if not snap.exists:
            return {"success": False, "error": "Task not found"}

        task = ScheduledTask.from_firestore(task_id, snap.to_dict())
        if task.status != "active":
            return {"success": False, "error": f"Task is {task.status}"}

        result = {"success": True, "output": ""}

        try:
            # Execute based on action type
            output = await self._run_action(task)
            result["output"] = output

            # Update task state
            task.last_run_at = datetime.now(UTC)
            task.run_count += 1
            task.last_result = str(output)[:500]
            task.updated_at = datetime.now(UTC)

            # For one-shot tasks, mark completed
            if task.schedule_type == "once":
                task.status = "completed"

            self.db.collection(COLLECTION).document(task_id).set(task.to_firestore())

            # Handle notification rule if present
            if task.notify_rule:
                await self._send_notification(task, output)

            # Publish execution event
            await self._publish_event(task.user_id, "task_executed", {
                "task_id": task.id,
                "description": task.description,
                "output": str(output)[:200],
                "run_count": task.run_count,
            })

        except Exception as exc:
            result = {"success": False, "error": str(exc)}
            task.last_result = f"ERROR: {exc}"
            task.status = "failed"
            task.updated_at = datetime.now(UTC)
            self.db.collection(COLLECTION).document(task_id).set(task.to_firestore())
            logger.exception("scheduled_task_execution_failed", task_id=task_id)

        return result

    async def _run_action(self, task: ScheduledTask) -> str:
        """Execute the task action. Dispatches to the appropriate handler."""
        action = task.action

        if action == "send_notification":
            return await self._action_send_notification(task)
        elif action == "send_email":
            return await self._action_send_email(task)
        elif action == "run_agent_query":
            return await self._action_run_agent_query(task)
        elif action == "fetch_and_summarize":
            return await self._action_fetch_and_summarize(task)
        elif action == "run_shell_command":
            return await self._action_run_shell_command(task)
        else:
            return f"Unknown action: {action}. Task description: {task.description}"

    # ── Action handlers ───────────────────────────────────────────────

    async def _action_send_notification(self, task: ScheduledTask) -> str:
        """Direct notification delivery (reminder-style: the task IS the notification)."""
        from app.plugins.courier_plugin import send_notification

        params = task.action_params
        result = await send_notification(
            message=params.get("message", task.description),
            channel=params.get("channel", "email"),
            recipient=params.get("recipient", ""),
            title=params.get("title", "Scheduled Reminder"),
        )
        return json.dumps(result)

    async def _action_send_email(self, task: ScheduledTask) -> str:
        """Send an email as the scheduled action."""
        from app.plugins.courier_plugin import send_email

        params = task.action_params
        result = await send_email(
            to=params.get("to", ""),
            subject=params.get("subject", "Scheduled Email"),
            body=params.get("body", task.description),
        )
        return json.dumps(result)

    async def _action_run_agent_query(self, task: ScheduledTask) -> str:
        """Run a query through the ADK agent and return the text result."""
        # Lightweight agent query for scheduled tasks
        params = task.action_params
        query = params.get("query", task.description)

        try:
            from google import genai

            client = genai.Client(
                vertexai=True,
                project=settings.GOOGLE_CLOUD_PROJECT,
                location=settings.GOOGLE_CLOUD_LOCATION,
            )
            response = client.models.generate_content(
                model=settings.TEXT_MODEL,
                contents=query,
            )
            return response.text or "No response generated."
        except Exception as exc:
            return f"Agent query failed: {exc}"

    async def _action_fetch_and_summarize(self, task: ScheduledTask) -> str:
        """Fetch a URL and summarize its content."""
        params = task.action_params
        url = params.get("url", "")
        if not url:
            return "No URL specified"

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(url)
                content = resp.text[:5000]
        except Exception as exc:
            return f"Fetch failed: {exc}"

        # Summarize with Gemini
        try:
            from google import genai

            client = genai.Client(
                vertexai=True,
                project=settings.GOOGLE_CLOUD_PROJECT,
                location=settings.GOOGLE_CLOUD_LOCATION,
            )
            response = client.models.generate_content(
                model=settings.TEXT_MODEL,
                contents=f"Summarize this content concisely:\n\n{content}",
            )
            return response.text or "No summary generated."
        except Exception as exc:
            return f"Summary failed: {exc}"

    async def _action_run_shell_command(self, task: ScheduledTask) -> str:
        """Run a shell command in an E2B sandbox (safe execution)."""
        params = task.action_params
        command = params.get("command", "")
        if not command:
            return "No command specified"

        try:
            from app.services.e2b_desktop_service import E2BDesktopService

            svc = E2BDesktopService()
            result = await svc.run_command(task.user_id, command, timeout=60.0)
            return result.get("stdout", "") or result.get("stderr", "Command completed")
        except Exception as exc:
            return f"Command failed: {exc}"

    # ── Notification delivery after task execution ────────────────────

    async def _send_notification(self, task: ScheduledTask, output: str) -> None:
        """Send notification based on task's notify_rule."""
        rule = task.notify_rule
        if not rule:
            return

        channel = rule.get("channel", "email")
        condition = rule.get("condition", "always")
        template = rule.get("message", "{output}")

        # Check condition
        if condition != "always":
            # Simple condition evaluation
            try:
                # Allow basic conditions like "result contains 'error'"
                if "contains" in condition:
                    keyword = condition.split("contains")[-1].strip().strip("'\"")
                    if keyword.lower() not in output.lower():
                        return
            except Exception:
                pass

        # Format message
        message = template.replace("{output}", output).replace("{result}", output)

        from app.plugins.courier_plugin import send_notification

        await send_notification(
            message=message,
            channel=channel,
            recipient=rule.get("recipient", ""),
            title=rule.get("title", f"Scheduled: {task.description}"),
        )

    # ── Cloud Scheduler integration ───────────────────────────────────

    async def _register_cloud_scheduler(self, task: ScheduledTask) -> None:
        """Register a recurring task with Google Cloud Scheduler."""
        try:
            from google.cloud import scheduler_v1

            client = scheduler_v1.CloudSchedulerClient()
            project = settings.GOOGLE_CLOUD_PROJECT
            location = settings.GOOGLE_CLOUD_LOCATION
            parent = f"projects/{project}/locations/{location}"

            backend_url = os.environ.get("BACKEND_URL", "")
            if not backend_url:
                logger.warning("cloud_scheduler_skip_no_backend_url", task_id=task.id)
                return

            job_name = f"{parent}/jobs/omni-sched-{task.id}"

            job = scheduler_v1.Job(
                name=job_name,
                schedule=task.schedule,
                time_zone="UTC",
                http_target=scheduler_v1.HttpTarget(
                    uri=f"{backend_url}/internal/scheduler/run/{task.id}",
                    http_method=scheduler_v1.HttpMethod.POST,
                    headers={"Content-Type": "application/json"},
                    body=json.dumps({"task_id": task.id}).encode(),
                    oidc_token=scheduler_v1.OidcToken(
                        service_account_email=os.environ.get("SCHEDULER_SA_EMAIL", ""),
                    ),
                ),
            )

            client.create_job(request={"parent": parent, "job": job})
            task.cloud_scheduler_name = job_name
            self.db.collection(COLLECTION).document(task.id).set(task.to_firestore())
            logger.info("cloud_scheduler_registered", task_id=task.id, job_name=job_name)
        except Exception:
            logger.warning(
                "cloud_scheduler_register_failed",
                task_id=task.id,
                exc_info=True,
            )

    async def _delete_cloud_scheduler(self, job_name: str) -> None:
        try:
            from google.cloud import scheduler_v1

            client = scheduler_v1.CloudSchedulerClient()
            client.delete_job(request={"name": job_name})
        except Exception:
            logger.warning("cloud_scheduler_delete_failed", job_name=job_name, exc_info=True)

    async def _pause_cloud_scheduler(self, job_name: str) -> None:
        try:
            from google.cloud import scheduler_v1

            client = scheduler_v1.CloudSchedulerClient()
            client.pause_job(request={"name": job_name})
        except Exception:
            pass

    async def _resume_cloud_scheduler(self, job_name: str) -> None:
        try:
            from google.cloud import scheduler_v1

            client = scheduler_v1.CloudSchedulerClient()
            client.resume_job(request={"name": job_name})
        except Exception:
            pass

    # ── EventBus ──────────────────────────────────────────────────────

    async def _publish_event(self, user_id: str, event_type: str, data: dict) -> None:
        payload = json.dumps({"type": event_type, **data})
        await self._event_bus.publish(user_id, payload)


# ── Singleton ─────────────────────────────────────────────────────────

_scheduler_service: SchedulerService | None = None


def get_scheduler_service() -> SchedulerService:
    global _scheduler_service
    if _scheduler_service is None:
        _scheduler_service = SchedulerService()
    return _scheduler_service
