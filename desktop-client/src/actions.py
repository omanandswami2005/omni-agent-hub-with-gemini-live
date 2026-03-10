"""Desktop actions — mouse, keyboard, application control.

Wraps ``pyautogui`` for mouse/keyboard automation with safety guards.
All public functions are designed to be called as cross-client action
handlers from the WebSocket client.
"""

from __future__ import annotations

import logging
import subprocess
import sys
import time

import pyautogui

logger = logging.getLogger(__name__)

# Safety — add a brief pause between automated actions to avoid runaway loops
pyautogui.PAUSE = 0.05
# Move mouse to corner to trigger pyautogui fail-safe only in emergencies
pyautogui.FAILSAFE = True


def click(x: int, y: int, button: str = "left") -> dict:
    """Click at screen coordinates.

    Args:
        x: Pixel X coordinate.
        y: Pixel Y coordinate.
        button: ``"left"``, ``"right"``, or ``"middle"``.

    Returns:
        Dict with ``ok`` and the coordinates clicked.
    """
    pyautogui.click(x, y, button=button)
    return {"ok": True, "x": x, "y": y, "button": button}


def double_click(x: int, y: int) -> dict:
    """Double-click at screen coordinates."""
    pyautogui.doubleClick(x, y)
    return {"ok": True, "x": x, "y": y}


def type_text(text: str, interval: float = 0.02) -> dict:
    """Type text using keyboard simulation.

    Args:
        text: The text string to type.
        interval: Seconds between each keystroke.

    Returns:
        Dict confirming the typed text length.
    """
    pyautogui.typewrite(text, interval=interval)
    return {"ok": True, "length": len(text)}


def hotkey(*keys: str) -> dict:
    """Press a keyboard shortcut (e.g. ``hotkey("ctrl", "s")``).

    Args:
        keys: Key names as accepted by ``pyautogui.hotkey``.

    Returns:
        Dict confirming the key combo.
    """
    pyautogui.hotkey(*keys)
    return {"ok": True, "keys": list(keys)}


def move_mouse(x: int, y: int) -> dict:
    """Move mouse cursor to the given coordinates."""
    pyautogui.moveTo(x, y)
    return {"ok": True, "x": x, "y": y}


def scroll(amount: int, x: int | None = None, y: int | None = None) -> dict:
    """Scroll the mouse wheel.

    Args:
        amount: Positive scrolls up, negative scrolls down.
        x: Optional X coordinate to scroll at.
        y: Optional Y coordinate to scroll at.

    Returns:
        Dict confirming the scroll.
    """
    if x is not None and y is not None:
        pyautogui.scroll(amount, x, y)
    else:
        pyautogui.scroll(amount)
    return {"ok": True, "amount": amount}


def open_application(name_or_path: str) -> dict:
    """Launch an application by name or path.

    Platform-specific: uses ``start`` on Windows, ``open`` on macOS,
    and falls back to direct ``subprocess`` execution on Linux.

    Args:
        name_or_path: Application name or full path.

    Returns:
        Dict with ``ok`` and the process launched.
    """
    try:
        if sys.platform == "win32":
            subprocess.Popen(  # noqa: S603
                ["cmd", "/c", "start", "", name_or_path],
                shell=False,
            )
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-a", name_or_path])  # noqa: S603
        else:
            subprocess.Popen([name_or_path])  # noqa: S603
        # Brief wait for the app to initialize
        time.sleep(0.5)
        return {"ok": True, "app": name_or_path}
    except FileNotFoundError:
        return {"ok": False, "error": f"Application not found: {name_or_path}"}


def get_active_window_title() -> str:
    """Get the title of the currently focused window."""
    try:
        win = pyautogui.getActiveWindow()
        return win.title if win else ""
    except Exception:
        return ""


def get_mouse_position() -> dict:
    """Return the current mouse cursor position."""
    pos = pyautogui.position()
    return {"x": pos.x, "y": pos.y}


def get_screen_size() -> dict:
    """Return the primary screen dimensions."""
    w, h = pyautogui.size()
    return {"width": w, "height": h}
