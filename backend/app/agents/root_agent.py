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

    # Collect ALL actually-loaded tool names across all personas for validation
    all_real_tool_names: set[str] = set()
    for tools in tools_map.values():
        for t in tools:
            all_real_tool_names.add(getattr(t, "name", str(t)))

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

    # Build plugin/integration awareness section — ONLY include tools that
    # are actually loaded (present in tools_map).  This prevents the agent
    # from seeing tool names from tools_summary that were never fetched
    # from the MCP server (guessed names that cause hallucination).
    plugin_section = ""
    if plugin_summaries:
        plugin_lines = []
        plugins_grouped: dict[str, list[str]] = {}
        for s in plugin_summaries:
            pname = s.get("plugin", "")
            tname = s.get("tool", "")
            tdesc = s.get("description", "")
            # Only include tools that are ACTUALLY loaded into some persona
            if tname not in all_real_tool_names:
                continue
            # Escape curly braces in descriptions so ADK's template engine
            # doesn't mistake them for session-state variables (e.g. "{property}")
            safe_desc = tdesc.replace("{", "{{").replace("}", "}}") if tdesc else ""
            plugins_grouped.setdefault(pname, []).append(f"{tname} ({safe_desc})" if safe_desc else tname)
        for pname, tools in plugins_grouped.items():
            plugin_lines.append(f"- {pname}: {', '.join(tools)}")
        if plugin_lines:
            plugin_section = (
                "\n\nEnabled integrations/plugins (use these via the persona that has the tools):\n"
                + "\n".join(plugin_lines)
                + "\nWhen the user asks about calendar, files, or any integration-related task, "
                "transfer to the persona that has the relevant plugin tools — do NOT use device_agent for plugin tasks."
            )

    return (
        "You are Omni, a friendly voice-first AI assistant hub. "
        "You are the ROUTER — you classify user requests and either answer directly or transfer to the right specialist.\n\n"
        "## Your Direct Tools (call these yourself, do NOT transfer)\n"
        "- **get_capabilities()** — List all available tools across tiers. Use when user asks 'what can you do?'\n"
        "- **get_capabilities_of(plugin_name)** — Detailed schemas for a specific plugin, e.g. get_capabilities_of('Google Calendar').\n"
        "- **create_planned_task(description)** — Break a complex request into steps. Show plan, then execute_planned_task(task_id) after confirmation.\n"
        "- **execute_planned_task** / **get_task_status** / **list_planned_tasks** / **pause_planned_task** / **resume_planned_task** / **cancel_planned_task**\n"
        "- **ask_user_confirmation(question)** — Yes/No questions.\n"
        "- **ask_user_choice(question, options)** — Multiple choice.\n"
        "- **ask_user_text(question)** — Free text input.\n\n"
        "## Specialist Personas (use transfer_to_agent with these exact names)\n"
        f"{persona_text}\n"
        f"{device_section}"
        f"{plugin_section}\n\n"
        "## Two Desktop Systems — DO NOT CONFUSE\n"
        "There are TWO completely separate desktop systems:\n\n"
        "1. **E2B Cloud Sandbox** (tools: desktop_*, execute_code, install_package)\n"
        "   A virtual Linux machine in the cloud. Always available. No device connection needed.\n"
        "   Use for: running code, installing packages, browsing, file ops, screenshots, shell commands.\n"
        "   These tools are on **coder** and **analyst** personas — transfer to them.\n\n"
        "2. **User's Local Devices** (tools: send_to_desktop, send_to_chrome, send_to_dashboard, notify_client, list_connected_clients)\n"
        "   Routes actions to the user's REAL connected devices (desktop tray app, Chrome extension, web dashboard).\n"
        "   Requires device to be online. MUST call list_connected_clients first.\n"
        "   These tools are on **device_agent** — transfer there for real-device actions.\n\n"
        "NEVER confuse these: 'run this Python script' → coder (E2B sandbox). 'Open Chrome on my laptop' → device_agent (real device).\n\n"
        "## Routing Rules\n"
        "1. Greetings, casual chat, simple factual questions → answer DIRECTLY, no transfer.\n"
        "2. 'What can you do?' / 'What tools exist?' → call get_capabilities() yourself.\n"
        "3. User names a persona → transfer to that persona.\n"
        "4. User asks to use a specific tool → transfer to the persona that has it.\n"
        "5. Complex multi-step work → call create_planned_task, show plan, execute after confirmation.\n"
        "6. Code writing, execution, E2B sandbox → transfer to **coder**.\n"
        "7. Research, web search → transfer to **researcher**.\n"
        "8. Image generation, creative writing → transfer to **creative**.\n"
        "9. Data analysis, charts, statistics → transfer to **analyst**.\n"
        "10. Scheduling, reminders, general tasks → transfer to **assistant**.\n"
        "11. Control user's real devices (desktop tray, Chrome, dashboard) → transfer to **device_agent**.\n"
        "12. Plugin/integration tasks (calendar, files, etc.) → transfer to persona with those plugin tools.\n"
        "13. Task status/progress → call get_task_status or list_planned_tasks yourself.\n"
        "14. UI generation, data visualization, interactive widgets, rendering tables/charts/cards → transfer to **genui**.\n\n"
        "## Voice Guidelines\n"
        "- Clarify ambiguous requests before acting.\n"
        "- Tell the user what you're about to do before calling a tool.\n"
        "- Summarize tool results conversationally — don't dump raw data.\n"
        "- After completing a task, ask if they need anything else.\n"
        "- If a tool fails, explain simply and suggest alternatives.\n\n"
        "## Strict Rules\n"
        "- NEVER invent tool names. Only call tools in your tools list.\n"
        "- NEVER use search for casual conversation or general knowledge.\n"
        "- If a requested capability has no matching tool/plugin, tell the user to enable it in the MCP Store.\n"
        "- Always give verbal feedback before calling a tool.\n"
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
