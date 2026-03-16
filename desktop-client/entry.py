"""PyInstaller entry point for Omni Desktop Client.

This thin wrapper calls the Typer CLI app defined in src/main.py,
which handles the ``connect``, ``status``, and ``config`` sub-commands.
When launched directly without arguments it defaults to ``connect``.
"""
import sys
import os

# Make sure the bundled src package is importable when running in a frozen exe
if getattr(sys, "frozen", False):
    # PyInstaller sets sys._MEIPASS to the temporary extraction dir.
    # Prepend it so `import src.*` resolves correctly.
    sys.path.insert(0, sys._MEIPASS)  # noqa: SLF001

from src.main import app  # noqa: E402

if __name__ == "__main__":
    # If no sub-command given, default to 'connect'
    if len(sys.argv) == 1:
        sys.argv.append("connect")
    app()
