"""PluginRegistry — central orchestrator for all plugin types.

Replaces the old MCPManager with a unified system that handles:
  - MCP servers (stdio + HTTP)
  - Native Python plugins
  - E2B sandbox
  - Lazy tool loading (agent gets summaries first, schemas on demand)

Architecture
------------
Each plugin goes through these states:

  AVAILABLE → (user toggles on) → ENABLED → (first tool access) → CONNECTED
                                                                       ↓
                                                                    ERROR → retry

Developers register plugins by adding a PluginManifest to the built-in
catalog or by placing a plugin module in ``app/plugins/``.  No other
backend code needs to change.
"""

from __future__ import annotations

import contextlib
import importlib
import os
import time
from pathlib import Path
from typing import Any

from google.adk.tools import FunctionTool
from google.adk.tools.mcp_tool.mcp_toolset import (
    McpToolset,
    StdioConnectionParams,
    StreamableHTTPConnectionParams,
)
from mcp.client.stdio import StdioServerParameters

from app.models.plugin import (
    PluginCategory,
    PluginKind,
    PluginManifest,
    PluginState,
    PluginStatus,
    PluginToggle,
    ToolSchema,
    ToolSummary,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)

# Idle TTL for toolsets — evicted after 30 min of inactivity
_TOOLSET_IDLE_TTL = 30 * 60


# ---------------------------------------------------------------------------
# Built-in plugin catalog
# ---------------------------------------------------------------------------

def _builtin_plugins() -> list[PluginManifest]:
    """Return the built-in plugin catalog.

    To add a new plugin, just append a PluginManifest here.
    """
    return [
        # ── E2B Sandbox (special built-in) ──
        PluginManifest(
            id="e2b-sandbox",
            name="E2B Sandbox",
            description="Sandboxed code execution — run Python, Node.js, shell commands with full file system.",
            category=PluginCategory.SANDBOX,
            kind=PluginKind.E2B,
            icon="sandbox",
            lazy=False,
            tools_summary=[
                ToolSummary(name="execute_code", description="Run code in a sandboxed environment"),
                ToolSummary(name="install_package", description="Install a package in the sandbox"),
            ],
        ),
        # ── Wikipedia (remote HTTP MCP — no API key needed) ──
        PluginManifest(
            id="wikipedia",
            name="Wikipedia",
            description="Search and read Wikipedia articles for factual research.",
            category=PluginCategory.SEARCH,
            kind=PluginKind.MCP_HTTP,
            url="https://mcp.wiki/api",
            icon="wikipedia",
        ),
        # ── Filesystem (stdio MCP — sandboxed to /tmp/sandbox) ──
        PluginManifest(
            id="filesystem",
            name="Filesystem",
            description="Read/write files in a sandboxed directory.",
            category=PluginCategory.OTHER,
            kind=PluginKind.MCP_STDIO,
            command="npx",
            args=["-y", "@anthropic/mcp-filesystem", "/tmp/sandbox"],
            icon="folder",
        ),
        # ── Brave Search ──
        PluginManifest(
            id="brave-search",
            name="Brave Search",
            description="Web search via the Brave Search API.",
            category=PluginCategory.SEARCH,
            kind=PluginKind.MCP_STDIO,
            command="npx",
            args=["-y", "@anthropic/mcp-brave-search"],
            env_keys=["BRAVE_API_KEY"],
            requires_auth=True,
            icon="brave",
        ),
        # ── GitHub ──
        PluginManifest(
            id="github",
            name="GitHub",
            description="Interact with GitHub repos, issues, PRs.",
            category=PluginCategory.DEV,
            kind=PluginKind.MCP_STDIO,
            command="npx",
            args=["-y", "@anthropic/mcp-github"],
            env_keys=["GITHUB_TOKEN"],
            requires_auth=True,
            icon="github",
        ),
        # ── Playwright ──
        PluginManifest(
            id="playwright",
            name="Playwright",
            description="Browser automation — navigate, click, screenshot.",
            category=PluginCategory.DEV,
            kind=PluginKind.MCP_STDIO,
            command="npx",
            args=["-y", "@anthropic/mcp-playwright"],
            icon="playwright",
        ),
        # ── Notion ──
        PluginManifest(
            id="notion",
            name="Notion",
            description="Read and write Notion pages and databases.",
            category=PluginCategory.PRODUCTIVITY,
            kind=PluginKind.MCP_STDIO,
            command="npx",
            args=["-y", "@anthropic/mcp-notion"],
            env_keys=["NOTION_TOKEN"],
            requires_auth=True,
            icon="notion",
        ),
        # ── Slack ──
        PluginManifest(
            id="slack",
            name="Slack",
            description="Send messages, read channels in Slack.",
            category=PluginCategory.COMMUNICATION,
            kind=PluginKind.MCP_STDIO,
            command="npx",
            args=["-y", "@anthropic/mcp-slack"],
            env_keys=["SLACK_TOKEN"],
            requires_auth=True,
            icon="slack",
        ),
    ]


# ---------------------------------------------------------------------------
# PluginRegistry
# ---------------------------------------------------------------------------


class PluginRegistry:
    """Unified plugin lifecycle manager.

    Manages MCP servers, native Python tools, and E2B sandbox through
    a single interface.  Supports lazy tool loading: the agent only
    receives tool summaries until a plugin is explicitly activated.
    """

    def __init__(self) -> None:
        # Catalog: { plugin_id: PluginManifest }
        self._catalog: dict[str, PluginManifest] = {}
        # User enabled state: { user_id: { plugin_id: True } }
        self._user_enabled: dict[str, dict[str, bool]] = {}
        # Active MCP toolsets: { (user_id, plugin_id): (McpToolset, last_access) }
        self._mcp_toolsets: dict[tuple[str, str], tuple[McpToolset, float]] = {}
        # Cached native tools: { plugin_id: list[FunctionTool] }
        self._native_tool_cache: dict[str, list[FunctionTool]] = {}
        # Discovered tool summaries: { plugin_id: list[ToolSummary] }
        self._discovered_summaries: dict[str, list[ToolSummary]] = {}
        # User secrets: { user_id: { plugin_id: { key: value } } }
        self._user_secrets: dict[str, dict[str, dict[str, str]]] = {}
        # Plugin errors: { (user_id, plugin_id): error_msg }
        self._errors: dict[tuple[str, str], str] = {}

        # Load built-in catalog
        for manifest in _builtin_plugins():
            self._catalog[manifest.id] = manifest

        # Auto-discover plugins from app/plugins/ directory
        self._discover_plugin_modules()

    # ------------------------------------------------------------------
    # Plugin discovery
    # ------------------------------------------------------------------

    def _discover_plugin_modules(self) -> None:
        """Scan ``app/plugins/`` for Python modules with a ``MANIFEST`` attribute."""
        plugins_dir = Path(__file__).parent.parent / "plugins"
        if not plugins_dir.is_dir():
            return
        for path in plugins_dir.glob("*.py"):
            if path.name.startswith("_"):
                continue
            module_name = f"app.plugins.{path.stem}"
            try:
                mod = importlib.import_module(module_name)
                manifest = getattr(mod, "MANIFEST", None)
                if isinstance(manifest, PluginManifest):
                    self._catalog[manifest.id] = manifest
                    logger.info("plugin_discovered", plugin_id=manifest.id, module=module_name)
            except Exception:
                logger.warning("plugin_discovery_failed", module=module_name, exc_info=True)

    def register_plugin(self, manifest: PluginManifest) -> None:
        """Dynamically register a plugin at runtime."""
        self._catalog[manifest.id] = manifest
        logger.info("plugin_registered", plugin_id=manifest.id, kind=manifest.kind)

    # ------------------------------------------------------------------
    # Catalog
    # ------------------------------------------------------------------

    def get_catalog(self, user_id: str | None = None) -> list[PluginStatus]:
        """Return the full catalog with per-user state."""
        enabled = self._user_enabled.get(user_id, {}) if user_id else {}
        result = []
        for m in self._catalog.values():
            state = PluginState.AVAILABLE
            error = None
            if user_id:
                key = (user_id, m.id)
                if key in self._errors:
                    state = PluginState.ERROR
                    error = self._errors[key]
                elif enabled.get(m.id, False):
                    # Check if toolset is connected
                    if m.kind in (PluginKind.MCP_STDIO, PluginKind.MCP_HTTP):
                        if (user_id, m.id) in self._mcp_toolsets:
                            state = PluginState.CONNECTED
                        else:
                            state = PluginState.ENABLED
                    else:
                        state = PluginState.CONNECTED

            summaries = self._discovered_summaries.get(m.id, m.tools_summary)

            result.append(PluginStatus(
                id=m.id,
                name=m.name,
                description=m.description,
                category=m.category,
                kind=m.kind,
                icon=m.icon,
                state=state,
                error=error,
                tools_summary=summaries,
                requires_auth=m.requires_auth,
                version=m.version,
                author=m.author,
            ))
        return result

    def get_manifest(self, plugin_id: str) -> PluginManifest | None:
        return self._catalog.get(plugin_id)

    def get_enabled_ids(self, user_id: str) -> list[str]:
        return [
            pid for pid, on in self._user_enabled.get(user_id, {}).items()
            if on
        ]

    # ------------------------------------------------------------------
    # User secrets
    # ------------------------------------------------------------------

    def set_user_secrets(self, user_id: str, plugin_id: str, secrets: dict[str, str]) -> None:
        """Store user-provided secrets (API keys, tokens) for a plugin."""
        self._user_secrets.setdefault(user_id, {})[plugin_id] = secrets
        logger.info("plugin_secrets_set", user_id=user_id, plugin_id=plugin_id)

    def _resolve_env(self, manifest: PluginManifest, user_id: str) -> dict[str, str] | None:
        """Build the environment dict for an MCP process.

        Merges: manifest.env → os.environ → user secrets.
        Returns None if required keys are missing.
        """
        env: dict[str, str] = {}
        env.update(manifest.env)

        user_secrets = self._user_secrets.get(user_id, {}).get(manifest.id, {})

        for key in manifest.env_keys:
            # Priority: user secrets > os.environ > manifest defaults
            value = user_secrets.get(key) or os.environ.get(key) or env.get(key)
            if not value:
                return None  # Missing required key
            env[key] = value

        return env

    # ------------------------------------------------------------------
    # Connect / disconnect
    # ------------------------------------------------------------------

    def _build_mcp_params(
        self, manifest: PluginManifest, env: dict[str, str] | None = None,
    ) -> StdioConnectionParams | StreamableHTTPConnectionParams:
        if manifest.kind == PluginKind.MCP_HTTP:
            return StreamableHTTPConnectionParams(url=manifest.url)
        return StdioConnectionParams(
            server_params=StdioServerParameters(
                command=manifest.command,
                args=manifest.args,
                env=env or None,
            ),
        )

    async def connect_plugin(self, user_id: str, plugin_id: str) -> bool:
        """Activate a plugin for a user.  Returns True on success."""
        manifest = self._catalog.get(plugin_id)
        if manifest is None:
            return False

        # Clear previous error
        self._errors.pop((user_id, plugin_id), None)

        try:
            if manifest.kind in (PluginKind.MCP_STDIO, PluginKind.MCP_HTTP):
                return await self._connect_mcp(user_id, plugin_id, manifest)
            elif manifest.kind == PluginKind.NATIVE:
                success = self._connect_native(plugin_id, manifest)
                if success:
                    self._user_enabled.setdefault(user_id, {})[plugin_id] = True
                return success
            elif manifest.kind == PluginKind.E2B:
                # E2B is always available; just mark enabled
                self._user_enabled.setdefault(user_id, {})[plugin_id] = True
                return True
        except Exception as exc:
            self._errors[(user_id, plugin_id)] = str(exc)
            logger.warning("plugin_connect_failed", plugin_id=plugin_id, exc_info=True)
            return False

        return False

    async def _connect_mcp(
        self, user_id: str, plugin_id: str, manifest: PluginManifest,
    ) -> bool:
        key = (user_id, plugin_id)

        # Return existing if connected
        existing = self._mcp_toolsets.get(key)
        if existing is not None:
            self._mcp_toolsets[key] = (existing[0], time.monotonic())
            return True

        # Resolve env vars
        env = self._resolve_env(manifest, user_id)
        if manifest.requires_auth and env is None:
            self._errors[key] = f"Missing required credentials: {manifest.env_keys}"
            return False

        params = self._build_mcp_params(manifest, env)
        toolset = McpToolset(connection_params=params)

        # Try to discover tools (validates the connection)
        try:
            tools = await toolset.get_tools()
            # Cache discovered tool summaries
            self._discovered_summaries[plugin_id] = [
                ToolSummary(
                    name=getattr(t, "name", str(t)),
                    description=getattr(t, "description", ""),
                )
                for t in tools
            ]
        except Exception as exc:
            # Connection failed — clean up
            with contextlib.suppress(Exception):
                await toolset.close()
            self._errors[key] = f"Connection failed: {exc}"
            logger.warning("mcp_connect_failed", plugin_id=plugin_id, error=str(exc))
            return False

        self._mcp_toolsets[key] = (toolset, time.monotonic())
        self._user_enabled.setdefault(user_id, {})[plugin_id] = True
        logger.info("mcp_connected", user_id=user_id, plugin_id=plugin_id, tools=len(tools))
        return True

    def _connect_native(self, plugin_id: str, manifest: PluginManifest) -> bool:
        if plugin_id in self._native_tool_cache:
            return True
        mod = importlib.import_module(manifest.module)
        factory = getattr(mod, manifest.factory)
        tools = factory()
        self._native_tool_cache[plugin_id] = tools
        # Cache summaries
        self._discovered_summaries[plugin_id] = [
            ToolSummary(name=t.name, description=getattr(t, "description", ""))
            for t in tools
        ]
        logger.info("native_plugin_loaded", plugin_id=plugin_id, tools=len(tools))
        return True

    async def disconnect_plugin(self, user_id: str, plugin_id: str) -> bool:
        """Deactivate a plugin for a user."""
        manifest = self._catalog.get(plugin_id)
        if manifest is None:
            return False

        self._errors.pop((user_id, plugin_id), None)

        if manifest.kind in (PluginKind.MCP_STDIO, PluginKind.MCP_HTTP):
            key = (user_id, plugin_id)
            entry = self._mcp_toolsets.pop(key, None)
            if entry is not None:
                with contextlib.suppress(Exception):
                    await entry[0].close()

        user_mcps = self._user_enabled.get(user_id, {})
        user_mcps.pop(plugin_id, None)
        logger.info("plugin_disconnected", user_id=user_id, plugin_id=plugin_id)
        return True

    async def toggle_plugin(self, user_id: str, toggle: PluginToggle) -> bool:
        """Enable or disable a plugin.  Returns the new enabled state."""
        if toggle.enabled:
            success = await self.connect_plugin(user_id, toggle.plugin_id)
            return success
        else:
            await self.disconnect_plugin(user_id, toggle.plugin_id)
            return False

    # ------------------------------------------------------------------
    # Tool retrieval (the core API)
    # ------------------------------------------------------------------

    async def get_tools(self, user_id: str) -> list:
        """Return all ADK tools from enabled plugins for a user.

        This is the main entry point called by the Runner builder.
        """
        tools: list = []
        for plugin_id in self.get_enabled_ids(user_id):
            manifest = self._catalog.get(plugin_id)
            if manifest is None:
                continue
            try:
                plugin_tools = await self._get_plugin_tools(user_id, plugin_id, manifest)
                tools.extend(plugin_tools)
            except Exception:
                logger.warning("plugin_get_tools_failed", plugin_id=plugin_id, exc_info=True)
        return tools

    async def _get_plugin_tools(
        self, user_id: str, plugin_id: str, manifest: PluginManifest,
    ) -> list:
        """Get tools for a specific plugin."""
        if manifest.kind == PluginKind.E2B:
            from app.tools.code_exec import get_e2b_tools
            return get_e2b_tools()

        if manifest.kind == PluginKind.NATIVE:
            return self._native_tool_cache.get(plugin_id, [])

        if manifest.kind in (PluginKind.MCP_STDIO, PluginKind.MCP_HTTP):
            key = (user_id, plugin_id)
            entry = self._mcp_toolsets.get(key)
            if entry is None:
                # Lazy connect on first tool access
                success = await self.connect_plugin(user_id, plugin_id)
                if not success:
                    return []
                entry = self._mcp_toolsets.get(key)
                if entry is None:
                    return []

            toolset, _ = entry
            self._mcp_toolsets[key] = (toolset, time.monotonic())
            return await toolset.get_tools()

        return []

    # ------------------------------------------------------------------
    # Lazy tool loading: summaries + on-demand schemas
    # ------------------------------------------------------------------

    def get_tool_summaries(self, user_id: str) -> list[dict[str, Any]]:
        """Return lightweight tool summaries for all enabled plugins.

        The agent instruction can reference these summaries so it knows
        what capabilities exist without loading full schemas.
        """
        result = []
        for plugin_id in self.get_enabled_ids(user_id):
            manifest = self._catalog.get(plugin_id)
            if manifest is None:
                continue
            summaries = self._discovered_summaries.get(plugin_id, manifest.tools_summary)
            for s in summaries:
                result.append({
                    "plugin": manifest.name,
                    "plugin_id": plugin_id,
                    "tool": s.name,
                    "description": s.description,
                })
        return result

    async def get_tool_schemas(self, plugin_id: str, user_id: str) -> list[ToolSchema]:
        """Return full tool schemas for a plugin (on-demand loading).

        Called when the agent decides it needs a specific plugin's tools.
        """
        manifest = self._catalog.get(plugin_id)
        if manifest is None:
            return []

        try:
            tools = await self._get_plugin_tools(user_id, plugin_id, manifest)
        except Exception:
            return []

        schemas = []
        for t in tools:
            name = getattr(t, "name", str(t))
            desc = getattr(t, "description", "")
            params = {}
            # Try to extract parameter schema from ADK tool
            func_decl = getattr(t, "_function_declaration", None)
            if func_decl is not None:
                params_schema = getattr(func_decl, "parameters", None)
                if params_schema is not None:
                    params = (
                        params_schema.model_dump()
                        if hasattr(params_schema, "model_dump")
                        else dict(params_schema)
                    )
            schemas.append(ToolSchema(name=name, description=desc, parameters=params))
        return schemas

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    async def disconnect_all(self, user_id: str) -> None:
        """Disconnect all plugins for a user."""
        ids = self.get_enabled_ids(user_id)
        for pid in ids:
            await self.disconnect_plugin(user_id, pid)

    async def evict_idle_toolsets(self) -> int:
        """Close MCP toolsets idle longer than the TTL."""
        now = time.monotonic()
        expired: list[tuple[str, str]] = [
            k for k, (_, ts) in self._mcp_toolsets.items()
            if now - ts > _TOOLSET_IDLE_TTL
        ]
        for key in expired:
            entry = self._mcp_toolsets.pop(key, None)
            if entry is not None:
                with contextlib.suppress(Exception):
                    await entry[0].close()
                user_id, plugin_id = key
                user_mcps = self._user_enabled.get(user_id, {})
                user_mcps.pop(plugin_id, None)
        if expired:
            logger.info("plugins_idle_evicted", count=len(expired))
        return len(expired)

    async def shutdown(self) -> None:
        """Close all connections (server shutdown)."""
        for (_uid, _pid), (toolset, _) in list(self._mcp_toolsets.items()):
            with contextlib.suppress(Exception):
                await toolset.close()
        self._mcp_toolsets.clear()
        self._user_enabled.clear()
        self._native_tool_cache.clear()
        logger.info("plugin_registry_shutdown")


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_registry: PluginRegistry | None = None


def get_plugin_registry() -> PluginRegistry:
    """Return the global plugin registry instance."""
    global _registry
    if _registry is None:
        _registry = PluginRegistry()
    return _registry
