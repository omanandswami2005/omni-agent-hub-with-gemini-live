"""MCP plugin Pydantic schemas."""

from enum import StrEnum

from pydantic import BaseModel


class TransportType(StrEnum):
    STDIO = "stdio"
    STREAMABLE_HTTP = "streamable_http"


class MCPCategory(StrEnum):
    SEARCH = "search"
    PRODUCTIVITY = "productivity"
    DEV = "dev"
    COMMUNICATION = "communication"
    FINANCE = "finance"
    SANDBOX = "sandbox"  # For E2B sandbox
    OTHER = "other"


class MCPConfig(BaseModel):
    """Full MCP server configuration."""

    id: str
    name: str
    description: str = ""
    category: MCPCategory = MCPCategory.OTHER
    transport: TransportType = TransportType.STDIO
    command: str = ""  # For stdio MCPs
    args: list[str] = []
    url: str = ""  # For HTTP MCPs
    env: dict[str, str] = {}
    icon: str = ""
    enabled: bool = False
    is_sandbox: bool = False  # True for E2B sandbox (not an MCP server)


class MCPCatalogItem(BaseModel):
    """Lightweight entry shown in the MCP catalog / marketplace."""

    id: str
    name: str
    description: str = ""
    category: MCPCategory = MCPCategory.OTHER
    icon: str = ""
    enabled: bool = False
    is_sandbox: bool = False  # True for E2B sandbox


class MCPToggle(BaseModel):
    """Toggle a single MCP on or off."""

    mcp_id: str
    enabled: bool
