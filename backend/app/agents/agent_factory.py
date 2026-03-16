"""Dynamic agent creation from a persona config.

``create_agent`` turns a :class:`PersonaResponse` (from Firestore or the
default list) into a fully-configured ADK ``Agent`` with the correct voice,
system instruction, and tool set.

This is intentionally the *only* place ADK ``Agent`` objects are
instantiated so the rest of the codebase stays testable without importing
the heavy ADK/genai stack.
"""

from __future__ import annotations

from collections.abc import Callable

from google.adk.agents import Agent
from google.genai import types

from app.config import settings
from app.middleware.agent_callbacks import (
    after_agent_callback,
    before_agent_callback,
    context_injection_callback,
    cost_estimation_callback,
    permission_check_callback,
)
from app.models.persona import PersonaResponse
from app.models.plugin import ToolCapability as TC
from app.tools.capabilities_tool import get_capability_tools
from app.tools.code_exec import get_code_exec_tools
from app.tools.cross_client import get_cross_client_tools
from app.tools.desktop_tools import get_desktop_tools
from app.tools.genui_schema import get_genui_schema_tools
from app.tools.image_gen import get_image_gen_tools
from app.tools.search import get_search_tool
from app.tools.task_tools import get_human_input_tools, get_planned_task_tools
from app.utils.logging import get_logger

logger = get_logger(__name__)

# Model names — configurable via env vars LIVE_MODEL / TEXT_MODEL
LIVE_MODEL = settings.LIVE_MODEL
TEXT_MODEL = settings.TEXT_MODEL

# ── Capability → T1 tool factory mapping ──────────────────────────────
# Each capability tag maps to a factory function that returns a list of
# ADK tools.  Persona.capabilities drives which T1 tools it receives.
T1_TOOL_REGISTRY: dict[str, Callable[[], list]] = {
    TC.SEARCH: lambda: [get_search_tool()],
    TC.CODE_EXECUTION: get_code_exec_tools,
    TC.MEDIA: get_image_gen_tools,
    TC.DEVICE: lambda: get_cross_client_tools(),
    TC.DESKTOP: get_desktop_tools,
    TC.TASK: get_planned_task_tools,
    TC.WILDCARD: lambda: [*get_capability_tools(), *get_human_input_tools()],
    TC.GENUI: get_genui_schema_tools,
}

# ── Built-in persona ID → capability mapping ─────────────────────────
# When _default_tools_for_persona receives a string persona ID (e.g. in
# tests), we resolve capabilities from this mapping.

_CODE_EXEC_PERSONA_IDS: frozenset[str] = frozenset({"coder", "analyst"})

# ── Per-persona model overrides (for REST / non-live sessions) ────────
# In live (streaming) sessions, the runner's live model takes precedence
# and these overrides are ignored.  For REST / text sessions, the agent
# uses the override model for better specialization.
_MODEL_OVERRIDES: dict[str, str] = {
    "genui": "gemini-3.1-flash-lite-preview",
}

_PERSONA_CAPABILITIES: dict[str, list[str]] = {
    "assistant": [TC.COMMUNICATION, TC.TASK, TC.WILDCARD],
    "coder": [TC.CODE_EXECUTION, TC.DESKTOP, TC.TASK, TC.WILDCARD],
    "researcher": [TC.SEARCH, TC.TASK, TC.WILDCARD],
    "analyst": [TC.SEARCH, TC.CODE_EXECUTION, TC.DESKTOP, TC.TASK, TC.WILDCARD],
    "creative": [TC.MEDIA, TC.TASK, TC.WILDCARD],
    "genui": [TC.CODE_EXECUTION, TC.TASK, TC.WILDCARD, TC.GENUI],
}


def get_tools_for_capabilities(capabilities: list[str]) -> list:
    """Return T1 tools matching any of the given capability tags."""
    tools: list = []
    seen: set[str] = set()
    for cap in capabilities:
        if cap in seen:
            continue
        factory = T1_TOOL_REGISTRY.get(cap)
        if factory:
            seen.add(cap)
            tools.extend(factory())
    return tools


def _build_speech_config(voice_name: str) -> types.SpeechConfig:
    """Build a ``SpeechConfig`` for a prebuilt Gemini voice."""
    return types.SpeechConfig(
        voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                voice_name=voice_name,
            ),
        ),
    )


def _default_tools_for_persona(persona: PersonaResponse | str) -> list:
    """Return T1 tools matched by the persona's capability tags.

    Accepts a :class:`PersonaResponse` or a string persona ID (resolved
    via ``_PERSONA_CAPABILITIES``).

    Always prefers the authoritative ``_PERSONA_CAPABILITIES`` mapping
    over the persona's own ``capabilities`` field (which is for UI
    categorization, not tool assignment).
    """
    if isinstance(persona, str):
        caps = _PERSONA_CAPABILITIES.get(persona, [])
    else:
        # Always use _PERSONA_CAPABILITIES for known personas to avoid
        # UI category labels (like "knowledge", "productivity") being
        # misinterpreted as tool capability tags.
        caps = _PERSONA_CAPABILITIES.get(persona.id, persona.capabilities or [])
    return get_tools_for_capabilities(caps)


def create_agent(
    persona: PersonaResponse,
    extra_tools: list | None = None,
    model: str | None = None,
) -> Agent:
    """Build an ADK ``Agent`` from a persona configuration.

    Parameters
    ----------
    persona:
        A :class:`PersonaResponse` with at least ``id``, ``name``,
        ``voice``, and ``system_instruction``.
    extra_tools:
        Pre-filtered T2 plugin tools matched by capability tags.
        Only tools whose tags intersect with persona.capabilities are passed.
    model:
        Override the default model. Defaults to ``LIVE_MODEL``.

    Returns
    -------
    Agent
        A configured ADK agent ready for use as a sub-agent of the root.
    """
    tools = _default_tools_for_persona(persona)
    if extra_tools:
        # Deduplicate: T2 plugin tools may overlap with T1 tools (e.g. E2B
        # plugin provides execute_code which is already a T1 CODE_EXECUTION
        # tool).  Gemini Live API rejects duplicate function declarations.
        existing = {getattr(t, "name", str(t)) for t in tools}
        for t in extra_tools:
            if getattr(t, "name", str(t)) not in existing:
                tools.append(t)

    # Use persona-specific model override ONLY for non-live (text) sessions.
    # In live mode, all sub-agents MUST use a live-capable model because ADK
    # opens a new live WebSocket connection using the sub-agent's `.model`.
    effective_model = model or LIVE_MODEL
    is_live_session = effective_model == LIVE_MODEL
    if persona.id in _MODEL_OVERRIDES and not is_live_session:
        effective_model = _MODEL_OVERRIDES[persona.id]

    # Build a strict tool list addendum so the persona never hallucinates tool names
    tool_names = sorted({getattr(t, "name", str(t)) for t in tools})
    # Escape curly braces so ADK's template engine doesn't treat them as variables
    safe_tool_names = [n.replace("{", "{{").replace("}", "}}") for n in tool_names]
    # Always include transfer_to_agent — ADK auto-injects it for parent/peer transfer
    if "transfer_to_agent" not in safe_tool_names:
        safe_tool_names.append("transfer_to_agent")
        safe_tool_names.sort()
    tool_guard = (
        "\n\nSTRICT TOOL REGISTRY: You can ONLY call these tools: "
        + ", ".join(safe_tool_names)
        + ". Do NOT call any tool name not in this list — if a user request needs a tool "
        "you don't have, transfer to omni_root with context of what the user wants."
    ) if tool_names else ""

    # Add escalation instruction so personas hand off out-of-scope requests
    # with full context of what the user asked — the receiving agent sees
    # the text emitted before the transfer_to_agent call in conversation history.
    escalation_instruction = (
        "\n\n## TRANSFER PROTOCOL — Out-of-Scope Requests\n"
        "If the user asks for something you CANNOT do (missing tool, different specialty, "
        "device control, image generation, desktop streaming, search, etc.):\n\n"
        "1. **Say what the user needs** — emit a short text message summarizing the request, e.g.:\n"
        '   "The user wants to generate an image of a sunset. Transferring to the right specialist."\n'
        "2. **Transfer immediately** — call transfer_to_agent with the target:\n"
        "   - `transfer_to_agent(agent_name='omni_root')` — when unsure who should handle it.\n"
        "   - Or transfer directly to a sibling if obvious: 'coder', 'researcher', 'creative', "
        "'analyst', 'genui', 'device_agent'.\n\n"
        "**RULES:**\n"
        "- NEVER attempt a task you lack tools for — always transfer.\n"
        "- NEVER say 'I can't do that' or 'tool not found' — just transfer with context.\n"
        "- NEVER say 'no devices connected' for desktop/streaming requests — transfer to root.\n"
        "- The text you emit BEFORE the transfer becomes context for the next agent.\n"
        "- After your task is complete and there's nothing more to do, "
        "transfer back: transfer_to_agent(agent_name='omni_root')."
    )

    base_instruction = persona.system_instruction or f"You are {persona.name}."

    agent = Agent(
        name=persona.id,
        model=effective_model,
        description=f"{persona.name} — {', '.join(persona.capabilities or [])} specialist",
        instruction=base_instruction + escalation_instruction + tool_guard,
        tools=tools,
        before_model_callback=context_injection_callback,
        after_model_callback=cost_estimation_callback,
        before_tool_callback=permission_check_callback,
        before_agent_callback=before_agent_callback,
        after_agent_callback=after_agent_callback,
    )
    logger.info(
        "agent_created",
        persona_id=persona.id,
        name=persona.name,
        voice=persona.voice,
        tool_count=len(tools),
    )
    return agent


def get_speech_config(persona: PersonaResponse) -> types.SpeechConfig:
    """Return the ``SpeechConfig`` for a persona (used in ``RunConfig``)."""
    return _build_speech_config(persona.voice)
