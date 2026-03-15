"""PlannedTask & related models — persistent task tracking with human-in-the-loop.

Firestore collections:
  planned_tasks/{task_id}  →  PlannedTask document
  planned_tasks/{task_id}/inputs/{input_id}  →  HumanInput sub-document
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field

# ── Enums ─────────────────────────────────────────────────────────────


class TaskStatus(StrEnum):
    """Lifecycle states for a PlannedTask."""

    PENDING = "pending"           # Created, not yet planned
    PLANNING = "planning"         # LLM is decomposing into steps
    AWAITING_CONFIRMATION = "awaiting_confirmation"  # Plan ready, needs user OK
    RUNNING = "running"           # Actively executing steps
    PAUSED = "paused"             # User paused or waiting for human input
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepStatus(StrEnum):
    """Lifecycle states for a TaskStep."""

    PENDING = "pending"
    RUNNING = "running"
    AWAITING_INPUT = "awaiting_input"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class InputType(StrEnum):
    """Kinds of human-in-the-loop input requests."""

    CONFIRMATION = "confirmation"  # Yes/No
    CHOICE = "choice"              # Multiple choice
    TEXT = "text"                   # Free-form text
    FILE = "file"                  # File upload


class InputStatus(StrEnum):
    PENDING = "pending"
    RESPONDED = "responded"
    EXPIRED = "expired"


# ── Data Models ───────────────────────────────────────────────────────


class TaskStep(BaseModel):
    """A single step in a planned task."""

    id: str = Field(default_factory=lambda: uuid4().hex[:8])
    title: str
    description: str = ""
    instruction: str = ""
    persona_id: str = "assistant"
    status: StepStatus = StepStatus.PENDING
    depends_on: list[str] = Field(default_factory=list)
    output: str = ""
    error: str = ""
    started_at: datetime | None = None
    completed_at: datetime | None = None
    tool_calls: list[dict] = Field(default_factory=list)

    def to_firestore(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "instruction": self.instruction,
            "persona_id": self.persona_id,
            "status": self.status.value,
            "depends_on": self.depends_on,
            "output": self.output,
            "error": self.error,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "tool_calls": self.tool_calls,
        }

    @classmethod
    def from_firestore(cls, data: dict) -> TaskStep:
        safe = {**data}
        # Firestore DatetimeWithNanoseconds → regular datetime
        for dt_field in ("started_at", "completed_at"):
            v = safe.get(dt_field)
            if v is not None and not isinstance(v, datetime):
                try:
                    safe[dt_field] = datetime.fromisoformat(str(v))
                except (ValueError, TypeError):
                    safe[dt_field] = None
        return cls(**safe)


class HumanInput(BaseModel):
    """A request for human input during task execution."""

    id: str = Field(default_factory=lambda: uuid4().hex[:10])
    task_id: str = ""
    step_id: str = ""
    input_type: InputType = InputType.CONFIRMATION
    prompt: str
    options: list[str] = Field(default_factory=list)
    default_value: str = ""
    required: bool = True
    response: str | None = None
    status: InputStatus = InputStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    responded_at: datetime | None = None

    def to_firestore(self) -> dict:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "step_id": self.step_id,
            "input_type": self.input_type.value,
            "prompt": self.prompt,
            "options": self.options,
            "default_value": self.default_value,
            "required": self.required,
            "response": self.response,
            "status": self.status.value,
            "created_at": self.created_at,
            "responded_at": self.responded_at,
        }

    @classmethod
    def from_firestore(cls, data: dict) -> HumanInput:
        return cls(**data)


class PlannedTask(BaseModel):
    """A persistent, trackable multi-step task."""

    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    user_id: str
    title: str = ""
    description: str
    status: TaskStatus = TaskStatus.PENDING
    steps: list[TaskStep] = Field(default_factory=list)
    context: dict = Field(default_factory=dict)
    result_summary: str = ""
    e2b_desktop_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def to_firestore(self) -> dict:
        return {
            "user_id": self.user_id,
            "title": self.title,
            "description": self.description,
            "status": self.status.value,
            "steps": [s.to_firestore() for s in self.steps],
            "context": self.context,
            "result_summary": self.result_summary,
            "e2b_desktop_id": self.e2b_desktop_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_firestore(cls, task_id: str, data: dict) -> PlannedTask:
        steps = [TaskStep.from_firestore(s) for s in data.get("steps", [])]
        return cls(
            id=task_id,
            user_id=data["user_id"],
            title=data.get("title", ""),
            description=data.get("description", ""),
            status=TaskStatus(data.get("status", "pending")),
            steps=steps,
            context=data.get("context", {}),
            result_summary=data.get("result_summary", ""),
            e2b_desktop_id=data.get("e2b_desktop_id"),
            created_at=data.get("created_at", datetime.now(UTC)),
            updated_at=data.get("updated_at", datetime.now(UTC)),
        )

    @property
    def progress(self) -> float:
        """0.0 - 1.0 completion ratio."""
        if not self.steps:
            return 0.0
        done = sum(1 for s in self.steps if s.status in (StepStatus.COMPLETED, StepStatus.SKIPPED))
        return done / len(self.steps)

    @property
    def current_step(self) -> TaskStep | None:
        """First non-completed step."""
        for s in self.steps:
            if s.status in (StepStatus.PENDING, StepStatus.RUNNING, StepStatus.AWAITING_INPUT):
                return s
        return None


# ── API Request/Response Models ───────────────────────────────────────


class TaskCreateRequest(BaseModel):
    """REST API request to create a planned task."""

    description: str
    auto_execute: bool = False


class TaskInputResponse(BaseModel):
    """REST/WS response providing human input."""

    input_id: str
    response: str


class TaskActionRequest(BaseModel):
    """REST request to pause/resume/cancel a task."""

    action: str  # "pause" | "resume" | "cancel"


class TaskEditRequest(BaseModel):
    """REST request to edit a task description and replan."""

    description: str


class TaskSummary(BaseModel):
    """Lightweight task listing item."""

    id: str
    title: str
    description: str
    status: TaskStatus
    step_count: int
    progress: float
    created_at: datetime
    updated_at: datetime
