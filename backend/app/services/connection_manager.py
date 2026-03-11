"""In-memory ConnectionManager — tracks connected WebSocket clients per user.

Replaces Socket.IO rooms with a simple dict-of-dicts keyed by
``(user_id, client_type)``.  Each value is the ``WebSocket`` instance.

Includes a periodic heartbeat reaper that pings connected sockets and
evicts dead connections that failed to respond.

Thread-safety note: FastAPI runs on a single asyncio event loop,
so plain dicts are safe — no locks needed.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.models.client import ClientInfo, ClientType
from app.utils.logging import get_logger

if TYPE_CHECKING:
    from fastapi import WebSocket

logger = get_logger(__name__)

__all__ = ["ConnectionManager", "get_connection_manager"]

# Heartbeat interval + timeout (seconds)
_HEARTBEAT_INTERVAL = 30
_PING_TIMEOUT = 10


class ConnectionManager:
    """In-memory registry of active WebSocket connections with heartbeat."""

    def __init__(self) -> None:
        # { user_id: { client_type: (WebSocket, connected_at, os_name) } }
        self._connections: dict[str, dict[ClientType, tuple[WebSocket, datetime, str]]] = {}
        self._reaper_task: asyncio.Task | None = None

    # ── Connect / Disconnect ──────────────────────────────────────────

    async def connect(
        self,
        websocket: WebSocket,
        user_id: str,
        client_type: ClientType = ClientType.WEB,
        os_name: str = "Unknown",
    ) -> None:
        """Register *websocket* for the given user + device type.

        If the same ``(user_id, client_type)`` already has an active
        connection the old socket is closed first (one device per type).
        """
        user_conns = self._connections.setdefault(user_id, {})
        old = user_conns.get(client_type)
        if old is not None:
            old_ws, _, _os = old
            with contextlib.suppress(Exception):
                await old_ws.close(code=4000, reason="Replaced by new connection")
            logger.info(
                "replaced_connection",
                user_id=user_id,
                client_type=client_type,
            )
        user_conns[client_type] = (websocket, datetime.now(UTC), os_name)
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
        for ct, (ws, _, _os) in user_conns.items():
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
        ws, _, _os = entry
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
                client_id=str(ct),
                connected_at=connected_at,
                last_ping=now,
                os_name=os_name,
            )
            for ct, (_, connected_at, os_name) in user_conns.items()
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

    # ── Heartbeat / Reaper ────────────────────────────────────────────

    def start_reaper(self) -> None:
        """Launch the background heartbeat reaper (call once at startup)."""
        if self._reaper_task is None or self._reaper_task.done():
            self._reaper_task = asyncio.create_task(
                self._reap_loop(), name="ws-heartbeat-reaper",
            )

    def stop_reaper(self) -> None:
        """Cancel the background reaper (call at shutdown)."""
        if self._reaper_task and not self._reaper_task.done():
            self._reaper_task.cancel()

    async def _reap_loop(self) -> None:
        """Periodically ping every connected WebSocket; evict non-responders."""
        while True:
            await asyncio.sleep(_HEARTBEAT_INTERVAL)
            await self._ping_all()
            # Also evict idle MCP toolsets while we're here
            try:
                from app.services.mcp_manager import get_mcp_manager
                await get_mcp_manager().evict_idle_toolsets()
            except Exception:
                pass  # MCP manager may not be initialised yet

    async def _ping_all(self) -> None:
        """Send a WebSocket ping to every connection; disconnect failures."""
        dead: list[tuple[str, ClientType]] = []
        for user_id, user_conns in list(self._connections.items()):
            for ct, (ws, _, _os) in list(user_conns.items()):
                try:
                    await asyncio.wait_for(ws.send_text('{"type":"ping"}'), timeout=_PING_TIMEOUT)
                except Exception:
                    dead.append((user_id, ct))
        for user_id, ct in dead:
            logger.warning("heartbeat_stale_reaped", user_id=user_id, client_type=ct)
            await self.disconnect(user_id, ct)
        if dead:
            logger.info("heartbeat_reap_complete", reaped=len(dead), remaining=self.total_connections)


# ── Module singleton ──────────────────────────────────────────────────

_manager: ConnectionManager | None = None


def get_connection_manager() -> ConnectionManager:
    global _manager
    if _manager is None:
        _manager = ConnectionManager()
    return _manager
