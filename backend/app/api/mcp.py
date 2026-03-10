"""MCP plugin management — catalog, enable/disable, detail."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.models.mcp import MCPCatalogItem, MCPConfig, MCPToggle
from app.services.mcp_manager import get_mcp_manager

router = APIRouter()

# Hard-coded user_id placeholder until auth middleware wires the real one.
_DEFAULT_USER = "anonymous"


@router.get("/catalog", response_model=list[MCPCatalogItem])
async def list_catalog(user_id: str = _DEFAULT_USER):
    """Return available MCPs with per-user enabled state."""
    mgr = get_mcp_manager()
    return mgr.get_catalog(user_id)


@router.get("/enabled", response_model=list[str])
async def list_enabled(user_id: str = _DEFAULT_USER):
    """Return IDs of MCPs currently enabled for the user."""
    mgr = get_mcp_manager()
    return mgr.get_enabled_ids(user_id)


@router.post("/toggle")
async def toggle_mcp(body: MCPToggle, user_id: str = _DEFAULT_USER):
    """Enable or disable an MCP plugin for the user."""
    mgr = get_mcp_manager()
    config = mgr.get_mcp_config(body.mcp_id)
    if config is None:
        raise HTTPException(status_code=404, detail=f"MCP '{body.mcp_id}' not found")
    enabled = await mgr.toggle_mcp(user_id, body)
    return {"mcp_id": body.mcp_id, "enabled": enabled}


@router.get("/{mcp_id}", response_model=MCPConfig)
async def get_mcp_detail(mcp_id: str):
    """Return full config for a single MCP."""
    mgr = get_mcp_manager()
    config = mgr.get_mcp_config(mcp_id)
    if config is None:
        raise HTTPException(status_code=404, detail=f"MCP '{mcp_id}' not found")
    return config
