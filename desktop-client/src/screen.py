"""Screen capture utilities using mss + Pillow.

Provides functions for full-screen, region, and active-window capture.
Returns JPEG-compressed bytes suitable for WebSocket transmission.
"""

from __future__ import annotations

import io
import logging
import subprocess
import sys

import mss
from PIL import Image

logger = logging.getLogger(__name__)

# Default JPEG quality — balances size vs clarity
_DEFAULT_QUALITY = 75


def capture_screen(region: dict | None = None, quality: int = _DEFAULT_QUALITY) -> bytes:
    """Capture screen or region, return JPEG bytes.

    Args:
        region: Optional dict with keys ``x``, ``y``, ``width``, ``height``.
                If *None*, captures the entire primary monitor.
        quality: JPEG compression quality (1-100).

    Returns:
        JPEG image bytes.
    """
    with mss.mss() as sct:
        if region:
            monitor = {
                "left": region["x"],
                "top": region["y"],
                "width": region["width"],
                "height": region["height"],
            }
        else:
            # Primary monitor (index 1); index 0 is all monitors combined
            monitor = sct.monitors[1]

        screenshot = sct.grab(monitor)
        img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")

    return _image_to_jpeg(img, quality)


def get_screen_info() -> dict:
    """Return screen resolution and monitor layout.

    Returns:
        Dict with ``monitors`` list (each has left, top, width, height)
        and ``primary`` with the primary monitor dimensions.
    """
    with mss.mss() as sct:
        monitors = []
        for i, m in enumerate(sct.monitors):
            monitors.append({
                "index": i,
                "left": m["left"],
                "top": m["top"],
                "width": m["width"],
                "height": m["height"],
            })
        primary = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
        return {
            "monitors": monitors,
            "primary": {
                "width": primary["width"],
                "height": primary["height"],
            },
        }


def capture_active_window() -> bytes | None:
    """Capture only the active/focused window.

    Uses platform-specific methods to detect the foreground window bounds,
    then captures that region. Falls back to full screen if detection fails.

    Returns:
        JPEG image bytes, or *None* if capture fails entirely.
    """
    bounds = _get_active_window_bounds()
    if bounds is None:
        logger.warning("Could not detect active window bounds; falling back to full screen")
        return capture_screen()

    return capture_screen(region=bounds)


# ── Internal helpers ──────────────────────────────────────────────────


def _image_to_jpeg(img: Image.Image, quality: int) -> bytes:
    """Compress a PIL Image to JPEG bytes."""
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def _get_active_window_bounds() -> dict | None:
    """Return ``{x, y, width, height}`` of the active window (Windows/Linux/macOS)."""
    if sys.platform == "win32":
        return _win32_active_window()
    if sys.platform == "darwin":
        return _macos_active_window()
    # Linux/X11 via xdotool
    return _linux_active_window()


def _win32_active_window() -> dict | None:
    try:
        import ctypes  # noqa: PLC0415

        user32 = ctypes.windll.user32  # type: ignore[attr-defined]

        class RECT(ctypes.Structure):
            _fields_ = [
                ("left", ctypes.c_long),
                ("top", ctypes.c_long),
                ("right", ctypes.c_long),
                ("bottom", ctypes.c_long),
            ]

        hwnd = user32.GetForegroundWindow()
        rect = RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        return {
            "x": rect.left,
            "y": rect.top,
            "width": rect.right - rect.left,
            "height": rect.bottom - rect.top,
        }
    except Exception:
        return None


def _macos_active_window() -> dict | None:
    try:
        script = (
            'tell application "System Events" to get '
            "{position, size} of first window of "
            "(first application process whose frontmost is true)"
        )
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None
        # Output: "x, y, w, h"
        parts = [int(p.strip()) for p in result.stdout.strip().split(",")]
        if len(parts) == 4:
            return {"x": parts[0], "y": parts[1], "width": parts[2], "height": parts[3]}
    except Exception:
        pass
    return None


def _linux_active_window() -> dict | None:
    try:
        result = subprocess.run(
            ["xdotool", "getactivewindow", "getwindowgeometry", "--shell"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None
        vals: dict[str, int] = {}
        for line in result.stdout.strip().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                vals[k.strip()] = int(v.strip())
        return {
            "x": vals.get("X", 0),
            "y": vals.get("Y", 0),
            "width": vals.get("WIDTH", 0),
            "height": vals.get("HEIGHT", 0),
        }
    except Exception:
        return None
