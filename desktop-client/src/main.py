"""Omni Desktop Client — CLI entry point."""

# TODO: Implement with Typer:
#   - `omni-desktop connect` — connect to server via raw WS
#   - `omni-desktop status` — show connection status
#   - `omni-desktop config` — configure server URL, auth token
#   - System tray icon (optional, via pystray)

import typer

app = typer.Typer(name="omni-desktop", help="Omni desktop agent client")


@app.command()
def connect(
    server_url: str = typer.Option("ws://localhost:8080/ws/live", help="Server WebSocket URL"),
):
    """Connect to Omni server and start desktop agent."""
    typer.echo(f"Connecting to {server_url}...")
    # TODO: Initialize ws_client, register capabilities, start event loop


@app.command()
def status():
    """Show current connection status."""
    typer.echo("Status: disconnected")


if __name__ == "__main__":
    app()
