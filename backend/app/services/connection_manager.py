"""In-memory ConnectionManager — tracks connected WebSocket clients per user.

Replaces Socket.IO rooms with a simple dict-of-dicts keyed by
``(user_id, client_type)``.  Each value is the ``WebSocket`` instance.

Thread-safety note: FastAPI runs on a single asyncio event loop,
so plain dicts are safe — no locks needed.
"""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.models.client import ClientInfo, ClientType
from app.utils.logging import get_logger

if TYPE_CHECKING:
    from fastapi import WebSocket

logger = get_logger(__name__)

__all__ = ["ConnectionManager", "get_connection_manager"]


class ConnectionManager:
    """In-memory registry of active WebSocket connections."""

    def __init__(self) -> None:
        # { user_id: { client_type: (WebSocket, connected_at) } }
        self._connections: dict[str, dict[ClientType, tuple[WebSocket, datetime]]] = {}

    # ── Connect / Disconnect ──────────────────────────────────────────

    async def connect(
        self,
        websocket: WebSocket,
        user_id: str,
        client_type: ClientType = ClientType.WEB,
    ) -> None:
        """Register *websocket* for the given user + device type.

        If the same ``(user_id, client_type)`` already has an active
        connection the old socket is closed first (one device per type).
        """
        user_conns = self._connections.setdefault(user_id, {})
        old = user_conns.get(client_type)
        if old is not None:
            old_ws, _ = old
            with contextlib.suppress(Exception):
                await old_ws.close(code=4000, reason="Replaced by new connection")
            logger.info(
                "replaced_connection",
                user_id=user_id,
                client_type=client_type,
            )
        user_conns[client_type] = (websocket, datetime.now(UTC))
        logger.info("client_connected", user_id=user_id, client_type=client_type)

    async def disconnect(
        self,
        user_id: str,
        client_type: ClientType = ClientType.WEB,
    ) -> None:
        """Remove the connection for ``(user_id, client_type)``."""
        user_conns = self._connections.get(user_id)
        if user_conns is None:
            return
        user_conns.pop(client_type, None)
        if not user_conns:
            self._connections.pop(user_id, None)
        logger.info("client_disconnected", user_id=user_id, client_type=client_type)

    # ── Messaging ─────────────────────────────────────────────────────

    async def send_to_user(self, user_id: str, message: str) -> None:
        """Broadcast a JSON text frame to **all** connected clients of a user."""
        user_conns = self._connections.get(user_id, {})
        dead: list[ClientType] = []
        for ct, (ws, _) in user_conns.items():
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ct)
        for ct in dead:
            await self.disconnect(user_id, ct)

    async def send_to_client(
        self,
        user_id: str,
        client_type: ClientType,
        message: str,
    ) -> None:
        """Send a JSON text frame to a **specific** client."""
        user_conns = self._connections.get(user_id, {})
        entry = user_conns.get(client_type)
        if entry is None:
            return
        ws, _ = entry
        try:
            await ws.send_text(message)
        except Exception:
            await self.disconnect(user_id, client_type)

    # ── Queries ───────────────────────────────────────────────────────

    def get_connected_clients(self, user_id: str) -> list[ClientInfo]:
        """Return ``ClientInfo`` for every active connection of *user_id*."""
        user_conns = self._connections.get(user_id, {})
        now = datetime.now(UTC)
        return [
            ClientInfo(
                user_id=user_id,
                client_type=ct,
                client_id=f"{user_id}:{ct}",
                connected_at=connected_at,
                last_ping=now,
            )
            for ct, (_, connected_at) in user_conns.items()
        ]

    def is_online(self, user_id: str, client_type: ClientType | None = None) -> bool:
        """Check whether a user (or specific device) is connected."""
        user_conns = self._connections.get(user_id)
        if user_conns is None:
            return False
        if client_type is None:
            return bool(user_conns)
        return client_type in user_conns

    def get_other_clients_online(
        self, user_id: str, current_client_type: ClientType
    ) -> list[ClientType]:
        """Return list of OTHER client types that are online (excluding current)."""
        user_conns = self._connections.get(user_id, {})
        return [
            ct for ct in user_conns.keys()
            if ct != current_client_type
        ]

    @property
    def total_connections(self) -> int:
        return sum(len(v) for v in self._connections.values())


# ── Module singleton ──────────────────────────────────────────────────

_manager: ConnectionManager | None = None


def get_connection_manager() -> ConnectionManager:
    global _manager
    if _manager is None:
        _manager = ConnectionManager()
    return _manager
