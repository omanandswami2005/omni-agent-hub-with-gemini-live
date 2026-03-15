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
from app.tools.email import get_email_tools
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
    TC.COMMUNICATION: get_email_tools,
    TC.DEVICE: lambda: get_cross_client_tools(),
    TC.DESKTOP: get_desktop_tools,
    TC.TASK: get_planned_task_tools,
    TC.WILDCARD: lambda: [*get_capability_tools(), *get_human_input_tools()],
}

# ── Built-in persona ID → capability mapping ─────────────────────────
# When _default_tools_for_persona receives a string persona ID (e.g. in
# tests), we resolve capabilities from this mapping.

_CODE_EXEC_PERSONA_IDS: frozenset[str] = frozenset({"coder", "analyst"})

_PERSONA_CAPABILITIES: dict[str, list[str]] = {
    "assistant": [TC.COMMUNICATION, TC.DEVICE, TC.TASK, TC.WILDCARD],
    "coder": [TC.CODE_EXECUTION, TC.DESKTOP, TC.DEVICE, TC.TASK, TC.WILDCARD],
    "researcher": [TC.SEARCH, TC.DEVICE, TC.TASK, TC.WILDCARD],
    "analyst": [TC.SEARCH, TC.CODE_EXECUTION, TC.DESKTOP, TC.DEVICE, TC.TASK, TC.WILDCARD],
    "creative": [TC.MEDIA, TC.DEVICE, TC.TASK, TC.WILDCARD],
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
    """
    if isinstance(persona, str):
        caps = _PERSONA_CAPABILITIES.get(persona, [])
    else:
        caps = persona.capabilities or _PERSONA_CAPABILITIES.get(persona.id, [])
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
        tools.extend(extra_tools)

    # Build a strict tool list addendum so the persona never hallucinates tool names
    tool_names = sorted({getattr(t, "name", str(t)) for t in tools})
    # Escape curly braces so ADK's template engine doesn't treat them as variables
    safe_tool_names = [n.replace("{", "{{").replace("}", "}}") for n in tool_names]
    tool_guard = (
        "\n\nSTRICT TOOL REGISTRY: You can ONLY call these tools: "
        + ", ".join(safe_tool_names)
        + ". Do NOT call any tool name not in this list — if a tool is missing, "
        "tell the user to enable the relevant plugin."
    ) if tool_names else ""

    base_instruction = persona.system_instruction or f"You are {persona.name}."

    agent = Agent(
        name=persona.id,
        model=model or LIVE_MODEL,
        instruction=base_instruction + tool_guard,
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
