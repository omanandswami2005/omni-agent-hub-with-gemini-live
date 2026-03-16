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
    auth_token = token or cfg.auth_token

    # Apply allowed directories from config
    set_allowed_directories(cfg.allowed_directories)

    # Configure logging
    logging.basicConfig(level=getattr(logging, cfg.log_level.upper(), logging.INFO))

    # Set up Qt Application and async event loop
    qt_app = QApplication(sys.argv)
    loop = qasync.QEventLoop(qt_app)
    asyncio.set_event_loop(loop)

    # ── Login flow ────────────────────────────────────────────────
    # If no token on CLI/env, show the login dialog (requires firebase_api_key)
    auth_result = None
    if not auth_token:
        api_key = cfg.firebase_api_key
        if not api_key:
            console.print(
                "[red]Error:[/red] No auth token and no Firebase API key configured.\n"
                "Set OMNI_DESKTOP_AUTH_TOKEN or OMNI_DESKTOP_FIREBASE_API_KEY."
            )
            raise typer.Exit(code=1)

        from src.login_dialog import LoginDialog

        dialog = LoginDialog(api_key)
        if dialog.exec() != LoginDialog.DialogCode.Accepted or not dialog.auth_result:
            console.print("[yellow]Login cancelled.[/yellow]")
            raise typer.Exit(code=0)

        auth_result = dialog.auth_result
        auth_token = auth_result.id_token
        console.print(f"[green]Signed in as[/green] {auth_result.email}")

    # ── GUI + plugins ─────────────────────────────────────────────
    # Initialize Main Window before discovering plugins
    main_window = MainWindow()
    set_gui_instance(main_window)  # Provide GUI reference to command plugin

    # Discover plugins and build the handler registry
    registry = _build_registry()
    registry.load_all(cfg)
    console.print(
        f"[green]Loaded {len(registry)} plugin(s):[/green] "
        f"{', '.join(registry.plugin_names)}"
    )

    console.print(f"[green]Connecting to[/green] {url}")

    global _client  # noqa: PLW0603
    _client = DesktopWSClient(url, auth_token)

    # If we logged in via dialog, give the client the refresh token
    # so it can auto-refresh before the ID token expires.
    if auth_result:
        _client.set_auth_refresh(cfg.firebase_api_key, auth_result.refresh_token)

    # Register all plugin handlers
    for action_name, handler_fn in registry.handlers.items():
        _client.register_handler(action_name, handler_fn)

    # Advertise T3 capabilities and local tools from plugins
    _client.set_t3_tools(registry.capabilities, registry.tool_defs)

    _client.set_gui(main_window) # Inject GUI to client
    main_window.show()

    with loop:
        # Auto-connect: schedule start after loop begins running
        loop.call_soon(_auto_connect, _client, main_window)

        task = loop.create_task(_run_app_watcher(_client, main_window))
        try:
            loop.run_forever()
        except KeyboardInterrupt:
            console.print("\n[yellow]Shutting down…[/yellow]")
        finally:
            task.cancel()
            _client._should_run = False


def _auto_connect(client: DesktopWSClient, window: MainWindow) -> None:
    """Auto-connect the client once the event loop is running."""
    client.start()
    window.connect_button.setChecked(True)
    window.connect_button.setText("Disconnect")


async def _run_app_watcher(client: DesktopWSClient, window: MainWindow) -> None:
    """Run watcher for app lifetime."""
    while True:
         # Need to break when window is closed
         if window.isHidden():
              client._should_run = False
              await client.disconnect()
              break
         await asyncio.sleep(0.5)

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
