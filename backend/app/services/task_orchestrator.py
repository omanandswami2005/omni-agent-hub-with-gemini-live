"""TaskOrchestrator — async task planning, execution, and human-in-the-loop.

Manages the full lifecycle of PlannedTasks:
  1. Create task → decompose via Gemini → store steps in Firestore
  2. Pre-flight resource validation before execution
  3. Execute steps asynchronously (background asyncio tasks) with timeouts
  4. Pause for human input → resume when response arrives
  5. Publish real-time events via EventBus for dashboard
  6. Retry failed steps

Firestore collection: planned_tasks/{task_id}
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import UTC, datetime
from uuid import uuid4

from google.cloud import firestore

from app.config import settings
from app.models.planned_task import (
    HumanInput,
    InputStatus,
    InputType,
    PlannedTask,
    StepStatus,
    TaskStatus,
    TaskStep,
)
from app.services.event_bus import get_event_bus
from app.utils.logging import get_logger

logger = get_logger(__name__)

COLLECTION = "planned_tasks"
STEP_TIMEOUT_SECONDS = 300  # 5 min per step

# Persona → capability tags used for tool resolution and resource validation
_PERSONA_CAPS: dict[str, list[str]] = {
    "assistant": ["search", "web", "knowledge", "communication", "media"],
    "coder": ["code_execution", "sandbox", "search", "web"],
    "researcher": ["search", "web", "knowledge"],
    "analyst": ["code_execution", "sandbox", "search", "data", "web"],
    "creative": ["creative", "media", "communication"],
}

# Keywords in step instructions that suggest a T2 MCP plugin is needed
_MCP_HINT_KEYWORDS: dict[str, list[str]] = {
    "calendar": ["calendar", "schedule", "meeting", "event", "appointment"],
    "email": ["email", "mail", "send email", "inbox", "gmail"],
    "notion": ["notion", "wiki", "workspace", "page", "database"],
    "slack": ["slack", "message", "channel", "workspace"],
    "github": ["github", "repository", "pull request", "issue", "commit"],
    "drive": ["google drive", "drive", "docs", "sheets", "spreadsheet"],
}


class TaskOrchestrator:
    """Manages PlannedTask lifecycle with Firestore persistence and async execution."""

    def __init__(self, db: firestore.Client | None = None) -> None:
        self._db = db
        self._event_bus = get_event_bus()
        # In-flight task execution handles: {task_id: asyncio.Task}
        self._running_tasks: dict[str, asyncio.Task] = {}
        # Pending human input futures: {input_id: asyncio.Future}
        self._pending_inputs: dict[str, asyncio.Future] = {}

    @property
    def db(self) -> firestore.Client:
        if self._db is None:
            self._db = firestore.Client(project=settings.GOOGLE_CLOUD_PROJECT or None)
        return self._db

    # ── Firestore CRUD ────────────────────────────────────────────────

    async def _save_task(self, task: PlannedTask) -> None:
        """Persist task state to Firestore."""
        task.updated_at = datetime.now(UTC)
        self.db.collection(COLLECTION).document(task.id).set(task.to_firestore())

    async def get_task(self, user_id: str, task_id: str) -> PlannedTask | None:
        """Load a task from Firestore, verifying ownership."""
        snap = self.db.collection(COLLECTION).document(task_id).get()
        if not snap.exists:
            return None
        data = snap.to_dict()
        if data.get("user_id") != user_id:
            return None
        return PlannedTask.from_firestore(task_id, data)

    async def list_tasks(self, user_id: str) -> list[PlannedTask]:
        """List all tasks for a user, newest first."""
        try:
            query = (
                self.db.collection(COLLECTION)
                .where(filter=firestore.FieldFilter("user_id", "==", user_id))
                .order_by("created_at", direction=firestore.Query.DESCENDING)
            )
            return [
                PlannedTask.from_firestore(snap.id, snap.to_dict())
                for snap in query.stream()
            ]
        except Exception:
            # Fallback: query without order_by (no composite index)
            logger.warning("list_tasks_fallback", user_id=user_id)
            query = (
                self.db.collection(COLLECTION)
                .where(filter=firestore.FieldFilter("user_id", "==", user_id))
            )
            tasks = [
                PlannedTask.from_firestore(snap.id, snap.to_dict())
                for snap in query.stream()
            ]
            tasks.sort(key=lambda t: t.created_at, reverse=True)
            return tasks

    async def _update_task_field(self, task_id: str, **fields) -> None:
        """Atomic field update on a task doc."""
        fields["updated_at"] = datetime.now(UTC)
        self.db.collection(COLLECTION).document(task_id).update(fields)

    # ── Task Creation ─────────────────────────────────────────────────

    async def create_task(self, user_id: str, description: str) -> PlannedTask:
        """Create a new PlannedTask and begin planning."""
        task = PlannedTask(
            id=uuid4().hex[:12],
            user_id=user_id,
            description=description,
            status=TaskStatus.PENDING,
        )
        await self._save_task(task)
        await self._publish_event(task, "task_created")
        logger.info("task_created", task_id=task.id, user_id=user_id)
        return task

    # ── Task Planning (Decomposition) ─────────────────────────────────

    async def plan_task(self, task: PlannedTask) -> PlannedTask:
        """Use Gemini to decompose the task description into steps, then validate resources."""
        task.status = TaskStatus.PLANNING
        await self._save_task(task)
        await self._publish_event(task, "task_updated")

        try:
            steps = await self._decompose_with_gemini(task)
            task.steps = steps
            task.title = await self._generate_title(task.description)

            # Pre-flight resource validation
            validation = self._validate_resources(task)
            if validation["warnings"] or validation["blockers"]:
                task.context = {**task.context, "validation": validation}

            task.status = TaskStatus.AWAITING_CONFIRMATION
            await self._save_task(task)
            await self._publish_event(task, "task_planned")
            logger.info("task_planned", task_id=task.id, step_count=len(steps),
                        blockers=len(validation.get("blockers", [])),
                        warnings=len(validation.get("warnings", [])))
        except Exception:
            task.status = TaskStatus.FAILED
            task.result_summary = "Failed to decompose task into steps."
            await self._save_task(task)
            await self._publish_event(task, "task_updated")
            logger.exception("task_planning_failed", task_id=task.id)

        return task

    async def _decompose_with_gemini(self, task: PlannedTask) -> list[TaskStep]:
        """Call Gemini to break down the task into ordered steps.

        Injects available tool context so Gemini only plans steps using
        tools that are actually available for the user.
        """
        from google.genai import Client

        from app.agents.agent_factory import TEXT_MODEL

        tool_context = self._build_tool_context(task.user_id)
        prompt = _DECOMPOSE_PROMPT.format(task=task.description, tool_context=tool_context)
        client = Client(vertexai=True)
        response = client.models.generate_content(model=TEXT_MODEL, contents=[prompt])

        raw_text = response.text or ""
        if raw_text.startswith("```"):
            raw_text = raw_text.split("\n", 1)[1]
        if raw_text.endswith("```"):
            raw_text = raw_text.rsplit("```", 1)[0]
        raw_text = raw_text.strip()

        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError:
            logger.warning("decompose_bad_json", raw=raw_text[:300])
            return [
                TaskStep(
                    title="Execute task",
                    description=task.description,
                    instruction=task.description,
                    persona_id="assistant",
                )
            ]

        steps: list[TaskStep] = []
        for raw_step in data.get("steps", []):
            steps.append(
                TaskStep(
                    id=raw_step.get("id", uuid4().hex[:8]),
                    title=raw_step.get("title", "Step"),
                    description=raw_step.get("description", ""),
                    instruction=raw_step.get("instruction", raw_step.get("description", "")),
                    persona_id=raw_step.get("persona_id", "assistant"),
                    depends_on=raw_step.get("depends_on", []),
                )
            )
        return steps or [
            TaskStep(
                title="Execute task",
                description=task.description,
                instruction=task.description,
                persona_id="assistant",
            )
        ]

    async def _generate_title(self, description: str) -> str:
        """Generate a short task title from the description."""
        from google.genai import Client

        from app.agents.agent_factory import TEXT_MODEL

        try:
            client = Client(vertexai=True)
            response = client.models.generate_content(
                model=TEXT_MODEL,
                contents=[
                    f"Generate a short title (max 8 words) for this task. "
                    f"Return ONLY the title, nothing else:\n{description[:500]}"
                ],
            )
            title = (response.text or "").strip().strip('"').strip("'")
            return title[:100] if title else description[:80]
        except Exception:
            return description[:80]

    # ── Task Execution ────────────────────────────────────────────────

    async def start_execution(self, task: PlannedTask) -> None:
        """Begin async execution of a planned task.

        Returns immediately — execution runs in a background asyncio task.
        Rejects if there are unresolved validation blockers.
        """
        if task.id in self._running_tasks:
            logger.warning("task_already_running", task_id=task.id)
            return

        # Re-validate resources right before execution
        validation = self._validate_resources(task)
        if validation["blockers"]:
            task.context = {**task.context, "validation": validation}
            task.status = TaskStatus.FAILED
            blocker_msg = "; ".join(validation["blockers"])
            task.result_summary = f"Cannot execute — missing requirements: {blocker_msg}"
            await self._save_task(task)
            await self._publish_event(task, "task_updated")
            logger.warning("task_blocked", task_id=task.id, blockers=validation["blockers"])
            return

        task.status = TaskStatus.RUNNING
        await self._save_task(task)
        await self._publish_event(task, "task_updated")

        bg_task = asyncio.create_task(self._execute_steps(task))
        self._running_tasks[task.id] = bg_task
        bg_task.add_done_callback(lambda _: self._running_tasks.pop(task.id, None))

    async def _execute_steps(self, task: PlannedTask) -> None:
        """Execute task steps sequentially, respecting dependencies."""
        try:
            has_failure = False
            for step in task.steps:
                if task.status == TaskStatus.CANCELLED:
                    break

                # Wait if paused
                while task.status == TaskStatus.PAUSED:
                    await asyncio.sleep(1)
                    # Reload from Firestore to check for resume
                    refreshed = await self.get_task(task.user_id, task.id)
                    if refreshed:
                        task.status = refreshed.status

                if task.status == TaskStatus.CANCELLED:
                    break

                # Check dependencies
                if step.depends_on:
                    failed_deps = []
                    unmet = False
                    for dep_id in step.depends_on:
                        dep_step = self._get_step(task, dep_id)
                        if not dep_step or dep_step.status != StepStatus.COMPLETED:
                            unmet = True
                            if dep_step and dep_step.status == StepStatus.FAILED:
                                failed_deps.append(dep_step.title)
                    if unmet:
                        step.status = StepStatus.SKIPPED
                        if failed_deps:
                            step.error = f"Skipped because required step(s) failed: {', '.join(failed_deps)}. Fix the failed steps and retry."
                        else:
                            step.error = "Skipped because prerequisite steps did not complete."
                        await self._save_task(task)
                        await self._publish_step_event(task, step)
                        continue

                # Execute the step
                await self._execute_single_step(task, step)

                # Track step failures
                if step.status == StepStatus.FAILED:
                    has_failure = True

            # All steps done — determine final status
            if task.status != TaskStatus.CANCELLED:
                task.status = TaskStatus.FAILED if has_failure else TaskStatus.COMPLETED
                task.result_summary = self._build_result_summary(task)
                await self._save_task(task)
                await self._publish_event(task, "task_completed")
                logger.info("task_finished", task_id=task.id, status=task.status.value)

        except asyncio.CancelledError:
            task.status = TaskStatus.CANCELLED
            await self._save_task(task)
            await self._publish_event(task, "task_updated")
        except Exception:
            task.status = TaskStatus.FAILED
            task.result_summary = "Task execution failed unexpectedly."
            await self._save_task(task)
            await self._publish_event(task, "task_updated")
            logger.exception("task_execution_failed", task_id=task.id)

    async def _execute_single_step(self, task: PlannedTask, step: TaskStep) -> None:
        """Execute one step using ADK agent for the assigned persona, with timeout."""
        step.status = StepStatus.RUNNING
        step.started_at = datetime.now(UTC)
        await self._save_task(task)
        await self._publish_step_event(task, step)

        try:
            output = await asyncio.wait_for(
                self._run_step_agent(task, step),
                timeout=STEP_TIMEOUT_SECONDS,
            )
            step.status = StepStatus.COMPLETED
            step.output = output[:10000]
            step.completed_at = datetime.now(UTC)
        except TimeoutError:
            step.status = StepStatus.FAILED
            step.error = (
                f"Step timed out after {STEP_TIMEOUT_SECONDS // 60} minutes. "
                "The operation may be too complex — try breaking it into smaller steps or retrying."
            )
            step.completed_at = datetime.now(UTC)
            logger.warning("step_timeout", task_id=task.id, step_id=step.id)
        except ConnectionError as e:
            step.status = StepStatus.FAILED
            step.error = f"Connection error: could not reach the AI service. Details: {str(e)[:500]}. Please retry."
            step.completed_at = datetime.now(UTC)
            logger.exception("step_connection_error", task_id=task.id, step_id=step.id)
        except Exception as e:
            step.status = StepStatus.FAILED
            step.error = self._categorize_error(e)
            step.completed_at = datetime.now(UTC)
            logger.exception("step_execution_failed", task_id=task.id, step_id=step.id)

        await self._save_task(task)
        await self._publish_step_event(task, step)

    async def _run_step_agent(self, task: PlannedTask, step: TaskStep) -> str:
        """Run an ADK agent for a specific step and collect output."""
        from google.adk.agents import Agent
        from google.adk.runners import Runner
        from google.adk.sessions import InMemorySessionService
        from google.genai import types as genai_types

        from app.agents.agent_factory import TEXT_MODEL, get_tools_for_capabilities

        caps = _PERSONA_CAPS.get(step.persona_id, ["search"])
        tools = get_tools_for_capabilities(caps)

        # Also include T2 MCP plugin tools if connected for this user
        try:
            from app.services.plugin_registry import get_plugin_registry
            registry = get_plugin_registry()
            t2_tools = registry.get_tools_for_capabilities(task.user_id, caps)
            if t2_tools:
                existing = {getattr(t, "name", str(t)) for t in tools}
                for t in t2_tools:
                    if getattr(t, "name", str(t)) not in existing:
                        tools.append(t)
        except Exception:
            logger.debug("t2_tools_unavailable", step_id=step.id)

        # Build context from previous step outputs
        context_parts = []
        for prev_step in task.steps:
            if prev_step.id == step.id:
                break
            if prev_step.status == StepStatus.COMPLETED and prev_step.output:
                context_parts.append(f"[{prev_step.title}]: {prev_step.output[:2000]}")

        context_str = "\n\n".join(context_parts) if context_parts else ""
        full_instruction = step.instruction
        if context_str:
            full_instruction = (
                f"Context from previous steps:\n{context_str}\n\n"
                f"Your task:\n{step.instruction}"
            )

        agent = Agent(
            name=f"step_{step.id}",
            model=TEXT_MODEL,
            instruction=full_instruction,
            tools=tools,
        )

        session_service = InMemorySessionService()
        runner = Runner(
            app_name="omni-task-step",
            agent=agent,
            session_service=session_service,
        )
        session = await session_service.create_session(
            app_name="omni-task-step",
            user_id=task.user_id,
        )

        content = genai_types.Content(
            role="user",
            parts=[genai_types.Part(text=step.instruction)],
        )

        results: list[str] = []
        async for event in runner.run_async(
            user_id=task.user_id,
            session_id=session.id,
            new_message=content,
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        results.append(part.text)

        return "\n".join(results) if results else "Step completed with no text output."

    # ── Human-in-the-Loop ─────────────────────────────────────────────

    async def request_input(
        self,
        task: PlannedTask,
        step: TaskStep,
        *,
        prompt: str,
        input_type: InputType = InputType.CONFIRMATION,
        options: list[str] | None = None,
    ) -> str:
        """Pause step execution and request input from the user.

        Blocks until the user provides a response via provide_input().
        """
        human_input = HumanInput(
            task_id=task.id,
            step_id=step.id,
            prompt=prompt,
            input_type=input_type,
            options=options or [],
        )

        # Save to Firestore
        self.db.collection(COLLECTION).document(task.id).collection("inputs").document(
            human_input.id
        ).set(human_input.to_firestore())

        # Update step status
        step.status = StepStatus.AWAITING_INPUT
        task.status = TaskStatus.PAUSED
        await self._save_task(task)

        # Publish event for dashboard
        await self._publish_input_event(task, human_input)

        # Wait for response via asyncio.Future
        future: asyncio.Future[str] = asyncio.get_event_loop().create_future()
        self._pending_inputs[human_input.id] = future

        try:
            response = await asyncio.wait_for(future, timeout=600)  # 10 min timeout
        except TimeoutError:
            human_input.status = InputStatus.EXPIRED
            self.db.collection(COLLECTION).document(task.id).collection("inputs").document(
                human_input.id
            ).update({"status": "expired"})
            raise
        finally:
            self._pending_inputs.pop(human_input.id, None)

        return response

    async def provide_input(self, user_id: str, task_id: str, input_id: str, response: str) -> bool:
        """User provides a response to a human input request."""
        task = await self.get_task(user_id, task_id)
        if not task:
            return False

        # Update Firestore
        now = datetime.now(UTC)
        self.db.collection(COLLECTION).document(task_id).collection("inputs").document(
            input_id
        ).update({
            "response": response,
            "status": InputStatus.RESPONDED.value,
            "responded_at": now,
        })

        # Resume the waiting future
        future = self._pending_inputs.get(input_id)
        if future and not future.done():
            future.set_result(response)

        # Resume task
        task.status = TaskStatus.RUNNING
        for step in task.steps:
            if step.status == StepStatus.AWAITING_INPUT:
                step.status = StepStatus.RUNNING
        await self._save_task(task)
        await self._publish_event(task, "task_updated")

        logger.info("input_provided", task_id=task_id, input_id=input_id)
        return True

    # ── Task Actions ──────────────────────────────────────────────────

    async def pause_task(self, user_id: str, task_id: str) -> bool:
        task = await self.get_task(user_id, task_id)
        if not task or task.status != TaskStatus.RUNNING:
            return False
        task.status = TaskStatus.PAUSED
        await self._save_task(task)
        await self._publish_event(task, "task_updated")
        return True

    async def resume_task(self, user_id: str, task_id: str) -> bool:
        task = await self.get_task(user_id, task_id)
        if not task or task.status != TaskStatus.PAUSED:
            return False
        task.status = TaskStatus.RUNNING
        await self._save_task(task)
        await self._publish_event(task, "task_updated")
        return True

    async def cancel_task(self, user_id: str, task_id: str) -> bool:
        task = await self.get_task(user_id, task_id)
        if not task:
            return False
        if task.status in (TaskStatus.COMPLETED, TaskStatus.CANCELLED):
            return False

        # Cancel the background asyncio task
        bg = self._running_tasks.get(task_id)
        if bg and not bg.done():
            bg.cancel()

        # Cancel pending inputs
        for _input_id, future in list(self._pending_inputs.items()):
            if not future.done():
                future.cancel()

        task.status = TaskStatus.CANCELLED
        await self._save_task(task)
        await self._publish_event(task, "task_updated")
        logger.info("task_cancelled", task_id=task_id)
        return True

    async def delete_task(self, user_id: str, task_id: str) -> bool:
        """Permanently delete a task. Running tasks are cancelled first."""
        task = await self.get_task(user_id, task_id)
        if not task:
            return False
        # Cancel if running
        if task.status in (TaskStatus.RUNNING, TaskStatus.PAUSED):
            await self.cancel_task(user_id, task_id)
        self.db.collection(COLLECTION).document(task_id).delete()
        logger.info("task_deleted", task_id=task_id)
        return True

    async def edit_task(self, user_id: str, task_id: str, description: str) -> PlannedTask | None:
        """Edit a task description and re-plan it. Only non-running tasks can be edited."""
        task = await self.get_task(user_id, task_id)
        if not task:
            return None
        if task.status in (TaskStatus.RUNNING,):
            return None
        task.description = description
        task.steps = []
        task.status = TaskStatus.PENDING
        task.result_summary = ""
        task.context = {k: v for k, v in task.context.items() if k != "validation"}
        await self._save_task(task)
        await self._publish_event(task, "task_updated")
        # Re-plan
        task = await self.plan_task(task)
        return task

    async def retry_failed_steps(self, user_id: str, task_id: str) -> PlannedTask | None:
        """Reset failed/skipped steps back to pending and re-execute the task."""
        task = await self.get_task(user_id, task_id)
        if not task:
            return None
        if task.status not in (TaskStatus.FAILED, TaskStatus.COMPLETED):
            return None

        # Reset failed and skipped steps
        reset_count = 0
        for step in task.steps:
            if step.status in (StepStatus.FAILED, StepStatus.SKIPPED):
                step.status = StepStatus.PENDING
                step.error = ""
                step.output = ""
                step.started_at = None
                step.completed_at = None
                reset_count += 1

        if reset_count == 0:
            return task

        task.status = TaskStatus.PENDING
        task.result_summary = ""
        await self._save_task(task)
        await self._publish_event(task, "task_updated")

        # Start execution
        await self.start_execution(task)
        logger.info("task_retry", task_id=task.id, reset_steps=reset_count)
        return task

    # ── Event Publishing ──────────────────────────────────────────────

    async def _publish_event(self, task: PlannedTask, event_type: str) -> None:
        """Publish a task-level event to the EventBus."""
        event = json.dumps({
            "type": event_type,
            "task": {
                "id": task.id,
                "title": task.title,
                "description": task.description,
                "status": task.status.value,
                "steps": [
                    {
                        "id": s.id,
                        "title": s.title,
                        "description": s.description,
                        "persona_id": s.persona_id,
                        "status": s.status.value,
                        "output": s.output[:500] if s.output else "",
                        "error": s.error,
                    }
                    for s in task.steps
                ],
                "progress": round(task.progress * 100, 1),
                "result_summary": task.result_summary,
                "context": task.context,
            },
            "timestamp": time.time(),
        })
        await self._event_bus.publish(task.user_id, event)

    async def _publish_step_event(self, task: PlannedTask, step: TaskStep) -> None:
        """Publish a step-level progress event."""
        event = json.dumps({
            "type": "task_step_update",
            "task_id": task.id,
            "step": {
                "id": step.id,
                "title": step.title,
                "persona_id": step.persona_id,
                "status": step.status.value,
                "output": step.output[:500] if step.output else "",
                "error": step.error,
            },
            "progress": round(task.progress * 100, 1),
            "timestamp": time.time(),
        })
        await self._event_bus.publish(task.user_id, event)

    async def _publish_input_event(self, task: PlannedTask, human_input: HumanInput) -> None:
        """Publish a human-input-required event."""
        event = json.dumps({
            "type": "task_input_required",
            "task_id": task.id,
            "input": {
                "id": human_input.id,
                "step_id": human_input.step_id,
                "input_type": human_input.input_type.value,
                "prompt": human_input.prompt,
                "options": human_input.options,
                "default_value": human_input.default_value,
            },
            "timestamp": time.time(),
        })
        await self._event_bus.publish(task.user_id, event)

    # ── Resource Validation ─────────────────────────────────────────────

    def _validate_resources(self, task: PlannedTask) -> dict:
        """Pre-flight check: verify required resources are available.

        Returns dict with 'warnings' and 'blockers' lists.
        Blockers prevent execution; warnings are informational.
        """
        warnings: list[str] = []
        blockers: list[str] = []

        # Check T2 plugin availability based on step instructions
        try:
            from app.services.plugin_registry import get_plugin_registry
            registry = get_plugin_registry()
            enabled_ids = set(registry.get_enabled_ids(task.user_id))
        except Exception:
            enabled_ids = set()

        for step in task.steps:
            instruction_lower = (step.instruction + " " + step.description).lower()
            for plugin_key, keywords in _MCP_HINT_KEYWORDS.items():
                if any(kw in instruction_lower for kw in keywords):
                    # Check if any enabled plugin relates to this keyword
                    has_plugin = any(plugin_key in pid.lower() for pid in enabled_ids)
                    if not has_plugin:
                        warnings.append(
                            f"Step '{step.title}' may need a {plugin_key} plugin "
                            f"(mentions: {plugin_key}). Enable one in Settings → Integrations."
                        )

        return {"warnings": warnings, "blockers": blockers}

    def _build_tool_context(self, user_id: str) -> str:
        """Build a string describing available tools for decomposition prompt."""
        lines = []

        # T1: Always-available built-in tools per persona
        lines.append("\nBuilt-in tools (always available, NO plugin needed):")
        lines.append("  researcher: google_search (web search, news, fact-finding)")
        lines.append("  coder: execute_code, install_package, desktop tools (E2B sandbox)")
        lines.append("  analyst: google_search, execute_code, install_package, desktop tools")
        lines.append("  creative: generate_image (Imagen)")
        lines.append("  assistant: general tasks, communication")
        lines.append("  genui: render_genui_component (charts, tables, UI components)")

        try:
            from app.tools.capabilities_tool import _get_capabilities_data
            data = _get_capabilities_data(user_id)

            # T2 enabled plugins
            t2 = data.get("t2", [])
            if t2:
                plugins: dict[str, list[str]] = {}
                for entry in t2:
                    pname = entry.get("plugin", "unknown")
                    tool_name = entry.get("tool", "")
                    if tool_name and tool_name != "(not connected yet)":
                        plugins.setdefault(pname, []).append(tool_name)
                    elif tool_name == "(not connected yet)":
                        plugins.setdefault(pname, []).append("(connecting...)")
                if plugins:
                    lines.append("\nEnabled plugins (T2 — user-activated):")
                    for pname, tools in plugins.items():
                        lines.append(f"  {pname}: {', '.join(tools)}")
            else:
                lines.append("\nNo additional plugins are currently enabled.")

        except Exception:
            lines.append("\nCould not determine enabled plugins.")

        return "\n".join(lines)

    @staticmethod
    def _categorize_error(exc: Exception) -> str:
        """Produce a user-friendly error message from an exception."""
        msg = str(exc)
        lower = msg.lower()

        if "disconnected" in lower or "server disconnected" in lower:
            return (
                "Lost connection to the AI service during execution. "
                "This is usually temporary — please retry the task."
            )
        if "timeout" in lower or "timed out" in lower:
            return (
                "The operation timed out. The service may be overloaded. "
                "Try again or simplify the step."
            )
        if "rate limit" in lower or "quota" in lower or "429" in lower:
            return (
                "Rate limit reached for the AI service. "
                "Wait a few minutes and retry."
            )
        if "not found" in lower and "tool" in lower:
            return (
                f"A required tool was not found: {msg[:300]}. "
                "Check that the necessary plugin is enabled in Settings → Integrations."
            )
        if "permission" in lower or "403" in lower or "unauthorized" in lower:
            return (
                "Permission denied. The plugin may need re-authorization. "
                "Go to Settings → Integrations and reconnect it."
            )
        if "api key" in lower or "authentication" in lower:
            return (
                "Authentication error with an external service. "
                "Check your API keys and plugin configuration."
            )
        # Generic fallback — still include actual error for debugging
        return f"Step failed: {msg[:500]}. You can retry or edit the task."

    # ── Helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _get_step(task: PlannedTask, step_id: str) -> TaskStep | None:
        for s in task.steps:
            if s.id == step_id:
                return s
        return None

    @staticmethod
    def _build_result_summary(task: PlannedTask) -> str:
        lines = [f"Task: {task.title or task.description[:80]}"]
        failed_steps = []
        for step in task.steps:
            status_icon = {"completed": "✓", "failed": "✗", "skipped": "⊘"}.get(
                step.status.value, "?"
            )
            detail = step.output[:200] if step.output else step.error or step.status.value
            lines.append(f"  {status_icon} {step.title}: {detail}")
            if step.status == StepStatus.FAILED:
                failed_steps.append(step.title)

        if failed_steps:
            lines.append("")
            lines.append(f"⚠ {len(failed_steps)} step(s) failed. You can retry failed steps or edit the task plan.")

        return "\n".join(lines)


# ── Decomposition Prompt ──────────────────────────────────────────────

_DECOMPOSE_PROMPT = """\
You are a task decomposition engine. Break the following task into clear,
actionable steps. Each step should be executable by one specialist agent.

Available personas (pick the best for each step):
  assistant — general tasks, communication, scheduling, plugin tools (calendar, email, etc.)
  coder — code writing, execution, debugging, E2B desktop sandbox
  researcher — web search (google_search is BUILT-IN, always available), deep research, fact-finding
  analyst — data analysis, charts, code execution, web search
  creative — image generation (generate_image is BUILT-IN), creative writing
  genui — interactive UI components, charts, tables, visualizations

{tool_context}

Return ONLY valid JSON matching this schema:
{{
  "steps": [
    {{
      "id": "s1",
      "title": "Short step title",
      "description": "What this step does",
      "instruction": "Detailed instruction for the agent",
      "persona_id": "researcher",
      "depends_on": []
    }}
  ]
}}

Rules:
- Keep total steps <= 10
- Steps should be ordered logically
- Use depends_on to reference step IDs when a step needs output from another
- Each step should be self-contained with clear instructions
- Be specific in instructions — the agent won't see the original request
- ONLY plan steps that use available tools listed above
- Built-in tools (google_search, execute_code, generate_image, etc.) are ALWAYS available — do NOT create steps saying they need a plugin
- Only flag a missing plugin if the task needs a T2 plugin (calendar, email, notion, etc.) that is not in the enabled plugins list

TASK:
{task}
"""


# ── Module singleton ──────────────────────────────────────────────────

_orchestrator: TaskOrchestrator | None = None


def get_task_orchestrator() -> TaskOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = TaskOrchestrator()
    return _orchestrator
