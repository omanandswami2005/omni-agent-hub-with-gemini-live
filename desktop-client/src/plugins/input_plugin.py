"""Input plugin — mouse clicks, keyboard typing, hotkeys, scrolling."""

from __future__ import annotations

from src.actions import (
    click,
    double_click,
    get_active_window_title,
    get_mouse_position,
    get_screen_size,
    hotkey,
    move_mouse,
    open_application,
    scroll,
    search_applications,
    type_text,
)
from src.plugin_registry import DesktopPlugin


async def _handle_click(**kwargs) -> dict:
    return click(kwargs["x"], kwargs["y"], kwargs.get("button", "left"))


async def _handle_double_click(**kwargs) -> dict:
    return double_click(kwargs["x"], kwargs["y"])


async def _handle_type_text(**kwargs) -> dict:
    return type_text(kwargs["text"], kwargs.get("interval", 0.02))


async def _handle_hotkey(**kwargs) -> dict:
    return hotkey(*kwargs.get("keys", []))


async def _handle_move_mouse(**kwargs) -> dict:
    return move_mouse(kwargs["x"], kwargs["y"])


async def _handle_scroll(**kwargs) -> dict:
    return scroll(kwargs["amount"], kwargs.get("x"), kwargs.get("y"))


async def _handle_open_app(**kwargs) -> dict:
    return open_application(kwargs["name"])


async def _handle_search_apps(**kwargs) -> dict:
    return search_applications(kwargs["query"])


async def _handle_get_window_title(**_kwargs) -> dict:
    return {"title": get_active_window_title()}


async def _handle_mouse_position(**_kwargs) -> dict:
    return get_mouse_position()


async def _handle_screen_size(**_kwargs) -> dict:
    return get_screen_size()


def register() -> DesktopPlugin:
    return DesktopPlugin(
        name="input",
        capabilities=[
            "mouse_control",
            "keyboard_control",
            "app_launch",
        ],
        handlers={
            "click": _handle_click,
            "double_click": _handle_double_click,
            "type_text": _handle_type_text,
            "hotkey": _handle_hotkey,
            "move_mouse": _handle_move_mouse,
            "scroll": _handle_scroll,
            "open_app": _handle_open_app,
            "search_apps": _handle_search_apps,
            "get_window_title": _handle_get_window_title,
            "mouse_position": _handle_mouse_position,
            "screen_size": _handle_screen_size,
        },
        tool_defs=[
            {
                "name": "click",
                "description": "Click at screen coordinates (x, y)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "x": {"type": "integer", "description": "X coordinate"},
                        "y": {"type": "integer", "description": "Y coordinate"},
                        "button": {"type": "string", "description": "Mouse button: left, right, middle", "default": "left"},
                    },
                    "required": ["x", "y"],
                },
            },
            {
                "name": "double_click",
                "description": "Double-click at screen coordinates (x, y)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "x": {"type": "integer", "description": "X coordinate"},
                        "y": {"type": "integer", "description": "Y coordinate"},
                    },
                    "required": ["x", "y"],
                },
            },
            {
                "name": "type_text",
                "description": "Type text on the user's keyboard",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "Text to type"},
                        "interval": {"type": "number", "description": "Delay between keystrokes (seconds)", "default": 0.02},
                    },
                    "required": ["text"],
                },
            },
            {
                "name": "hotkey",
                "description": "Press a keyboard shortcut (e.g. ctrl, c for copy)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "keys": {"type": "array", "items": {"type": "string"}, "description": "Keys to press simultaneously"},
                    },
                    "required": ["keys"],
                },
            },
            {
                "name": "move_mouse",
                "description": "Move the mouse cursor to screen coordinates",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "x": {"type": "integer", "description": "X coordinate"},
                        "y": {"type": "integer", "description": "Y coordinate"},
                    },
                    "required": ["x", "y"],
                },
            },
            {
                "name": "scroll",
                "description": "Scroll the mouse wheel at optional coordinates",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "amount": {"type": "integer", "description": "Scroll amount (positive=up, negative=down)"},
                        "x": {"type": "integer", "description": "Optional X coordinate"},
                        "y": {"type": "integer", "description": "Optional Y coordinate"},
                    },
                    "required": ["amount"],
                },
            },
            {
                "name": "open_app",
                "description": "Open an application by name on the user's desktop. Automatically searches Start Menu, installed programs, and PATH to find the correct executable. Use natural names like 'chrome', 'firefox', 'vscode', 'notepad'.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Application name to open (e.g. 'chrome', 'spotify', 'visual studio code')"},
                    },
                    "required": ["name"],
                },
            },
            {
                "name": "search_apps",
                "description": "Search for installed applications matching a query. Use this FIRST when unsure of the exact application name. Returns a list of matching apps with names and paths.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search term (e.g. 'chrome', 'visual studio', 'note')"},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "get_window_title",
                "description": "Get the title of the currently active window",
                "parameters": {"type": "object", "properties": {}},
            },
            {
                "name": "mouse_position",
                "description": "Get the current mouse cursor position",
                "parameters": {"type": "object", "properties": {}},
            },
            {
                "name": "screen_size",
                "description": "Get the screen dimensions",
                "parameters": {"type": "object", "properties": {}},
            },
        ],
    )
