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
import json
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
    """In-memory registry of active WebSocket connections with heartbeat.

    Primary connections (from ``/ws/live``) are keyed by
    ``(user_id, client_type)`` — one per device.  They appear in client
    lists and receive status broadcasts.

    Auxiliary sockets (e.g. ``/ws/chat``) are stored separately.  They
    receive broadcasts but do NOT show as distinct clients.
    """

    def __init__(self) -> None:
        # { user_id: { client_type: (WebSocket, connected_at, os_name) } }
        self._connections: dict[str, dict[ClientType, tuple[WebSocket, datetime, str]]] = {}
        # Auxiliary sockets that also receive broadcasts (e.g. /ws/chat)
        # { user_id: { aux_key: WebSocket } }
        self._aux_sockets: dict[str, dict[str, WebSocket]] = {}
        # { user_id: { client_type: { "capabilities": [...], "local_tools": [...] } } }
        self._capabilities: dict[str, dict[ClientType, dict]] = {}
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
        await self._broadcast_client_status(user_id, event="connected", changed_client_type=client_type)

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
        # Clean up capabilities for this client
        user_caps = self._capabilities.get(user_id)
        if user_caps is not None:
            user_caps.pop(client_type, None)
            if not user_caps:
                self._capabilities.pop(user_id, None)
        logger.info("client_disconnected", user_id=user_id, client_type=client_type)
        await self._broadcast_client_status(user_id, event="disconnected", changed_client_type=client_type)

    # ── Auxiliary sockets (receive broadcasts but aren't listed as clients) ──

    def add_aux_socket(self, user_id: str, key: str, websocket: WebSocket) -> None:
        """Register an auxiliary socket that receives broadcasts."""
        self._aux_sockets.setdefault(user_id, {})[key] = websocket
        logger.debug("aux_socket_added", user_id=user_id, key=key)

    def remove_aux_socket(self, user_id: str, key: str) -> None:
        """Remove an auxiliary socket."""
        user_aux = self._aux_sockets.get(user_id)
        if user_aux is not None:
            user_aux.pop(key, None)
            if not user_aux:
                self._aux_sockets.pop(user_id, None)

    # ── Status Broadcasting ────────────────────────────────────────────

    async def _broadcast_client_status(
        self,
        user_id: str,
        event: str,
        changed_client_type: ClientType,
    ) -> None:
        """Notify all connected clients of this user about the current client list."""
        clients = self.get_connected_clients(user_id)
        payload = json.dumps({
            "type": "client_status_update",
            "event": event,
            "client_type": str(changed_client_type),
            "clients": [
                {
                    "client_type": str(c.client_type),
                    "client_id": c.client_id,
                    "connected_at": c.connected_at.isoformat() if c.connected_at else None,
                    "os_name": c.os_name,
                    "connected": True,
                }
                for c in clients
            ],
        })
        await self.send_to_user(user_id, payload)

    # ── Messaging ─────────────────────────────────────────────────────

    async def send_to_user(self, user_id: str, message: str) -> None:
        """Broadcast a JSON text frame to **all** connected clients of a user.

        Sends to both primary connections and auxiliary sockets.
        """
        # Snapshot items to avoid RuntimeError if the dict is mutated during iteration
        user_conns = self._connections.get(user_id, {})
        snapshot = list(user_conns.items())
        dead: list[ClientType] = []
        for ct, (ws, _, _os) in snapshot:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ct)
        for ct in dead:
            await self.disconnect(user_id, ct)

        # Also send to auxiliary sockets
        user_aux = self._aux_sockets.get(user_id, {})
        aux_snapshot = list(user_aux.items())
        dead_aux: list[str] = []
        for key, ws in aux_snapshot:
            try:
                await ws.send_text(message)
            except Exception:
                dead_aux.append(key)
        for key in dead_aux:
            self.remove_aux_socket(user_id, key)

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

    # ── Capabilities ────────────────────────────────────────────────────

    def store_capabilities(
        self,
        user_id: str,
        client_type: ClientType,
        capabilities: list[str] | None = None,
        local_tools: list[dict] | None = None,
    ) -> None:
        """Store advertised capabilities and local tools for a client."""
        user_caps = self._capabilities.setdefault(user_id, {})
        user_caps[client_type] = {
            "capabilities": capabilities or [],
            "local_tools": local_tools or [],
        }
        logger.info(
            "capabilities_stored",
            user_id=user_id,
            client_type=client_type,
            capability_count=len(capabilities or []),
            tool_count=len(local_tools or []),
        )

    def get_capabilities(self, user_id: str) -> dict[ClientType, dict]:
        """Return capabilities for all connected clients of a user."""
        return dict(self._capabilities.get(user_id, {}))

    def update_capabilities(
        self,
        user_id: str,
        client_type: ClientType,
        added: list[str] | None = None,
        removed: list[str] | None = None,
        added_tools: list[dict] | None = None,
        removed_tools: list[str] | None = None,
    ) -> None:
        """Update capabilities mid-session (add/remove)."""
        user_caps = self._capabilities.setdefault(user_id, {})
        entry = user_caps.setdefault(client_type, {"capabilities": [], "local_tools": []})

        caps = set(entry["capabilities"])
        if added:
            caps.update(added)
        if removed:
            caps -= set(removed)
        entry["capabilities"] = sorted(caps)

        if added_tools:
            existing_names = {t["name"] for t in entry["local_tools"]}
            for t in added_tools:
                if t.get("name") and t["name"] not in existing_names:
                    entry["local_tools"].append(t)
                    existing_names.add(t["name"])

        if removed_tools:
            entry["local_tools"] = [
                t for t in entry["local_tools"]
                if t.get("name") not in set(removed_tools)
            ]

        logger.info(
            "capabilities_updated",
            user_id=user_id,
            client_type=client_type,
            total_capabilities=len(entry["capabilities"]),
            total_tools=len(entry["local_tools"]),
        )

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
            ct for ct in user_conns
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
            for ct, (ws, _, _os) in list(dict(user_conns).items()):
                try:
                    await asyncio.wait_for(ws.send_text('{"type":"ping"}'), timeout=_PING_TIMEOUT)
                except Exception:
                    dead.append((user_id, ct))
        for user_id, ct in dead:
            logger.warning("heartbeat_stale_reaped", user_id=user_id, client_type=ct)
            await self.disconnect(user_id, ct)

        # Ping auxiliary sockets too
        dead_aux: list[tuple[str, str]] = []
        for user_id, aux in list(self._aux_sockets.items()):
            for key, ws in list(dict(aux).items()):
                try:
                    await asyncio.wait_for(ws.send_text('{"type":"ping"}'), timeout=_PING_TIMEOUT)
                except Exception:
                    dead_aux.append((user_id, key))
        for user_id, key in dead_aux:
            self.remove_aux_socket(user_id, key)

        total_reaped = len(dead) + len(dead_aux)
        if total_reaped:
            logger.info("heartbeat_reap_complete", reaped=total_reaped, remaining=self.total_connections)


# ── Module singleton ──────────────────────────────────────────────────

_manager: ConnectionManager | None = None


def get_connection_manager() -> ConnectionManager:
    global _manager
    if _manager is None:
        _manager = ConnectionManager()
    return _manager
