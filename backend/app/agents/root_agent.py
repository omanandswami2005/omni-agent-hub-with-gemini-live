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
from app.tools.cross_client import get_cross_client_tools
from app.middleware.agent_callbacks import (
    after_agent_callback,
    before_agent_callback,
    context_injection_callback,
    cost_estimation_callback,
    tool_activity_after_callback,
    tool_activity_before_callback,
)
from app.models.persona import PersonaResponse
from app.tools.capabilities_tool import get_capability_tools
from app.tools.task_tools import get_human_input_tools, get_planned_task_tools
from app.utils.logging import get_logger

logger = get_logger(__name__)


def _build_root_instruction(
    persona_names: list[tuple[str, str]],
) -> str:
    """Build a lightweight root instruction — capabilities discovered on demand."""

    persona_text = "\n".join(f"- **{pid}** — {pname}" for pid, pname in persona_names)

    return (
        "You are Omni, a friendly voice-first AI assistant hub.\n"
        "You are the ROUTER — classify requests and either answer directly or transfer to the right specialist.\n\n"
        "## Capability Discovery\n"
        "Call **get_capabilities()** to see all available tools (core, plugins, device-local).\n"
        "Call **get_capabilities_of(name)** for full parameter schemas of a specific plugin or tier.\n"
        "Use these BEFORE acting when you're unsure what's available.\n\n"
        "## Specialist Personas (transfer_to_agent)\n"
        f"{persona_text}\n\n"
        "## Routing Rules\n"
        "1. Greetings, casual chat, factual questions → answer DIRECTLY.\n"
        "2. 'What can you do?' → call **get_capabilities()**.\n"
        "3. User names a persona → transfer to that persona.\n"
        "4. Code, execution, E2B sandbox → transfer to **coder**.\n"
        "5. Research, web search → transfer to **researcher**.\n"
        "6. Image generation, creative → transfer to **creative**.\n"
        "7. Data analysis, charts → transfer to **analyst**.\n"
        "8. Scheduling, reminders → transfer to **assistant**.\n"
        "9. UI generation, widgets, interactive visuals → transfer to **genui**.\n"
        "10. Complex multi-step work → call **create_planned_task()**, show plan, execute after confirmation.\n"
        "11. Device control (desktop tray, Chrome, dashboard) → call **list_connected_clients()** first, "
        "then call send_to_desktop / send_to_chrome / notify_client DIRECTLY (NO transfer).\n"
        "12. Desktop-local tasks (files, apps, commands, screen) → call the T3 tool DIRECTLY (NO transfer). "
        "These are reverse-RPC tools on your tools list.\n"
        "13. Plugin/integration tasks → transfer to persona that has the plugin tools.\n"
        "14. If unsure which tool or persona → call **get_capabilities()** first, then route.\n\n"
        "## Two Desktop Systems — DO NOT CONFUSE\n"
        "1. **E2B Cloud Sandbox** (coder/analyst personas) — virtual Linux machine, always available.\n"
        "2. **User's Real Devices** (your direct tools) — requires device online, call list_connected_clients first.\n"
        "'Run Python' → coder. 'Open Chrome on my laptop' → your send_to_desktop tool.\n\n"
        "## Rules\n"
        "- NEVER invent tool names. Only call tools in your tools list or transfer to a persona.\n"
        "- Tell the user what you're doing before calling a tool.\n"
        "- Summarize results conversationally.\n"
        "- If unsure about available capabilities, call get_capabilities().\n"
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
        **Deprecated** — no longer baked into instruction. Capabilities
        are discovered on-demand via ``get_capabilities()``.
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
    device_agent = build_cross_client_agent(
        device_tools=device_tools,
        model=effective_model,
    )
    sub_agents.append(device_agent)

    # ── Layer 2: Task planner + capability + cross-client + T3 tools on root ─
    # Cross-client AND T3 (device-local) tools live on root directly because
    # agent transfers break the Gemini Live bidi stream (run_live restarts
    # on transfer).  Same fix applied for cross-client tools earlier.
    root_tools = [
        *get_planned_task_tools(),
        *get_human_input_tools(),
        *get_capability_tools(),
        *get_cross_client_tools(),
        *(device_tools or []),
    ]

    # ── Build full tools map (T1 + T2) for instruction generation ─────
    # No longer needed — lightweight instruction discovers capabilities
    # on demand via get_capabilities() instead of baking tool names in.

    # ── Layer 0: Root router ──────────────────────────────────────────
    instruction = _build_root_instruction(persona_names)

    root = Agent(
        name="omni_root",
        model=effective_model,
        instruction=instruction,
        sub_agents=sub_agents,
        tools=root_tools,
        before_model_callback=context_injection_callback,
        after_model_callback=cost_estimation_callback,
        before_tool_callback=tool_activity_before_callback,
        after_tool_callback=tool_activity_after_callback,
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
