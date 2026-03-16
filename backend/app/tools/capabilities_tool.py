"""Capability introspection tools — let agents discover what they can do.

Two ADK ``FunctionTool`` instances are provided:

``get_capabilities``
    Returns a live markdown summary of **all** available tools across
    all three tiers (T1 core, T2 plugins/MCPs, T3 client-local).
    Always reflects the latest state — if the user just enabled a plugin,
    the next call returns the new tools immediately.

``get_capabilities_of``
    Returns the full function schema (name, description, parameters) for
    all tools provided by a single named plugin, MCP server, or tier
    (``"T1"``, ``"T2"``, ``"T3"``).

Both tools are given to the root agent and every persona sub-agent so
any layer of the routing hierarchy can answer "what can you do?".
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from google.adk.tools import FunctionTool
from google.adk.tools.tool_context import ToolContext

from app.utils.logging import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_user_id(tool_context: ToolContext | None) -> str:
    if tool_context is None:
        return ""
    return getattr(tool_context, "user_id", "") or ""


def _get_capabilities_data(user_id: str) -> dict:
    """Assemble the full capability map for *user_id*.

    Returns a structured dict with:
      - t1: list of {name, description, parameters}  — always-on core tools
      - t2: list of {plugin, plugin_id, kind, tool, description, parameters}
      - t3: list of {tool, description, parameters}  — client-local proxy tools
      - summary: short human-readable string
    """
    # Lazy imports to avoid circular deps at module load time
    from app.agents.agent_factory import T1_TOOL_REGISTRY
    from app.services.connection_manager import get_connection_manager
    from app.services.plugin_registry import get_plugin_registry

    registry = get_plugin_registry()
    cm = get_connection_manager()

    # ── T1: always-on core tools ────────────────────────────────────
    t1_entries: list[dict] = []
    seen_t1: set[str] = set()
    for cap, factory in T1_TOOL_REGISTRY.items():
        try:
            tools = factory()
        except Exception:
            continue
        for t in tools:
            name = getattr(t, "name", str(t))
            if name in seen_t1:
                continue
            seen_t1.add(name)
            desc = getattr(t, "description", "") or getattr(t, "__doc__", "") or ""
            params = _extract_params(t)
            t1_entries.append(
                {"name": name, "description": desc.strip(), "parameters": params, "capability": cap}
            )

    # ── T2: enabled plugins / MCPs ──────────────────────────────────
    t2_entries: list[dict] = []
    for plugin_id in registry.get_enabled_ids(user_id):
        manifest = registry.get_manifest(plugin_id)
        if manifest is None:
            continue
        # ONLY use discovered summaries (populated by actual MCP connection).
        # Never fall back to manifest.tools_summary — those are guessed names
        # that may not match real MCP tool names and cause hallucination.
        discovered = registry._discovered_summaries.get(plugin_id)
        if discovered is None:
            # MCP not connected yet — show plugin as enabled but tools pending
            t2_entries.append(
                {
                    "plugin": manifest.name,
                    "plugin_id": plugin_id,
                    "kind": str(manifest.kind),
                    "tool": "(not connected yet)",
                    "description": f"{manifest.name} is enabled but not yet connected. Tools will appear after authorization is complete.",
                    "parameters": {},
                }
            )
            continue
        for s in discovered:
            t2_entries.append(
                {
                    "plugin": manifest.name,
                    "plugin_id": plugin_id,
                    "kind": str(manifest.kind),
                    "tool": s.name,
                    "description": s.description or "",
                    # Parameters available via get_capabilities_of(plugin_name)
                    "parameters": {},
                }
            )

    # ── T3: client-local proxy tools ────────────────────────────────
    t3_entries: list[dict] = []
    capabilities = cm.get_capabilities(user_id)
    for _ct, cap_data in capabilities.items():
        for tool_def in cap_data.get("local_tools", []):
            if tool_def.get("name"):
                t3_entries.append(
                    {
                        "tool": tool_def["name"],
                        "description": tool_def.get("description", ""),
                        "parameters": tool_def.get("parameters", {}),
                        "client_type": str(_ct),
                    }
                )

    # ── Build short summary ─────────────────────────────────────────
    t2_plugins = {e["plugin"] for e in t2_entries}
    t3_clients = {e["client_type"] for e in t3_entries} if t3_entries else set()
    summary_parts = [f"{len(t1_entries)} core tools (T1)"]
    if t2_entries:
        summary_parts.append(
            f"{len(t2_entries)} plugin tools from {len(t2_plugins)} plugin(s): "
            f"{', '.join(sorted(t2_plugins))} (T2)"
        )
    else:
        summary_parts.append("0 plugins enabled (T2)")
    if t3_entries:
        summary_parts.append(
            f"{len(t3_entries)} client-local tools from "
            f"{', '.join(sorted(t3_clients))} (T3)"
        )
    else:
        summary_parts.append("0 client-local tools (T3)")

    return {
        "t1": t1_entries,
        "t2": t2_entries,
        "t3": t3_entries,
        "summary": "; ".join(summary_parts),
    }


def _extract_params(tool) -> dict:
    """Extract the parameter schema from an ADK FunctionTool or similar."""
    import contextlib

    decl = None
    with contextlib.suppress(Exception):
        if hasattr(tool, "_get_declaration"):
            decl = tool._get_declaration()
    if decl is None:
        decl = getattr(tool, "_function_declaration", None)
    if decl is None:
        return {}
    params_schema = getattr(decl, "parameters", None)
    if params_schema is None:
        return {}
    with contextlib.suppress(Exception):
        if hasattr(params_schema, "model_dump"):
            return params_schema.model_dump(exclude_none=True)
        return dict(params_schema)
    return {}


def _render_markdown(data: dict) -> str:
    """Render the capability data dict as a readable markdown string.

    Groups tools under the specialist persona that handles them, so the
    root agent (and the user) can see exactly which specialist to call.
    """
    from app.agents.agent_factory import _PERSONA_CAPABILITIES
    from app.models.plugin import ToolCapability as TC

    # Build a readable persona → capability mapping
    _PERSONA_DISPLAY = {
        "coder": ("Dev — Software Engineer", "code execution, E2B sandbox, GitHub, debugging"),
        "researcher": ("Sage — Research Analyst", "web search, fact-checking, data gathering"),
        "analyst": ("Nova — Data Analyst", "data analysis, charts, statistics, code execution"),
        "creative": ("Muse — Creative", "image generation, illustrations, brainstorming"),
        "genui": ("Pixel — Visual UI", "interactive charts, tables, cards, timelines, dashboards"),
    }

    lines: list[str] = ["# Omni Capabilities\n"]
    lines.append(f"**{data['summary']}**\n")

    # ── Persona specialists ────────────────────────────────────────
    lines.append("\n## Specialist Agents (call via `persona_id(request)`)\n")
    lines.append(
        "**IMPORTANT:** You (root) do NOT call specialist-only tools like "
        "`execute_code`, `google_search`, `generate_image` directly. "
        "Route to the right specialist below. However, communication tools "
        "(calendar, email, Notion) are YOUR tools — call them directly.\n"
    )
    for pid, (display_name, desc) in _PERSONA_DISPLAY.items():
        caps = _PERSONA_CAPABILITIES.get(pid, [])
        # Gather matching T1 tool names for this persona
        t1_names = []
        for e in data["t1"]:
            cap = e.get("capability", "")
            if cap in caps or TC.WILDCARD in caps:
                t1_names.append(e["name"])
        # Gather T2 plugin tools for this persona's MCP IDs
        t2_tools = []
        for e in data["t2"]:
            t2_tools.append(f"{e['tool']} ({e['plugin']})")
        tool_list = ", ".join(t1_names[:8])
        if len(t1_names) > 8:
            tool_list += f", +{len(t1_names) - 8} more"
        lines.append(f"### {display_name}")
        lines.append(f"Call: `{pid}(\"your request\")` — {desc}")
        if tool_list:
            lines.append(f"Core tools: {tool_list}")
        lines.append("")

    # ── T2 Plugins — mention which persona routes to them ──────────
    lines.append("\n## Enabled Plugins (T2) — routed through specialist agents\n")
    if data["t2"]:
        by_plugin: dict[str, list[dict]] = {}
        for e in data["t2"]:
            by_plugin.setdefault(e["plugin"], []).append(e)
        for plugin_name, tools in sorted(by_plugin.items()):
            tool_names = ", ".join(t["tool"] for t in tools)
            lines.append(
                f"- **{plugin_name}**: {tool_names}\n"
                f"  → Route to the appropriate specialist (e.g., **coder** for GitHub) "
                f"or call directly for calendar/email/Notion."
            )
    else:
        lines.append(
            "*(No plugins enabled — user can enable plugins in the dashboard Settings)*"
        )

    # ── T3 Client-local ────────────────────────────────────────────
    lines.append("\n## Client-local Tools (T3) — call directly from root\n")
    if data["t3"]:
        for e in data["t3"]:
            lines.append(
                f"- **{e['tool']}** [{e.get('client_type', '')}]: {e['description']}"
            )
    else:
        lines.append("*(No client-local tools — desktop/chrome not connected)*")

    lines.append(
        "\n---\n*Remember: As the root agent, only call your own tools "
        "(list_connected_clients, send_to_desktop, etc.) and route everything "
        "else to the correct specialist via `persona_id(request)`.*"
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 1: get_capabilities
# ---------------------------------------------------------------------------


async def get_capabilities(
    tool_context: ToolContext | None = None,
) -> str:
    """Get a complete summary of all available tools and capabilities.

    Returns a structured overview of everything this agent can do right now,
    grouped by tier:
    - T1: Core built-in tools (search, code execution, image generation, etc.)
    - T2: Plugin & MCP tools currently enabled by the user
    - T3: Client-local tools advertised by connected desktop/browser clients

    Use this when the user asks "what can you do?", "what tools do you have?",
    "show me your capabilities", or before deciding which persona to route to.

    Returns:
        A markdown-formatted capability summary with tool names and descriptions.
    """
    user_id = _get_user_id(tool_context)
    logger.info("get_capabilities_called", user_id=user_id)
    data = _get_capabilities_data(user_id)
    return _render_markdown(data)


get_capabilities_tool = FunctionTool(get_capabilities)


# ---------------------------------------------------------------------------
# Tool 2: get_capabilities_of
# ---------------------------------------------------------------------------


async def get_capabilities_of(
    plugin_name: str,
    tool_context: ToolContext | None = None,
) -> str:
    """Get full function schemas for a specific plugin, MCP, or tool tier.

    Use this to understand exactly what parameters a specific plugin's tools
    accept before calling them, or when the user asks about a specific
    integration.

    Args:
        plugin_name: The plugin or MCP name (e.g. "GitHub", "Google Calendar",
                     "Notion"), OR a tier identifier: "T1", "T2", or "T3".
                     Case-insensitive. Partial matches are supported.

    Returns:
        A JSON-formatted list of tool schemas including name, description,
        and full parameter definitions. Returns an error message if the
        plugin is not found or not enabled.
    """
    user_id = _get_user_id(tool_context)
    logger.info("get_capabilities_of_called", user_id=user_id, plugin_name=plugin_name)

    query = plugin_name.strip().lower()

    # ── Handle tier queries ─────────────────────────────────────────
    if query in ("t1", "tier1", "tier 1", "core", "built-in"):
        return _get_tier1_schemas()
    if query in ("t2", "tier2", "tier 2", "plugins", "mcp"):
        return _get_tier2_schemas(user_id)
    if query in ("t3", "tier3", "tier 3", "client", "local", "device"):
        return _get_tier3_schemas(user_id)

    # ── Plugin or MCP lookup ────────────────────────────────────────
    from app.services.plugin_registry import get_plugin_registry

    registry = get_plugin_registry()

    # Find plugin by name (case-insensitive, partial match)
    target_id: str | None = None
    target_manifest = None
    for pid, manifest in registry._catalog.items():
        if query in manifest.name.lower() or query in pid.lower():
            target_id = pid
            target_manifest = manifest
            break

    if target_id is None:
        # Try to match against T1 tool names
        t1_result = _get_tier1_schemas_filtered(query)
        if t1_result:
            return t1_result
        enabled_names = [
            registry.get_manifest(pid).name
            for pid in registry.get_enabled_ids(user_id)
            if registry.get_manifest(pid)
        ]
        all_plugin_names = [m.name for m in registry._catalog.values()]
        return json.dumps(
            {
                "error": f"Plugin '{plugin_name}' not found.",
                "enabled_plugins": enabled_names,
                "all_available_plugins": all_plugin_names,
                "hint": "Use get_capabilities() to see all enabled tools.",
            },
            indent=2,
        )

    # Check if enabled
    enabled_ids = registry.get_enabled_ids(user_id)
    if target_id not in enabled_ids:
        return json.dumps(
            {
                "error": f"Plugin '{target_manifest.name}' is not enabled.",
                "plugin_id": target_id,
                "status": "available_but_not_enabled",
                "tools_preview": [
                    {"name": s.name, "description": s.description}
                    for s in target_manifest.tools_summary
                ],
                "hint": "Enable this plugin in the dashboard to use its tools.",
            },
            indent=2,
        )

    # Fetch full schemas from the live toolset
    try:
        schemas = await registry.get_tool_schemas(target_id, user_id)
    except Exception as exc:
        return json.dumps({"error": f"Failed to load schemas: {exc}"}, indent=2)

    if not schemas:
        # Only show discovered summaries (verified tool names), never guessed manifest names
        discovered = registry._discovered_summaries.get(target_id)
        if discovered:
            return json.dumps(
                {
                    "plugin": target_manifest.name,
                    "plugin_id": target_id,
                    "kind": str(target_manifest.kind),
                    "tools": [{"name": s.name, "description": s.description} for s in discovered],
                    "note": "Full parameter schemas not yet available (connect plugin first).",
                },
                indent=2,
            )
        return json.dumps(
            {
                "plugin": target_manifest.name,
                "plugin_id": target_id,
                "kind": str(target_manifest.kind),
                "tools": [],
                "note": f"{target_manifest.name} is enabled but not yet connected. Complete authorization in the Integrations page first.",
            },
            indent=2,
        )

    return json.dumps(
        {
            "plugin": target_manifest.name,
            "plugin_id": target_id,
            "kind": str(target_manifest.kind),
            "description": target_manifest.description,
            "tools": [
                {
                    "name": s.name,
                    "description": s.description,
                    "parameters": s.parameters,
                }
                for s in schemas
            ],
        },
        indent=2,
    )


def _get_tier1_schemas() -> str:
    """Return JSON schemas for all T1 core tools."""
    from app.agents.agent_factory import T1_TOOL_REGISTRY

    tools_out: list[dict] = []
    seen: set[str] = set()
    for cap, factory in T1_TOOL_REGISTRY.items():
        try:
            tools = factory()
        except Exception:
            continue
        for t in tools:
            name = getattr(t, "name", str(t))
            if name in seen:
                continue
            seen.add(name)
            desc = (getattr(t, "description", "") or getattr(t, "__doc__", "") or "").strip()
            params = _extract_params(t)
            tools_out.append(
                {"name": name, "description": desc, "parameters": params, "capability_tag": cap}
            )
    return json.dumps({"tier": "T1", "description": "Core built-in tools", "tools": tools_out}, indent=2)


def _get_tier1_schemas_filtered(query: str) -> str:
    """Return T1 schemas filtered by tool name containing query. Empty string if no match."""
    from app.agents.agent_factory import T1_TOOL_REGISTRY

    tools_out: list[dict] = []
    seen: set[str] = set()
    for cap, factory in T1_TOOL_REGISTRY.items():
        try:
            tools = factory()
        except Exception:
            continue
        for t in tools:
            name = getattr(t, "name", str(t))
            if name in seen:
                continue
            if query not in name.lower():
                continue
            seen.add(name)
            desc = (getattr(t, "description", "") or getattr(t, "__doc__", "") or "").strip()
            params = _extract_params(t)
            tools_out.append(
                {"name": name, "description": desc, "parameters": params, "capability_tag": cap}
            )
    if not tools_out:
        return ""
    return json.dumps({"tier": "T1", "tools": tools_out}, indent=2)


def _get_tier2_schemas(user_id: str) -> str:
    """Return summary schemas for all enabled T2 plugins."""
    from app.services.plugin_registry import PluginKind, get_plugin_registry

    registry = get_plugin_registry()
    plugins_out: list[dict] = []
    for plugin_id in registry.get_enabled_ids(user_id):
        manifest = registry.get_manifest(plugin_id)
        if manifest is None:
            continue
        # Only use verified discovered summaries for MCP plugins
        discovered = registry._discovered_summaries.get(plugin_id)
        if discovered is not None:
            summaries = discovered
        elif manifest.kind in (PluginKind.MCP_STDIO, PluginKind.MCP_HTTP, PluginKind.MCP_OAUTH):
            summaries = []  # MCP not connected — don't leak guessed names
        else:
            summaries = manifest.tools_summary  # Native plugins: names match Python functions
        tools_list = [{"name": s.name, "description": s.description} for s in summaries]
        if not tools_list and manifest.kind in (PluginKind.MCP_STDIO, PluginKind.MCP_HTTP, PluginKind.MCP_OAUTH):
            tools_list = [{"name": "(not connected)", "description": f"{manifest.name} is enabled but not yet connected. Complete authorization first."}]
        plugins_out.append(
            {
                "plugin": manifest.name,
                "plugin_id": plugin_id,
                "kind": str(manifest.kind),
                "tools": tools_list,
            }
        )
    return json.dumps(
        {
            "tier": "T2",
            "description": "User-enabled plugins and MCP servers",
            "plugins": plugins_out,
        },
        indent=2,
    )


def _get_tier3_schemas(user_id: str) -> str:
    """Return schemas for T3 client-local tools."""
    from app.services.connection_manager import get_connection_manager

    cm = get_connection_manager()
    capabilities = cm.get_capabilities(user_id)
    tools_out: list[dict] = []
    for ct, cap_data in capabilities.items():
        for tool_def in cap_data.get("local_tools", []):
            if tool_def.get("name"):
                tools_out.append(
                    {
                        "name": tool_def["name"],
                        "description": tool_def.get("description", ""),
                        "parameters": tool_def.get("parameters", {}),
                        "client_type": str(ct),
                    }
                )
    return json.dumps(
        {
            "tier": "T3",
            "description": "Client-local tools (desktop, Chrome, dashboard)",
            "tools": tools_out,
        },
        indent=2,
    )


get_capabilities_of_tool = FunctionTool(get_capabilities_of)


def get_capability_tools() -> list[FunctionTool]:
    """Return the two capability introspection tools."""
    return [get_capabilities_tool, get_capabilities_of_tool]
