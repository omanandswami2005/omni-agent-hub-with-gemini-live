"""Dynamic McpToolset instantiation — load/unload MCP plugins at runtime.

The :class:`MCPManager` maintains a per-user registry of active
:class:`McpToolset` instances keyed by MCP id.  Toolsets are lazily
created on first access and torn down on disconnect or toggle-off.
"""

from __future__ import annotations

import contextlib

from google.adk.tools.mcp_tool.mcp_toolset import (
    McpToolset,
    StdioConnectionParams,
    StreamableHTTPConnectionParams,
)
from mcp.client.stdio import StdioServerParameters

from app.models.mcp import MCPCatalogItem, MCPConfig, MCPToggle, TransportType
from app.utils.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Built-in MCP catalog (seed data)
# ---------------------------------------------------------------------------

MCP_CATALOG: list[MCPConfig] = [
    MCPConfig(
        id="brave-search",
        name="Brave Search",
        description="Web search via the Brave Search API.",
        category="search",
        transport=TransportType.STDIO,
        command="npx",
        args=["-y", "@anthropic/mcp-brave-search"],
        env={"BRAVE_API_KEY": ""},
        icon="brave",
    ),
    MCPConfig(
        id="playwright",
        name="Playwright",
        description="Browser automation — navigate, click, screenshot.",
        category="dev",
        transport=TransportType.STDIO,
        command="npx",
        args=["-y", "@anthropic/mcp-playwright"],
        icon="playwright",
    ),
    MCPConfig(
        id="github",
        name="GitHub",
        description="Interact with GitHub repos, issues, PRs.",
        category="dev",
        transport=TransportType.STDIO,
        command="npx",
        args=["-y", "@anthropic/mcp-github"],
        env={"GITHUB_TOKEN": ""},
        icon="github",
    ),
    MCPConfig(
        id="notion",
        name="Notion",
        description="Read and write Notion pages and databases.",
        category="productivity",
        transport=TransportType.STDIO,
        command="npx",
        args=["-y", "@anthropic/mcp-notion"],
        env={"NOTION_TOKEN": ""},
        icon="notion",
    ),
    MCPConfig(
        id="google-calendar",
        name="Google Calendar",
        description="Manage Google Calendar events.",
        category="productivity",
        transport=TransportType.STDIO,
        command="npx",
        args=["-y", "@anthropic/mcp-google-calendar"],
        icon="calendar",
    ),
    MCPConfig(
        id="slack",
        name="Slack",
        description="Send messages, read channels in Slack.",
        category="communication",
        transport=TransportType.STDIO,
        command="npx",
        args=["-y", "@anthropic/mcp-slack"],
        env={"SLACK_TOKEN": ""},
        icon="slack",
    ),
    MCPConfig(
        id="wolfram-alpha",
        name="Wolfram Alpha",
        description="Computational knowledge engine queries.",
        category="other",
        transport=TransportType.STDIO,
        command="npx",
        args=["-y", "@anthropic/mcp-wolfram-alpha"],
        env={"WOLFRAM_APP_ID": ""},
        icon="wolfram",
    ),
    MCPConfig(
        id="wikipedia",
        name="Wikipedia",
        description="Search and read Wikipedia articles.",
        category="search",
        transport=TransportType.STREAMABLE_HTTP,
        url="https://mcp.wiki/api",
        icon="wikipedia",
    ),
    MCPConfig(
        id="filesystem",
        name="Filesystem",
        description="Read/write local files (sandboxed).",
        category="other",
        transport=TransportType.STDIO,
        command="npx",
        args=["-y", "@anthropic/mcp-filesystem", "/tmp/sandbox"],
        icon="folder",
    ),
]

_CATALOG_MAP: dict[str, MCPConfig] = {m.id: m for m in MCP_CATALOG}


# ---------------------------------------------------------------------------
# MCPManager
# ---------------------------------------------------------------------------


class MCPManager:
    """Per-user MCP connection lifecycle manager.

    Connections are keyed by ``(user_id, mcp_id)``.  Each connection wraps
    an ADK :class:`McpToolset` that can be injected into an agent's tool
    list at runtime.
    """

    def __init__(self) -> None:
        # { (user_id, mcp_id): McpToolset }
        self._toolsets: dict[tuple[str, str], McpToolset] = {}
        # { user_id: { mcp_id: enabled } }
        self._user_enabled: dict[str, dict[str, bool]] = {}

    # ------------------------------------------------------------------
    # Catalog helpers
    # ------------------------------------------------------------------

    def get_catalog(self, user_id: str | None = None) -> list[MCPCatalogItem]:
        """Return the full MCP catalog with per-user enabled state."""
        enabled = self._user_enabled.get(user_id, {}) if user_id else {}
        return [
            MCPCatalogItem(
                id=m.id,
                name=m.name,
                description=m.description,
                category=m.category,
                icon=m.icon,
                enabled=enabled.get(m.id, False),
            )
            for m in MCP_CATALOG
        ]

    def get_mcp_config(self, mcp_id: str) -> MCPConfig | None:
        """Return config for a single MCP, or *None*."""
        return _CATALOG_MAP.get(mcp_id)

    def get_enabled_ids(self, user_id: str) -> list[str]:
        """Return list of enabled MCP ids for a user."""
        return [
            mcp_id
            for mcp_id, on in self._user_enabled.get(user_id, {}).items()
            if on
        ]

    # ------------------------------------------------------------------
    # Connect / disconnect
    # ------------------------------------------------------------------

    def _build_connection_params(
        self, config: MCPConfig
    ) -> StdioConnectionParams | StreamableHTTPConnectionParams:
        """Create the correct connection params from an :class:`MCPConfig`."""
        if config.transport == TransportType.STREAMABLE_HTTP:
            return StreamableHTTPConnectionParams(url=config.url)
        # Default: stdio
        return StdioConnectionParams(
            server_params=StdioServerParameters(
                command=config.command,
                args=config.args,
                env=config.env or None,
            ),
        )

    async def connect_mcp(self, user_id: str, mcp_id: str) -> McpToolset | None:
        """Instantiate and return a :class:`McpToolset` for *mcp_id*.

        Returns an existing toolset if already connected.
        """
        key = (user_id, mcp_id)
        if key in self._toolsets:
            return self._toolsets[key]

        config = self.get_mcp_config(mcp_id)
        if config is None:
            logger.warning("mcp_not_found", mcp_id=mcp_id)
            return None

        params = self._build_connection_params(config)
        toolset = McpToolset(connection_params=params)
        self._toolsets[key] = toolset

        # Mark enabled
        self._user_enabled.setdefault(user_id, {})[mcp_id] = True
        logger.info("mcp_connected", user_id=user_id, mcp_id=mcp_id)
        return toolset

    async def disconnect_mcp(self, user_id: str, mcp_id: str) -> bool:
        """Disconnect and clean up a toolset.  Returns True if it existed."""
        key = (user_id, mcp_id)
        toolset = self._toolsets.pop(key, None)
        if toolset is not None:
            try:
                await toolset.close()
            except Exception:
                logger.warning("mcp_close_failed", mcp_id=mcp_id, exc_info=True)
        # Mark disabled
        user_mcps = self._user_enabled.get(user_id, {})
        user_mcps.pop(mcp_id, None)
        logger.info("mcp_disconnected", user_id=user_id, mcp_id=mcp_id)
        return toolset is not None

    async def toggle_mcp(self, user_id: str, toggle: MCPToggle) -> bool:
        """Enable or disable an MCP.  Returns the new enabled state."""
        if toggle.enabled:
            await self.connect_mcp(user_id, toggle.mcp_id)
        else:
            await self.disconnect_mcp(user_id, toggle.mcp_id)
        return toggle.enabled

    # ------------------------------------------------------------------
    # Tool retrieval
    # ------------------------------------------------------------------

    async def get_tools(self, user_id: str) -> list:
        """Return all ADK tools from enabled MCPs for a user."""
        tools: list = []
        for mcp_id in self.get_enabled_ids(user_id):
            key = (user_id, mcp_id)
            toolset = self._toolsets.get(key)
            if toolset is not None:
                try:
                    mcp_tools = await toolset.get_tools()
                    tools.extend(mcp_tools)
                except Exception:
                    logger.warning(
                        "mcp_get_tools_failed", mcp_id=mcp_id, exc_info=True
                    )
        return tools

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    async def disconnect_all(self, user_id: str) -> None:
        """Disconnect all MCPs for a user (e.g. on session end)."""
        ids = self.get_enabled_ids(user_id)
        for mcp_id in ids:
            await self.disconnect_mcp(user_id, mcp_id)

    async def shutdown(self) -> None:
        """Close all connections (server shutdown)."""
        for (_user_id, _mcp_id), toolset in list(self._toolsets.items()):
            with contextlib.suppress(Exception):
                await toolset.close()
        self._toolsets.clear()
        self._user_enabled.clear()
        logger.info("mcp_manager_shutdown")


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
