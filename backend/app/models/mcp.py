"""MCP plugin Pydantic schemas."""

from pydantic import BaseModel


class MCPConfig(BaseModel):
    id: str
    name: str
    description: str
    category: str  # search, productivity, dev, communication, etc.
    transport: str  # "stdio" | "streamable_http"
    command: str = ""  # For stdio MCPs
    url: str = ""  # For HTTP MCPs
    env: dict[str, str] = {}  # Required env vars
    icon: str = ""
    enabled: bool = False


class MCPToggle(BaseModel):
    mcp_id: str
    enabled: bool
