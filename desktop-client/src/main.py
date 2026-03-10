"""Omni Desktop Client — CLI entry point with system tray.

Provides a ``typer`` CLI that:
- ``connect`` — starts the WebSocket client with a system-tray icon
- ``status``  — prints current connection status
- ``config``  — shows the active configuration
"""

from __future__ import annotations

import asyncio
import base64
import logging
import threading

import typer
from PIL import Image, ImageDraw
from rich.console import Console

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
    type_text,
)
from src.config import DesktopConfig
from src.files import file_info, list_directory, read_file, set_allowed_directories, write_file
from src.screen import capture_active_window, capture_screen, get_screen_info
from src.ws_client import DesktopWSClient

logger = logging.getLogger(__name__)
console = Console()

app = typer.Typer(name="omni-desktop", help="Omni desktop agent client")

# Module-level state so ``status`` can inspect it
_client: DesktopWSClient | None = None


# ── Action handler wrappers (sync → dict) ─────────────────────────────
# The WS client calls these as ``await handler(**payload)``, so they are
# async wrappers around the mostly-sync action/screen/file functions.


async def _handle_capture_screen(**kwargs) -> dict:  # type: ignore[no-untyped-def]
    quality = kwargs.get("quality", 75)
    region = kwargs.get("region")
    data = capture_screen(region=region, quality=quality)
    return {"image_b64": base64.b64encode(data).decode(), "size": len(data)}


async def _handle_capture_active_window(**_kwargs) -> dict:  # type: ignore[no-untyped-def]
    data = capture_active_window()
    if data is None:
        return {"error": "Capture failed"}
    return {"image_b64": base64.b64encode(data).decode(), "size": len(data)}


async def _handle_screen_info(**_kwargs) -> dict:  # type: ignore[no-untyped-def]
    return get_screen_info()


async def _handle_click(**kwargs) -> dict:  # type: ignore[no-untyped-def]
    return click(kwargs["x"], kwargs["y"], kwargs.get("button", "left"))


async def _handle_double_click(**kwargs) -> dict:  # type: ignore[no-untyped-def]
    return double_click(kwargs["x"], kwargs["y"])


async def _handle_type_text(**kwargs) -> dict:  # type: ignore[no-untyped-def]
    return type_text(kwargs["text"], kwargs.get("interval", 0.02))


async def _handle_hotkey(**kwargs) -> dict:  # type: ignore[no-untyped-def]
    keys = kwargs.get("keys", [])
    return hotkey(*keys)


async def _handle_move_mouse(**kwargs) -> dict:  # type: ignore[no-untyped-def]
    return move_mouse(kwargs["x"], kwargs["y"])


async def _handle_scroll(**kwargs) -> dict:  # type: ignore[no-untyped-def]
    return scroll(kwargs["amount"], kwargs.get("x"), kwargs.get("y"))


async def _handle_open_app(**kwargs) -> dict:  # type: ignore[no-untyped-def]
    return open_application(kwargs["name"])


async def _handle_get_window_title(**_kwargs) -> dict:  # type: ignore[no-untyped-def]
    return {"title": get_active_window_title()}


async def _handle_mouse_position(**_kwargs) -> dict:  # type: ignore[no-untyped-def]
    return get_mouse_position()


async def _handle_screen_size(**_kwargs) -> dict:  # type: ignore[no-untyped-def]
    return get_screen_size()


async def _handle_read_file(**kwargs) -> dict:  # type: ignore[no-untyped-def]
    result = read_file(kwargs["path"], kwargs.get("max_size", 1_000_000))
    if isinstance(result, dict):
        return result
    return {"content": result}


async def _handle_write_file(**kwargs) -> dict:  # type: ignore[no-untyped-def]
    return write_file(kwargs["path"], kwargs["content"])


async def _handle_list_directory(**kwargs) -> dict:  # type: ignore[no-untyped-def]
    result = list_directory(kwargs.get("path", "."))
    if isinstance(result, dict):
        return result
    return {"entries": result}


async def _handle_file_info(**kwargs) -> dict:  # type: ignore[no-untyped-def]
    return file_info(kwargs["path"])


# ── Handler registration ──────────────────────────────────────────────

_ACTION_HANDLERS: dict = {
    "capture_screen": _handle_capture_screen,
    "capture_active_window": _handle_capture_active_window,
    "screen_info": _handle_screen_info,
    "click": _handle_click,
    "double_click": _handle_double_click,
    "type_text": _handle_type_text,
    "hotkey": _handle_hotkey,
    "move_mouse": _handle_move_mouse,
    "scroll": _handle_scroll,
    "open_app": _handle_open_app,
    "get_window_title": _handle_get_window_title,
    "mouse_position": _handle_mouse_position,
    "screen_size": _handle_screen_size,
    "read_file": _handle_read_file,
    "write_file": _handle_write_file,
    "list_directory": _handle_list_directory,
    "file_info": _handle_file_info,
}


# ── System tray ───────────────────────────────────────────────────────


def _create_tray_icon() -> Image.Image:
    """Generate a simple 64×64 tray icon (green circle on transparent bg)."""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([8, 8, 56, 56], fill=(34, 197, 94, 255))  # green
    draw.text((20, 18), "O", fill=(255, 255, 255, 255))
    return img


def _run_tray(stop_event: threading.Event) -> None:
    """Run the pystray system-tray icon in a background thread."""
    try:
        import pystray  # noqa: PLC0415
    except ImportError:
        logger.warning("pystray not installed — running without system tray")
        return

    def on_quit(icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        stop_event.set()
        icon.stop()

    icon = pystray.Icon(
        "omni-desktop",
        _create_tray_icon(),
        "Omni Desktop Agent",
        menu=pystray.Menu(
            pystray.MenuItem("Status: Connected", lambda *_: None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", on_quit),
        ),
    )
    icon.run()


# ── CLI commands ──────────────────────────────────────────────────────


@app.command()
def connect(
    server_url: str = typer.Option(None, help="Server WebSocket URL (overrides config)"),
    token: str = typer.Option(None, help="Auth token (overrides config)"),
) -> None:
    """Connect to Omni server and start desktop agent."""
    cfg = DesktopConfig()
    url = server_url or cfg.server_url
    auth = token or cfg.auth_token

    if not auth:
        console.print("[red]Error:[/red] No auth token provided. Set OMNI_DESKTOP_AUTH_TOKEN or use --token.")
        raise typer.Exit(code=1)

    # Apply allowed directories from config
    set_allowed_directories(cfg.allowed_directories)

    # Configure logging
    logging.basicConfig(level=getattr(logging, cfg.log_level.upper(), logging.INFO))

    console.print(f"[green]Connecting to[/green] {url}")

    global _client  # noqa: PLW0603
    _client = DesktopWSClient(url, auth)

    # Register all action handlers
    for action_name, handler_fn in _ACTION_HANDLERS.items():
        _client.register_handler(action_name, handler_fn)

    # Start system tray in a background thread
    stop_event = threading.Event()
    tray_thread = threading.Thread(target=_run_tray, args=(stop_event,), daemon=True)
    tray_thread.start()

    # Run the WS client (blocks until stop_event or Ctrl+C)
    try:
        asyncio.run(_run_client(_client, stop_event))
    except KeyboardInterrupt:
        console.print("\n[yellow]Shutting down…[/yellow]")
    finally:
        stop_event.set()


async def _run_client(client: DesktopWSClient, stop_event: threading.Event) -> None:
    """Run WS client until the stop event is set."""
    task = asyncio.create_task(client.run())

    # Poll the threading event periodically
    while not stop_event.is_set():
        await asyncio.sleep(0.5)

    await client.disconnect()
    task.cancel()


@app.command()
def status() -> None:
    """Show current connection status."""
    if _client and _client.connected:
        console.print("[green]Status:[/green] Connected")
    else:
        console.print("[yellow]Status:[/yellow] Disconnected")


@app.command()
def show_config() -> None:
    """Show the active configuration."""
    cfg = DesktopConfig()
    console.print("[bold]Omni Desktop Configuration[/bold]")
    console.print(f"  Server URL:    {cfg.server_url}")
    console.print(f"  Auth Token:    {'***' + cfg.auth_token[-4:] if len(cfg.auth_token) > 4 else '(not set)'}")
    console.print(f"  Capture Qual:  {cfg.capture_quality}")
    console.print(f"  Allowed Dirs:  {cfg.allowed_directories}")
    console.print(f"  Log Level:     {cfg.log_level}")


if __name__ == "__main__":
    app()
