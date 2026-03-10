"""Dynamic agent creation from a persona config.

``create_agent`` turns a :class:`PersonaResponse` (from Firestore or the
default list) into a fully-configured ADK ``Agent`` with the correct voice,
system instruction, and tool set.

This is intentionally the *only* place ADK ``Agent`` objects are
instantiated so the rest of the codebase stays testable without importing
the heavy ADK/genai stack.
"""

from __future__ import annotations

from google.adk.agents import Agent
from google.genai import types

from app.models.persona import PersonaResponse
from app.tools.search import get_search_tool
from app.utils.logging import get_logger

logger = get_logger(__name__)

# Live-capable native audio model
LIVE_MODEL = "gemini-2.5-flash-native-audio"
TEXT_MODEL = "gemini-2.5-flash"

# Persona IDs that get Google Search grounding by default
_SEARCH_PERSONA_IDS = {"assistant", "researcher", "analyst"}


def _build_speech_config(voice_name: str) -> types.SpeechConfig:
    """Build a ``SpeechConfig`` for a prebuilt Gemini voice."""
    return types.SpeechConfig(
        voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                voice_name=voice_name,
            ),
        ),
    )


def _default_tools_for_persona(persona_id: str) -> list:
    """Return default tools for a persona based on its ID."""
    tools = []
    if persona_id in _SEARCH_PERSONA_IDS:
        tools.append(get_search_tool())
    return tools


def create_agent(persona: PersonaResponse) -> Agent:
    """Build an ADK ``Agent`` from a persona configuration.

    Parameters
    ----------
    persona:
        A :class:`PersonaResponse` with at least ``id``, ``name``,
        ``voice``, and ``system_instruction``.

    Returns
    -------
    Agent
        A configured ADK agent ready for use as a sub-agent of the root.
    """
    tools = _default_tools_for_persona(persona.id)

    agent = Agent(
        name=persona.id,
        model=LIVE_MODEL,
        instruction=persona.system_instruction or f"You are {persona.name}.",
        tools=tools,
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
