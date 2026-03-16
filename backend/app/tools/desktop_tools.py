"""E2B Desktop ADK tools — cloud desktop control for agents.

Provides FunctionTools for agents to interact with a virtual desktop:
  - Create/destroy desktop sandbox
  - Start/stop screen streaming to Live API (agent vision)
  - Screenshots, mouse, keyboard
  - App launching, URL browsing
  - File operations, shell commands

These tools are registered under the 'desktop' capability tag.
"""

from __future__ import annotations

import asyncio
import base64

from google.adk.tools import FunctionTool

from app.services.e2b_desktop_service import get_e2b_desktop_service
from app.utils.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Pending-screenshot queue (drained by ws_live._process_event)
# ---------------------------------------------------------------------------
_pending_screenshots: dict[str, list[dict]] = {}

SCREENSHOT_TOOL_NAMES = frozenset({
    "desktop_screenshot",
    "desktop_exec_and_show",
    "desktop_multi_step",
})


def _queue_screenshot(user_id: str, b64: str, mime_type: str = "image/png", description: str = "") -> None:
    _pending_screenshots.setdefault(user_id, []).append({
        "tool_name": "desktop_screenshot",
        "image_base64": b64,
        "mime_type": mime_type,
        "description": description,
    })


def drain_pending_screenshots(user_id: str) -> list[dict]:
    return _pending_screenshots.pop(user_id, [])


# ---------------------------------------------------------------------------
# E2B → Live API screen streaming (server-side screenshot polling)
# ---------------------------------------------------------------------------
# When streaming is active, a background task captures E2B screenshots at
# ~1 FPS and pushes them into the Gemini Live session via the queue's
# send_realtime(). This gives the agent real-time vision of the cloud desktop
# so tools like desktop_click(x, y) become usable.
#
# The queue reference is stored per-user by ws_live.py when it creates the
# LiveRequestQueue for the session.
_active_streams: dict[str, asyncio.Task] = {}  # user_id → task
_stream_queues: dict[str, object] = {}  # user_id → LiveRequestQueue


def register_live_queue(user_id: str, queue: object) -> None:
    """Called by ws_live.py to register the LiveRequestQueue for a user."""
    _stream_queues[user_id] = queue


def unregister_live_queue(user_id: str) -> None:
    """Called by ws_live.py on disconnect to clean up."""
    _stream_queues.pop(user_id, None)
    _stop_streaming(user_id)


def _stop_streaming(user_id: str) -> bool:
    task = _active_streams.pop(user_id, None)
    if task and not task.done():
        task.cancel()
        return True
    return False


async def _stream_loop(user_id: str, fps: float = 1.0) -> None:
    """Background coroutine: screenshot E2B desktop → send_realtime to Live API."""
    from google.genai import types

    interval = 1.0 / fps
    svc = get_e2b_desktop_service()
    logger.info("e2b_stream_started", user_id=user_id, fps=fps)
    try:
        while True:
            queue = _stream_queues.get(user_id)
            if queue is None:
                logger.info("e2b_stream_no_queue", user_id=user_id)
                break
            try:
                img_bytes = await svc.screenshot(user_id)
                blob = types.Blob(mime_type="image/png", data=img_bytes)
                queue.send_realtime(blob)
            except Exception:
                logger.warning("e2b_stream_frame_error", user_id=user_id, exc_info=True)
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        pass
    finally:
        logger.info("e2b_stream_stopped", user_id=user_id)


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

    Also stops screen streaming if active.

    Args:
        user_id: User identifier.

    Returns:
        Confirmation of destruction.
    """
    _stop_streaming(user_id)
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


# ── Screen Streaming (E2B → Gemini Live API vision) ──────────────────


async def desktop_start_streaming(fps: float = 1.0, user_id: str = "default") -> dict:
    """Start streaming the cloud desktop screen to the AI agent (vision).

    This captures screenshots at the specified FPS and feeds them directly
    into the Gemini Live API as video input. Once streaming, the agent can
    SEE the desktop in real-time and perform actions like desktop_click(x, y)
    accurately.

    Call this after start_desktop() so there is an active sandbox.

    Args:
        fps: Frames per second (0.5-2.0 recommended). Default 1.0.
        user_id: User identifier.

    Returns:
        Streaming status.
    """
    fps = max(0.5, min(fps, 2.0))
    queue = _stream_queues.get(user_id)
    if queue is None:
        return {"streaming": False, "error": "No active Live API session. Connect via voice first."}

    svc = get_e2b_desktop_service()
    info = await svc.get_desktop_info(user_id)
    if not info:
        return {"streaming": False, "error": "No active desktop. Call start_desktop() first."}

    _stop_streaming(user_id)
    task = asyncio.create_task(_stream_loop(user_id, fps=fps), name=f"e2b_stream_{user_id}")
    _active_streams[user_id] = task
    return {
        "streaming": True,
        "fps": fps,
        "message": (
            f"Desktop screen streaming started at {fps} FPS. "
            "You can now SEE the desktop. Use desktop_click(x, y) to interact. "
            "Call desktop_stop_streaming() when done."
        ),
    }


async def desktop_stop_streaming(user_id: str = "default") -> dict:
    """Stop streaming the cloud desktop screen to the AI agent.

    Saves resources when the agent doesn't need to see the desktop.

    Args:
        user_id: User identifier.

    Returns:
        Confirmation.
    """
    stopped = _stop_streaming(user_id)
    return {
        "streaming": False,
        "message": "Desktop streaming stopped." if stopped else "No active stream.",
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
    _queue_screenshot(user_id, b64, description="Desktop screenshot")
    return {"message": "Screenshot captured and sent to dashboard for display."}


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


async def desktop_download_file(path: str, user_id: str = "default") -> dict:
    """Download a file from the virtual desktop filesystem.

    Use this when the user asks to retrieve, export, or read a file from
    the cloud desktop.

    Args:
        path: File path in the sandbox (e.g. '/home/user/report.pdf').
        user_id: User identifier.

    Returns:
        Dict with base64-encoded content, filename and size.
    """
    svc = get_e2b_desktop_service()
    content = await svc.download_file(user_id, path)
    encoded = base64.b64encode(content).decode("utf-8")
    filename = path.rsplit("/", 1)[-1] if "/" in path else path
    return {
        "filename": filename,
        "path": path,
        "content_base64": encoded,
        "size": len(content),
    }


async def desktop_find_file(
    name: str = "",
    content: str = "",
    directory: str = "/home/user",
    user_id: str = "default",
) -> dict:
    """Search for files on the virtual desktop by name pattern or content.

    Use this to discover where uploaded or generated files are located in
    the E2B sandbox.  Supports glob patterns for names and grep-style
    content matching.

    Args:
        name: Filename pattern (glob) to search for, e.g. ``*.csv``,
              ``report*``, ``data.xlsx``.  Leave empty to match all files.
        content: Text to search for inside files (grep -ril).
              Leave empty to skip content matching.
        directory: Root directory to search (default: /home/user).
        user_id: User identifier.

    Returns:
        Dict with list of matching file paths, sizes, and match details.
    """
    svc = get_e2b_desktop_service()

    if content:
        # grep for content first — most precise
        cmd = f"grep -ril --include='*' '{content}' {directory} 2>/dev/null | head -50"
        if name:
            cmd = f"grep -ril --include='{name}' '{content}' {directory} 2>/dev/null | head -50"
        result = await svc.run_command(user_id, cmd)
        paths = [p.strip() for p in result.get("stdout", "").splitlines() if p.strip()]
    elif name:
        # find by name pattern
        cmd = f"find {directory} -name '{name}' -type f 2>/dev/null | head -50"
        result = await svc.run_command(user_id, cmd)
        paths = [p.strip() for p in result.get("stdout", "").splitlines() if p.strip()]
    else:
        # list all files
        cmd = f"find {directory} -type f 2>/dev/null | head -50"
        result = await svc.run_command(user_id, cmd)
        paths = [p.strip() for p in result.get("stdout", "").splitlines() if p.strip()]

    # Gather sizes for found files
    files = []
    if paths:
        stat_cmd = "stat --format='%n %s' " + " ".join(f"'{p}'" for p in paths[:50]) + " 2>/dev/null"
        stat_result = await svc.run_command(user_id, stat_cmd)
        for line in stat_result.get("stdout", "").splitlines():
            line = line.strip()
            if not line:
                continue
            # format: /path/to/file 12345
            parts = line.rsplit(" ", 1)
            if len(parts) == 2:
                files.append({"path": parts[0], "size": int(parts[1])})
            else:
                files.append({"path": line, "size": 0})

    return {
        "directory": directory,
        "name_pattern": name or "*",
        "content_pattern": content or "",
        "files": files,
        "count": len(files),
    }


async def desktop_read_screen(user_id: str = "default") -> dict:
    """Take a screenshot and send it to the dashboard for display.

    Use when the user asks "What's on the screen?" — the screenshot is
    sent to the dashboard. If desktop streaming is active, the agent
    already has vision and can describe what it sees directly.

    Args:
        user_id: User identifier.

    Returns:
        Confirmation.
    """
    svc = get_e2b_desktop_service()
    raw = await svc.screenshot(user_id)
    b64 = base64.b64encode(raw).decode("utf-8")
    _queue_screenshot(user_id, b64, description="Desktop screen contents")
    is_streaming = user_id in _active_streams
    if is_streaming:
        return {
            "message": (
                "Screenshot sent to dashboard. You have active vision streaming — "
                "describe what you see on the desktop."
            )
        }
    return {
        "message": (
            "Screenshot sent to dashboard. "
            "Consider calling desktop_start_streaming() for continuous vision."
        )
    }


async def desktop_exec_and_show(
    command: str,
    user_id: str = "default",
) -> dict:
    """Run a shell command and capture a screenshot of the result.

    Combines desktop_bash + desktop_screenshot in one call — ideal for
    voice-driven workflows where the user says "run X and show me."

    Args:
        command: Shell command to execute.
        user_id: User identifier.

    Returns:
        Dict with command output AND a screenshot of the desktop state.
    """
    svc = get_e2b_desktop_service()
    cmd_result = await svc.run_command(user_id, command)
    raw = await svc.screenshot(user_id)
    b64 = base64.b64encode(raw).decode("utf-8")
    _queue_screenshot(user_id, b64, description=f"Result of: {command}")
    return {
        "stdout": cmd_result.get("stdout", ""),
        "stderr": cmd_result.get("stderr", ""),
        "exit_code": cmd_result.get("exit_code", -1),
        "message": "Command executed. Screenshot sent to dashboard for visual confirmation.",
    }


async def desktop_find_and_click(
    text_to_find: str,
    user_id: str = "default",
) -> dict:
    """Find a UI element by text label and click it.

    Requires desktop_start_streaming() to be active so the agent has vision.
    The agent should look at the current stream, identify the element's
    coordinates, and call desktop_click(x, y).

    If streaming is NOT active, takes a screenshot and sends to dashboard,
    then asks the user for help.

    Args:
        text_to_find: The text label / button / link to locate on screen.
        user_id: User identifier.

    Returns:
        Guidance on how to proceed.
    """
    is_streaming = user_id in _active_streams
    if is_streaming:
        return {
            "text_to_find": text_to_find,
            "message": (
                f"You have active desktop vision. Look at the stream and find "
                f"'{text_to_find}'. Determine its (x, y) center coordinates, "
                f"then call desktop_click(x, y) to click it."
            ),
        }
    # No streaming — take a screenshot for the dashboard and ask the user
    svc = get_e2b_desktop_service()
    raw = await svc.screenshot(user_id)
    b64 = base64.b64encode(raw).decode("utf-8")
    _queue_screenshot(user_id, b64, description=f"Finding: {text_to_find}")
    return {
        "text_to_find": text_to_find,
        "message": (
            f"Screenshot sent to dashboard. Without active streaming I cannot see the screen. "
            f"Please call desktop_start_streaming() first, or ask the user to "
            f"identify where '{text_to_find}' is on screen."
        ),
    }


async def desktop_list_files(
    directory: str = "/home/user",
    pattern: str = "",
    user_id: str = "default",
) -> dict:
    """List files in a directory on the virtual desktop.

    Voice-friendly: user says "what files are on the desktop?" or
    "show me the CSV files in Downloads."

    Args:
        directory: Directory to list (default: /home/user).
        pattern: Optional glob pattern to filter (e.g. '*.csv', '*.py').
        user_id: User identifier.

    Returns:
        Dict with list of files and their sizes.
    """
    svc = get_e2b_desktop_service()
    cmd = f"ls -la {directory}"
    if pattern:
        cmd = f"find {directory} -maxdepth 1 -name '{pattern}' -exec ls -la {{}} \\;"
    result = await svc.run_command(user_id, cmd)
    stdout = result.get("stdout", "")
    lines = [line.strip() for line in stdout.strip().splitlines() if line.strip() and not line.startswith("total")]
    return {
        "directory": directory,
        "pattern": pattern or "*",
        "files": lines,
        "count": len(lines),
    }


async def desktop_multi_step(
    steps: list[str],
    user_id: str = "default",
) -> dict:
    """Execute a sequence of shell commands on the desktop.

    For complex voice instructions like "install pandas, create a script
    that loads my CSV, and run it." Each step is a separate command.

    Args:
        steps: List of shell commands to execute in order.
        user_id: User identifier.

    Returns:
        Dict with results for each step and a final screenshot.
    """
    svc = get_e2b_desktop_service()
    results = []
    for i, cmd in enumerate(steps):
        r = await svc.run_command(user_id, cmd)
        results.append({
            "step": i + 1,
            "command": cmd,
            "stdout": r.get("stdout", ""),
            "stderr": r.get("stderr", ""),
            "exit_code": r.get("exit_code", -1),
        })
        if r.get("exit_code", -1) != 0:
            break  # Stop on failure

    raw = await svc.screenshot(user_id)
    b64 = base64.b64encode(raw).decode("utf-8")
    _queue_screenshot(user_id, b64, description="Final desktop state after multi-step execution")
    return {
        "steps_completed": len(results),
        "steps_total": len(steps),
        "results": results,
        "all_success": all(r["exit_code"] == 0 for r in results),
        "message": "All steps completed. Final screenshot sent to dashboard.",
    }


# ── Tool Registration ─────────────────────────────────────────────────

_DESKTOP_TOOLS: list[FunctionTool] | None = None


def get_desktop_tools() -> list[FunctionTool]:
    """Return all E2B Desktop tools as FunctionTool instances."""
    global _DESKTOP_TOOLS
    if _DESKTOP_TOOLS is None:
        _DESKTOP_TOOLS = [
            # Lifecycle
            FunctionTool(start_desktop),
            FunctionTool(stop_desktop),
            FunctionTool(desktop_status),
            # Streaming (agent vision)
            FunctionTool(desktop_start_streaming),
            FunctionTool(desktop_stop_streaming),
            # Screenshot (send to dashboard)
            FunctionTool(desktop_screenshot),
            # Mouse & keyboard
            FunctionTool(desktop_click),
            FunctionTool(desktop_scroll),
            FunctionTool(desktop_drag),
            FunctionTool(desktop_type),
            FunctionTool(desktop_hotkey),
            # Apps & browser
            FunctionTool(desktop_launch),
            FunctionTool(desktop_open_url),
            FunctionTool(desktop_get_windows),
            # Shell & files
            FunctionTool(desktop_bash),
            FunctionTool(desktop_upload_file),
            FunctionTool(desktop_download_file),
            FunctionTool(desktop_find_file),
            # Voice-enhanced combos
            FunctionTool(desktop_read_screen),
            FunctionTool(desktop_exec_and_show),
            FunctionTool(desktop_find_and_click),
            FunctionTool(desktop_list_files),
            FunctionTool(desktop_multi_step),
        ]
    return _DESKTOP_TOOLS
