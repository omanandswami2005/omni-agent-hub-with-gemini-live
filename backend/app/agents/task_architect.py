"""TaskArchitect — Dynamic pipeline orchestrator for complex multi-step tasks.

Analyses a complex user request, decomposes it into a DAG of sub-tasks,
selects execution patterns (Sequential / Parallel / Loop / Hybrid), and
dynamically constructs an ADK agent pipeline at runtime.

The dashboard receives live progress events via the EventBus so the user
can watch the pipeline execute as a visual DAG.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from enum import StrEnum

from google.adk.agents import Agent, LoopAgent, ParallelAgent, SequentialAgent

from app.agents.agent_factory import TEXT_MODEL, get_tools_for_capabilities
from app.services.event_bus import get_event_bus
from app.utils.logging import get_logger

logger = get_logger(__name__)

__all__ = [
    "PipelineBlueprint",
    "StageType",
    "SubTask",
    "TaskArchitect",
    "TaskStage",
]

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

# Minimum apparent complexity (number of sub-tasks) before using the
# architect — simple queries go straight to a persona agent.
COMPLEXITY_THRESHOLD = 2


class StageType(StrEnum):
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    LOOP = "loop"
    SINGLE = "single"


@dataclass
class SubTask:
    """A single unit of work inside a pipeline stage."""

    id: str
    description: str
    persona_id: str = "assistant"
    instruction: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "description": self.description,
            "persona_id": self.persona_id,
            "instruction": self.instruction,
        }


@dataclass
class TaskStage:
    """A stage in the pipeline — groups sub-tasks with an execution pattern."""

    name: str
    stage_type: StageType
    tasks: list[SubTask] = field(default_factory=list)
    max_iterations: int = 3

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "stage_type": self.stage_type.value,
            "tasks": [t.to_dict() for t in self.tasks],
            "max_iterations": self.max_iterations,
        }


@dataclass
class PipelineBlueprint:
    """The full decomposition of a task into stages."""

    task_description: str
    stages: list[TaskStage] = field(default_factory=list)
    pipeline_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    @property
    def total_agents(self) -> int:
        return sum(len(s.tasks) for s in self.stages)

    def to_dict(self) -> dict:
        return {
            "pipeline_id": self.pipeline_id,
            "task_description": self.task_description,
            "stages": [s.to_dict() for s in self.stages],
            "total_agents": self.total_agents,
        }

    @classmethod
    def from_analysis(cls, analysis: dict, task_description: str) -> PipelineBlueprint:
        """Build a blueprint from the LLM JSON analysis."""
        stages: list[TaskStage] = []
        for raw_stage in analysis.get("stages", []):
            stage_type = StageType(raw_stage.get("type", "sequential"))
            sub_tasks = [
                SubTask(
                    id=t.get("id", uuid.uuid4().hex[:8]),
                    description=t.get("description", ""),
                    persona_id=t.get("persona_id", "assistant"),
                    instruction=t.get("instruction", t.get("description", "")),
                )
                for t in raw_stage.get("tasks", [])
            ]
            stages.append(
                TaskStage(
                    name=raw_stage.get("name", f"stage_{len(stages)}"),
                    stage_type=stage_type,
                    tasks=sub_tasks,
                    max_iterations=raw_stage.get("max_iterations", 3),
                )
            )
        return cls(
            task_description=task_description,
            stages=stages,
        )


# ---------------------------------------------------------------------------
# Decomposition prompt
# ---------------------------------------------------------------------------

_DECOMPOSE_PROMPT = """\
You are a task decomposition engine.  Analyse the complex task below and
break it into stages.  Each stage has an execution type:

- **parallel** — sub-tasks that can run at the same time
- **sequential** — sub-tasks that must run in order
- **loop** — iterative refinement until quality is good
- **single** — one sub-task only

For every sub-task pick the best persona:
  assistant, coder, researcher, analyst, creative

Return **only** valid JSON (no markdown fences) matching this schema:
{{
  "stages": [
    {{
      "name": "stage name",
      "type": "parallel|sequential|loop|single",
      "max_iterations": 3,
      "tasks": [
        {{
          "id": "t1",
          "description": "what this agent does",
          "persona_id": "researcher",
          "instruction": "detailed instruction for the agent"
        }}
      ]
    }}
  ]
}}

Rules:
- Keep the total number of stages <= 5 and total sub-tasks <= 12.
- Loop stages must have exactly one sub-task and max_iterations between 2 and 5.
- If the task is simple (1 step), return a single stage with one task.

TASK:
{task}
"""


# ---------------------------------------------------------------------------
# TaskArchitect
# ---------------------------------------------------------------------------


class TaskArchitect:
    """Meta-orchestrator that decomposes tasks and builds ADK pipelines.

    Parameters
    ----------
    user_id:
        Used to publish progress events to the correct dashboard.
    """

    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        self._event_bus = get_event_bus()

    # -- Public API --------------------------------------------------------

    async def analyse_task(self, task: str) -> PipelineBlueprint:
        """Use Gemini to decompose *task* into a :class:`PipelineBlueprint`."""
        from google.genai import Client

        client = Client(vertexai=True)
        response = client.models.generate_content(
            model=TEXT_MODEL,
            contents=[_DECOMPOSE_PROMPT.format(task=task)],
        )

        raw_text = response.text or ""
        # Strip markdown code fences if present
        if raw_text.startswith("```"):
            raw_text = raw_text.split("\n", 1)[1]
        if raw_text.endswith("```"):
            raw_text = raw_text.rsplit("```", 1)[0]
        raw_text = raw_text.strip()

        try:
            analysis = json.loads(raw_text)
        except json.JSONDecodeError:
            logger.warning("task_decomposition_bad_json", raw=raw_text[:200])
            # Fallback: single-stage sequential pipeline
            analysis = {
                "stages": [
                    {
                        "name": "execute",
                        "type": "single",
                        "tasks": [
                            {
                                "id": "t1",
                                "description": task,
                                "persona_id": "assistant",
                                "instruction": task,
                            }
                        ],
                    }
                ]
            }

        blueprint = PipelineBlueprint.from_analysis(analysis, task)
        logger.info(
            "task_decomposed",
            pipeline_id=blueprint.pipeline_id,
            stages=len(blueprint.stages),
            total_agents=blueprint.total_agents,
        )
        return blueprint

    def build_pipeline(self, blueprint: PipelineBlueprint) -> Agent:
        """Construct an ADK agent graph from *blueprint*."""
        stage_agents: list[Agent] = []

        for stage in blueprint.stages:
            sub_agents = [self._create_sub_agent(t) for t in stage.tasks]

            if stage.stage_type == StageType.PARALLEL and len(sub_agents) > 1:
                stage_agents.append(
                    ParallelAgent(name=stage.name, sub_agents=sub_agents)
                )
            elif stage.stage_type == StageType.LOOP:
                stage_agents.append(
                    LoopAgent(
                        name=stage.name,
                        sub_agents=sub_agents,
                        max_iterations=stage.max_iterations,
                    )
                )
            elif stage.stage_type == StageType.SEQUENTIAL and len(sub_agents) > 1:
                stage_agents.append(
                    SequentialAgent(name=stage.name, sub_agents=sub_agents)
                )
            elif sub_agents:
                # Single agent — no wrapper needed
                stage_agents.append(sub_agents[0])

        if len(stage_agents) == 1:
            return stage_agents[0]

        pipeline = SequentialAgent(
            name=f"pipeline_{blueprint.pipeline_id}",
            sub_agents=stage_agents,
        )
        logger.info(
            "pipeline_built",
            pipeline_id=blueprint.pipeline_id,
            stage_count=len(stage_agents),
        )
        return pipeline

    async def publish_blueprint(self, blueprint: PipelineBlueprint) -> None:
        """Send the blueprint to dashboard via event bus."""
        event = json.dumps({
            "type": "pipeline_created",
            "pipeline": blueprint.to_dict(),
            "timestamp": time.time(),
        })
        await self._event_bus.publish(self.user_id, event)

    async def publish_stage_update(
        self,
        pipeline_id: str,
        stage_name: str,
        status: str,
        progress: float = 0.0,
    ) -> None:
        """Push a progress event for a pipeline stage."""
        event = json.dumps({
            "type": "pipeline_progress",
            "pipeline_id": pipeline_id,
            "stage": stage_name,
            "status": status,
            "progress": round(progress, 2),
            "timestamp": time.time(),
        })
        await self._event_bus.publish(self.user_id, event)

    # -- Internals ---------------------------------------------------------

    def _create_sub_agent(self, task: SubTask) -> Agent:
        """Build a focused LlmAgent for a single sub-task."""
        # Map persona_id to typical capabilities for task pipeline agents
        _PERSONA_CAPS: dict[str, list[str]] = {
            "assistant": ["search", "web", "knowledge", "communication", "media"],
            "coder": ["code_execution", "sandbox", "search", "web"],
            "researcher": ["search", "web", "knowledge"],
            "analyst": ["code_execution", "sandbox", "search", "data", "web"],
            "creative": ["creative", "media"],
        }
        caps = _PERSONA_CAPS.get(task.persona_id, ["search"])
        tools = get_tools_for_capabilities(caps)
        return Agent(
            name=task.id,
            model=TEXT_MODEL,
            instruction=task.instruction or task.description,
            tools=tools,
        )
