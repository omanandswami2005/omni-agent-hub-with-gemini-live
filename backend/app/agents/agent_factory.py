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

from app.config import settings
from app.models.persona import PersonaResponse
from app.tools.code_exec import get_code_exec_tools
from app.tools.cross_client import get_cross_client_tools
from app.tools.image_gen import get_image_gen_tools
from app.tools.search import get_search_tool
from app.utils.logging import get_logger

logger = get_logger(__name__)

# Model names — configurable via env vars LIVE_MODEL / TEXT_MODEL
LIVE_MODEL = settings.LIVE_MODEL
TEXT_MODEL = settings.TEXT_MODEL

# Persona IDs that get Google Search grounding by default
_SEARCH_PERSONA_IDS = {"assistant", "researcher", "analyst"}

# Persona IDs that get code execution tools
_CODE_EXEC_PERSONA_IDS = {"coder", "analyst"}

# Persona IDs that get image generation tools (all personas can generate images)
_IMAGE_GEN_PERSONA_IDS = {"creative", "assistant", "researcher", "analyst", "coder"}

# RAG tools are now in the 'rag-documents' plugin — enable via plugin store
# (removed from hardcoded agent_factory)


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
    tools: list = []
    if persona_id in _SEARCH_PERSONA_IDS:
        tools.append(get_search_tool())
    if persona_id in _CODE_EXEC_PERSONA_IDS:
        tools.extend(get_code_exec_tools())
    if persona_id in _IMAGE_GEN_PERSONA_IDS:
        tools.extend(get_image_gen_tools())
    # All personas get cross-client action tools
    tools.extend(get_cross_client_tools())
    return tools


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
        Additional tools to include (e.g., MCP tools from get_mcp_manager().get_tools()).
    model:
        Override the default model. Defaults to ``LIVE_MODEL``.

    Returns
    -------
    Agent
        A configured ADK agent ready for use as a sub-agent of the root.
    """
    tools = _default_tools_for_persona(persona.id)
    if extra_tools:
        tools.extend(extra_tools)

    agent = Agent(
        name=persona.id,
        model=model or LIVE_MODEL,
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
