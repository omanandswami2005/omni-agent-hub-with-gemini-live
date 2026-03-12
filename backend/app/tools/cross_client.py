"""Cross-client action ADK tools — send commands between connected devices.

An agent can invoke these tools to push data or actions to specific
client types (desktop tray, Chrome extension, web dashboard) via the
:class:`~app.services.connection_manager.ConnectionManager`.
"""

from __future__ import annotations

import json

from google.adk.tools import FunctionTool

from app.models.client import ClientType
from app.services.connection_manager import get_connection_manager
from app.utils.logging import get_logger

logger = get_logger(__name__)

# Timeout (seconds) for waiting on a client response.
_ACTION_TIMEOUT = 10.0


def _safe_parse_json(payload: str) -> dict | list | str:
    """Parse a JSON string, returning the raw string on failure."""
    try:
        return json.loads(payload)
    except (json.JSONDecodeError, TypeError):
        return payload


# ---------------------------------------------------------------------------
# ADK tool functions
# ---------------------------------------------------------------------------


async def send_to_desktop(
    user_id: str,
    action: str,
    payload: str = "{}",
) -> dict:
    """Send an action to the user's desktop tray client.

    Args:
        user_id: The authenticated user's ID.
        action: Action name the desktop client should execute
                (e.g. ``open_app``, ``type_text``, ``capture_screen``).
        payload: JSON string with action parameters.

    Returns:
        A dict with ``delivered`` bool and optional ``error``.
    """
    return await _send_action(user_id, ClientType.DESKTOP, action, payload)


async def send_to_chrome(
    user_id: str,
    action: str,
    payload: str = "{}",
) -> dict:
    """Send an action to the user's Chrome extension.

    Args:
        user_id: The authenticated user's ID.
        action: Action name (e.g. ``open_tab``, ``get_page_content``).
        payload: JSON string with action parameters.

    Returns:
        A dict with ``delivered`` bool and optional ``error``.
    """
    return await _send_action(user_id, ClientType.CHROME, action, payload)


async def send_to_dashboard(
    user_id: str,
    action: str,
    payload: str = "{}",
) -> dict:
    """Send an action or data to the user's web dashboard.

    Args:
        user_id: The authenticated user's ID.
        action: Action name (e.g. ``show_notification``, ``render_genui``).
        payload: JSON string with action parameters.

    Returns:
        A dict with ``delivered`` bool and optional ``error``.
    """
    return await _send_action(user_id, ClientType.WEB, action, payload)


async def notify_client(
    user_id: str,
    message: str,
    client_type: str = "web",
) -> dict:
    """Send a notification to a specific client type.

    Args:
        user_id: The authenticated user's ID.
        message: Notification text.
        client_type: One of ``web``, ``desktop``, ``chrome``.

    Returns:
        A dict with ``delivered`` bool and optional ``error``.
    """
    try:
        ct = ClientType(client_type)
    except ValueError:
        return {"delivered": False, "error": f"Unknown client type: {client_type}"}

    payload = json.dumps({"message": message})
    return await _send_action(user_id, ct, "notification", payload)


async def list_connected_clients(user_id: str) -> dict:
    """List all currently connected clients for the user.

    Args:
        user_id: The authenticated user's ID.

    Returns:
        A dict with a ``clients`` list of connected client types.
    """
    mgr = get_connection_manager()
    clients = mgr.get_connected_clients(user_id)
    return {
        "clients": [
            {"client_type": c.client_type, "client_id": c.client_id}
            for c in clients
        ],
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _send_action(
    user_id: str,
    client_type: ClientType,
    action: str,
    payload: str,
) -> dict:
    """Route an action message to a specific client via ConnectionManager."""
    mgr = get_connection_manager()

    if not mgr.is_online(user_id, client_type):
        logger.warning(
            "client_not_connected",
            user_id=user_id,
            client_type=client_type,
            action=action,
        )
        return {
            "delivered": False,
            "error": f"{client_type} client is not connected",
        }

    message = json.dumps({
        "type": "cross_client_action",
        "action": action,
        "payload": _safe_parse_json(payload) if isinstance(payload, str) else payload,
    })

    await mgr.send_to_client(user_id, client_type, message)
    logger.info(
        "action_sent",
        user_id=user_id,
        client_type=client_type,
        action=action,
    )
    return {"delivered": True, "client_type": str(client_type)}


# ---------------------------------------------------------------------------
# Pre-built FunctionTool instances
# ---------------------------------------------------------------------------

send_to_desktop_tool = FunctionTool(send_to_desktop)
send_to_chrome_tool = FunctionTool(send_to_chrome)
send_to_dashboard_tool = FunctionTool(send_to_dashboard)
notify_client_tool = FunctionTool(notify_client)
list_connected_clients_tool = FunctionTool(list_connected_clients)


def get_cross_client_tools() -> list[FunctionTool]:
    """Return all cross-client action tools."""
    return [
        send_to_desktop_tool,
        send_to_chrome_tool,
        send_to_dashboard_tool,
        notify_client_tool,
        list_connected_clients_tool,
    ]
