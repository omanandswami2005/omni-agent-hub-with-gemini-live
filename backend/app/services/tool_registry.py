"""ToolRegistry — Central orchestrator that assembles T1 + T2 + T3 tools.

Combines:
- T1: Core backend tools (always available, from app/tools/)
- T2: Backend-managed plugins (MCP + native + E2B, via PluginRegistry)
- T3: Client-local tools (advertised at connect, proxied via reverse-RPC)

build_for_session returns a ``dict[str, list]`` keyed by persona_id.
Each persona only receives T2 tools whose plugin tags overlap with its
capabilities.  T3 proxy tools live under the ``__device__`` key so the
cross-client orchestrator agent can consume them.
"""

from __future__ import annotations

import asyncio
import inspect
import json
from uuid import uuid4

from google.adk.tools import FunctionTool

from app.models.client import ClientType
from app.models.persona import PersonaResponse
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
    except TimeoutError:
        return {"error": f"Client did not respond within {timeout}s"}
    finally:
        _pending_results.pop(call_id, None)


def _create_proxy_tool(tool_def: dict, user_id: str, client_type: ClientType) -> FunctionTool:
    """Create an ephemeral proxy tool that routes calls to a connected client via reverse-RPC."""

    tool_name = tool_def.get("name", "unknown_tool")
    tool_desc = tool_def.get("description", "")
    tool_params = tool_def.get("parameters", {})

    async def proxy_fn(**kwargs) -> dict:
        cm = get_connection_manager()
        if not cm.is_online(user_id, client_type):
            return {"error": f"{client_type} client is not connected."}

        # Strip ADK-injected tool_context — not serializable / not for the client
        clean_args = {k: v for k, v in kwargs.items() if k != "tool_context"}

        call_id = uuid4().hex
        invocation = json.dumps(
            {
                "type": "tool_invocation",
                "call_id": call_id,
                "tool": tool_name,
                "args": clean_args,
            }
        )

        await cm.send_to_client(user_id, client_type, invocation)
        logger.info(
            "t3_tool_invoked",
            user_id=user_id,
            client_type=client_type,
            tool=tool_name,
            call_id=call_id,
        )

        result = await _await_tool_result(call_id)
        if isinstance(result, str):
            return {"result": result}
        return result

    # Set function metadata for ADK introspection
    proxy_fn.__name__ = tool_name
    proxy_fn.__doc__ = tool_desc
    # Attach parameter hints as annotations for ADK to discover
    # AND set __signature__ so ADK's arg-filtering in run_async passes them through
    sig_params: list[inspect.Parameter] = []
    if tool_params:
        annotations = {}
        # Unwrap JSON Schema: parameters may be {"type": "object", "properties": {...}}
        props = tool_params.get("properties", tool_params) if isinstance(tool_params, dict) else {}
        for param_name, param_info in props.items():
            if not isinstance(param_info, dict):
                continue
            ptype = param_info.get("type", "string")
            type_map = {
                "string": str,
                "integer": int,
                "number": float,
                "boolean": bool,
                "array": list,
                "object": dict,
            }
            annotations[param_name] = type_map.get(ptype, str)
            sig_params.append(
                inspect.Parameter(param_name, inspect.Parameter.KEYWORD_ONLY, annotation=annotations[param_name])
            )
        annotations["return"] = dict
        proxy_fn.__annotations__ = annotations

    # ADK FunctionTool.run_async filters args to valid_params from inspect.signature.
    # Without an explicit __signature__, **kwargs only shows 'kwargs' and all real
    # args get dropped.  Setting __signature__ fixes this.
    proxy_fn.__signature__ = inspect.Signature(sig_params)

    return FunctionTool(proxy_fn)


class ToolRegistry:
    """Assembles the final tool dict for an agent session.

    Returns ``dict[str, list]`` keyed by **persona_id**.  T2 tools are
    distributed based on ``plugin.tags ∩ persona.capabilities``.
    T3 (client-local) proxy tools are placed under the key ``__device__``.
    """

    async def build_for_session(
        self,
        user_id: str,
        personas: list[PersonaResponse] | None = None,
    ) -> dict[str, list]:
        """Build per-persona T2 tool lists plus a ``__device__`` T3 list.

        Parameters
        ----------
        user_id:
            Authenticated user id.
        personas:
            List of active personas.  When *None* a flat ``{"__all__": tools}``
            dict is returned for backward compat (all T2 mixed together).
        """
        plugin_registry = get_plugin_registry()

        # ── T2: Collect tools per enabled plugin ──────────────────────
        # ── T2: Collect tools per enabled plugin (parallel) ──────────
        enabled_manifests: list[tuple[str, object]] = []
        for plugin_id in plugin_registry.get_enabled_ids(user_id):
            manifest = plugin_registry.get_manifest(plugin_id)
            if manifest is not None:
                enabled_manifests.append((plugin_id, manifest))

        async def _load(pid: str, m: object) -> tuple[str, list]:
            try:
                tools = await plugin_registry._get_plugin_tools(user_id, pid, m)
                return (pid, tools or [])
            except Exception:
                logger.warning("t2_tools_load_failed", user_id=user_id, plugin_id=pid, exc_info=True)
                return (pid, [])

        results = await asyncio.gather(
            *(_load(pid, m) for pid, m in enabled_manifests)
        )
        plugin_tools: dict[str, list] = {pid: tools for pid, tools in results if tools}

        # ── Distribute T2 tools to personas by tag matching ───────────
        result: dict[str, list] = {}

        if personas is None:
            # Backward compat: flat list under __all__
            all_tools: list = []
            for tools in plugin_tools.values():
                all_tools.extend(tools)
            result["__all__"] = all_tools
        else:
            for persona in personas:
                matched: list = []
                pcaps = set(persona.capabilities)
                for plugin_id, tools in plugin_tools.items():
                    manifest = plugin_registry.get_manifest(plugin_id)
                    if manifest is None:
                        continue
                    ptags = set(manifest.tags)
                    # Wildcard "*" matches everything
                    if "*" in ptags or ptags & pcaps:
                        matched.extend(tools)
                result[persona.id] = matched

            logger.debug(
                "t2_tools_distributed",
                user_id=user_id,
                distribution={pid: len(t) for pid, t in result.items()},
            )

        # ── T3: Client-local proxy tools → __device__ ────────────────
        cm = get_connection_manager()
        capabilities = cm.get_capabilities(user_id)
        device_tools: list = []
        for ct, cap_data in capabilities.items():
            for tool_def in cap_data.get("local_tools", []):
                if tool_def.get("name"):
                    device_tools.append(_create_proxy_tool(tool_def, user_id, ct))
        if device_tools:
            result["__device__"] = device_tools
            logger.debug("t3_tools_loaded", user_id=user_id, count=len(device_tools))

        return result

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
