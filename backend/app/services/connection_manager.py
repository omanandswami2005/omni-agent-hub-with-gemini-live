"""ConnectionManager — tracks connected WebSocket clients per user.

Local in-memory dict holds live WebSocket references for messaging.
A Firestore ``client_presence`` collection provides cross-instance
visibility so that ``GET /clients`` returns devices connected to
**any** Cloud Run instance.

Thread-safety note: FastAPI runs on a single asyncio event loop,
so plain dicts are safe — no locks needed.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.models.client import ClientInfo, ClientType
from app.utils.logging import get_logger

if TYPE_CHECKING:
    from fastapi import WebSocket

logger = get_logger(__name__)

__all__ = ["ConnectionManager", "get_connection_manager"]

_background_tasks: set[asyncio.Task] = set()


def _fire_and_forget(coro) -> asyncio.Task:
    """Schedule *coro* as a background task and prevent GC until done."""
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task

# Heartbeat interval + timeout (seconds)
_HEARTBEAT_INTERVAL = 30
_PING_TIMEOUT = 10
# Firestore presence docs older than this are considered stale
_PRESENCE_STALE_SECONDS = 90

# Unique per-container instance ID (Cloud Run assigns K_REVISION + random suffix)
_INSTANCE_ID = os.environ.get("K_REVISION", "") + "-" + os.urandom(4).hex()

_PRESENCE_COLLECTION = "client_presence"

# How long (seconds) a mic floor holder can be silent before the lock expires.
# Prevents indefinite locks when a client stops sending audio without releasing.
_STALE_MIC_TIMEOUT_S = 30.0


class ConnectionManager:
    """Hybrid connection registry: local WebSocket refs + Firestore presence.

    Local in-memory dict stores live ``WebSocket`` objects for messaging.
    Firestore ``client_presence`` collection stores cross-instance client
    metadata so all Cloud Run instances see every connected device.
    """

    def __init__(self) -> None:
        # { user_id: { client_type: (WebSocket, connected_at, os_name) } }
        self._connections: dict[str, dict[ClientType, tuple[WebSocket, datetime, str]]] = {}
        # Auxiliary sockets that also receive broadcasts (e.g. /ws/chat)
        # { user_id: { aux_key: WebSocket } }
        self._aux_sockets: dict[str, dict[str, WebSocket]] = {}
        # { user_id: { client_type: { "capabilities": [...], "local_tools": [...] } } }
        self._capabilities: dict[str, dict[ClientType, dict]] = {}
        # Mic floor lock: tracks which client_type currently holds the active voice mic per user.
        # Only one device can stream audio at a time to avoid Gemini Live collision.
        # { user_id: ClientType }
        self._mic_floor: dict[str, ClientType] = {}
        # Timestamp (monotonic) of the last audio frame from the current floor holder.
        # Used to expire stale locks when a holder goes silent without releasing.
        # { user_id: float }
        self._mic_last_audio: dict[str, float] = {}
        # Per-WebSocket asyncio.Lock — serialises concurrent sends so that
        # relay_task / _upstream / _downstream never interleave frames.
        # Keyed by id(websocket) so callers only need the WebSocket object.
        self._send_locks: dict[int, asyncio.Lock] = {}
        self._reaper_task: asyncio.Task | None = None
        self._db = None  # lazy Firestore client

    def _get_db(self):
        """Lazy Firestore client — only created when first needed."""
        if self._db is None:
            from google.cloud import firestore

            from app.config import settings

            self._db = firestore.Client(project=settings.GOOGLE_CLOUD_PROJECT or None)
        return self._db

    @staticmethod
    def _presence_doc_id(user_id: str, client_type: ClientType) -> str:
        return f"{user_id}_{client_type.value}"

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
        Also writes a Firestore presence doc for cross-instance visibility.
        """
        user_conns = self._connections.setdefault(user_id, {})
        old = user_conns.get(client_type)
        if old is not None:
            old_ws, _, _os = old
            self._send_locks.pop(id(old_ws), None)  # discard stale lock
            with contextlib.suppress(Exception):
                await old_ws.close(code=4000, reason="Replaced by new connection")
            logger.info(
                "replaced_connection",
                user_id=user_id,
                client_type=client_type,
            )
        now = datetime.now(UTC)
        user_conns[client_type] = (websocket, now, os_name)
        self._send_locks[id(websocket)] = asyncio.Lock()
        logger.info("client_connected", user_id=user_id, client_type=client_type)

        # Write Firestore presence (best-effort, non-blocking)
        _fire_and_forget(self._set_presence(user_id, client_type, os_name, now))

        await self._broadcast_client_status(
            user_id, event="connected", changed_client_type=client_type
        )

    async def disconnect(
        self,
        user_id: str,
        client_type: ClientType = ClientType.WEB,
    ) -> None:
        """Remove the connection for ``(user_id, client_type)``."""
        user_conns = self._connections.get(user_id)
        if user_conns is None:
            return
        entry = user_conns.pop(client_type, None)
        if entry is not None:
            self._send_locks.pop(id(entry[0]), None)  # clean up send lock
        if not user_conns:
            self._connections.pop(user_id, None)
        # Clean up capabilities for this client
        user_caps = self._capabilities.get(user_id)
        if user_caps is not None:
            user_caps.pop(client_type, None)
            if not user_caps:
                self._capabilities.pop(user_id, None)
        # Release mic floor if this client was holding it
        self.release_mic_floor(user_id, client_type)
        logger.info("client_disconnected", user_id=user_id, client_type=client_type)

        # Remove Firestore presence (best-effort, non-blocking)
        _fire_and_forget(self._clear_presence(user_id, client_type))

        await self._broadcast_client_status(
            user_id, event="disconnected", changed_client_type=client_type
        )

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
        payload = json.dumps(
            {
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
            }
        )
        await self.send_to_user(user_id, payload)

    # ── Mic Floor Lock ────────────────────────────────────────────────

    def try_acquire_mic_floor(self, user_id: str, client_type: ClientType) -> bool:
        """Try to acquire the voice mic floor for *client_type*.

        Returns True if the floor was acquired (or already held by this client).
        Returns False if another client_type is currently holding the floor.

        Stale-lock eviction: if the current holder has not sent audio for
        ``_STALE_MIC_TIMEOUT_S`` seconds the lock is automatically expired
        before the new acquire is evaluated.
        """
        current = self._mic_floor.get(user_id)
        if current is not None and current != client_type:
            # Auto-expire if the holder has gone silent
            last = self._mic_last_audio.get(user_id, 0.0)
            if time.monotonic() - last > _STALE_MIC_TIMEOUT_S:
                logger.info(
                    "mic_floor_stale_expired",
                    user_id=user_id,
                    evicted=current,
                    new_holder=client_type,
                )
                current = None  # fall through to acquire
        if current is None or current == client_type:
            self._mic_floor[user_id] = client_type
            self._mic_last_audio[user_id] = time.monotonic()
            logger.debug("mic_floor_acquired", user_id=user_id, client_type=client_type)
            return True
        return False

    def touch_mic_floor(self, user_id: str, client_type: ClientType) -> None:
        """Update the last-audio timestamp for *client_type* if it holds the floor.

        Call this on every audio frame to keep the stale-lock watchdog alive.
        """
        if self._mic_floor.get(user_id) == client_type:
            self._mic_last_audio[user_id] = time.monotonic()

    def release_mic_floor(self, user_id: str, client_type: ClientType) -> bool:
        """Release the floor if *client_type* currently holds it.

        Returns True if the floor was released, False if it wasn't held.
        """
        if self._mic_floor.get(user_id) == client_type:
            del self._mic_floor[user_id]
            self._mic_last_audio.pop(user_id, None)
            logger.debug("mic_floor_released", user_id=user_id, client_type=client_type)
            return True
        return False

    def get_mic_floor_holder(self, user_id: str) -> ClientType | None:
        """Return which client_type currently holds the mic floor, or None."""
        return self._mic_floor.get(user_id)

    # ── Messaging ─────────────────────────────────────────────────────

    def get_send_lock(self, websocket: WebSocket) -> asyncio.Lock | None:
        """Return the serialisation lock for *websocket*, or None if not tracked."""
        return self._send_locks.get(id(websocket))

    async def _safe_send(self, ws: WebSocket, message: str) -> None:
        """Send *message* to *ws* while holding its per-socket send lock.

        Serialises concurrent send callers (relay_task, _upstream, _downstream)
        so that WebSocket frames are never interleaved or silently dropped
        due to concurrent asyncio send calls on the same socket.
        """
        lock = self._send_locks.get(id(ws))
        if lock is None:
            # Fallback: send without lock (e.g. aux sockets)
            await ws.send_text(message)
            return
        async with lock:
            await ws.send_text(message)

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
                await self._safe_send(ws, message)
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
            await self._safe_send(ws, message)
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
                t for t in entry["local_tools"] if t.get("name") not in set(removed_tools)
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
        """Return ``ClientInfo`` for every active connection of *user_id*.

        Merges local in-memory connections with Firestore ``client_presence``
        so clients on **all** Cloud Run instances are visible.  Local data
        is always included first (it's authoritative for this instance and
        avoids race conditions with async Firestore presence writes).
        """
        # Start with local connections (always up-to-date for this instance)
        seen_types: set[str] = set()
        clients: list[ClientInfo] = []
        for info in self._get_local_clients(user_id):
            seen_types.add(str(info.client_type))
            clients.append(info)

        # Merge Firestore entries for clients on OTHER instances
        try:
            db = self._get_db()
            docs = db.collection(_PRESENCE_COLLECTION).where("user_id", "==", user_id).stream()
            cutoff = datetime.now(UTC).timestamp() - _PRESENCE_STALE_SECONDS
            for doc in docs:
                d = doc.to_dict()
                hb = d.get("last_heartbeat")
                if hb is not None and hb.timestamp() < cutoff:
                    continue
                ct_val = d.get("client_type", "web")
                if ct_val in seen_types:
                    continue  # already have this client_type from local
                try:
                    ct = ClientType(ct_val)
                except ValueError:
                    ct = ClientType.WEB
                connected_at = d.get("connected_at")
                if connected_at and hasattr(connected_at, "replace"):
                    connected_at = (
                        connected_at.replace(tzinfo=UTC)
                        if connected_at.tzinfo is None
                        else connected_at
                    )
                clients.append(
                    ClientInfo(
                        user_id=user_id,
                        client_type=ct,
                        client_id=str(ct),
                        connected_at=connected_at or datetime.now(UTC),
                        last_ping=datetime.now(UTC),
                        os_name=d.get("os_name", "Unknown"),
                    )
                )
                seen_types.add(ct_val)
        except Exception:
            logger.warning("firestore_presence_read_failed", user_id=user_id, exc_info=True)

        return clients

    def _get_local_clients(self, user_id: str) -> list[ClientInfo]:
        """Fallback: return clients from local in-memory state only."""
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
        """Return list of OTHER client types that are online (excluding current).

        Uses Firestore for cross-instance visibility.
        """
        all_clients = self.get_connected_clients(user_id)
        return [c.client_type for c in all_clients if c.client_type != current_client_type]

    @property
    def total_connections(self) -> int:
        return sum(len(v) for v in self._connections.values())

    # ── Heartbeat / Reaper ────────────────────────────────────────────

    def start_reaper(self) -> None:
        """Launch the background heartbeat reaper (call once at startup)."""
        if self._reaper_task is None or self._reaper_task.done():
            self._reaper_task = asyncio.create_task(
                self._reap_loop(),
                name="ws-heartbeat-reaper",
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
            # Reap stale Firestore presence docs from this instance
            await self._reap_stale_presence()
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
            logger.info(
                "heartbeat_reap_complete", reaped=total_reaped, remaining=self.total_connections
            )

        # Refresh Firestore heartbeat for all live connections on this instance
        await self._refresh_presence_heartbeats()

    # ── Firestore Presence Helpers ────────────────────────────────────

    async def _set_presence(
        self, user_id: str, client_type: ClientType, os_name: str, connected_at: datetime
    ) -> None:
        """Write a presence doc to Firestore (best-effort)."""
        try:
            db = self._get_db()
            doc_id = self._presence_doc_id(user_id, client_type)
            db.collection(_PRESENCE_COLLECTION).document(doc_id).set(
                {
                    "user_id": user_id,
                    "client_type": client_type.value,
                    "os_name": os_name,
                    "connected_at": connected_at,
                    "last_heartbeat": datetime.now(UTC),
                    "instance_id": _INSTANCE_ID,
                }
            )
            logger.debug("presence_set", user_id=user_id, client_type=client_type.value)
        except Exception:
            logger.warning("presence_set_failed", user_id=user_id, exc_info=True)

    async def _clear_presence(self, user_id: str, client_type: ClientType) -> None:
        """Delete a presence doc from Firestore (best-effort)."""
        try:
            db = self._get_db()
            doc_id = self._presence_doc_id(user_id, client_type)
            db.collection(_PRESENCE_COLLECTION).document(doc_id).delete()
            logger.debug("presence_cleared", user_id=user_id, client_type=client_type.value)
        except Exception:
            logger.warning("presence_clear_failed", user_id=user_id, exc_info=True)

    async def _refresh_presence_heartbeats(self) -> None:
        """Update last_heartbeat for all local connections in Firestore."""
        try:
            db = self._get_db()
            now = datetime.now(UTC)
            batch = db.batch()
            count = 0
            for user_id, user_conns in self._connections.items():
                for ct in user_conns:
                    doc_id = self._presence_doc_id(user_id, ct)
                    ref = db.collection(_PRESENCE_COLLECTION).document(doc_id)
                    batch.update(ref, {"last_heartbeat": now})
                    count += 1
            if count:
                batch.commit()
        except Exception:
            logger.debug("presence_heartbeat_refresh_failed", exc_info=True)

    async def _reap_stale_presence(self) -> None:
        """Delete Firestore presence docs that haven't been refreshed recently."""
        try:
            db = self._get_db()
            cutoff = datetime.now(UTC).timestamp() - _PRESENCE_STALE_SECONDS
            from google.cloud.firestore_v1.base_query import FieldFilter

            # Query for stale docs belonging to THIS instance only
            docs = (
                db.collection(_PRESENCE_COLLECTION)
                .where(filter=FieldFilter("instance_id", "==", _INSTANCE_ID))
                .stream()
            )
            batch = db.batch()
            count = 0
            for doc in docs:
                d = doc.to_dict()
                hb = d.get("last_heartbeat")
                if hb is not None and hb.timestamp() < cutoff:
                    batch.delete(doc.reference)
                    count += 1
            if count:
                batch.commit()
                logger.info("stale_presence_reaped", count=count, instance=_INSTANCE_ID)
        except Exception:
            logger.debug("stale_presence_reap_failed", exc_info=True)


# ── Module singleton ──────────────────────────────────────────────────

_manager: ConnectionManager | None = None


def get_connection_manager() -> ConnectionManager:
    global _manager
    if _manager is None:
        _manager = ConnectionManager()
    return _manager
