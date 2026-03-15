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
from app.middleware.agent_callbacks import (
    after_agent_callback,
    before_agent_callback,
    context_injection_callback,
    cost_estimation_callback,
    permission_check_callback,
)
from app.models.persona import PersonaResponse
from app.tools.capabilities_tool import get_capability_tools
from app.tools.task_tools import get_human_input_tools, get_planned_task_tools
from app.utils.logging import get_logger

logger = get_logger(__name__)


def _build_root_instruction(
    persona_names: list[tuple[str, str]], has_device: bool, tools_map: dict[str, list],
    plugin_summaries: list[dict] | None = None,
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

    # Build plugin/integration awareness section
    plugin_section = ""
    if plugin_summaries:
        plugin_lines = []
        # Group by plugin
        plugins_grouped: dict[str, list[str]] = {}
        for s in plugin_summaries:
            pname = s.get("plugin", "")
            tname = s.get("tool", "")
            tdesc = s.get("description", "")
            plugins_grouped.setdefault(pname, []).append(f"{tname} ({tdesc})" if tdesc else tname)
        for pname, tools in plugins_grouped.items():
            plugin_lines.append(f"- {pname}: {', '.join(tools)}")
        plugin_section = (
            "\n\nEnabled integrations/plugins (use these via the persona that has the tools):\n"
            + "\n".join(plugin_lines)
            + "\nWhen the user asks about calendar, files, or any integration-related task, "
            "transfer to the persona that has the relevant plugin tools — do NOT use device_agent for plugin tasks."
        )

    return (
        "You are Omni, a friendly and capable AI hub. "
        "For simple greetings, casual conversation, or short factual questions you already know the answer to, "
        "respond DIRECTLY without calling any tool or transferring. "
        "Only use transfer_to_agent when a specialist agent is genuinely needed.\n\n"
        "Available personas (use these exact names with transfer_to_agent) and their specific tools:\n"
        f"{persona_text}\n"
        f"{device_section}"
        f"{plugin_section}\n\n"
        "## Planned Task System\n"
        "You have a TASK PLANNING system. Use it for complex multi-step requests:\n"
        "- **create_planned_task(description, auto_execute=False)** — Decomposes a complex request into "
        "a step-by-step plan, stores it in the database, and optionally auto-executes it. "
        "Returns the plan with step IDs. The task runs ASYNCHRONOUSLY in the background.\n"
        "- **execute_planned_task(task_id)** — Start executing a planned task after user confirms.\n"
        "- **get_task_status(task_id)** — Check progress of a running task.\n"
        "- **list_planned_tasks()** — Show all user's tasks.\n"
        "- **pause_planned_task(task_id)** / **resume_planned_task(task_id)** / **cancel_planned_task(task_id)**\n\n"
        "## Human-in-the-Loop\n"
        "When you need user input during execution:\n"
        "- **ask_user_confirmation(question)** — Yes/No questions\n"
        "- **ask_user_choice(question, options)** — Multiple choice\n"
        "- **ask_user_text(question)** — Free text input\n\n"
        "## Capability Introspection\n"
        "- **get_capabilities()** — Overview of ALL available tools (T1/T2/T3).\n"
        "- **get_capabilities_of(plugin_name)** — Full schemas for a specific plugin/tier.\n\n"
        "Routing rules:\n"
        "0. Greetings, pleasantries, 'how are you?' — answer DIRECTLY, no transfer.\n"
        "0a. 'What can you do?' / 'What tools do you have?' — call get_capabilities() DIRECTLY, no transfer.\n"
        "1. If the user asks to use a specific tool, transfer to the persona that has that tool available!\n"
        "2. If the user names a persona explicitly, transfer to that persona.\n"
        "3. For complex multi-step requests → call create_planned_task first. Show the plan to the user.\n"
        "   If the user confirms, call execute_planned_task. The task runs in the background.\n"
        "4. For device control, sending to desktop/chrome/dashboard → transfer to device_agent.\n"
        "5. For plugin/integration tasks (calendar, files, etc.) → transfer to the persona with those tools.\n"
        "6. For deep research → transfer to researcher.\n"
        "7. For code writing or execution → transfer to coder.\n"
        "8. For image generation → transfer to creative.\n"
        "9. For data/charts/analysis → transfer to analyst.\n"
        "10. For scheduling, email, general tasks → transfer to assistant.\n"
        "11. When user asks about task status/progress → call get_task_status or list_planned_tasks.\n\n"
        "IMPORTANT: Do NOT use Google Search for casual conversation. "
        "Do NOT invent tool names."
    )


def build_root_agent(
    personas: list[PersonaResponse] | None = None,
    tools_by_persona: dict[str, list] | None = None,
    model: str | None = None,
    # Legacy compat for callers that haven't migrated yet
    mcp_tools: list | None = None,
    plugin_summaries: list[dict] | None = None,
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
    plugin_summaries:
        Lightweight plugin tool summaries for agent awareness.
    """
    effective_model = model or LIVE_MODEL
    if personas is None:
        personas = get_default_personas()

    tools_map = tools_by_persona or {}

    # ── Layer 1: Persona sub-agents with capability-matched T2 tools ──
    sub_agents: list[Agent] = []
    persona_names: list[tuple[str, str]] = []

    for p in personas:
        # Decide T2 tools for this persona (legacy path: flat mcp_tools for all)
        extra = tools_map.get(p.id, []) if tools_by_persona is not None else mcp_tools

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

    # ── Layer 2: Task planner + capability tools on the root ─────────
    root_tools = [
        *get_planned_task_tools(),
        *get_human_input_tools(),
        *get_capability_tools(),
    ]

    # ── Layer 0: Root router ──────────────────────────────────────────
    instruction = _build_root_instruction(persona_names, has_device, tools_map, plugin_summaries)

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
