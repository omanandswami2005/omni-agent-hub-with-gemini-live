"""Desktop computer-use ADK tools — control the desktop tray client.

These tools send commands to the desktop client via the cross-client
action layer.  The desktop tray app receives these as WebSocket messages
and executes them locally (screenshot, click, type, launch app).
"""

from __future__ import annotations

import json

from google.adk.tools import FunctionTool

from app.models.client import ClientType
from app.tools.cross_client import _send_action


async def capture_screen(user_id: str) -> dict:
    """Request a screenshot from the desktop tray client.

    Args:
        user_id: The authenticated user's ID.

    Returns:
        A dict with ``delivered`` bool.  The actual screenshot is
        returned asynchronously via the ``tool_response`` WS message.
    """
    return await _send_action(
        user_id,
        ClientType.DESKTOP,
        "capture_screen",
        "{}",
    )


async def click_at(user_id: str, x: int, y: int) -> dict:
    """Click at screen coordinates on the desktop.

    Args:
        user_id: The authenticated user's ID.
        x: Horizontal pixel coordinate.
        y: Vertical pixel coordinate.

    Returns:
        A dict with ``delivered`` bool.
    """
    return await _send_action(
        user_id,
        ClientType.DESKTOP,
        "click_at",
        json.dumps({"x": x, "y": y}),
    )


async def type_text(user_id: str, text: str) -> dict:
    """Type text via keyboard on the desktop.

    Args:
        user_id: The authenticated user's ID.
        text: The text to type.

    Returns:
        A dict with ``delivered`` bool.
    """
    return await _send_action(
        user_id,
        ClientType.DESKTOP,
        "type_text",
        json.dumps({"text": text}),
    )


async def open_application(user_id: str, app_name: str) -> dict:
    """Launch an application on the desktop.

    Args:
        user_id: The authenticated user's ID.
        app_name: Name or path of the application to launch.

    Returns:
        A dict with ``delivered`` bool.
    """
    return await _send_action(
        user_id,
        ClientType.DESKTOP,
        "open_app",
        json.dumps({"app_name": app_name}),
    )


async def manage_files(user_id: str, action: str, path: str, content: str = "") -> dict:
    """Manage files on the desktop (read, write, list, delete).

    Args:
        user_id: The authenticated user's ID.
        action: One of ``read``, ``write``, ``list``, ``delete``.
        path: File or directory path on the desktop.
        content: File content (only used for ``write`` action).

    Returns:
        A dict with ``delivered`` bool.
    """
    if action not in ("read", "write", "list", "delete"):
        return {"delivered": False, "error": f"Unknown action: {action}"}
    return await _send_action(
        user_id,
        ClientType.DESKTOP,
        "manage_files",
        json.dumps({"action": action, "path": path, "content": content}),
    )


async def press_key(user_id: str, key_combo: str) -> dict:
    """Press a key or key combination on the desktop.

    Args:
        user_id: The authenticated user's ID.
        key_combo: Key combination string, e.g. ``ctrl+c``, ``enter``,
            ``alt+tab``.

    Returns:
        A dict with ``delivered`` bool.
    """
    return await _send_action(
        user_id,
        ClientType.DESKTOP,
        "press_key",
        json.dumps({"key_combo": key_combo}),
    )


# ---------------------------------------------------------------------------
# Pre-built FunctionTool instances
# ---------------------------------------------------------------------------

capture_screen_tool = FunctionTool(capture_screen)
click_at_tool = FunctionTool(click_at)
type_text_tool = FunctionTool(type_text)
open_application_tool = FunctionTool(open_application)
manage_files_tool = FunctionTool(manage_files)
press_key_tool = FunctionTool(press_key)


def get_desktop_tools() -> list[FunctionTool]:
    """Return all desktop computer-use tools."""
    return [
        capture_screen_tool,
        click_at_tool,
        type_text_tool,
        open_application_tool,
        manage_files_tool,
        press_key_tool,
    ]
