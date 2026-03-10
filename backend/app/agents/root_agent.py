"""Root router agent — ADK Agent that delegates to persona sub-agents.

The root agent acts as a lightweight dispatcher.  When a user switches
personas the corresponding sub-agent is looked up and attached.  In live
(bidi-streaming) mode, ADK's ``run_live()`` handles audio routing while
the root decides which sub-agent should respond.

Usage
-----
::

    from app.agents.root_agent import build_root_agent
    root = build_root_agent(personas)
    # Pass to Runner(agent=root, ...)
"""

from __future__ import annotations

from google.adk.agents import Agent

from app.agents.agent_factory import LIVE_MODEL, create_agent
from app.agents.personas import get_default_personas
from app.models.persona import PersonaResponse
from app.utils.logging import get_logger

logger = get_logger(__name__)

ROOT_INSTRUCTION = (
    "You are Omni, a multi-persona AI hub. "
    "Route the user's request to the most appropriate specialist persona. "
    "If the user explicitly asks for a persona by name, switch to it. "
    "Otherwise, use your judgement based on the topic."
)


def build_root_agent(
    personas: list[PersonaResponse] | None = None,
) -> Agent:
    """Construct the root ADK agent with persona sub-agents.

    Parameters
    ----------
    personas:
        Persona configs to register as sub-agents.  Falls back to the
        five built-in defaults when *None*.

    Returns
    -------
    Agent
        A root agent whose ``sub_agents`` are the persona agents.
    """
    if personas is None:
        personas = get_default_personas()

    sub_agents = [create_agent(p) for p in personas]
    names = [a.name for a in sub_agents]

    root = Agent(
        name="omni_root",
        model=LIVE_MODEL,
        instruction=ROOT_INSTRUCTION,
        sub_agents=sub_agents,
    )
    logger.info("root_agent_built", sub_agents=names)
    return root
