"""Root router agent — ADK Agent that delegates to persona AgentTools.

The root agent uses AgentTool-wrapped persona agents instead of sub_agents
with transfer_to_agent.  This preserves the Gemini Live bidi stream (no
generator exhaustion on agent hand-offs) and provides clean state_delta
forwarding for GenUI/image results.

Architecture
------------
- Root agent: classifies requests, calls persona tools or built-in tools
- Persona AgentTools: each wraps an isolated Agent+Runner via AgentTool
- Device tools: cross-client + T3 proxy tools live on root directly
- Task planner: create_planned_task() also on root directly

Usage
-----
::

    from app.agents.root_agent import build_root_agent
    root = build_root_agent(personas, tools_by_persona={"coder": [...], ...})
    # Pass to Runner(agent=root, ...)
"""

from __future__ import annotations

from google.adk.agents import Agent
from google.adk.tools.agent_tool import AgentTool

from app.agents.agent_factory import LIVE_MODEL, create_agent
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
    root_tool_names: list[str],
) -> str:
    """Build a lightweight root instruction — delegates via AgentTool calls."""

    persona_text = "\n".join(
        f"- **{pid}(request)** — {pname}" for pid, pname in persona_names
    )
    non_persona_ids = {pid for pid, _ in persona_names}
    other_tools = sorted(t for t in root_tool_names if t not in non_persona_ids)
    other_list = ", ".join(other_tools) if other_tools else "(none)"

    return (
        "You are Omni, a friendly voice-first AI assistant hub.\n"
        "You are the ROUTER — classify requests and either answer directly "
        "or call the right specialist tool.\n\n"
        "## VOICE FEEDBACK (CRITICAL)\n"
        "You are voice-first. BEFORE calling ANY specialist tool, you MUST first speak a "
        "brief sentence telling the user what you're about to do. Examples:\n"
        "- 'Let me create that image for you.' → then call creative(request)\n"
        "- 'I'll generate that table now.' → then call genui(request)\n"
        "- 'Let me look that up.' → then call researcher(request)\n"
        "- 'I'll run that code for you.' → then call coder(request)\n"
        "Always acknowledge first, THEN call the tool in the same turn.\n\n"
        "## Specialist Tools (call with a natural-language request string)\n"
        f"{persona_text}\n\n"
        "## Routing Rules\n"
        "1. Greetings, casual chat, factual questions → answer DIRECTLY.\n"
        "2. 'What can you do?' → call **get_capabilities()**.\n"
        "3. Code, execution, E2B sandbox → **coder(request)**.\n"
        "4. Research, web search → **researcher(request)**.\n"
        "5. Image generation, creative → **creative(request)**.\n"
        "6. Data analysis → **analyst(request)**.\n"
        "7. Scheduling, reminders → **assistant(request)**.\n"
        "8. UI components, charts, tables, interactive visuals → **genui(request)**.\n"
        "9. Complex multi-step work → call **create_planned_task()** first.\n"
        "10. Device control (desktop, Chrome, dashboard) → call **list_connected_clients()** "
        "then use send_to_desktop / send_to_chrome / notify_client DIRECTLY.\n"
        "11. Desktop-local tasks (files, apps, screen) → call the T3 tool DIRECTLY.\n"
        "12. If unsure → call **get_capabilities()** first, then route.\n\n"
        "## Two Desktop Systems — DO NOT CONFUSE\n"
        "1. **E2B Cloud Sandbox** (coder/analyst tools) — virtual Linux, always available.\n"
        "2. **User's Real Devices** (your direct tools) — call list_connected_clients first.\n"
        "'Run Python' → coder. 'Open Chrome on my laptop' → send_to_desktop.\n\n"
        "## YOUR TOOL REGISTRY\n"
        f"Specialist tools: {', '.join(pid for pid, _ in persona_names)}.\n"
        f"Utility tools: {other_list}.\n"
        "You CANNOT call render_genui_component, get_genui_schema, execute_code, "
        "generate_image, google_search — these belong to specialist agents.\n\n"
        "## IMPORTANT DELIVERY RULES\n"
        "- When you call a specialist like genui(), it AUTOMATICALLY delivers results to the dashboard.\n"
        "- NEVER use send_to_dashboard to re-send GenUI, charts, tables, images, or code.\n"
        "- send_to_desktop / send_to_chrome / send_to_dashboard are ONLY for device actions.\n"
        "- After a specialist returns, just tell the user what was shown — do NOT re-deliver.\n"
    )


def build_root_agent(
    personas: list[PersonaResponse] | None = None,
    tools_by_persona: dict[str, list] | None = None,
    model: str | None = None,
    # Legacy compat for callers that haven't migrated yet
    mcp_tools: list | None = None,
    plugin_summaries: list[dict] | None = None,
) -> Agent:
    """Construct the root ADK agent with AgentTool-wrapped persona delegation.

    Parameters
    ----------
    personas:
        Persona configs to wrap as AgentTools.  Falls back to defaults
        when *None*.
    tools_by_persona:
        Dict from ``ToolRegistry.build_for_session()``.
        Keys are persona_ids → list of T2 tools.
        ``__device__`` key → T3 proxy tools placed on root directly.
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

    # ── Persona AgentTools — each persona wrapped in AgentTool ────────
    persona_agent_tools: list[AgentTool] = []
    persona_names: list[tuple[str, str]] = []

    for p in personas:
        # Decide T2 tools for this persona (legacy path: flat mcp_tools for all)
        extra = tools_map.get(p.id, []) if tools_by_persona is not None else mcp_tools

        agent = create_agent(p, extra_tools=extra, model=effective_model)
        persona_agent_tools.append(
            AgentTool(agent=agent, skip_summarization=True)
        )
        persona_names.append((p.id, p.name))

    # ── Device tools: cross-client + T3 on root directly ─────────────
    device_tools = tools_map.get("__device__")

    # ── Root tools: planning + capabilities + cross-client + T3 + AgentTools ─
    root_tools = [
        *get_planned_task_tools(),
        *get_human_input_tools(),
        *get_capability_tools(),
        *get_cross_client_tools(),
        *(device_tools or []),
        *persona_agent_tools,
    ]

    # ── Root agent ────────────────────────────────────────────────────
    root_tool_names = sorted({getattr(t, "name", str(t)) for t in root_tools})
    instruction = _build_root_instruction(persona_names, root_tool_names)

    root = Agent(
        name="omni_root",
        model=effective_model,
        instruction=instruction,
        tools=root_tools,
        before_model_callback=context_injection_callback,
        after_model_callback=cost_estimation_callback,
        before_tool_callback=tool_activity_before_callback,
        after_tool_callback=tool_activity_after_callback,
        before_agent_callback=before_agent_callback,
        after_agent_callback=after_agent_callback,
    )

    agent_names = [getattr(t, "name", "?") for t in persona_agent_tools]
    t2_total = sum(len(tools_map.get(p.id, [])) for p in personas)
    logger.info(
        "root_agent_built",
        persona_tools=agent_names,
        t2_tool_distribution={p.id: len(tools_map.get(p.id, [])) for p in personas},
        t3_tool_count=len(device_tools or []),
        total_t2=t2_total,
    )
    return root
