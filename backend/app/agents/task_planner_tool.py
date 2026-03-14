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


async def _build_tools_for_architect(user_id: str) -> dict[str, list]:
    """Build per-persona tool map for the TaskArchitect."""
    try:
        from app.agents.personas import get_default_personas
        from app.services.tool_registry import get_tool_registry

        personas = get_default_personas()
        return await get_tool_registry().build_for_session(user_id, personas)
    except Exception:
        logger.warning("plan_task_tool_build_failed", user_id=user_id, exc_info=True)
        return {}


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
    tools_by_persona = await _build_tools_for_architect(user_id)
    architect = TaskArchitect(user_id=user_id, tools_by_persona=tools_by_persona)
    blueprint = await architect.analyse_task(task)

    # Publish to dashboard for visual DAG display
    await architect.publish_blueprint(blueprint)

    # Build and execute the pipeline with live stage progress
    pipeline = architect.build_pipeline(blueprint)
    summary = await architect.execute_pipeline(blueprint, pipeline)

    # Format as a clear plan + execution result the root can relay
    lines = [f"Plan '{blueprint.pipeline_id}' — {len(blueprint.stages)} stage(s):\n"]
    step = 1
    for stage in blueprint.stages:
        lines.append(f"Stage: {stage.name} ({stage.stage_type})")
        for t in stage.tasks:
            lines.append(f"  Step {step}: [{t.persona_id}] {t.description}")
            step += 1
        lines.append("")

    lines.append("--- Execution Result ---")
    lines.append(summary[:4000])  # Truncate to avoid excessive context
    return "\n".join(lines)


def get_task_planner_tool() -> FunctionTool:
    """Return the plan_task tool for the root agent."""
    return FunctionTool(plan_task)
