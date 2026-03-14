"""Root router agent — 3-layer ADK Agent that routes to persona pool,
device controller, and task planner.

Layer 0 — Root (this agent): classify & route via transfer_to_agent
Layer 1 — Persona pool: each persona receives capability-matched T1+T2 tools
Layer 2 — TaskArchitect: plan_task tool for complex multi-step requests
Layer 3 — Device controller: cross-client + T3 proxy tools

Usage
-----
::

    from app.agents.root_agent import build_root_agent
    root = build_root_agent(personas, tools_by_persona={"coder": [...], ...})
    # Pass to Runner(agent=root, ...)
"""

from __future__ import annotations

from google.adk.agents import Agent

from app.agents.agent_factory import LIVE_MODEL, create_agent
from app.agents.cross_client_agent import build_cross_client_agent
from app.agents.personas import get_default_personas
from app.agents.task_planner_tool import get_task_planner_tool
from app.middleware.agent_callbacks import (
    after_agent_callback,
    before_agent_callback,
    context_injection_callback,
    cost_estimation_callback,
    permission_check_callback,
)
from app.models.persona import PersonaResponse
from app.utils.logging import get_logger

logger = get_logger(__name__)


def _build_root_instruction(
    persona_names: list[tuple[str, str]], has_device: bool, tools_map: dict[str, list]
) -> str:
    """Dynamically build the root instruction from active personas and their available tools."""

    # Build detailed persona list with their tools
    persona_lines = []
    for pid, pname in persona_names:
        tools = tools_map.get(pid, [])
        tool_names = [getattr(t, "name", str(t)) for t in tools] if tools else []
        if tool_names:
            persona_lines.append(f"- {pid} — {pname}. Available tools: {', '.join(tool_names)}")
        else:
            persona_lines.append(f"- {pid} — {pname}")

    persona_text = "\n".join(persona_lines)

    device_tools = tools_map.get("__device__", [])
    device_tool_names = [getattr(t, "name", str(t)) for t in device_tools] if device_tools else []
    device_tools_text = (
        f" Available tools: {', '.join(device_tool_names)}" if device_tool_names else ""
    )

    device_section = (
        "\n\nDevice actions:\n"
        f"- device_agent — controls connected devices (desktop, Chrome, web dashboard).{device_tools_text} "
        "Transfer here for any device-control, cross-client, or local tool requests."
        if has_device
        else ""
    )

    return (
        "You are Omni, a friendly and capable AI hub. "
        "For simple greetings, casual conversation, or short factual questions you already know the answer to, "
        "respond DIRECTLY without calling any tool or transferring. "
        "Only use transfer_to_agent when a specialist agent is genuinely needed.\n\n"
        "Available personas (use these exact names with transfer_to_agent) and their specific tools:\n"
        f"{persona_text}\n"
        f"{device_section}\n\n"
        "You also have a plan_task tool. Call it when the user request clearly "
        "requires MULTIPLE specialists working together (e.g. 'research X, write code, "
        "then make an image'). Pass only the `task` argument — the full user request. "
        "The tool returns an ordered plan; then transfer to each "
        "persona in order.\n\n"
        "Routing rules:\n"
        "0. Greetings, pleasantries, 'what can you do?', 'how are you?' — answer DIRECTLY, no transfer.\n"
        "1. If the user asks to use a specific tool, transfer to the persona that has that tool available!\n"
        "2. If the user names a persona explicitly, transfer to that persona.\n"
        "3. For complex multi-step requests → call plan_task first.\n"
        "4. For device control, sending to desktop/chrome/dashboard → transfer to device_agent.\n"
        "5. For deep research, complex analysis, or when the user EXPLICITLY asks to search/look up something → transfer to researcher.\n"
        "6. For code writing or execution → transfer to coder.\n"
        "7. For image generation → transfer to creative.\n"
        "8. For data/charts/analysis → transfer to analyst.\n"
        "9. For scheduling, email drafts, reminders, calendar, and general tasks → transfer to assistant.\n\n"
        "IMPORTANT: Do NOT use Google Search or any search for casual conversation, greetings, or questions you can answer from your training knowledge. "
        "Do NOT invent tool names. You only have transfer_to_agent and plan_task."
    )


def build_root_agent(
    personas: list[PersonaResponse] | None = None,
    tools_by_persona: dict[str, list] | None = None,
    model: str | None = None,
    # Legacy compat for callers that haven't migrated yet
    mcp_tools: list | None = None,
) -> Agent:
    """Construct the root ADK agent with 3-layer routing.

    Parameters
    ----------
    personas:
        Persona configs to register as sub-agents.  Falls back to
        defaults when *None*.
    tools_by_persona:
        Dict from ``ToolRegistry.build_for_session()``.
        Keys are persona_ids → list of T2 tools.
        ``__device__`` key → T3 proxy tools for the device agent.
    model:
        Override the default model.  Defaults to ``LIVE_MODEL``.
    mcp_tools:
        **Legacy** — flat tool list given to every persona (old behavior).
        Use ``tools_by_persona`` instead.
    """
    effective_model = model or LIVE_MODEL
    if personas is None:
        personas = get_default_personas()

    tools_map = tools_by_persona or {}

    # ── Layer 1: Persona sub-agents with capability-matched T2 tools ──
    sub_agents: list[Agent] = []
    persona_names: list[tuple[str, str]] = []

    for p in personas:
        # Decide T2 tools for this persona
        if tools_by_persona is not None:
            extra = tools_map.get(p.id, [])
        else:
            # Legacy path: flat mcp_tools for all personas
            extra = mcp_tools

        agent = create_agent(p, extra_tools=extra, model=effective_model)
        sub_agents.append(agent)
        persona_names.append((p.id, p.name))

    # ── Layer 3: Device controller (cross-client + T3) ────────────────
    device_tools = tools_map.get("__device__")
    has_device = True  # Always include device_agent (cross-client always available)
    device_agent = build_cross_client_agent(
        device_tools=device_tools,
        model=effective_model,
    )
    sub_agents.append(device_agent)

    # ── Layer 2: Task planner tool on the root ────────────────────────
    root_tools = [get_task_planner_tool()]

    # ── Layer 0: Root router ──────────────────────────────────────────
    instruction = _build_root_instruction(persona_names, has_device, tools_map)

    root = Agent(
        name="omni_root",
        model=effective_model,
        instruction=instruction,
        sub_agents=sub_agents,
        tools=root_tools,
        before_model_callback=context_injection_callback,
        after_model_callback=cost_estimation_callback,
        before_tool_callback=permission_check_callback,
        before_agent_callback=before_agent_callback,
        after_agent_callback=after_agent_callback,
    )

    agent_names = [a.name for a in sub_agents]
    t2_total = sum(len(tools_map.get(p.id, [])) for p in personas)
    logger.info(
        "root_agent_built",
        sub_agents=agent_names,
        t2_tool_distribution={p.id: len(tools_map.get(p.id, [])) for p in personas},
        t3_tool_count=len(device_tools or []),
        total_t2=t2_total,
    )
    return root
