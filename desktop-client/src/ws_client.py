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

        self.gui = None
        self.audio_streamer = AudioStreamer(self)

        # Handlers map: action_name -> async func
        self._handlers: dict[str, Callable[..., Coroutine[Any, Any, Any]]] = {}
        # T3 definitions to send during auth
        self._capabilities: list[str] = []
        self._local_tools: list[dict] = []
        # Cancellation tracking
        self._active_tasks: dict[str, asyncio.Task] = {}

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
            # Send it as a tool result or specialized message type.
            # In a full multimodal setup we could send a specialized message,
            # here we'll send a text message with the image attached, or
            # a specific 'screen_frame' cross client event.
            # Using 'user_message'/'text' format to stream image to agent.
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
        self.ws = await websockets.connect(self.server_url, max_size=10 * 1024 * 1024)
        self.connected = True
        logger.info("Connected to %s", self.server_url)

        if self.gui:
            self.gui.set_status(True)

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

        if self.gui:
            self.gui.set_status(False)

        self.audio_streamer.stop_recording()
        self.audio_streamer.stop_playback()

        await self.cancel_all()
        if self.ws:
            await self.ws.close()
            self.ws = None
        logger.info("Disconnected from server")

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
