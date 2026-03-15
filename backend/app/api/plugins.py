"""Plugin management API — catalog, toggle, secrets, tool schemas, registration, OAuth.

Extends the legacy /mcp/ endpoints with the new unified plugin system.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from app.middleware.auth_middleware import CurrentUser
from app.models.plugin import (
    PluginKind,
    PluginManifest,
    PluginStatus,
    PluginToggle,
    PluginUserSecrets,
    ToolSchema,
)
from app.services.google_oauth_service import get_google_oauth_service
from app.services.oauth_service import get_oauth_service
from app.services.plugin_registry import get_plugin_registry

router = APIRouter()

# Directory for persisted MCP server configs
_MCPS_DIR = Path(__file__).parent.parent / "mcps"


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

    # Block activation when required API keys are missing
    if body.enabled and manifest.requires_auth and manifest.env_keys:
        user_secrets = registry._user_secrets.get(user.uid, {}).get(body.plugin_id) or {}
        missing = [k for k in manifest.env_keys if not user_secrets.get(k)]
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"Missing required API keys for {manifest.name}: {missing}. "
                f"Please add them in the plugin settings first.",
            )

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


@router.get("/capabilities")
async def get_capabilities_snapshot(user: CurrentUser):
    """Return a live capability snapshot for the authenticated user.

    Includes:
    - **T1** core built-in tools (always available, from the agent factory registry)
    - **T2** enabled plugin/MCP tool summaries
    - Available (but not yet enabled) plugins for discovery

    This is the REST equivalent of the agent's ``get_capabilities()`` tool call.
    Poll this endpoint after toggling a plugin to update the UI.
    """
    from app.agents.agent_factory import T1_TOOL_REGISTRY
    from app.services.connection_manager import get_connection_manager

    registry = get_plugin_registry()
    cm = get_connection_manager()

    # T1: build from registry (avoid ADK heavy init for search tool in HTTP context)
    t1: list[dict] = []
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
            desc = (getattr(t, "description", "") or "").strip()
            t1.append({"name": name, "description": desc, "capability_tag": cap})

    # T2: snapshot from registry
    snapshot = registry.get_capability_snapshot(user.uid)

    # T3: from connection manager
    capabilities = cm.get_capabilities(user.uid)
    t3: list[dict] = []
    for ct, cap_data in capabilities.items():
        for tool_def in cap_data.get("local_tools", []):
            if tool_def.get("name"):
                t3.append({
                    "name": tool_def["name"],
                    "description": tool_def.get("description", ""),
                    "client_type": str(ct),
                })

    return {
        "t1": t1,
        "t2": snapshot["t2"],
        "t2_enabled_count": snapshot["t2_enabled_count"],
        "t3": t3,
        "available_plugins": snapshot["available_plugins"],
    }


@router.get("/{plugin_id}/tools", response_model=list[ToolSchema])
async def get_tool_schemas(plugin_id: str, user: CurrentUser):
    """Return full tool schemas for a specific plugin (on-demand loading)."""
    registry = get_plugin_registry()
    manifest = registry.get_manifest(plugin_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")
    return await registry.get_tool_schemas(plugin_id, user.uid)


@router.get("/{plugin_id}/capabilities")
async def get_plugin_capabilities(plugin_id: str, user: CurrentUser):
    """Return full function schemas (name, description, parameters) for a specific plugin.

    This is the REST equivalent of the agent's ``get_capabilities_of(plugin_name)`` tool.
    Returns tool schemas including full parameter definitions once the plugin is connected.
    Falls back to lightweight summaries if the plugin is enabled but not yet connected.
    """
    registry = get_plugin_registry()
    manifest = registry.get_manifest(plugin_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")

    enabled_ids = registry.get_enabled_ids(user.uid)
    if plugin_id not in enabled_ids:
        # Return manifest-level summary even if not enabled
        return {
            "plugin_id": plugin_id,
            "plugin": manifest.name,
            "kind": str(manifest.kind),
            "enabled": False,
            "tools": [
                {"name": s.name, "description": s.description, "parameters": {}}
                for s in manifest.tools_summary
            ],
            "hint": "Enable this plugin to load full function schemas.",
        }

    schemas = await registry.get_tool_schemas(plugin_id, user.uid)
    summaries = registry._discovered_summaries.get(plugin_id, manifest.tools_summary)
    tools = (
        [{"name": s.name, "description": s.description, "parameters": s.parameters} for s in schemas]
        if schemas
        else [{"name": s.name, "description": s.description, "parameters": {}} for s in summaries]
    )
    return {
        "plugin_id": plugin_id,
        "plugin": manifest.name,
        "kind": str(manifest.kind),
        "enabled": True,
        "tools": tools,
    }


@router.get("/{plugin_id}", response_model=PluginStatus)
async def get_plugin_detail(plugin_id: str, user: CurrentUser):
    """Return detailed status for a single plugin."""
    registry = get_plugin_registry()
    catalog = registry.get_catalog(user.uid)
    for p in catalog:
        if p.id == plugin_id:
            return p
    raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")


# ---------------------------------------------------------------------------
# OAuth flow for MCP_OAUTH plugins
# ---------------------------------------------------------------------------


@router.post("/{plugin_id}/oauth/start")
async def start_oauth(plugin_id: str, user: CurrentUser):
    """Start OAuth authorization for an MCP_OAUTH plugin.

    Returns the authorization URL that the frontend should redirect the user to.
    """
    registry = get_plugin_registry()
    manifest = registry.get_manifest(plugin_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")
    if manifest.kind != PluginKind.MCP_OAUTH:
        raise HTTPException(status_code=400, detail=f"Plugin '{plugin_id}' does not use OAuth")
    if not manifest.url:
        raise HTTPException(status_code=400, detail=f"Plugin '{plugin_id}' has no MCP server URL")

    oauth_cfg = manifest.oauth
    client_name = oauth_cfg.client_name if oauth_cfg else "Omni Hub"
    scopes = oauth_cfg.scopes if oauth_cfg else []
    redirect_uri = oauth_cfg.redirect_uri if oauth_cfg and oauth_cfg.redirect_uri else ""

    try:
        oauth = get_oauth_service()
        auth_url = await oauth.start_oauth_flow(
            plugin_id=plugin_id,
            user_id=user.uid,
            mcp_server_url=manifest.url,
            client_name=client_name,
            scopes=scopes,
            redirect_uri=redirect_uri,
        )
        return {"auth_url": auth_url, "plugin_id": plugin_id}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/oauth/callback", response_class=HTMLResponse)
async def oauth_callback(request: Request):
    """Handle OAuth redirect callback.

    The OAuth server redirects here with ``?code=...&state=...``.
    After token exchange, auto-connects the plugin and closes the popup.
    """
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    error = request.query_params.get("error")

    if error:
        error_desc = request.query_params.get("error_description", error)
        return HTMLResponse(_oauth_result_page(success=False, message=error_desc))

    if not code or not state:
        return HTMLResponse(_oauth_result_page(success=False, message="Missing code or state"))

    try:
        oauth = get_oauth_service()
        user_id, plugin_id = await oauth.handle_callback(code, state)

        # Auto-connect the plugin now that we have tokens
        registry = get_plugin_registry()
        await registry.connect_plugin(user_id, plugin_id)

        return HTMLResponse(
            _oauth_result_page(
                success=True,
                message=f"Connected to {plugin_id}!",
                plugin_id=plugin_id,
            )
        )
    except Exception as exc:
        return HTMLResponse(_oauth_result_page(success=False, message=str(exc)))


@router.post("/{plugin_id}/oauth/disconnect")
async def disconnect_oauth(plugin_id: str, user: CurrentUser):
    """Revoke OAuth tokens and disconnect an MCP_OAUTH plugin."""
    registry = get_plugin_registry()
    manifest = registry.get_manifest(plugin_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")
    if manifest.kind != PluginKind.MCP_OAUTH:
        raise HTTPException(status_code=400, detail=f"Plugin '{plugin_id}' does not use OAuth")

    await registry.disconnect_plugin(user.uid, plugin_id)
    return {"plugin_id": plugin_id, "status": "disconnected"}


# ---------------------------------------------------------------------------
# Google OAuth — per-user Google account connection for native plugins
# ---------------------------------------------------------------------------


@router.post("/{plugin_id}/google-oauth/start")
async def start_google_oauth(plugin_id: str, user: CurrentUser):
    """Start Google OAuth 2.0 flow for a native plugin that needs per-user Google access."""
    registry = get_plugin_registry()
    manifest = registry.get_manifest(plugin_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")
    if not manifest.google_oauth_scopes:
        raise HTTPException(
            status_code=400, detail=f"Plugin '{plugin_id}' does not use Google OAuth"
        )

    goauth = get_google_oauth_service()
    auth_url = goauth.start_flow(
        user_id=user.uid,
        plugin_id=plugin_id,
        scopes=manifest.google_oauth_scopes,
    )
    return {"auth_url": auth_url, "plugin_id": plugin_id}


@router.get("/google-oauth/callback", response_class=HTMLResponse)
async def google_oauth_callback(request: Request):
    """Handle Google OAuth redirect callback."""
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    error = request.query_params.get("error")

    if error:
        return HTMLResponse(_oauth_result_page(success=False, message=error))

    if not code or not state:
        return HTMLResponse(_oauth_result_page(success=False, message="Missing code or state"))

    try:
        goauth = get_google_oauth_service()
        user_id, plugin_id = await goauth.handle_callback(code, state)

        # Auto-enable the plugin
        registry = get_plugin_registry()
        await registry.connect_plugin(user_id, plugin_id)

        return HTMLResponse(
            _oauth_result_page(
                success=True,
                message=f"Google account connected for {plugin_id}!",
                plugin_id=plugin_id,
            )
        )
    except Exception as exc:
        return HTMLResponse(_oauth_result_page(success=False, message=str(exc)))


@router.post("/{plugin_id}/google-oauth/disconnect")
async def disconnect_google_oauth(plugin_id: str, user: CurrentUser):
    """Revoke Google OAuth tokens and disconnect."""
    registry = get_plugin_registry()
    manifest = registry.get_manifest(plugin_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")
    if not manifest.google_oauth_scopes:
        raise HTTPException(
            status_code=400, detail=f"Plugin '{plugin_id}' does not use Google OAuth"
        )

    await registry.disconnect_plugin(user.uid, plugin_id)
    return {"plugin_id": plugin_id, "status": "disconnected"}


def _oauth_result_page(
    success: bool,
    message: str,
    plugin_id: str = "",
) -> str:
    """Generate a small HTML page that communicates the OAuth result to the parent window."""
    frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:5173")
    status = "success" if success else "error"
    safe_message = message.replace("\\", "\\\\").replace("'", "\\'").replace("\n", " ")
    return f"""<!DOCTYPE html>
<html><head><title>OAuth {status}</title></head>
<body>
<p>{message}</p>
<script>
  if (window.opener) {{
    window.opener.postMessage({{
      type: 'oauth_callback',
      status: '{status}',
      plugin_id: '{plugin_id}',
      message: '{safe_message}'
    }}, '{frontend_url}');
    window.close();
  }} else {{
    setTimeout(function() {{ window.location.href = '{frontend_url}/mcp-store'; }}, 2000);
  }}
</script>
</body></html>"""


# ---------------------------------------------------------------------------
# MCP Server Registration (install / setup / auto-add to catalog)
# ---------------------------------------------------------------------------

_SAFE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{1,62}[a-z0-9]$")


class RegisterMCPRequest(BaseModel):
    """Payload for registering a new MCP server in the catalog."""

    id: str = Field(..., description="Unique slug (lowercase, hyphens allowed)")
    name: str
    description: str = ""
    kind: PluginKind = PluginKind.MCP_STDIO
    category: str = "other"
    command: str = ""
    args: list[str] = Field(default_factory=list)
    url: str = ""
    env: dict[str, str] = Field(default_factory=dict)
    env_keys: list[str] = Field(default_factory=list)
    requires_auth: bool = False
    tags: list[str] = Field(default_factory=list)
    icon: str = ""
    version: str = "0.1.0"
    author: str = ""


@router.post("/register")
async def register_mcp_server(body: RegisterMCPRequest, user: CurrentUser):
    """Register a new MCP server and persist its config as a JSON file.

    The server is immediately available in the catalog and persists across
    backend restarts.  After registration, toggle it on via ``POST /toggle``.
    """
    # Validate ID format (prevents path traversal and filesystem issues)
    if not _SAFE_ID_RE.match(body.id):
        raise HTTPException(
            status_code=400,
            detail="Invalid id: must be 3-64 lowercase alphanumeric chars or hyphens, "
            "starting and ending with alphanumeric.",
        )

    registry = get_plugin_registry()

    # Prevent overwriting existing plugins
    if registry.get_manifest(body.id) is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Plugin '{body.id}' already exists. Use a different id.",
        )

    # Validate kind-specific fields
    if body.kind == PluginKind.MCP_STDIO and not body.command:
        raise HTTPException(status_code=400, detail="mcp_stdio requires 'command' field")
    if body.kind == PluginKind.MCP_HTTP and not body.url:
        raise HTTPException(status_code=400, detail="mcp_http requires 'url' field")

    # Build manifest
    manifest = PluginManifest(
        id=body.id,
        name=body.name,
        description=body.description,
        kind=body.kind,
        category=body.category,
        command=body.command,
        args=body.args,
        url=body.url,
        env=body.env,
        env_keys=body.env_keys,
        requires_auth=body.requires_auth,
        tags=body.tags,
        icon=body.icon,
        version=body.version,
        author=body.author,
    )

    # Register in-memory (immediately available)
    registry.register_plugin(manifest)

    # Persist to JSON config file so it survives restarts
    _MCPS_DIR.mkdir(parents=True, exist_ok=True)
    config_path = _MCPS_DIR / f"{body.id}.json"
    config_data = manifest.model_dump(exclude_none=True, exclude_defaults=True)
    # Always include these core fields even if default
    config_data["id"] = body.id
    config_data["name"] = body.name
    config_data["kind"] = body.kind.value
    config_path.write_text(
        json.dumps(config_data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    return {
        "plugin_id": body.id,
        "status": "registered",
        "config_path": f"app/mcps/{body.id}.json",
        "message": f"MCP server '{body.name}' registered. Toggle it on via POST /toggle.",
    }


@router.delete("/{plugin_id}/unregister")
async def unregister_mcp_server(plugin_id: str, user: CurrentUser):
    """Remove a user-registered MCP server from the catalog.

    Only removes servers that have a JSON config in ``app/mcps/``.
    Built-in native plugins cannot be unregistered.
    """
    if not _SAFE_ID_RE.match(plugin_id):
        raise HTTPException(status_code=400, detail="Invalid plugin id")

    registry = get_plugin_registry()
    manifest = registry.get_manifest(plugin_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")

    # Only allow removing JSON-config MCPs (not native plugins)
    config_path = _MCPS_DIR / f"{plugin_id}.json"
    if not config_path.exists():
        raise HTTPException(
            status_code=403,
            detail=f"Plugin '{plugin_id}' is a built-in and cannot be unregistered.",
        )

    # Disconnect for all users (best-effort)
    await registry.disconnect_plugin(user.uid, plugin_id)

    # Remove from in-memory catalog
    registry._catalog.pop(plugin_id, None)

    # Remove config file
    config_path.unlink(missing_ok=True)

    return {"plugin_id": plugin_id, "status": "unregistered"}
