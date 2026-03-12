"""plan_and_execute — FunctionTool wrapper around TaskArchitect.

Gives the root agent the ability to decompose complex multi-step requests
into a plan.  The root then follows the plan by transferring to the
appropriate persona sub-agents in order.
"""

from __future__ import annotations

from google.adk.tools import FunctionTool

from app.agents.task_architect import TaskArchitect
from app.utils.logging import get_logger

logger = get_logger(__name__)


async def plan_task(user_id: str, task: str) -> str:
    """Decompose a complex task into an ordered plan of persona-routed steps.

    Call this when the user request clearly needs **multiple** specialists
    (e.g. "research X, write code for Y, then generate an image of Z").

    Args:
        user_id: Authenticated user ID.
        task: The full complex request to decompose.

    Returns:
        A structured plan listing each step, the persona to use, and
        the instruction for that step.
    """
    architect = TaskArchitect(user_id=user_id)
    blueprint = await architect.analyse_task(task)

    # Publish to dashboard for visual DAG display
    await architect.publish_blueprint(blueprint)

    # Format as a clear plan the root can follow
    lines = [f"Plan '{blueprint.pipeline_id}' — {len(blueprint.stages)} stage(s):\n"]
    step = 1
    for stage in blueprint.stages:
        lines.append(f"Stage: {stage.name} ({stage.stage_type})")
        for t in stage.tasks:
            lines.append(f"  Step {step}: [{t.persona_id}] {t.description}")
            step += 1
        lines.append("")

    lines.append(
        "Execute by transferring to each persona in order using transfer_to_agent. "
        "Pass the step instruction as context in your message to the persona."
    )
    return "\n".join(lines)


def get_task_planner_tool() -> FunctionTool:
    """Return the plan_task tool for the root agent."""
    return FunctionTool(plan_task)

