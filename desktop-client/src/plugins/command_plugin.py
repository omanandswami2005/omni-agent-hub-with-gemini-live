"""Command plugin — execute shell commands safely."""

from __future__ import annotations

import asyncio
import logging
import subprocess
from typing import Any

from src.plugin_registry import DesktopPlugin

logger = logging.getLogger(__name__)

# List of dangerous commands that require confirmation
DANGEROUS_KEYWORDS = ["rm", "delete", "del", "format", "mkfs", "fdisk", "dd", "mv"]

# Global reference to main window to show dialogs
_gui_instance = None

def set_gui_instance(gui):
    global _gui_instance
    _gui_instance = gui

async def _handle_execute_command(**kwargs) -> dict:
    command = kwargs.get("command", "")
    if not command:
        return {"error": "No command provided"}

    # Check for dangerous commands
    cmd_parts = command.split()
    is_dangerous = any(part.lower() in DANGEROUS_KEYWORDS for part in cmd_parts)

    if is_dangerous:
        # Require confirmation
        if _gui_instance:
            loop = asyncio.get_running_loop()
            future = loop.create_future()

            # Emit signal to GUI
            _gui_instance.show_confirmation_dialog_async(
                "Security Warning",
                f"The AI wants to run a dangerous command:\n\n{command}\n\nAllow execution?",
                future
            )

            # Wait for user input from GUI
            confirmed = await future

            if not confirmed:
                logger.info(f"User denied execution of: {command}")
                return {"error": "User denied execution of dangerous command"}
        else:
             logger.warning(f"GUI not available to confirm dangerous command: {command}")
             return {"error": "Execution denied (cannot confirm dangerous command without GUI)"}

    try:
        # Execute the command
        # Run in a thread to not block the event loop
        loop = asyncio.get_running_loop()

        def run_cmd():
            return subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30
            )

        result = await loop.run_in_executor(None, run_cmd)

        return {
            "ok": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {"error": "Command execution timed out"}
    except Exception as e:
        logger.error(f"Command execution failed: {e}")
        return {"error": str(e)}

def register() -> DesktopPlugin:
    return DesktopPlugin(
        name="command",
        capabilities=["execute_command"],
        handlers={
            "execute_command": _handle_execute_command,
        },
        tool_defs=[
            {
                "name": "execute_command",
                "description": "Execute a shell command on the user's desktop (e.g. grep, date). Warning: dangerous commands require user confirmation.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "The shell command to execute"},
                    },
                    "required": ["command"],
                },
            },
        ],
        on_load=lambda cfg: None,  # no-op load
    )
