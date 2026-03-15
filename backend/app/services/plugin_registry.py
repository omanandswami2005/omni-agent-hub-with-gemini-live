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

import asyncio
import contextlib
import importlib
import os
import time
from pathlib import Path
from typing import Any

from google.adk.tools import FunctionTool
from google.adk.tools.mcp_tool.mcp_toolset import (
    McpToolset,
    SseConnectionParams,
    StdioConnectionParams,
    StreamableHTTPConnectionParams,
)
from mcp.client.stdio import StdioServerParameters

from app.models.plugin import (
    PluginKind,
    PluginManifest,
    PluginState,
    PluginStatus,
    PluginToggle,
    ToolSchema,
    ToolSummary,
)
from app.services import secret_service
from app.services.google_oauth_service import get_google_oauth_service
from app.services.oauth_service import get_oauth_service
from app.utils.logging import get_logger

logger = get_logger(__name__)

# Idle TTL for toolsets — evicted after 30 min of inactivity
_TOOLSET_IDLE_TTL = 30 * 60


# ---------------------------------------------------------------------------
# Built-in plugin catalog
# ---------------------------------------------------------------------------


def _sandbox_dir() -> str:
    """Return a cross-platform temp sandbox directory, creating it if needed."""
    import tempfile

    d = os.path.join(tempfile.gettempdir(), "omni_sandbox")
    os.makedirs(d, exist_ok=True)
    return d


def _load_mcp_configs() -> list[PluginManifest]:
    """Auto-discover MCP server configs from ``app/mcps/*.json``.

    Each JSON file in the ``mcps/`` directory is parsed into a
    :class:`PluginManifest`.  The special placeholder ``__SANDBOX_DIR__``
    in ``args`` is replaced with the actual sandbox path at load time.
    """
    import json as _json

    mcps_dir = Path(__file__).parent.parent / "mcps"
    if not mcps_dir.is_dir():
        return []

    manifests: list[PluginManifest] = []
    sandbox = _sandbox_dir()

    for path in sorted(mcps_dir.glob("*.json")):
        if path.name.startswith("_") or path.name == "TEMPLATE.json":
            continue
        try:
            raw = _json.loads(path.read_text(encoding="utf-8"))
            # Replace sandbox placeholder in args
            if "args" in raw:
                raw["args"] = [sandbox if a == "__SANDBOX_DIR__" else a for a in raw["args"]]
            manifest = PluginManifest(**raw)
            manifests.append(manifest)
            logger.info("mcp_config_loaded", path=path.name, plugin_id=manifest.id)
        except Exception:
            logger.warning("mcp_config_load_failed", path=str(path), exc_info=True)

    return manifests


def _builtin_plugins() -> list[PluginManifest]:
    """Return the built-in plugin catalog.

    MCP server definitions are loaded from ``app/mcps/*.json`` config
    files.  To add a new MCP server, just drop a JSON file there —
    no Python code changes needed.
    """
    return _load_mcp_configs()


# ---------------------------------------------------------------------------
# PluginRegistry
# ---------------------------------------------------------------------------


class PluginRegistry:
    """Unified plugin lifecycle manager.

    Manages MCP servers, native Python tools, and E2B sandbox through
    a single interface.  Supports lazy tool loading: the agent only
    receives tool summaries until a plugin is explicitly activated.
    """

    _ENABLED_COLLECTION = "plugin_enabled_state"

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
        # Firestore client (lazy)
        self._db = None

        # Load built-in catalog
        for manifest in _builtin_plugins():
            self._catalog[manifest.id] = manifest

        # Auto-discover plugins from app/plugins/ directory
        self._discover_plugin_modules()

    # ------------------------------------------------------------------
    # Firestore persistence for enabled state
    # ------------------------------------------------------------------

    def _get_db(self):
        if self._db is None:
            from google.cloud import firestore

            from app.config import settings

            self._db = firestore.Client(project=settings.GOOGLE_CLOUD_PROJECT or None)
        return self._db

    def _persist_enabled(self, user_id: str) -> None:
        """Persist the enabled plugin set for *user_id* to Firestore."""
        try:
            db = self._get_db()
            enabled = self._user_enabled.get(user_id, {})
            enabled_ids = [pid for pid, on in enabled.items() if on]
            db.collection(self._ENABLED_COLLECTION).document(user_id).set(
                {"enabled_ids": enabled_ids}, merge=True,
            )
        except Exception:
            logger.warning("persist_enabled_failed", user_id=user_id, exc_info=True)

    def _load_enabled(self, user_id: str) -> dict[str, bool]:
        """Load enabled plugin IDs from Firestore for *user_id*."""
        try:
            db = self._get_db()
            doc = db.collection(self._ENABLED_COLLECTION).document(user_id).get()
            if doc.exists:
                data = doc.to_dict()
                return {pid: True for pid in data.get("enabled_ids", [])}
        except Exception:
            logger.warning("load_enabled_failed", user_id=user_id, exc_info=True)
        return {}

    def _ensure_enabled_loaded(self, user_id: str) -> dict[str, bool]:
        """Ensure enabled state is loaded from Firestore if not in memory."""
        if user_id not in self._user_enabled:
            loaded = self._load_enabled(user_id)
            if loaded:
                self._user_enabled[user_id] = loaded
                logger.info("enabled_state_recovered", user_id=user_id, plugins=list(loaded.keys()))
        return self._user_enabled.get(user_id, {})

    # ------------------------------------------------------------------
    # Plugin discovery
    # ------------------------------------------------------------------

    def _discover_plugin_modules(self) -> None:
        """Scan ``app/plugins/`` for Python modules with a ``MANIFEST`` attribute."""
        plugins_dir = Path(__file__).parent.parent / "plugins"
        if not plugins_dir.is_dir():
            return
        for path in plugins_dir.glob("*.py"):
            if path.name.startswith("_") or path.name == "TEMPLATE.py":
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
        enabled = self._ensure_enabled_loaded(user_id) if user_id else {}
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
                    if m.kind in (PluginKind.MCP_STDIO, PluginKind.MCP_HTTP, PluginKind.MCP_OAUTH):
                        if (user_id, m.id) in self._mcp_toolsets:
                            state = PluginState.CONNECTED
                        else:
                            state = PluginState.ENABLED
                    elif m.kind == PluginKind.NATIVE and m.google_oauth_scopes:
                        # Google OAuth native — connected only if tokens exist
                        goauth = get_google_oauth_service()
                        if goauth.has_tokens(user_id, m.id):
                            state = PluginState.CONNECTED
                        else:
                            state = PluginState.ENABLED
                    else:
                        state = PluginState.CONNECTED

            summaries = self._discovered_summaries.get(m.id, m.tools_summary)

            result.append(
                PluginStatus(
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
                    env_keys=m.env_keys,
                    google_oauth_scopes=m.google_oauth_scopes,
                    version=m.version,
                    author=m.author,
                )
            )
        return result

    def get_manifest(self, plugin_id: str) -> PluginManifest | None:
        return self._catalog.get(plugin_id)

    def get_enabled_ids(self, user_id: str) -> list[str]:
        enabled = self._ensure_enabled_loaded(user_id)
        return [pid for pid, on in enabled.items() if on]

    # ------------------------------------------------------------------
    # User secrets
    # ------------------------------------------------------------------

    def set_user_secrets(self, user_id: str, plugin_id: str, secrets: dict[str, str]) -> None:
        """Store user-provided secrets in GCP Secret Manager + local cache."""
        # Local cache for fast access during this process lifetime
        self._user_secrets.setdefault(user_id, {})[plugin_id] = secrets
        # Persist to GCP Secret Manager (encrypted at rest)
        try:
            secret_service.store_secrets(user_id, plugin_id, secrets)
            logger.info("plugin_secrets_stored_gcp", user_id=user_id, plugin_id=plugin_id)
        except Exception:
            logger.warning(
                "plugin_secrets_gcp_fallback", user_id=user_id, plugin_id=plugin_id, exc_info=True
            )

    def _resolve_env(self, manifest: PluginManifest, user_id: str) -> dict[str, str] | None:
        """Build the environment dict for an MCP process.

        Merges: manifest.env → os.environ → user secrets (cache + GCP).
        Returns None if required keys are missing.
        """
        env: dict[str, str] = {}
        env.update(manifest.env)

        # Try local cache first, then load from GCP Secret Manager
        user_secrets = self._user_secrets.get(user_id, {}).get(manifest.id, {})
        if not user_secrets:
            try:
                user_secrets = secret_service.load_secrets(user_id, manifest.id)
                if user_secrets:
                    self._user_secrets.setdefault(user_id, {})[manifest.id] = user_secrets
            except Exception:
                pass  # Fall through — os.environ or manifest defaults may suffice

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
        self,
        manifest: PluginManifest,
        env: dict[str, str] | None = None,
        oauth_headers: dict[str, str] | None = None,
    ) -> StdioConnectionParams | SseConnectionParams | StreamableHTTPConnectionParams:
        if manifest.kind == PluginKind.MCP_OAUTH:
            return StreamableHTTPConnectionParams(
                url=manifest.url,
                headers=oauth_headers,
            )
        if manifest.kind == PluginKind.MCP_HTTP:
            # Support dynamic URLs: if manifest.url is empty, resolve from env.
            # This allows per-user MCP URLs (e.g. Zapier MCP where each user
            # has a unique server URL provided via their secrets/env).
            url = manifest.url
            if not url and env:
                # Look for a *_URL key in env_keys
                for key in manifest.env_keys:
                    if key.endswith("_URL") and env.get(key):
                        url = env[key]
                        break
            if not url:
                msg = f"No URL configured for HTTP MCP '{manifest.id}'"
                raise ValueError(msg)
            return StreamableHTTPConnectionParams(url=url)
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
            elif manifest.kind == PluginKind.MCP_OAUTH:
                return await self._connect_mcp_oauth(user_id, plugin_id, manifest)
            elif manifest.kind == PluginKind.NATIVE:
                success = self._connect_native(plugin_id, manifest)
                if success:
                    self._user_enabled.setdefault(user_id, {})[plugin_id] = True
                    self._persist_enabled(user_id)
                return success
            elif manifest.kind == PluginKind.E2B:
                # E2B is always available; just mark enabled
                self._user_enabled.setdefault(user_id, {})[plugin_id] = True
                self._persist_enabled(user_id)
                return True
        except Exception as exc:
            self._errors[(user_id, plugin_id)] = str(exc)
            logger.warning("plugin_connect_failed", plugin_id=plugin_id, exc_info=True)
            return False

        return False

    def _mcp_key(
        self,
        user_id: str,
        plugin_id: str,
        manifest: PluginManifest,
    ) -> tuple[str, str]:
        """Return the toolset cache key — singleton MCPs share one instance."""
        if manifest.singleton and manifest.kind == PluginKind.MCP_STDIO:
            return ("__singleton__", plugin_id)
        return (user_id, plugin_id)

    async def _connect_mcp(
        self,
        user_id: str,
        plugin_id: str,
        manifest: PluginManifest,
    ) -> bool:
        key = self._mcp_key(user_id, plugin_id, manifest)

        # Return existing if connected
        existing = self._mcp_toolsets.get(key)
        if existing is not None:
            self._mcp_toolsets[key] = (existing[0], time.monotonic())
            self._user_enabled.setdefault(user_id, {})[plugin_id] = True
            self._persist_enabled(user_id)
            return True

        # Resolve env vars
        env = self._resolve_env(manifest, user_id)
        if manifest.requires_auth and env is None:
            self._errors[key] = f"Missing required credentials: {manifest.env_keys}"
            return False

        params = self._build_mcp_params(manifest, env)

        # Try to discover tools with retry (MCP subprocess can race on first connect)
        last_exc: Exception | None = None
        for attempt in range(3):
            toolset = McpToolset(connection_params=params)
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
                self._mcp_toolsets[key] = (toolset, time.monotonic())
                self._user_enabled.setdefault(user_id, {})[plugin_id] = True
                self._persist_enabled(user_id)
                logger.info("mcp_connected", user_id=user_id, plugin_id=plugin_id, tools=len(tools))
                return True
            except Exception as exc:
                last_exc = exc
                with contextlib.suppress(Exception):
                    await toolset.close()
                if attempt < 2:
                    logger.info("Retrying get_tools due to error: %s", exc)
                    await asyncio.sleep(1.5 * (attempt + 1))

        self._errors[key] = f"Connection failed: {last_exc}"
        logger.warning("mcp_connect_failed", plugin_id=plugin_id, error=str(last_exc))
        return False

    async def _connect_mcp_oauth(
        self,
        user_id: str,
        plugin_id: str,
        manifest: PluginManifest,
    ) -> bool:
        """Connect to an MCP_OAUTH server using stored OAuth tokens."""
        key = (user_id, plugin_id)

        # Return existing if connected
        existing = self._mcp_toolsets.get(key)
        if existing is not None:
            self._mcp_toolsets[key] = (existing[0], time.monotonic())
            return True

        oauth = get_oauth_service()

        # Refresh token if needed
        access_token = await oauth.refresh_token_if_needed(user_id, plugin_id, manifest.url)
        if not access_token:
            access_token = oauth.get_access_token(user_id, plugin_id)
        if not access_token:
            self._errors[key] = "OAuth not connected. Use the Connect button to authorize."
            return False

        headers = {"Authorization": f"Bearer {access_token}"}
        params = self._build_mcp_params(manifest, oauth_headers=headers)

        last_exc: Exception | None = None
        for attempt in range(3):
            toolset = McpToolset(connection_params=params)
            try:
                tools = await toolset.get_tools()
                self._discovered_summaries[plugin_id] = [
                    ToolSummary(
                        name=getattr(t, "name", str(t)),
                        description=getattr(t, "description", ""),
                    )
                    for t in tools
                ]
                self._mcp_toolsets[key] = (toolset, time.monotonic())
                self._user_enabled.setdefault(user_id, {})[plugin_id] = True
                self._persist_enabled(user_id)
                logger.info(
                    "mcp_oauth_connected", user_id=user_id, plugin_id=plugin_id, tools=len(tools)
                )
                return True
            except Exception as exc:
                last_exc = exc
                with contextlib.suppress(Exception):
                    await toolset.close()
                if attempt < 2:
                    logger.info("Retrying OAuth MCP get_tools: %s", exc)
                    await asyncio.sleep(1.5 * (attempt + 1))

        self._errors[key] = f"OAuth MCP connection failed: {last_exc}"
        logger.warning("mcp_oauth_connect_failed", plugin_id=plugin_id, error=str(last_exc))
        return False

    def _connect_native(self, plugin_id: str, manifest: PluginManifest) -> bool:
        if plugin_id in self._native_tool_cache:
            return True
        mod = importlib.import_module(manifest.module)
        factory = getattr(mod, manifest.factory)
        tools = factory()
        self._native_tool_cache[plugin_id] = tools
        # Cache summaries
        self._discovered_summaries[plugin_id] = [
            ToolSummary(name=t.name, description=getattr(t, "description", "")) for t in tools
        ]
        logger.info("native_plugin_loaded", plugin_id=plugin_id, tools=len(tools))
        return True

    async def disconnect_plugin(self, user_id: str, plugin_id: str) -> bool:
        """Deactivate a plugin for a user."""
        manifest = self._catalog.get(plugin_id)
        if manifest is None:
            return False

        self._errors.pop((user_id, plugin_id), None)

        if manifest.kind in (PluginKind.MCP_STDIO, PluginKind.MCP_HTTP, PluginKind.MCP_OAUTH):
            key = (user_id, plugin_id)
            entry = self._mcp_toolsets.pop(key, None)
            if entry is not None:
                with contextlib.suppress(Exception):
                    await entry[0].close()
            # Revoke OAuth tokens on disconnect
            if manifest.kind == PluginKind.MCP_OAUTH:
                get_oauth_service().revoke_tokens(user_id, plugin_id)

        # Revoke Google OAuth tokens for native plugins
        if manifest.kind == PluginKind.NATIVE and manifest.google_oauth_scopes:
            get_google_oauth_service().revoke(user_id, plugin_id)

        user_mcps = self._user_enabled.get(user_id, {})
        user_mcps.pop(plugin_id, None)
        self._persist_enabled(user_id)
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
        self,
        user_id: str,
        plugin_id: str,
        manifest: PluginManifest,
    ) -> list:
        """Get tools for a specific plugin."""
        if manifest.kind == PluginKind.E2B:
            from app.tools.code_exec import get_e2b_tools

            return get_e2b_tools()

        if manifest.kind == PluginKind.NATIVE:
            cached = self._native_tool_cache.get(plugin_id)
            if cached is None:
                # Lazy-load: tools not in cache (e.g. after process restart)
                self._connect_native(plugin_id, manifest)
                cached = self._native_tool_cache.get(plugin_id, [])
            return cached

        if manifest.kind in (PluginKind.MCP_STDIO, PluginKind.MCP_HTTP, PluginKind.MCP_OAUTH):
            key = self._mcp_key(user_id, plugin_id, manifest)
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
            try:
                return await toolset.get_tools()
            except Exception:
                # Connection/token may be stale — evict and reconnect once
                logger.warning("mcp_get_tools_stale", plugin_id=plugin_id, exc_info=True)
                # Only close if not a singleton shared by other users
                if not manifest.singleton:
                    with contextlib.suppress(Exception):
                        await toolset.close()
                self._mcp_toolsets.pop(key, None)
                success = await self.connect_plugin(user_id, plugin_id)
                if not success:
                    return []
                entry = self._mcp_toolsets.get(key)
                if entry is None:
                    return []
                return await entry[0].get_tools()

        return []

    # ------------------------------------------------------------------
    # Lazy tool loading: summaries + on-demand schemas
    # ------------------------------------------------------------------

    def get_tool_summaries(self, user_id: str) -> list[dict[str, Any]]:
        """Return lightweight tool summaries for all enabled plugins.

        Only includes tools from ``_discovered_summaries`` (verified by
        actually connecting to the MCP server / loading the native plugin).
        Falls back to ``manifest.tools_summary`` ONLY for native plugins
        whose factory function defines the tool names directly.  For MCP
        servers, unverified summaries are excluded to prevent the agent
        from hallucinating tool names that don't match the real MCP tools.
        """
        result = []
        for plugin_id in self.get_enabled_ids(user_id):
            manifest = self._catalog.get(plugin_id)
            if manifest is None:
                continue
            discovered = self._discovered_summaries.get(plugin_id)
            if discovered is not None:
                summaries = discovered
            elif manifest.kind == PluginKind.NATIVE:
                # Native plugins: tools_summary names match the Python function names
                summaries = manifest.tools_summary
            else:
                # MCP servers: tools_summary names are unverified guesses — skip them
                logger.debug(
                    "skipping_unverified_mcp_summaries",
                    plugin_id=plugin_id,
                    reason="MCP not connected yet; tools_summary names may not match real tool names",
                )
                continue
            for s in summaries:
                result.append(
                    {
                        "plugin": manifest.name,
                        "plugin_id": plugin_id,
                        "tool": s.name,
                        "description": s.description,
                    }
                )
        return result

    def get_capability_snapshot(self, user_id: str) -> dict[str, Any]:
        """Return a structured snapshot of all enabled T2 capabilities for *user_id*.

        Used by the REST API ``GET /plugins/capabilities`` endpoint so the
        dashboard can display a live capability overview without starting a WS session.
        Returns a dict with ``t2`` (enabled plugin summaries) and ``catalog``
        (all available plugin names for discovery).
        """
        t2: list[dict] = []
        for plugin_id in self.get_enabled_ids(user_id):
            manifest = self._catalog.get(plugin_id)
            if manifest is None:
                continue
            # Only use discovered summaries (verified names) — never guessed manifest names
            summaries = self._discovered_summaries.get(plugin_id)
            if summaries is None and manifest.kind in (PluginKind.MCP_STDIO, PluginKind.MCP_HTTP, PluginKind.MCP_OAUTH):
                summaries = []  # MCP not connected — don't guess tool names
            elif summaries is None:
                summaries = manifest.tools_summary  # Native plugins: names match Python functions
            t2.append(
                {
                    "plugin": manifest.name,
                    "plugin_id": plugin_id,
                    "kind": str(manifest.kind),
                    "description": manifest.description,
                    "tags": manifest.tags,
                    "tools": [{"name": s.name, "description": s.description} for s in summaries],
                }
            )

        available_catalog = [
            {"id": m.id, "name": m.name, "description": m.description, "kind": str(m.kind)}
            for m in self._catalog.values()
            if m.id not in self.get_enabled_ids(user_id)
        ]

        return {
            "t2_enabled_count": len(t2),
            "t2": t2,
            "available_plugins": available_catalog,
        }

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
            # Extract parameter schema from ADK tool declaration
            decl = None
            if hasattr(t, "_get_declaration"):
                with contextlib.suppress(Exception):
                    decl = t._get_declaration()
            if decl is None:
                decl = getattr(t, "_function_declaration", None)
            if decl is not None:
                params_schema = getattr(decl, "parameters", None)
                if params_schema is not None:
                    params = (
                        params_schema.model_dump(exclude_none=True)
                        if hasattr(params_schema, "model_dump")
                        else dict(params_schema)
                    )
            schemas.append(ToolSchema(name=name, description=desc, parameters=params))
        return schemas

    def get_tool_source(self, tool_name: str) -> str | None:
        """Return the plugin name that provides *tool_name*, or None.

        Checks discovered summaries first (MCP tools), then native tool caches.
        Used by the event pipeline to classify tool actions for the UI.
        """
        for plugin_id, summaries in self._discovered_summaries.items():
            for s in summaries:
                if s.name == tool_name:
                    manifest = self._catalog.get(plugin_id)
                    return manifest.name if manifest else plugin_id
        # Also check tool_summary from manifests (before first connection)
        for _plugin_id, manifest in self._catalog.items():
            for s in manifest.tools_summary:
                if s.name == tool_name:
                    return manifest.name
        return None

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    async def disconnect_all(self, user_id: str) -> None:
        """Disconnect all plugins for a user."""
        ids = self.get_enabled_ids(user_id)
        for pid in ids:
            await self.disconnect_plugin(user_id, pid)

    async def evict_idle_toolsets(self) -> int:
        """Close MCP toolsets idle longer than the TTL.

        Only closes the underlying connection — the plugin stays enabled
        so that lazy reconnection fires on next use.
        """
        now = time.monotonic()
        expired: list[tuple[str, str]] = [
            k for k, (_, ts) in self._mcp_toolsets.items() if now - ts > _TOOLSET_IDLE_TTL
        ]
        for key in expired:
            entry = self._mcp_toolsets.pop(key, None)
            if entry is not None:
                with contextlib.suppress(Exception):
                    await entry[0].close()
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
