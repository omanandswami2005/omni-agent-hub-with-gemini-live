"""Screen capture plugin — capture_screen, capture_active_window, screen_info."""

from __future__ import annotations

import base64

from src.plugin_registry import DesktopPlugin
from src.screen import capture_active_window, capture_screen, get_screen_info


async def _handle_capture_screen(**kwargs) -> dict:
    quality = kwargs.get("quality", 75)
    region = kwargs.get("region")
    data = capture_screen(region=region, quality=quality)
    return {"image_b64": base64.b64encode(data).decode(), "size": len(data)}


async def _handle_capture_active_window(**_kwargs) -> dict:
    data = capture_active_window()
    if data is None:
        return {"error": "Capture failed"}
    return {"image_b64": base64.b64encode(data).decode(), "size": len(data)}


async def _handle_screen_info(**_kwargs) -> dict:
    return get_screen_info()


def register() -> DesktopPlugin:
    return DesktopPlugin(
        name="screen",
        capabilities=["screen_capture"],
        handlers={
            "capture_screen": _handle_capture_screen,
            "capture_active_window": _handle_capture_active_window,
            "screen_info": _handle_screen_info,
        },
        tool_defs=[
            {
                "name": "capture_screen",
                "description": "Capture a screenshot of the user's desktop screen",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "quality": {"type": "integer", "description": "JPEG quality (1-100)", "default": 75},
                    },
                },
            },
            {
                "name": "capture_active_window",
                "description": "Capture a screenshot of the currently active window",
                "parameters": {"type": "object", "properties": {}},
            },
            {
                "name": "screen_info",
                "description": "Get screen resolution and display information",
                "parameters": {"type": "object", "properties": {}},
            },
        ],
    )
