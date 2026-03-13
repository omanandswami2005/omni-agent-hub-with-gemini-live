"""MCPManager — compatibility wrapper around PluginRegistry.

The old MCPManager API is preserved so that existing callers (ws_live,
init endpoint, MCP API) continue to work unchanged.  All heavy lifting
is delegated to :class:`~app.services.plugin_registry.PluginRegistry`.
"""

from __future__ import annotations

from app.models.mcp import MCPCatalogItem, MCPConfig, MCPToggle, TransportType, MCPCategory
from app.models.plugin import PluginToggle
from app.services.plugin_registry import _load_mcp_configs, get_plugin_registry
from app.utils.logging import get_logger

logger = get_logger(__name__)


def _safe_category(value: str) -> MCPCategory:
    """Convert a category string to MCPCategory, defaulting to OTHER."""
    try:
        return MCPCategory(value)
    except (ValueError, KeyError):
        return MCPCategory.OTHER


def _build_catalog() -> list[MCPConfig]:
    """Build a static MCPConfig list from the JSON MCP config files.

    Used to expose the legacy ``MCP_CATALOG`` constant for backward
    compatibility with older code and tests.  Only includes MCP server
    entries (not native plugins or E2B).
    """
    result: list[MCPConfig] = []
    for m in _load_mcp_configs():
        transport = TransportType.STDIO
        if m.kind in ("mcp_http", "mcp_oauth"):
            transport = TransportType.STREAMABLE_HTTP
        result.append(MCPConfig(
            id=m.id,
            name=m.name,
            description=m.description,
            category=_safe_category(m.category),
            transport=transport,
            command=m.command,
            args=m.args,
            url=m.url,
            env=m.env,
            icon=m.icon,
        ))
    return result


# Static catalog of MCP servers loaded from app/mcps/*.json
MCP_CATALOG: list[MCPConfig] = _build_catalog()


# ---------------------------------------------------------------------------
# MCPManager — thin compatibility wrapper
# ---------------------------------------------------------------------------


class MCPManager:
    """Backward-compatible wrapper — delegates everything to PluginRegistry.

    Existing callers (ws_live, init, mcp API) use this unchanged.
    New code should use ``get_plugin_registry()`` directly.
    """

    @property
    def _registry(self):
        return get_plugin_registry()

    # ------------------------------------------------------------------
    # Catalog helpers
    # ------------------------------------------------------------------

    def get_catalog(self, user_id: str | None = None) -> list[MCPCatalogItem]:
        """Return the full catalog with per-user enabled state."""
        statuses = self._registry.get_catalog(user_id)
        return [
            MCPCatalogItem(
                id=s.id,
                name=s.name,
                description=s.description,
                category=_safe_category(s.category),
                icon=s.icon,
                enabled=s.state in ("enabled", "connected"),
                is_sandbox=s.kind == "e2b",
            )
            for s in statuses
        ]

    def get_mcp_config(self, mcp_id: str) -> MCPConfig | None:
        """Return config for a single MCP (legacy format)."""
        manifest = self._registry.get_manifest(mcp_id)
        if manifest is None:
            return None
        transport = TransportType.STDIO
        if manifest.kind == "mcp_http":
            transport = TransportType.STREAMABLE_HTTP
        return MCPConfig(
            id=manifest.id,
            name=manifest.name,
            description=manifest.description,
            category=_safe_category(manifest.category),
            transport=transport,
            command=manifest.command,
            args=manifest.args,
            url=manifest.url,
            env=manifest.env,
            icon=manifest.icon,
            is_sandbox=manifest.kind == "e2b",
        )

    def get_enabled_ids(self, user_id: str) -> list[str]:
        return self._registry.get_enabled_ids(user_id)

    # ------------------------------------------------------------------
    # Connect / disconnect
    # ------------------------------------------------------------------

    async def connect_mcp(self, user_id: str, mcp_id: str):
        return await self._registry.connect_plugin(user_id, mcp_id)

    async def disconnect_mcp(self, user_id: str, mcp_id: str) -> bool:
        return await self._registry.disconnect_plugin(user_id, mcp_id)

    async def toggle_mcp(self, user_id: str, toggle: MCPToggle) -> bool:
        pt = PluginToggle(plugin_id=toggle.mcp_id, enabled=toggle.enabled)
        return await self._registry.toggle_plugin(user_id, pt)

    # ------------------------------------------------------------------
    # Tool retrieval
    # ------------------------------------------------------------------

    async def get_tools(self, user_id: str) -> list:
        return await self._registry.get_tools(user_id)

    # ------------------------------------------------------------------
    # Available capabilities (for UI display)
    # ------------------------------------------------------------------

    def get_available_capabilities(self, user_id: str | None = None) -> list[dict]:
        if user_id is None:
            return []
        summaries = self._registry.get_tool_summaries(user_id)
        return [
            {
                "id": f"{s['plugin_id']}_{s['tool']}",
                "name": s["tool"],
                "description": s["description"],
                "category": s["plugin_id"],
                "mcp_id": s["plugin_id"],
            }
            for s in summaries
        ]

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    async def disconnect_all(self, user_id: str) -> None:
        await self._registry.disconnect_all(user_id)

    async def evict_idle_toolsets(self) -> int:
        return await self._registry.evict_idle_toolsets()

    async def shutdown(self) -> None:
        await self._registry.shutdown()


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_manager: MCPManager | None = None


def get_mcp_manager() -> MCPManager:
    """Return the global MCP manager instance."""
    global _manager
    if _manager is None:
        _manager = MCPManager()
    return _manager

