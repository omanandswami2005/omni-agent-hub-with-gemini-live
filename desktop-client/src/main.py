"""Omni Desktop Client — CLI entry point with system tray and Qt GUI.

Provides a ``typer`` CLI that:
- ``connect`` — starts the WebSocket client and Qt GUI
- ``status``  — prints current connection status
- ``config``  — shows the active configuration

All tool handlers are loaded from the plugin system (see ``plugins/``).
"""

from __future__ import annotations

import asyncio
import logging
import sys
import threading
from pathlib import Path

import typer
from rich.console import Console

from PyQt6.QtWidgets import QApplication
import qasync

from src.config import DesktopConfig
from src.files import set_allowed_directories
from src.plugin_registry import PluginRegistry
from src.ws_client import DesktopWSClient
from src.gui import MainWindow
from src.plugins.command_plugin import set_gui_instance

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

    # Set up Qt Application and async event loop
    qt_app = QApplication(sys.argv)
    loop = qasync.QEventLoop(qt_app)
    asyncio.set_event_loop(loop)

    # Initialize Main Window before discovering plugins
    main_window = MainWindow()
    set_gui_instance(main_window) # Provide GUI reference to command plugin

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

    _client.set_gui(main_window) # Inject GUI to client
    main_window.show()

    # Create run task
    with loop:
        task = loop.create_task(_run_client(_client, main_window))
        try:
            loop.run_forever()
        except KeyboardInterrupt:
            console.print("\n[yellow]Shutting down…[/yellow]")
        finally:
            task.cancel()
            _client._should_run = False


async def _run_client(client: DesktopWSClient, window: MainWindow) -> None:
    """Run WS client"""
    # Create the task for running client loop
    run_task = asyncio.create_task(client.run())

    # Wait a tiny bit for the run loop to start and set _should_run
    await asyncio.sleep(0.1)

    while client._should_run or not run_task.done():
         # Need to break when window is closed
         if window.isHidden():
              client._should_run = False
              break
         await asyncio.sleep(0.5)

    await client.disconnect()
    if not run_task.done():
        run_task.cancel()
    QApplication.instance().quit()


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
