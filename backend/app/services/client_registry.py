"""Client registry — re-exports from connection_manager for spec compatibility.

The spec names this `client_registry.py` (in-memory client tracking).
Our implementation lives in `connection_manager.py` which handles both
WebSocket connection lifecycle and client registry in one class.
"""

from app.services.connection_manager import *  # noqa: F403
