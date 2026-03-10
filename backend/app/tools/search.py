"""Google Search grounding tool for ADK agents.

Provides grounded, citation-backed responses via Gemini's native Google
Search integration.  The ADK built-in ``google_search`` tool injects a
``GoogleSearch`` tool declaration into the LLM request so Gemini can
autonomously decide when to search.  Responses include
``grounding_metadata`` with source URLs and inline citations.

Usage::

    from app.tools.search import get_search_tool, get_search_tools

    # Single pre-configured instance
    tool = get_search_tool()

    # All search-related tools as a list
    tools = get_search_tools()

    # Use in an ADK Agent
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
from google.adk.tools.google_search_tool import GoogleSearchTool

from app.utils.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Pre-configured singleton
# ---------------------------------------------------------------------------

# ``bypass_multi_tools_limit=True`` allows google_search to coexist with
# other function-call tools on the same agent (e.g. code_exec, MCP tools).
_search_tool: GoogleSearchTool | None = None


def get_search_tool() -> GoogleSearchTool:
    """Return a re-usable ``GoogleSearchTool`` instance.

    The instance has ``bypass_multi_tools_limit`` enabled so it can be
    combined with other tools on the same agent without hitting Gemini's
    single-tool-type restriction.
    """
    global _search_tool
    if _search_tool is None:
        _search_tool = GoogleSearchTool(bypass_multi_tools_limit=True)
        logger.info("google_search_tool_initialized")
    return _search_tool


def get_search_tools() -> list[GoogleSearchTool]:
    """Return all search-related tools as a list.

    Currently returns only the Google Search grounding tool.  Can be
    extended to include Google Maps grounding when needed.
    """
    return [get_search_tool()]


# Re-export the ADK built-in for convenience (exact singleton from ADK)
builtin_google_search = _builtin_google_search

__all__ = [
    "GoogleSearchTool",
    "builtin_google_search",
    "get_search_tool",
    "get_search_tools",
]
