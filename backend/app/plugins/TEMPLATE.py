"""Plugin Template — Copy this file to create a new Omni Hub plugin.

Steps:
  1. Copy this file:  cp TEMPLATE.py my_plugin.py
  2. Edit the MANIFEST below (id, name, description, etc.)
  3. Implement your tool functions
  4. Update `get_tools()` to return your FunctionTool instances
  5. Restart the backend — PluginRegistry auto-discovers the new plugin

MANIFEST Fields:
  id          Unique slug (e.g. "my-plugin"). Used in API calls & Firestore.
  name        Human-readable display name.
  description Short description shown in the plugin catalog UI.
  version     Semver string.
  author      Your name or team.
  category    PluginCategory enum (SEARCH, COMMUNICATION, CODING, etc.).
  kind        PluginKind.NATIVE for Python plugins.
              PluginKind.MCP_STDIO / MCP_HTTP for MCP servers.
              PluginKind.E2B for sandboxed execution.
  icon        Icon name for the UI (optional).
  module      Dotted Python import path to this file.
  factory     Name of the function that returns list[FunctionTool].
  tools_summary  List of ToolSummary for lightweight discovery.

Tool Function Contract:
  - Must be `async def` (ADK requirement for FunctionTool).
  - All parameters must have type annotations (str, int, float, bool, list, dict).
  - Must return `str` or `dict` — ADK serialises the return value.
  - Docstring becomes the tool description shown to the LLM — be specific.
  - The `user_id` parameter is auto-injected by ADK if present in the signature.
"""

from __future__ import annotations

from google.adk.tools import FunctionTool

from app.models.plugin import (
    PluginCategory,
    PluginKind,
    PluginManifest,
    ToolSummary,
)

# ---------------------------------------------------------------------------
# 1. Plugin manifest — PluginRegistry reads this at startup
# ---------------------------------------------------------------------------

MANIFEST = PluginManifest(
    id="my-plugin",  # unique slug
    name="My Plugin",  # display name
    description="Does something useful.",  # catalog description
    version="0.1.0",
    author="Your Name",
    category=PluginCategory.OTHER,  # pick the best fit
    kind=PluginKind.NATIVE,
    icon="puzzle",  # any icon name
    module="app.plugins.TEMPLATE",  # dotted path to THIS file
    factory="get_tools",  # function below
    tools_summary=[
        ToolSummary(
            name="my_tool",
            description="A brief one-liner for lightweight discovery",
        ),
    ],
)


# ---------------------------------------------------------------------------
# 2. Tool implementations — each becomes an LLM-callable function
# ---------------------------------------------------------------------------


async def my_tool(query: str) -> dict:
    """Describe what this tool does — the LLM reads this docstring.

    Args:
        query: What the user is looking for.

    Returns:
        A dict with the result.
    """
    # Your logic here
    return {"result": f"Processed: {query}"}


# ---------------------------------------------------------------------------
# 3. Factory — must return list[FunctionTool]
# ---------------------------------------------------------------------------


def get_tools() -> list[FunctionTool]:
    """Return all tools provided by this plugin."""
    return [
        FunctionTool(my_tool),
    ]
