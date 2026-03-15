"""E2B Desktop ADK tools — cloud desktop control for agents.

Provides FunctionTools for agents to interact with a virtual desktop:
  - Create/destroy desktop sandbox
  - Screenshots, mouse, keyboard
  - App launching, URL browsing
  - File operations, shell commands

These tools are registered under the 'desktop' capability tag.
"""

from __future__ import annotations

import base64

from google.adk.tools import FunctionTool

from app.services.e2b_desktop_service import get_e2b_desktop_service
from app.utils.logging import get_logger

logger = get_logger(__name__)


# ── Desktop Lifecycle ─────────────────────────────────────────────────


async def start_desktop(user_id: str = "default") -> dict:
    """Start a cloud virtual desktop sandbox with screen streaming.

    Creates a full Linux desktop environment with browser, GUI apps,
    and live screen streaming. Call this before any desktop interaction.

    Args:
        user_id: User identifier (auto-injected by context).

    Returns:
        Desktop info with stream_url for live viewing.
    """
    svc = get_e2b_desktop_service()
    info = await svc.create_desktop(user_id)
    return {
        "status": info.status.value,
        "sandbox_id": info.sandbox_id,
        "stream_url": info.stream_url,
        "message": "Desktop started. Use the stream_url to view the desktop live.",
    }


async def stop_desktop(user_id: str = "default") -> dict:
    """Stop and destroy the user's cloud desktop sandbox.

    Args:
        user_id: User identifier.

    Returns:
        Confirmation of destruction.
    """
    svc = get_e2b_desktop_service()
    destroyed = await svc.destroy_desktop(user_id)
    return {"destroyed": destroyed, "message": "Desktop sandbox destroyed." if destroyed else "No active desktop."}


async def desktop_status(user_id: str = "default") -> dict:
    """Get the current status of the user's cloud desktop.

    Args:
        user_id: User identifier.

    Returns:
        Status info including stream URL if desktop is active.
    """
    svc = get_e2b_desktop_service()
    info = await svc.get_desktop_info(user_id)
    if not info:
        return {"status": "none", "message": "No desktop sandbox active."}
    return {
        "status": info.status.value,
        "sandbox_id": info.sandbox_id,
        "stream_url": info.stream_url,
    }


# ── Screenshot ────────────────────────────────────────────────────────


async def desktop_screenshot(user_id: str = "default") -> dict:
    """Take a screenshot of the virtual desktop.

    Args:
        user_id: User identifier.

    Returns:
        Base64-encoded PNG screenshot.
    """
    svc = get_e2b_desktop_service()
    img_bytes = await svc.screenshot(user_id)
    b64 = base64.b64encode(img_bytes).decode()
    return {
        "image_base64": b64,
        "mime_type": "image/png",
        "message": "Screenshot captured.",
    }


# ── Mouse Actions ─────────────────────────────────────────────────────


async def desktop_click(x: int, y: int, button: str = "left", user_id: str = "default") -> dict:
    """Click at a position on the virtual desktop.

    Args:
        x: X coordinate (pixels from left).
        y: Y coordinate (pixels from top).
        button: Mouse button — 'left', 'right', or 'double'.
        user_id: User identifier.

    Returns:
        Confirmation of click action.
    """
    svc = get_e2b_desktop_service()
    if button == "right":
        await svc.right_click(user_id, x, y)
    elif button == "double":
        await svc.double_click(user_id, x, y)
    else:
        await svc.left_click(user_id, x, y)
    return {"clicked": True, "x": x, "y": y, "button": button}


async def desktop_scroll(x: int, y: int, direction: str = "down", amount: int = 3, user_id: str = "default") -> dict:
    """Scroll the mouse wheel at a position.

    Args:
        x: X coordinate.
        y: Y coordinate.
        direction: 'up' or 'down'.
        amount: Number of scroll steps.
        user_id: User identifier.

    Returns:
        Confirmation of scroll action.
    """
    svc = get_e2b_desktop_service()
    await svc.scroll(user_id, x, y, direction=direction, amount=amount)
    return {"scrolled": True, "direction": direction, "amount": amount}


async def desktop_drag(start_x: int, start_y: int, end_x: int, end_y: int, user_id: str = "default") -> dict:
    """Drag from one position to another on the desktop.

    Args:
        start_x: Starting X coordinate.
        start_y: Starting Y coordinate.
        end_x: Ending X coordinate.
        end_y: Ending Y coordinate.
        user_id: User identifier.

    Returns:
        Confirmation of drag action.
    """
    svc = get_e2b_desktop_service()
    await svc.drag(user_id, start_x, start_y, end_x, end_y)
    return {"dragged": True, "from": [start_x, start_y], "to": [end_x, end_y]}


# ── Keyboard ──────────────────────────────────────────────────────────


async def desktop_type(text: str, user_id: str = "default") -> dict:
    """Type text on the virtual desktop keyboard.

    Args:
        text: Text to type.
        user_id: User identifier.

    Returns:
        Confirmation of typing action.
    """
    svc = get_e2b_desktop_service()
    await svc.write_text(user_id, text)
    return {"typed": True, "length": len(text)}


async def desktop_hotkey(keys: list[str], user_id: str = "default") -> dict:
    """Press a keyboard shortcut (e.g. Ctrl+C, Alt+Tab).

    Args:
        keys: List of key names to press simultaneously (e.g. ['ctrl', 'c']).
        user_id: User identifier.

    Returns:
        Confirmation of hotkey action.
    """
    svc = get_e2b_desktop_service()
    await svc.press_keys(user_id, keys)
    return {"pressed": True, "keys": keys}


# ── App & Browser ─────────────────────────────────────────────────────


async def desktop_launch(app_name: str, user_id: str = "default") -> dict:
    """Launch an application on the virtual desktop.

    Args:
        app_name: Application to launch (e.g. 'google-chrome', 'firefox',
                  'code', 'nautilus', 'terminal').
        user_id: User identifier.

    Returns:
        Confirmation of app launch.
    """
    svc = get_e2b_desktop_service()
    await svc.launch_app(user_id, app_name)
    return {"launched": True, "app": app_name}


async def desktop_open_url(url: str, user_id: str = "default") -> dict:
    """Open a URL in the desktop's browser.

    Args:
        url: The URL to open.
        user_id: User identifier.

    Returns:
        Confirmation of URL opening.
    """
    svc = get_e2b_desktop_service()
    await svc.open_url(user_id, url)
    return {"opened": True, "url": url}


async def desktop_get_windows(app_name: str = "", user_id: str = "default") -> dict:
    """List open windows on the desktop.

    Args:
        app_name: Optional filter by application name.
        user_id: User identifier.

    Returns:
        List of open windows with their IDs and titles.
    """
    svc = get_e2b_desktop_service()
    windows = await svc.get_windows(user_id, app_name)
    return {"windows": windows, "count": len(windows)}


# ── Shell & Files ─────────────────────────────────────────────────────


async def desktop_bash(command: str, user_id: str = "default") -> dict:
    """Run a shell command on the virtual desktop.

    Args:
        command: Shell command to execute.
        user_id: User identifier.

    Returns:
        Command output with stdout, stderr, and exit code.
    """
    svc = get_e2b_desktop_service()
    return await svc.run_command(user_id, command)


async def desktop_upload_file(path: str, content_base64: str, user_id: str = "default") -> dict:
    """Upload a file to the virtual desktop filesystem.

    Args:
        path: Destination path in the sandbox (e.g. '/home/user/file.txt').
        content_base64: Base64-encoded file content.
        user_id: User identifier.

    Returns:
        Confirmation with the path.
    """
    svc = get_e2b_desktop_service()
    content = base64.b64decode(content_base64)
    result_path = await svc.upload_file(user_id, path, content)
    return {"uploaded": True, "path": result_path, "size": len(content)}


# ── Tool Registration ─────────────────────────────────────────────────

_DESKTOP_TOOLS: list[FunctionTool] | None = None


def get_desktop_tools() -> list[FunctionTool]:
    """Return all E2B Desktop tools as FunctionTool instances."""
    global _DESKTOP_TOOLS
    if _DESKTOP_TOOLS is None:
        _DESKTOP_TOOLS = [
            FunctionTool(start_desktop),
            FunctionTool(stop_desktop),
            FunctionTool(desktop_status),
            FunctionTool(desktop_screenshot),
            FunctionTool(desktop_click),
            FunctionTool(desktop_scroll),
            FunctionTool(desktop_drag),
            FunctionTool(desktop_type),
            FunctionTool(desktop_hotkey),
            FunctionTool(desktop_launch),
            FunctionTool(desktop_open_url),
            FunctionTool(desktop_get_windows),
            FunctionTool(desktop_bash),
            FunctionTool(desktop_upload_file),
        ]
    return _DESKTOP_TOOLS
