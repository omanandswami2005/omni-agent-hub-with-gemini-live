"""TaskOrchestrator — async task planning, execution, and human-in-the-loop.

Manages the full lifecycle of PlannedTasks:
  1. Create task → decompose via Gemini → store steps in Firestore
  2. Execute steps asynchronously (background asyncio tasks)
  3. Pause for human input → resume when response arrives
  4. Publish real-time events via EventBus for dashboard

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
        query = (
            self.db.collection(COLLECTION)
            .where(filter=firestore.FieldFilter("user_id", "==", user_id))
            .order_by("created_at", direction=firestore.Query.DESCENDING)
        )
        return [
            PlannedTask.from_firestore(snap.id, snap.to_dict())
            for snap in query.stream()
        ]

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
        """Use Gemini to decompose the task description into steps."""
        task.status = TaskStatus.PLANNING
        await self._save_task(task)
        await self._publish_event(task, "task_updated")

        try:
            steps = await self._decompose_with_gemini(task.description)
            task.steps = steps
            task.title = await self._generate_title(task.description)
            task.status = TaskStatus.AWAITING_CONFIRMATION
            await self._save_task(task)
            await self._publish_event(task, "task_planned")
            logger.info("task_planned", task_id=task.id, step_count=len(steps))
        except Exception:
            task.status = TaskStatus.FAILED
            task.result_summary = "Failed to decompose task into steps."
            await self._save_task(task)
            await self._publish_event(task, "task_updated")
            logger.exception("task_planning_failed", task_id=task.id)

        return task

    async def _decompose_with_gemini(self, description: str) -> list[TaskStep]:
        """Call Gemini to break down the task into ordered steps."""
        from google.genai import Client

        from app.agents.agent_factory import TEXT_MODEL

        prompt = _DECOMPOSE_PROMPT.format(task=description)
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
                    description=description,
                    instruction=description,
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
                description=description,
                instruction=description,
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
        """
        if task.id in self._running_tasks:
            logger.warning("task_already_running", task_id=task.id)
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
                    deps_met = all(
                        self._get_step(task, dep_id)
                        and self._get_step(task, dep_id).status == StepStatus.COMPLETED
                        for dep_id in step.depends_on
                    )
                    if not deps_met:
                        step.status = StepStatus.SKIPPED
                        step.error = "Dependencies not met"
                        await self._save_task(task)
                        await self._publish_step_event(task, step)
                        continue

                # Execute the step
                await self._execute_single_step(task, step)

            # All steps done
            if task.status != TaskStatus.CANCELLED:
                task.status = TaskStatus.COMPLETED
                task.result_summary = self._build_result_summary(task)
                await self._save_task(task)
                await self._publish_event(task, "task_completed")
                logger.info("task_completed", task_id=task.id)

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
        """Execute one step using ADK agent for the assigned persona."""
        step.status = StepStatus.RUNNING
        step.started_at = datetime.now(UTC)
        await self._save_task(task)
        await self._publish_step_event(task, step)

        try:
            output = await self._run_step_agent(task, step)
            step.status = StepStatus.COMPLETED
            step.output = output[:10000]  # Truncate to prevent oversized docs
            step.completed_at = datetime.now(UTC)
        except Exception as e:
            step.status = StepStatus.FAILED
            step.error = str(e)[:2000]
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

        # Map persona to capabilities
        _PERSONA_CAPS: dict[str, list[str]] = {
            "assistant": ["search", "web", "knowledge", "communication", "media"],
            "coder": ["code_execution", "sandbox", "search", "web"],
            "researcher": ["search", "web", "knowledge"],
            "analyst": ["code_execution", "sandbox", "search", "data", "web"],
            "creative": ["creative", "media", "communication"],
        }
        caps = _PERSONA_CAPS.get(step.persona_id, ["search"])
        tools = get_tools_for_capabilities(caps)

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
                        "persona_id": s.persona_id,
                        "status": s.status.value,
                        "output": s.output[:500] if s.output else "",
                    }
                    for s in task.steps
                ],
                "progress": round(task.progress, 2),
                "result_summary": task.result_summary,
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
            "progress": round(task.progress, 2),
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
        for step in task.steps:
            status_icon = {"completed": "✓", "failed": "✗", "skipped": "⊘"}.get(
                step.status.value, "?"
            )
            lines.append(f"  {status_icon} {step.title}: {step.output[:200] if step.output else step.error or step.status.value}")
        return "\n".join(lines)


# ── Decomposition Prompt ──────────────────────────────────────────────

_DECOMPOSE_PROMPT = """\
You are a task decomposition engine. Break the following task into clear,
actionable steps. Each step should be executable by one specialist agent.

Available personas (pick the best for each step):
  assistant — general tasks, communication, scheduling
  coder — code writing, execution, debugging
  researcher — web search, deep research, fact-finding
  analyst — data analysis, charts, code execution
  creative — image generation, creative writing

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
