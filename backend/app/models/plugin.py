"""Plugin manifest & registry Pydantic schemas.

The plugin system supports three plugin kinds:
  - **mcp_stdio** — MCP server launched via subprocess (npx, python, etc.)
  - **mcp_http** — MCP server reachable at a StreamableHTTP URL
  - **native** — Python module providing ADK FunctionTool instances
  - **e2b** — Code execution via E2B sandbox (special built-in)

Every plugin declares a manifest describing its capabilities.  The agent
receives only the *summary* (name + one-line description) initially.
Full tool schemas are loaded on-demand when the user enables the plugin.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class PluginKind(StrEnum):
    """How the plugin is executed."""

    MCP_STDIO = "mcp_stdio"
    MCP_HTTP = "mcp_http"
    MCP_OAUTH = "mcp_oauth"
    NATIVE = "native"
    E2B = "e2b"


class ToolCapability(StrEnum):
    """Predefined capability tags for tool↔persona matching.

    Plugins declare which capabilities they provide via ``tags``.
    Personas declare which capabilities they need via ``capabilities``.
    The ToolRegistry matches tools to personas by tag intersection.
    """

    SEARCH = "search"
    CODE_EXECUTION = "code_execution"
    KNOWLEDGE = "knowledge"
    CREATIVE = "creative"
    COMMUNICATION = "communication"
    WEB = "web"
    SANDBOX = "sandbox"
    DATA = "data"
    MEDIA = "media"
    DEVICE = "device"
    WILDCARD = "*"


class PluginCategory(StrEnum):
    SEARCH = "search"
    PRODUCTIVITY = "productivity"
    DEV = "dev"
    COMMUNICATION = "communication"
    FINANCE = "finance"
    SANDBOX = "sandbox"
    DATA = "data"
    CREATIVE = "creative"
    KNOWLEDGE = "knowledge"
    OTHER = "other"


class ToolSummary(BaseModel):
    """Lightweight tool descriptor — sent to the agent before activation.

    The agent sees name + description and can decide whether to activate
    the tool (lazy loading).  Full JSON Schema ``parameters`` are only
    fetched once the user/agent requests it.
    """

    name: str
    description: str = ""


class ToolSchema(BaseModel):
    """Full tool schema — loaded on demand when the plugin is activated."""

    name: str
    description: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)


class OAuthConfig(BaseModel):
    """OAuth 2.0 configuration for MCP_OAUTH plugins.

    Fields are auto-discovered via RFC 9470 + RFC 8414 at runtime,
    so only ``client_name`` and ``scopes`` are typically specified in JSON.
    """

    client_name: str = Field(
        default="Omni Hub",
        description="Display name used during dynamic client registration.",
    )
    scopes: list[str] = Field(
        default_factory=list,
        description="OAuth scopes to request (empty = server default).",
    )
    redirect_uri: str = Field(
        default="",
        description="Override redirect URI. Auto-generated if empty.",
    )


class PluginManifest(BaseModel):
    """Self-describing plugin configuration.

    A developer creating a new plugin only needs to define this manifest.
    The PluginRegistry handles all lifecycle management.
    """

    id: str
    name: str
    description: str = ""
    version: str = "0.1.0"
    author: str = ""
    category: PluginCategory = PluginCategory.OTHER
    kind: PluginKind = PluginKind.MCP_STDIO
    icon: str = ""

    # ── Capability tags (for persona matching) ──
    tags: list[str] = Field(
        default_factory=list,
        description="Capability tags this plugin provides. "
        "Matched against persona capabilities for tool distribution. "
        "Use '*' to match all personas.",
    )

    # ── MCP_STDIO fields ──
    command: str = ""
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    env_keys: list[str] = Field(
        default_factory=list,
        description="Required env var names. Values come from user secrets or .env.",
    )

    # ── MCP_HTTP fields ──
    url: str = ""

    # ── MCP_OAUTH fields ──
    oauth: OAuthConfig | None = Field(
        default=None,
        description="OAuth 2.0 configuration for mcp_oauth plugins.",
    )

    # ── Native plugin fields ──
    module: str = Field(
        default="",
        description="Dotted Python module path, e.g. 'app.plugins.telegram_notify'",
    )
    factory: str = Field(
        default="get_tools",
        description="Name of the function in `module` that returns list[FunctionTool]",
    )

    # ── Tool discovery ──
    tools_summary: list[ToolSummary] = Field(
        default_factory=list,
        description="Pre-declared lightweight tool list. "
        "For MCP plugins, auto-discovered at first connect.",
    )

    # ── Behaviour flags ──
    lazy: bool = Field(
        default=True,
        description="If True, tools are only loaded when the user enables the plugin.",
    )
    singleton: bool = Field(
        default=False,
        description="If True, one instance is shared across all users.",
    )
    requires_auth: bool = Field(
        default=False,
        description="If True, user must provide credentials (API keys) before enabling.",
    )

    # ── Google OAuth scopes (for native plugins needing per-user Google tokens) ──
    google_oauth_scopes: list[str] = Field(
        default_factory=list,
        description="Google OAuth 2.0 scopes. If set, plugin uses per-user Google OAuth.",
    )

    # ── Context management ──
    max_context_tokens: int = Field(
        default=0,
        description="Max tokens this plugin's tools may consume per turn. 0 = no limit.",
    )


class PluginState(StrEnum):
    """Runtime state of a plugin for a user."""

    AVAILABLE = "available"  # In catalog, not enabled
    ENABLED = "enabled"  # User toggled on, toolset not yet connected
    CONNECTED = "connected"  # Toolset active, tools loaded
    ERROR = "error"  # Failed to connect/load


class PluginStatus(BaseModel):
    """Plugin runtime status for API responses."""

    id: str
    name: str
    description: str = ""
    category: PluginCategory = PluginCategory.OTHER
    kind: PluginKind = PluginKind.MCP_STDIO
    icon: str = ""
    state: PluginState = PluginState.AVAILABLE
    error: str | None = None
    tools_summary: list[ToolSummary] = Field(default_factory=list)
    requires_auth: bool = False
    env_keys: list[str] = Field(default_factory=list)
    google_oauth_scopes: list[str] = Field(default_factory=list)
    version: str = "0.1.0"
    author: str = ""


class PluginToggle(BaseModel):
    """Enable or disable a plugin."""

    plugin_id: str
    enabled: bool


class PluginUserSecrets(BaseModel):
    """User-provided secrets for a plugin (e.g., API keys)."""

    plugin_id: str
    secrets: dict[str, str] = Field(default_factory=dict)
