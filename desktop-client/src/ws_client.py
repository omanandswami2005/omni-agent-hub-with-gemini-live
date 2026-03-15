"""WebSocket client for Omni Desktop Agent.

Connects to the Omni backend, handles authentication, and routes incoming
cross-client action requests to registered plugin handlers. Also handles
audio streaming and basic text chat via GUI integration.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable, Coroutine

import websockets

from src.audio import AudioStreamer

logger = logging.getLogger(__name__)

_INITIAL_BACKOFF = 1.0
_MAX_BACKOFF = 30.0
_BACKOFF_FACTOR = 1.5


class DesktopWSClient:
    """Async WebSocket client for the desktop agent."""

    def __init__(self, server_url: str, token: str) -> None:
        self.server_url = server_url
        self.token = token
        self.ws: websockets.WebSocketClientProtocol | None = None
        self.connected = False
        self._should_run = False
        self._run_task = None
        self._refresh_task: asyncio.Task | None = None

        # Firebase token refresh (set via set_auth_refresh)
        self._firebase_api_key: str | None = None
        self._refresh_token: str | None = None

        self.gui = None
        self.audio_streamer = AudioStreamer(self)

        # Handlers map: action_name -> async func
        self._handlers: dict[str, Callable[..., Coroutine[Any, Any, Any]]] = {}
        # T3 definitions to send during auth
        self._capabilities: list[str] = []
        self._local_tools: list[dict] = []
        # Cancellation tracking
        self._active_tasks: dict[str, asyncio.Task] = {}

    def set_auth_refresh(self, api_key: str, refresh_token: str) -> None:
        """Enable automatic token refresh using Firebase refresh token."""
        self._firebase_api_key = api_key
        self._refresh_token = refresh_token

    def set_gui(self, gui):
        """Inject the GUI instance to update UI and receive signals."""
        self.gui = gui

        # Connect GUI signals
        if hasattr(self.gui, "send_text_signal"):
            self.gui.send_text_signal.connect(self._on_gui_send_text)
        if hasattr(self.gui, "toggle_mic_signal"):
            self.gui.toggle_mic_signal.connect(self._on_gui_toggle_mic)
        if hasattr(self.gui, "send_screen_signal"):
            self.gui.send_screen_signal.connect(self._on_gui_send_screen)
        if hasattr(self.gui, "connect_signal"):
            self.gui.connect_signal.connect(self._on_gui_connect_toggled)
        if hasattr(self.gui, "interrupt_signal"):
            self.gui.interrupt_signal.connect(self._on_gui_interrupt)

    def _on_gui_send_text(self, text: str):
        """Handle text sent from GUI."""
        if self.connected:
            asyncio.create_task(self.send_json({"type": "text", "content": text}))

    def _on_gui_toggle_mic(self, checked: bool):
        """Handle mic toggle from GUI."""
        if checked:
            self.audio_streamer.start_recording()
        else:
            self.audio_streamer.stop_recording()

    def _on_gui_send_screen(self, b64_img: str):
        """Handle periodic screen sharing from GUI."""
        if self.connected:
            msg = {
                "type": "text",
                "content": "[Screen Frame Update]",
                "attachments": [
                    {
                        "mime_type": "image/jpeg",
                        "data": b64_img
                    }
                ]
            }
            asyncio.create_task(self.send_json(msg))

    def _on_gui_connect_toggled(self, connect: bool):
        """Handle connection toggle from GUI."""
        if connect and not self.connected:
            self.start()
        elif not connect and self.connected:
            asyncio.create_task(self.disconnect())

    def _on_gui_interrupt(self):
        """Handle interrupt signal from GUI to stop ongoing agent tasks/audio."""
        if self.connected:
            # Tell server to interrupt ongoing text/audio generation
            asyncio.create_task(self.send_json({"type": "client_message", "action": "interrupt"}))
            # Also cancel local ongoing tasks locally
            asyncio.create_task(self.cancel_all())

    # ── Public API ────────────────────────────────────────────────────

    def register_handler(
        self,
        action: str,
        handler: Callable[..., Coroutine[Any, Any, Any]],
    ) -> None:
        """Register an async handler for a cross-client action name."""
        self._handlers[action] = handler

    def set_t3_tools(self, capabilities: list[str], local_tools: list[dict]) -> None:
        """Set T3 capabilities and local tool definitions for auth."""
        self._capabilities = capabilities
        self._local_tools = local_tools

    async def connect(self) -> None:
        """Establish WebSocket connection and send auth message."""
        import platform

        # Refresh token if we have a refresh mechanism and the token may be stale
        await self._maybe_refresh_token()

        self.ws = await websockets.connect(self.server_url, max_size=10 * 1024 * 1024)
        self.connected = True
        logger.info("Connected to %s", self.server_url)

        if self.gui:
            self.gui.set_status(True)

        # Start periodic token refresh (every 50 minutes)
        self._start_token_refresh_loop()

        # Send auth handshake with T3 capabilities and local tools
        auth_msg: dict[str, Any] = {
            "type": "auth",
            "token": self.token,
            "client_type": "desktop",
            "user_agent": f"OmniDesktop/1.0 ({platform.system()} {platform.release()})",
        }
        if self._capabilities:
            auth_msg["capabilities"] = self._capabilities
        if self._local_tools:
            auth_msg["local_tools"] = self._local_tools

        await self.send_json(auth_msg)

    def start(self):
        """Starts the run loop via asyncio task if not running."""
        if not self._should_run:
             self._should_run = True
             self._run_task = asyncio.create_task(self.run())

    async def run(self) -> None:
        """Connect and listen with auto-reconnect on failure."""
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

                if self.gui:
                    self.gui.set_status(False)

                # Cancel all in-flight tasks on disconnect
                await self.cancel_all()
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

        if self._refresh_task and not self._refresh_task.done():
            self._refresh_task.cancel()
            self._refresh_task = None

        if self.gui:
            self.gui.set_status(False)

        self.audio_streamer.stop_recording()
        self.audio_streamer.stop_playback()

        await self.cancel_all()
        if self.ws:
            await self.ws.close()
            self.ws = None
        logger.info("Disconnected from server")

        if self._run_task and not self._run_task.done():
            self._run_task.cancel()

    # ── Token refresh ───────────────────────────────────────────────

    async def _maybe_refresh_token(self) -> None:
        """Refresh the Firebase ID token if a refresh token is available."""
        if not self._firebase_api_key or not self._refresh_token:
            return
        try:
            from src.firebase_auth import FirebaseAuth
            fa = FirebaseAuth(self._firebase_api_key)
            result = fa.refresh_token(self._refresh_token)
            self.token = result.id_token
            self._refresh_token = result.refresh_token
            logger.info("Firebase token refreshed")
        except Exception as exc:
            logger.warning("Token refresh failed: %s", exc)

    def _start_token_refresh_loop(self) -> None:
        """Start a background task that refreshes the token every 50 minutes."""
        if not self._firebase_api_key or not self._refresh_token:
            return
        if self._refresh_task and not self._refresh_task.done():
            return
        self._refresh_task = asyncio.create_task(self._token_refresh_loop())

    async def _token_refresh_loop(self) -> None:
        """Periodically refresh the Firebase ID token (every 50 min)."""
        while self._should_run:
            await asyncio.sleep(50 * 60)  # 50 minutes
            await self._maybe_refresh_token()

    # ── Cancellation ──────────────────────────────────────────────────

    async def cancel_call(self, call_id: str) -> None:
        """Cancel a single in-flight tool invocation by call_id."""
        task = self._active_tasks.pop(call_id, None)
        if task and not task.done():
            task.cancel()
            logger.info("Cancelled call_id=%s", call_id)
            await self.send_json({
                "type": "tool_result",
                "call_id": call_id,
                "result": {},
                "error": "Cancelled by user",
            })

    async def cancel_all(self) -> None:
        """Cancel all in-flight tool invocations."""
        if not self._active_tasks:
            return
        call_ids = list(self._active_tasks.keys())
        for cid in call_ids:
            task = self._active_tasks.pop(cid, None)
            if task and not task.done():
                task.cancel()
        logger.info("Cancelled %d in-flight call(s)", len(call_ids))

    # ── Internal ────────────────────────────────────────────────────

    async def _listen(self) -> None:
        """Listen for incoming messages and dispatch to handlers."""
        if not self.ws:
            return
        async for raw in self.ws:
            if isinstance(raw, bytes):
                # Binary frame — audio playback data
                await self.audio_streamer.queue_audio(raw)
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

        # T3 reverse-RPC: server asking us to execute a tool
        if msg_type == "tool_invocation":
            call_id = msg.get("call_id", "")
            tool_name = msg.get("tool", "")
            args = msg.get("args", {})
            # Launch as a tracked Task so it can be cancelled mid-flight
            task = asyncio.create_task(
                self._run_tool(call_id, tool_name, args),
            )
            self._active_tasks[call_id] = task
            task.add_done_callback(lambda _t, cid=call_id: self._active_tasks.pop(cid, None))

        # Cancel a single in-flight tool invocation
        elif msg_type == "cancel":
            call_id = msg.get("call_id", "")
            if call_id:
                await self.cancel_call(call_id)

        # Cancel all in-flight tool invocations
        elif msg_type == "cancel_all":
            await self.cancel_all()

        # Status message — mirror dashboard interruption flow
        elif msg_type == "status":
            state = msg.get("state", "")
            detail = msg.get("detail", "")
            if state == "listening" and detail == "Interrupted by user":
                logger.info("Interrupted by user — cancelling all in-flight calls")
                await self.cancel_all()

        # Handle cross_client messages (matching backend protocol)
        elif msg_type == "cross_client":
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

        elif msg_type == "client_status_update":
            clients = msg.get("clients", [])
            logger.info("Client status update: %d clients online", len(clients))

        elif msg_type == "session_suggestion":
            session_id = msg.get("session_id", "")
            available = msg.get("available_clients", [])
            message = msg.get("message", "")
            logger.info(
                "Session suggestion: %s (active on: %s) — session: %s",
                message,
                ", ".join(available),
                session_id,
            )
            # Invoke registered callback if the host app set one
            handler = self._handlers.get("session_suggestion")
            if handler:
                asyncio.create_task(handler(
                    session_id=session_id,
                    available_clients=available,
                    message=message,
                ))

        elif msg_type == "auth_response":
            if msg.get("status") == "ok":
                logger.info("Authenticated as %s", msg.get("user_id"))
            else:
                logger.error("Auth failed: %s", msg.get("error"))

        # Simple text display in GUI
        elif msg_type == "transcript" or msg_type == "agent_response":
            if self.gui:
                text = msg.get("text", "")
                if text:
                    self.gui.append_chat(f"Omni: {text}")

        else:
            logger.debug("Unhandled message type: %s", msg_type)

    async def _run_tool(self, call_id: str, tool_name: str, args: dict) -> None:
        """Execute a tool handler and send the result (cancellable)."""
        handler = self._handlers.get(tool_name)
        if not handler:
            logger.warning("No handler for T3 tool: %s", tool_name)
            await self.send_json({
                "type": "tool_result",
                "call_id": call_id,
                "result": {},
                "error": f"Unknown tool: {tool_name}",
            })
            return
        try:
            result = await handler(**args) if args else await handler()
            await self.send_json({
                "type": "tool_result",
                "call_id": call_id,
                "result": result,
            })
        except asyncio.CancelledError:
            logger.info("Tool %s (call_id=%s) was cancelled", tool_name, call_id)
            # Result already sent in cancel_call if individually cancelled
        except Exception as exc:
            logger.error("T3 tool error for %s: %s", tool_name, exc)
            await self.send_json({
                "type": "tool_result",
                "call_id": call_id,
                "result": {},
                "error": str(exc),
            })
