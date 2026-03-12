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

from app.agents.agent_factory import LIVE_MODEL, TEXT_MODEL, create_agent
from app.agents.personas import get_default_personas
from app.models.persona import PersonaResponse
from app.utils.logging import get_logger

logger = get_logger(__name__)

ROOT_INSTRUCTION = (
    "You are Omni, a multi-persona AI hub that routes requests to specialist personas. "
    "You MUST use the transfer_to_agent tool to delegate every user request to the correct persona. "
    "NEVER try to answer directly or call tools yourself — always transfer first.\n\n"
    "Available personas (use these exact names with transfer_to_agent):\n"
    "- assistant — Claire: general questions, scheduling, everyday help\n"
    "- researcher — Sage: Google Search, web research, Wikipedia, fact-finding, citations\n"
    "- coder — Dev: code generation, debugging, code execution (execute_code tool)\n"
    "- analyst — Nova: data analysis, charts, statistics, financial insights\n"
    "- creative — Muse: brainstorming, writing, image generation\n\n"
    "Routing rules:\n"
    "1. If the user names a persona explicitly (e.g. 'use the researcher'), transfer to that persona.\n"
    "2. For ANY search, research, or factual query → transfer to researcher.\n"
    "3. For code writing or execution → transfer to coder.\n"
    "4. For image generation → transfer to creative.\n"
    "5. For data/charts/analysis → transfer to analyst.\n"
    "6. For everything else → transfer to assistant.\n\n"
    "IMPORTANT: Do NOT invent tool names. You only have transfer_to_agent."
)


def build_root_agent(
    personas: list[PersonaResponse] | None = None,
    mcp_tools: list | None = None,
    model: str | None = None,
) -> Agent:
    """Construct the root ADK agent with persona sub-agents.

    Parameters
    ----------
    personas:
        Persona configs to register as sub-agents.  Falls back to the
        five built-in defaults when *None*.
    mcp_tools:
        Additional MCP tools to include in the root agent.
    model:
        Override the default model for root + sub-agents.
        Defaults to ``LIVE_MODEL``.

    Returns
    -------
    Agent
        A root agent whose ``sub_agents`` are the persona agents.
    """
    effective_model = model or LIVE_MODEL
    if personas is None:
        personas = get_default_personas()

    sub_agents = [create_agent(p, mcp_tools, model=effective_model) for p in personas]
    names = [a.name for a in sub_agents]

    root = Agent(
        name="omni_root",
        model=effective_model,
        instruction=ROOT_INSTRUCTION,
        sub_agents=sub_agents,
        # Root agent has NO tools — it only routes via transfer_to_agent.
        # MCP tools are given to sub-agents via extra_tools in create_agent.
    )
    logger.info("root_agent_built", sub_agents=names, mcp_tool_count=len(mcp_tools or []))
    return root
