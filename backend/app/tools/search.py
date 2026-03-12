"""Google Search grounding tool for ADK agents.

Provides grounded, citation-backed responses via Gemini's native Google
Search integration.  Uses ADK's ``GoogleSearchAgentTool`` wrapper so the
search tool can safely coexist with other function-call tools on any
agent — regardless of how many explicit tools the agent has.

The wrapper runs an internal ``google_search_agent`` sub-agent that calls
``generateContent`` with only the ``GoogleSearch`` built-in tool,
avoiding Vertex AI's "Multiple tools must all be search tools" restriction.
Grounding metadata (source URLs, inline citations) flows back through
ADK session state (``temp:_adk_grounding_metadata``).

Usage::

    from app.tools.search import get_search_tool, get_search_tools

    tool = get_search_tool()
    agent = Agent(name="sage", tools=[tool], ...)

Compliance
----------
When displaying grounded responses in the UI, the dashboard **must**:

1. Render *Search Suggestions* chips exactly as returned (light + dark).
2. Keep chips visible while the grounded response is shown.
3. Chips link directly to Google Search results on tap.

See: https://ai.google.dev/gemini-api/docs/grounding/search-suggestions
"""

from __future__ import annotations

from google.adk.tools import google_search as _builtin_google_search
from google.adk.tools.google_search_agent_tool import (
    GoogleSearchAgentTool,
    create_google_search_agent,
)
from google.adk.tools.google_search_tool import GoogleSearchTool

from app.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Pre-configured singleton — always uses TEXT_MODEL for generateContent
# ---------------------------------------------------------------------------

_search_tool: GoogleSearchAgentTool | None = None


def get_search_tool() -> GoogleSearchAgentTool:
    """Return a re-usable ``GoogleSearchAgentTool`` instance.

    Uses ``TEXT_MODEL`` (``gemini-2.5-flash``) for the internal search
    sub-agent so it works correctly in both text-chat (``run_async``)
    and live-audio (``run_live``) flows.  The live audio model does not
    support ``generateContent``, so using TEXT_MODEL here is required.
    """
    global _search_tool
    if _search_tool is None:
        agent = create_google_search_agent(model=settings.TEXT_MODEL)
        _search_tool = GoogleSearchAgentTool(agent)
        logger.info("google_search_agent_tool_initialized", model=settings.TEXT_MODEL)
    return _search_tool


def get_search_tools() -> list[GoogleSearchAgentTool]:
    """Return all search-related tools as a list."""
    return [get_search_tool()]


# Re-export the ADK built-in for convenience (exact singleton from ADK)
builtin_google_search = _builtin_google_search

__all__ = [
    "GoogleSearchAgentTool",
    "GoogleSearchTool",
    "builtin_google_search",
    "get_search_tool",
    "get_search_tools",
]
