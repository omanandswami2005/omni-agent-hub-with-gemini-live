"""WebSocket client for desktop-to-server communication.

Connects to the Omni backend via raw WebSocket, authenticates with a
Firebase token, and dispatches incoming cross-client actions to the
appropriate handler (screenshot, click, type, file ops, etc.).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable, Coroutine

import websockets
from websockets.asyncio.client import ClientConnection

logger = logging.getLogger(__name__)

# Reconnection backoff
_INITIAL_BACKOFF = 1.0
_MAX_BACKOFF = 30.0
_BACKOFF_FACTOR = 2.0


class DesktopWSClient:
    """Raw WebSocket client for Omni server connection."""

    def __init__(self, server_url: str, token: str) -> None:
        self.server_url = server_url
        self.token = token
        self.ws: ClientConnection | None = None
        self.connected: bool = False
        self._should_run: bool = False
        self._handlers: dict[str, Callable[..., Coroutine[Any, Any, Any]]] = {}

    # ── Public API ────────────────────────────────────────────────────

    def register_handler(
        self,
        action: str,
        handler: Callable[..., Coroutine[Any, Any, Any]],
    ) -> None:
        """Register an async handler for a cross-client action name."""
        self._handlers[action] = handler

    async def connect(self) -> None:
        """Establish WebSocket connection and send auth message."""
        self.ws = await websockets.connect(self.server_url, max_size=10 * 1024 * 1024)
        self.connected = True
        logger.info("Connected to %s", self.server_url)

        # Send auth handshake as first message (matching backend protocol)
        await self.send_json({
            "type": "auth",
            "token": self.token,
            "client_type": "desktop",
        })

    async def run(self) -> None:
        """Connect and listen with auto-reconnect on failure."""
        self._should_run = True
        backoff = _INITIAL_BACKOFF

        while self._should_run:
            try:
                await self.connect()
                backoff = _INITIAL_BACKOFF  # reset on success
                await self._listen()
            except (
                websockets.ConnectionClosed,
                OSError,
                ConnectionRefusedError,
            ) as exc:
                self.connected = False
                self.ws = None
                if not self._should_run:
                    break
                logger.warning(
                    "Connection lost (%s). Reconnecting in %.1fs…",
                    exc,
                    backoff,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * _BACKOFF_FACTOR, _MAX_BACKOFF)

    async def send_audio(self, pcm_data: bytes) -> None:
        """Send raw PCM16 audio as a binary frame."""
        if self.ws and self.connected:
            await self.ws.send(pcm_data)

    async def send_json(self, message: dict) -> None:
        """Send a JSON control message as a text frame."""
        if self.ws and self.connected:
            await self.ws.send(json.dumps(message))

    async def send_response(self, action: str, result: Any) -> None:
        """Send an action response back to the server."""
        await self.send_json({
            "type": "action_response",
            "action": action,
            "result": result,
        })

    async def disconnect(self) -> None:
        """Gracefully close connection and stop reconnection."""
        self._should_run = False
        self.connected = False
        if self.ws:
            await self.ws.close()
            self.ws = None
        logger.info("Disconnected from server")

    # ── Internal ────────────────────────────────────────────────────

    async def _listen(self) -> None:
        """Listen for incoming messages and dispatch to handlers."""
        if not self.ws:
            return
        async for raw in self.ws:
            if isinstance(raw, bytes):
                # Binary frame — audio playback data; ignore for now
                continue
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("Received non-JSON text frame")
                continue
            await self._dispatch(msg)

    async def _dispatch(self, msg: dict) -> None:
        """Route an incoming message to the appropriate handler."""
        msg_type = msg.get("type", "")

        # Handle cross_client messages (matching backend protocol)
        if msg_type == "cross_client":
            action = msg.get("action", "")
            payload = msg.get("data", {})
            handler = self._handlers.get(action)
            if handler:
                try:
                    result = await handler(**payload) if payload else await handler()
                    await self.send_response(action, result)
                except Exception as exc:
                    logger.error("Handler error for %s: %s", action, exc)
                    await self.send_response(action, {"error": str(exc)})
            else:
                logger.warning("No handler for action: %s", action)
                await self.send_response(action, {"error": f"Unknown action: {action}"})

        elif msg_type == "ping":
            await self.send_json({"type": "pong"})

        else:
            logger.debug("Unhandled message type: %s", msg_type)
