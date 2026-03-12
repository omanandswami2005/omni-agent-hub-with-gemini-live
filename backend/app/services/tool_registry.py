"""ToolRegistry — Central orchestrator that assembles T1 + T2 + T3 tools.

Combines:
- T1: Core backend tools (always available, from app/tools/)
- T2: Backend-managed plugins (MCP + native + E2B, via PluginRegistry)
- T3: Client-local tools (advertised at connect, proxied via reverse-RPC)

The agent sees one flat list of tools. Routing is transparent.
"""

from __future__ import annotations

import asyncio
import json
from uuid import uuid4

from google.adk.tools import FunctionTool

from app.models.client import ClientType
from app.services.connection_manager import get_connection_manager
from app.services.plugin_registry import get_plugin_registry
from app.utils.logging import get_logger

logger = get_logger(__name__)

__all__ = ["ToolRegistry", "get_tool_registry"]

# T3 reverse-RPC timeout (seconds)
_T3_TIMEOUT = 30

# Pending T3 tool results: { call_id: asyncio.Future }
_pending_results: dict[str, asyncio.Future] = {}


def resolve_tool_result(call_id: str, result: dict | str, error: str = "") -> bool:
    """Resolve a pending T3 tool invocation with the client's result.

    Called from the WS upstream handler when a ``tool_result`` message arrives.
    Returns True if the call_id was found and resolved.
    """
    fut = _pending_results.pop(call_id, None)
    if fut is None or fut.done():
        return False
    if error:
        fut.set_result({"error": error})
    else:
        fut.set_result(result)
    return True


async def _await_tool_result(call_id: str, timeout: float = _T3_TIMEOUT) -> dict | str:
    """Wait for a T3 tool result with timeout."""
    fut = asyncio.get_running_loop().create_future()
    _pending_results[call_id] = fut
    try:
        result = await asyncio.wait_for(fut, timeout=timeout)
        return result
    except asyncio.TimeoutError:
        return {"error": f"Client did not respond within {timeout}s"}
    finally:
        _pending_results.pop(call_id, None)


def _create_proxy_tool(
    tool_def: dict, user_id: str, client_type: ClientType
) -> FunctionTool:
    """Create an ephemeral proxy tool that routes calls to a connected client via reverse-RPC."""

    tool_name = tool_def.get("name", "unknown_tool")
    tool_desc = tool_def.get("description", "")
    tool_params = tool_def.get("parameters", {})

    async def proxy_fn(**kwargs) -> dict | str:
        cm = get_connection_manager()
        if not cm.is_online(user_id, client_type):
            return f"Error: {client_type} client is not connected."

        call_id = uuid4().hex
        invocation = json.dumps({
            "type": "tool_invocation",
            "call_id": call_id,
            "tool": tool_name,
            "args": kwargs,
        })

        await cm.send_to_client(user_id, client_type, invocation)
        logger.info(
            "t3_tool_invoked",
            user_id=user_id,
            client_type=client_type,
            tool=tool_name,
            call_id=call_id,
        )

        result = await _await_tool_result(call_id)
        return result

    # Set function metadata for ADK introspection
    proxy_fn.__name__ = tool_name
    proxy_fn.__doc__ = tool_desc
    # Attach parameter hints as annotations for ADK to discover
    if tool_params:
        annotations = {}
        for param_name, param_info in tool_params.items():
            ptype = param_info.get("type", "string")
            type_map = {"string": str, "integer": int, "number": float, "boolean": bool, "array": list, "object": dict}
            annotations[param_name] = type_map.get(ptype, str)
        annotations["return"] = dict | str
        proxy_fn.__annotations__ = annotations

    return FunctionTool(proxy_fn)


class ToolRegistry:
    """Assembles the final tool list for an agent session."""

    async def build_for_session(self, user_id: str) -> list:
        """Build the complete tool list for a user session (T1 + T2 + T3)."""
        tools: list = []

        # T2 — All user-enabled plugins (MCP + native + E2B)
        plugin_registry = get_plugin_registry()
        try:
            t2_tools = await plugin_registry.get_tools(user_id)
            tools.extend(t2_tools)
            logger.debug("t2_tools_loaded", user_id=user_id, count=len(t2_tools))
        except Exception:
            logger.warning("t2_tools_load_failed", user_id=user_id, exc_info=True)

        # T3 — Client-local tools (from ConnectionManager capabilities)
        cm = get_connection_manager()
        capabilities = cm.get_capabilities(user_id)
        t3_count = 0
        for ct, cap_data in capabilities.items():
            for tool_def in cap_data.get("local_tools", []):
                if tool_def.get("name"):
                    tools.append(_create_proxy_tool(tool_def, user_id, ct))
                    t3_count += 1
        if t3_count:
            logger.debug("t3_tools_loaded", user_id=user_id, count=t3_count)

        return tools

    def get_t3_tool_names(self, user_id: str) -> list[str]:
        """Return names of all T3 proxy tools for a user (lightweight, no async)."""
        cm = get_connection_manager()
        names = []
        for _ct, cap_data in cm.get_capabilities(user_id).items():
            for tool_def in cap_data.get("local_tools", []):
                if tool_def.get("name"):
                    names.append(tool_def["name"])
        return names


# ── Module singleton ──────────────────────────────────────────────────

_registry: ToolRegistry | None = None


def get_tool_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry
