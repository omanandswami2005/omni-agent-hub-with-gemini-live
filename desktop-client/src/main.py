"""Omni Desktop Client — CLI entry point with system tray.

Provides a ``typer`` CLI that:
- ``connect`` — starts the WebSocket client with a system-tray icon
- ``status``  — prints current connection status
- ``config``  — shows the active configuration

All tool handlers are loaded from the plugin system (see ``plugins/``). The
only built-in logic here is the tray icon and the CLI commands.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from pathlib import Path

import typer
from PIL import Image, ImageDraw
from rich.console import Console

from src.config import DesktopConfig
from src.files import set_allowed_directories
from src.plugin_registry import PluginRegistry
from src.ws_client import DesktopWSClient

logger = logging.getLogger(__name__)
console = Console()

app = typer.Typer(name="omni-desktop", help="Omni desktop agent client")

# Module-level state so ``status`` can inspect it
_client: DesktopWSClient | None = None

# Plugins directory (sibling to this file)
_PLUGINS_DIR = str(Path(__file__).resolve().parent / "plugins")


def _build_registry() -> PluginRegistry:
    """Discover and register all desktop-client plugins."""
    registry = PluginRegistry()
    registry.discover(_PLUGINS_DIR)
    return registry


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

    # Discover plugins and build the handler registry
    registry = _build_registry()
    registry.load_all(cfg)
    console.print(
        f"[green]Loaded {len(registry)} plugin(s):[/green] "
        f"{', '.join(registry.plugin_names)}"
    )

    console.print(f"[green]Connecting to[/green] {url}")

    global _client  # noqa: PLW0603
    _client = DesktopWSClient(url, auth)

    # Register all plugin handlers
    for action_name, handler_fn in registry.handlers.items():
        _client.register_handler(action_name, handler_fn)

    # Advertise T3 capabilities and local tools from plugins
    _client.set_t3_tools(registry.capabilities, registry.tool_defs)

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
