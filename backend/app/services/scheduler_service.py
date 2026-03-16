"""Scheduler Service — Firestore-backed cron/scheduled task management.

Stores scheduled tasks in Firestore and integrates with Google Cloud
Scheduler (recurring) and Cloud Tasks (one-shot delayed) for execution.

Firestore collection: ``scheduled_tasks/{task_id}``
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime
from uuid import uuid4

import httpx
from croniter import croniter
from google.cloud import firestore

from app.config import settings
from app.services.event_bus import get_event_bus
from app.utils.logging import get_logger

logger = get_logger(__name__)

COLLECTION = "scheduled_tasks"


# ── Data model ────────────────────────────────────────────────────────


class ScheduledTask:
    """In-memory representation of a Firestore scheduled_task document."""

    MAX_RETRIES = 3
    EXECUTION_TIMEOUT = 120  # seconds

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
        fail_count: int = 0,
        consecutive_failures: int = 0,
        max_retries: int = 3,
        last_result: str = "",
        last_execution_id: str = "",
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
        self.fail_count = fail_count
        self.consecutive_failures = consecutive_failures
        self.max_retries = max_retries
        self.last_result = last_result
        self.last_execution_id = last_execution_id
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
            "fail_count": self.fail_count,
            "consecutive_failures": self.consecutive_failures,
            "max_retries": self.max_retries,
            "last_result": self.last_result,
            "last_execution_id": self.last_execution_id,
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
            fail_count=data.get("fail_count", 0),
            consecutive_failures=data.get("consecutive_failures", 0),
            max_retries=data.get("max_retries", 3),
            last_result=data.get("last_result", ""),
            last_execution_id=data.get("last_execution_id", ""),
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
            "fail_count": self.fail_count,
            "consecutive_failures": self.consecutive_failures,
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "last_result": self.last_result[:200] if self.last_result else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ── Service ───────────────────────────────────────────────────────────


class SchedulerService:
    """Manages scheduled tasks with Firestore persistence and Cloud Scheduler/Tasks integration."""

    def __init__(self, db: firestore.Client | None = None) -> None:
        self._db = db
        self._event_bus = get_event_bus()
        self._cron_task: asyncio.Task | None = None
        self._cron_running = False
        self._poll_interval = 15.0

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

    async def get_task_by_id(self, task_id: str) -> ScheduledTask | None:
        """Look up a task by ID only (no user ownership check). For internal callers."""
        snap = self.db.collection(COLLECTION).document(task_id).get()
        if not snap.exists:
            return None
        return ScheduledTask.from_firestore(task_id, snap.to_dict())

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

    async def execute_task(self, task_id: str, execution_id: str = "") -> dict:
        """Execute a scheduled task with idempotency, retry, and timeout.

        Args:
            task_id: The task document ID.
            execution_id: Optional dedup key from Cloud Scheduler. If the task
                          was already executed with this ID, the call is skipped.

        Returns:
            Dict with ``success``, ``output`` or ``error``, and ``execution_id``.
        """
        snap = self.db.collection(COLLECTION).document(task_id).get()
        if not snap.exists:
            return {"success": False, "error": "Task not found"}

        task = ScheduledTask.from_firestore(task_id, snap.to_dict())
        if task.status != "active":
            return {"success": False, "error": f"Task is {task.status}"}

        # Idempotency: skip if Cloud Scheduler retried / double-delivered
        exec_id = execution_id or f"exec_{uuid4().hex[:10]}"
        if execution_id and task.last_execution_id == execution_id:
            logger.info("task_execution_dedup", task_id=task_id, execution_id=execution_id)
            return {"success": True, "output": task.last_result, "deduplicated": True}

        result = {"success": True, "output": "", "execution_id": exec_id}

        try:
            # Run action with timeout enforcement
            output = await asyncio.wait_for(
                self._run_action(task),
                timeout=ScheduledTask.EXECUTION_TIMEOUT,
            )
            result["output"] = output

            # Update task state — success
            task.last_run_at = datetime.now(UTC)
            task.run_count += 1
            task.consecutive_failures = 0  # Reset on success
            task.last_result = str(output)[:500]
            task.last_execution_id = exec_id
            task.updated_at = datetime.now(UTC)

            # For one-shot tasks, mark completed
            if task.schedule_type == "once":
                task.status = "completed"

            self.db.collection(COLLECTION).document(task_id).set(task.to_firestore())

            # Store execution in history subcollection
            await self._record_execution(task, exec_id, True, output)

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

        except TimeoutError:
            error_msg = f"Execution timed out after {ScheduledTask.EXECUTION_TIMEOUT}s"
            result = {"success": False, "error": error_msg, "execution_id": exec_id}
            await self._handle_task_failure(task, exec_id, error_msg)
            logger.error("scheduled_task_timeout", task_id=task_id, timeout=ScheduledTask.EXECUTION_TIMEOUT)

        except Exception as exc:
            error_msg = str(exc)
            result = {"success": False, "error": error_msg, "execution_id": exec_id}
            await self._handle_task_failure(task, exec_id, error_msg)
            logger.exception("scheduled_task_execution_failed", task_id=task_id)

        return result

    async def _handle_task_failure(self, task: ScheduledTask, exec_id: str, error: str) -> None:
        """Handle a failed task execution with retry tracking."""
        task.fail_count += 1
        task.consecutive_failures += 1
        task.last_result = f"ERROR: {error}"
        task.last_execution_id = exec_id
        task.updated_at = datetime.now(UTC)

        # Mark as failed only after exhausting retries (for cron tasks, allow continued retries)
        if task.schedule_type == "once" and task.consecutive_failures >= task.max_retries:
            task.status = "failed"
            logger.warning(
                "task_permanently_failed",
                task_id=task.id,
                consecutive_failures=task.consecutive_failures,
            )
        elif task.schedule_type == "cron" and task.consecutive_failures >= task.max_retries * 2:
            # Recurring tasks get more leeway but eventually pause
            task.status = "paused"
            logger.warning(
                "cron_task_auto_paused",
                task_id=task.id,
                consecutive_failures=task.consecutive_failures,
            )

        self.db.collection(COLLECTION).document(task.id).set(task.to_firestore())
        await self._record_execution(task, exec_id, False, error)

        # Notify on failure
        if task.notify_rule:
            await self._send_notification(task, f"FAILED: {error}")

    async def _record_execution(
        self, task: ScheduledTask, exec_id: str, success: bool, output: str
    ) -> None:
        """Write an execution record to the task's history subcollection."""
        try:
            self.db.collection(COLLECTION).document(task.id).collection(
                "executions"
            ).document(exec_id).set({
                "execution_id": exec_id,
                "success": success,
                "output": str(output)[:2000],
                "executed_at": datetime.now(UTC),
                "run_count": task.run_count,
            })
        except Exception:
            logger.warning("execution_history_write_failed", task_id=task.id, exc_info=True)

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
        elif action == "run_plugin_tool":
            return await self._action_run_plugin_tool(task)
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

    async def _action_run_plugin_tool(self, task: ScheduledTask) -> str:
        """Run a server-side plugin tool (T2: native plugin or MCP).

        T3 (client-local) tools CANNOT be used by scheduled tasks because
        they require a live device connection.  This handler supports:
          - Native plugins (e.g. Courier): calls the Python function directly
          - MCP STDIO/HTTP/OAuth plugins: connects to the server, calls the
            tool, and returns the result

        Required action_params:
          - plugin_id: ID of the plugin (e.g. "courier", "brave-search")
          - tool_name: Name of the tool to call
          - tool_args: Dict of arguments to pass to the tool
        """
        import importlib

        from app.models.plugin import PluginKind
        from app.services.plugin_registry import get_plugin_registry

        params = task.action_params
        plugin_id = params.get("plugin_id", "")
        tool_name = params.get("tool_name", "")
        tool_args = params.get("tool_args", {})

        if not plugin_id or not tool_name:
            return "Missing plugin_id or tool_name in action_params"

        registry = get_plugin_registry()
        manifest = registry.get_manifest(plugin_id)
        if manifest is None:
            return f"Plugin '{plugin_id}' not found in catalog"

        # Native plugins — call the underlying function directly
        if manifest.kind == PluginKind.NATIVE:
            try:
                module = importlib.import_module(manifest.module)
                factory = getattr(module, manifest.factory)
                tools = factory()
                for t in tools:
                    if getattr(t, "name", "") == tool_name:
                        fn = getattr(t, "_function", None) or t.func
                        result = await fn(**tool_args)
                        return json.dumps(result) if isinstance(result, dict) else str(result)
                return f"Tool '{tool_name}' not found in native plugin '{plugin_id}'"
            except Exception as exc:
                return f"Native plugin call failed: {exc}"

        # MCP plugins — connect and call via McpToolset
        if manifest.kind in (PluginKind.MCP_STDIO, PluginKind.MCP_HTTP, PluginKind.MCP_OAUTH):
            try:
                tools = await registry._get_plugin_tools(task.user_id, plugin_id, manifest)
                if not tools:
                    return f"No tools available from MCP plugin '{plugin_id}'"
                for t in tools:
                    if getattr(t, "name", "") == tool_name:
                        # ADK MCP tools expose run_async; pass args directly
                        result = await t.run_async(args=tool_args, tool_context=None)
                        return json.dumps(result) if isinstance(result, dict) else str(result)
                return f"Tool '{tool_name}' not found in MCP plugin '{plugin_id}'"
            except Exception as exc:
                return f"MCP tool call failed: {exc}"

        return f"Plugin kind '{manifest.kind}' not supported for scheduled tasks"

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
                retry_config=scheduler_v1.RetryConfig(
                    retry_count=2,
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

    # ── Local Dev Cron Runner ─────────────────────────────────────────

    async def start_local_cron(self, poll_interval: float = 15.0) -> None:
        """Start an in-process cron loop that polls Firestore for due tasks.

        Used in development when Google Cloud Scheduler is unavailable.
        Checks every ``poll_interval`` seconds for active tasks whose
        cron schedule indicates they are due.
        """
        if self._cron_task is not None:
            return
        self._poll_interval = poll_interval
        self._cron_running = True
        self._cron_task = asyncio.create_task(self._cron_loop())
        logger.info("local_cron_started", poll_interval=poll_interval)

    async def stop_local_cron(self) -> None:
        """Stop the in-process cron loop."""
        self._cron_running = False
        if self._cron_task:
            self._cron_task.cancel()
            try:
                await self._cron_task
            except asyncio.CancelledError:
                pass
            self._cron_task = None
            logger.info("local_cron_stopped")

    async def _cron_loop(self) -> None:
        """Poll Firestore for tasks whose cron is due and execute them."""
        while self._cron_running:
            try:
                await self._check_and_run_due_tasks()
            except Exception:
                logger.exception("local_cron_poll_error")
            await asyncio.sleep(self._poll_interval)

    async def _check_and_run_due_tasks(self) -> None:
        """Find all active cron tasks that are due and execute them."""
        now = datetime.now(UTC)
        query = (
            self.db.collection(COLLECTION)
            .where(filter=firestore.FieldFilter("status", "==", "active"))
        )
        for doc in query.stream():
            task = ScheduledTask.from_firestore(doc.id, doc.to_dict())
            if not task.schedule:
                continue
            try:
                if not croniter.is_valid(task.schedule):
                    continue
                # Determine if task is due: next fire time after last_run (or created) <= now
                base_time = task.last_run_at or task.created_at or now
                cron = croniter(task.schedule, base_time)
                next_fire = cron.get_next(datetime)
                if next_fire <= now:
                    logger.info(
                        "local_cron_firing",
                        task_id=task.id,
                        description=task.description[:60],
                        schedule=task.schedule,
                    )
                    await self.execute_task(task_id=task.id)
            except Exception:
                logger.exception("local_cron_task_check_error", task_id=task.id)


# ── Singleton ─────────────────────────────────────────────────────────

_scheduler_service: SchedulerService | None = None


def get_scheduler_service() -> SchedulerService:
    global _scheduler_service
    if _scheduler_service is None:
        _scheduler_service = SchedulerService()
    return _scheduler_service
