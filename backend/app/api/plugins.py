"""Plugin management API — catalog, toggle, secrets, tool schemas.

Extends the legacy /mcp/ endpoints with the new unified plugin system.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.middleware.auth_middleware import CurrentUser
from app.models.plugin import (
    PluginManifest,
    PluginStatus,
    PluginToggle,
    PluginUserSecrets,
    ToolSchema,
)
from app.services.plugin_registry import get_plugin_registry

router = APIRouter()


@router.get("/catalog", response_model=list[PluginStatus])
async def list_catalog(user: CurrentUser):
    """Return all plugins with per-user state (available/enabled/connected/error)."""
    registry = get_plugin_registry()
    return registry.get_catalog(user.uid)


@router.get("/enabled", response_model=list[str])
async def list_enabled(user: CurrentUser):
    """Return IDs of plugins currently enabled for the user."""
    registry = get_plugin_registry()
    return registry.get_enabled_ids(user.uid)


@router.post("/toggle")
async def toggle_plugin(body: PluginToggle, user: CurrentUser):
    """Enable or disable a plugin for the user."""
    registry = get_plugin_registry()
    manifest = registry.get_manifest(body.plugin_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail=f"Plugin '{body.plugin_id}' not found")
    enabled = await registry.toggle_plugin(user.uid, body)
    return {"plugin_id": body.plugin_id, "enabled": enabled}


@router.post("/secrets")
async def set_secrets(body: PluginUserSecrets, user: CurrentUser):
    """Store user-provided secrets (API keys) for a plugin."""
    registry = get_plugin_registry()
    manifest = registry.get_manifest(body.plugin_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail=f"Plugin '{body.plugin_id}' not found")
    registry.set_user_secrets(user.uid, body.plugin_id, body.secrets)
    return {"plugin_id": body.plugin_id, "status": "secrets_saved"}


@router.get("/summaries")
async def list_tool_summaries(user: CurrentUser):
    """Return lightweight tool summaries for all enabled plugins.

    Used by the agent for capability awareness without loading full schemas.
    """
    registry = get_plugin_registry()
    return registry.get_tool_summaries(user.uid)


@router.get("/{plugin_id}/tools", response_model=list[ToolSchema])
async def get_tool_schemas(plugin_id: str, user: CurrentUser):
    """Return full tool schemas for a specific plugin (on-demand loading)."""
    registry = get_plugin_registry()
    manifest = registry.get_manifest(plugin_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")
    return await registry.get_tool_schemas(plugin_id, user.uid)


@router.get("/{plugin_id}", response_model=PluginStatus)
async def get_plugin_detail(plugin_id: str, user: CurrentUser):
    """Return detailed status for a single plugin."""
    registry = get_plugin_registry()
    catalog = registry.get_catalog(user.uid)
    for p in catalog:
        if p.id == plugin_id:
            return p
    raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")
