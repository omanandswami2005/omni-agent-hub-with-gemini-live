#!/usr/bin/env python3
"""Omni Hub Smart Glasses Client — ESP32-CAM + Mic → Backend → Speaker.

Connects to the Omni Hub backend via /ws/live WebSocket (not directly to
Gemini), following the same protocol as dashboard and desktop clients.

Architecture
------------
┌────────────────────────────────┐
│   ESP32-CAM  (+INMP441 mic)   │
│   /snapshot (JPEG)             │
│   /audio    (PCM stream)       │
└──────────┬─────────────────────┘
           │ WiFi HTTP
┌──────────▼─────────────────────┐
│   This Python Client           │
│   - Camera frames → backend    │
│   - Mic audio → backend        │
│   - Speaker ← backend audio    │
│   - T3 tool handling           │
└──────────┬─────────────────────┘
           │ WebSocket /ws/live
┌──────────▼─────────────────────┐
│   Omni Hub Backend             │
│   Agent + Tools + Plugins      │
└────────────────────────────────┘

Usage
-----
    # With host mic (default — no ESP32 mic needed):
    python glasses_client.py --token <firebase-jwt>

    # With ESP32 mic (INMP441 on the glasses):
    python glasses_client.py --token <jwt> --mic esp32

    # Custom ESP32 IP + backend server:
    python glasses_client.py --token <jwt> --esp32-ip 192.168.1.100 --server ws://myserver:8000

    # Camera-only mode (narrate what you see, no mic input):
    python glasses_client.py --token <jwt> --no-mic
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import sys

try:
    import aiohttp
except ImportError:
    print("Install aiohttp: pip install aiohttp")
    sys.exit(1)

try:
    import pyaudio
except ImportError:
    print("Install pyaudio: pip install pyaudio")
    sys.exit(1)

try:
    import websockets
except ImportError:
    print("Install websockets: pip install websockets")
    sys.exit(1)


# ─── Audio constants (match backend expectations) ────────────────────
MIC_RATE = 16000       # Backend expects 16kHz PCM input
MIC_CHANNELS = 1
MIC_FORMAT = pyaudio.paInt16
MIC_CHUNK = 1024       # ~64ms per chunk at 16kHz

SPK_RATE = 24000       # Backend sends 24kHz PCM output
SPK_CHANNELS = 1
SPK_FORMAT = pyaudio.paInt16
SPK_CHUNK = 4096

# ─── Defaults ────────────────────────────────────────────────────────
DEFAULT_SERVER = "ws://localhost:8000"
DEFAULT_ESP32_IP = "192.168.1.100"
DEFAULT_SNAPSHOT_INTERVAL = 5.0    # seconds between camera frames

# Capabilities advertised to the backend (what these glasses can do)
GLASSES_CAPABILITIES = [
    "camera_capture",
    "microphone",
    "speaker",
    "visual_narration",
]

# T3 local tools — agent can ask glasses to do things
GLASSES_LOCAL_TOOLS = [
    {
        "name": "capture_photo",
        "description": "Take a photo with the smart glasses camera",
        "parameters": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "Optional description of what to capture",
                }
            },
            "required": [],
        },
    },
    {
        "name": "set_frame_rate",
        "description": "Change how often the glasses send camera frames (seconds between frames)",
        "parameters": {
            "type": "object",
            "properties": {
                "interval": {
                    "type": "number",
                    "description": "Seconds between frames (1-30)",
                }
            },
            "required": ["interval"],
        },
    },
]


class GlassesClient:
    """Smart glasses WebSocket client for Omni Hub backend."""

    def __init__(
        self,
        server: str,
        token: str,
        esp32_ip: str,
        snapshot_interval: float = DEFAULT_SNAPSHOT_INTERVAL,
        mic_source: str = "host",      # "host" | "esp32" | "none"
    ):
        self.server = server
        self.token = token
        self.esp32_ip = esp32_ip
        self.snapshot_url = f"http://{esp32_ip}/snapshot"
        self.esp32_audio_url = f"http://{esp32_ip}/audio"
        self.snapshot_interval = snapshot_interval
        self.mic_source = mic_source

        self._ws = None
        self._pya = pyaudio.PyAudio()
        self._spk_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._running = False
        self._active_tool_calls: dict[str, asyncio.Task] = {}

        # Mutable — agent can change via T3 set_frame_rate tool
        self._current_interval = snapshot_interval

    # ── Camera ────────────────────────────────────────────────────

    async def _fetch_frame(self, session: aiohttp.ClientSession) -> bytes | None:
        """Fetch a JPEG snapshot from the ESP32-CAM."""
        try:
            async with session.get(
                self.snapshot_url,
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status == 200:
                    return await resp.read()
        except Exception as e:
            print(f"[CAM] Error: {e}")
        return None

    async def _send_camera_frames(
        self, ws, http: aiohttp.ClientSession
    ) -> None:
        """Periodically capture and send camera frames to backend."""
        frame_count = 0
        while self._running:
            raw = await self._fetch_frame(http)
            if raw:
                frame_count += 1
                # Send as base64 image (per client developer protocol)
                img_msg = {
                    "type": "image",
                    "data_base64": base64.b64encode(raw).decode("ascii"),
                    "mime_type": "image/jpeg",
                }
                await ws.send(json.dumps(img_msg))
                print(f"[CAM] Frame {frame_count} sent ({len(raw) // 1024}KB)")

            await asyncio.sleep(self._current_interval)

    # ── Microphone (host) ─────────────────────────────────────────

    async def _stream_host_mic(self, ws) -> None:
        """Stream audio from host machine mic → backend as binary PCM."""
        stream = await asyncio.to_thread(
            self._pya.open,
            format=MIC_FORMAT,
            channels=MIC_CHANNELS,
            rate=MIC_RATE,
            input=True,
            frames_per_buffer=MIC_CHUNK,
        )
        print("[MIC] Host mic active (16kHz PCM)")
        try:
            while self._running:
                data = await asyncio.to_thread(
                    stream.read, MIC_CHUNK, exception_on_overflow=False
                )
                # Binary frame — backend interprets as PCM audio
                await ws.send(data)
        finally:
            stream.stop_stream()
            stream.close()

    # ── Microphone (ESP32 INMP441) ────────────────────────────────

    async def _stream_esp32_mic(self, ws, http: aiohttp.ClientSession) -> None:
        """Stream audio from ESP32 I2S mic → backend.

        The ESP32 firmware serves raw PCM at /audio as a chunked HTTP
        stream (16kHz, 16-bit, mono, little-endian).
        """
        print(f"[MIC] Connecting to ESP32 mic at {self.esp32_audio_url}")
        retry_delay = 2
        while self._running:
            try:
                async with http.get(
                    self.esp32_audio_url,
                    timeout=aiohttp.ClientTimeout(total=None, sock_read=5),
                ) as resp:
                    if resp.status != 200:
                        print(f"[MIC] ESP32 audio endpoint returned {resp.status}")
                        await asyncio.sleep(retry_delay)
                        continue
                    print("[MIC] ESP32 mic streaming (16kHz PCM)")
                    retry_delay = 2
                    async for chunk in resp.content.iter_chunked(MIC_CHUNK * 2):
                        if not self._running:
                            break
                        # Forward raw PCM to backend as binary frame
                        await ws.send(chunk)
            except Exception as e:
                print(f"[MIC] ESP32 mic error: {e}, retrying in {retry_delay}s")
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 15)

    # ── Speaker ───────────────────────────────────────────────────

    async def _play_speaker(self) -> None:
        """Play audio data from the speaker queue."""
        stream = await asyncio.to_thread(
            self._pya.open,
            format=SPK_FORMAT,
            channels=SPK_CHANNELS,
            rate=SPK_RATE,
            output=True,
            frames_per_buffer=SPK_CHUNK,
        )
        print("[SPK] Speaker ready (24kHz PCM)")
        try:
            while self._running:
                data = await self._spk_queue.get()
                await asyncio.to_thread(stream.write, data)
        finally:
            stream.stop_stream()
            stream.close()

    # ── T3 Tool Execution ─────────────────────────────────────────

    async def _handle_tool_invocation(
        self, ws, call_id: str, tool: str, args: dict,
        http: aiohttp.ClientSession,
    ) -> None:
        """Execute a T3 tool invocation from the agent."""
        result: dict = {}
        try:
            if tool == "capture_photo":
                frame = await self._fetch_frame(http)
                if frame:
                    result = {
                        "status": "ok",
                        "image_base64": base64.b64encode(frame).decode("ascii"),
                        "size_kb": len(frame) // 1024,
                    }
                else:
                    result = {"status": "error", "message": "Camera unreachable"}

            elif tool == "set_frame_rate":
                interval = args.get("interval", self.snapshot_interval)
                interval = max(1.0, min(30.0, float(interval)))
                self._current_interval = interval
                result = {"status": "ok", "interval": interval}
                print(f"[T3] Frame interval set to {interval}s")

            else:
                result = {"status": "error", "message": f"Unknown tool: {tool}"}
        except Exception as e:
            result = {"status": "error", "message": str(e)}

        # Send result back to backend
        response = {
            "type": "tool_result",
            "call_id": call_id,
            "result": result,
        }
        await ws.send(json.dumps(response))
        print(f"[T3] {tool} → {result.get('status', '?')}")

    # ── Message Receiver ──────────────────────────────────────────

    async def _receive_messages(
        self, ws, http: aiohttp.ClientSession
    ) -> None:
        """Receive and handle messages from the backend."""
        try:
            async for raw_msg in ws:
                # Binary frame → audio data → speaker
                if isinstance(raw_msg, bytes):
                    await self._spk_queue.put(raw_msg)
                    continue

                # JSON text frame
                try:
                    msg = json.loads(raw_msg)
                except json.JSONDecodeError:
                    continue

                msg_type = msg.get("type", "")

                if msg_type == "response":
                    text = msg.get("data", "")
                    if text:
                        print(f"[AGENT] {text}")

                elif msg_type == "transcription":
                    direction = msg.get("direction", "")
                    text = msg.get("text", "")
                    if text.strip():
                        label = "YOU" if direction == "input" else "AGENT"
                        print(f"[{label}] {text}")

                elif msg_type == "tool_call":
                    tool = msg.get("tool_name", "?")
                    status = msg.get("status", "")
                    if status == "started":
                        print(f"[TOOL] {tool} started...")

                elif msg_type == "tool_response":
                    tool = msg.get("tool_name", "?")
                    result = msg.get("result", "")
                    # Truncate long results for display
                    display = result[:150] + "..." if len(result) > 150 else result
                    print(f"[TOOL] {tool} → {display}")

                elif msg_type == "image_response":
                    desc = msg.get("description", "")
                    print(f"[IMAGE] {desc}")

                elif msg_type == "tool_invocation":
                    # T3 reverse-RPC: agent asking US to run a tool
                    call_id = msg.get("call_id", "")
                    tool = msg.get("tool", "")
                    args = msg.get("args", {})
                    print(f"[T3] Invoking {tool}({json.dumps(args)})")
                    # Run in background so we don't block the receiver
                    task = asyncio.create_task(
                        self._handle_tool_invocation(ws, call_id, tool, args, http)
                    )
                    self._active_tool_calls[call_id] = task
                    task.add_done_callback(
                        lambda t, cid=call_id: self._active_tool_calls.pop(cid, None)
                    )

                elif msg_type == "status":
                    state = msg.get("state", "")
                    detail = msg.get("detail", "")
                    if state == "processing":
                        print("[...thinking...]")
                    elif state == "listening" and "interrupt" in detail.lower():
                        print("[INTERRUPTED]")

                elif msg_type == "error":
                    code = msg.get("code", "")
                    desc = msg.get("description", "")
                    print(f"[ERROR] {code}: {desc}")

                elif msg_type == "agent_transfer":
                    to_agent = msg.get("to_agent", "")
                    print(f"[TRANSFER] → {to_agent}")

                elif msg_type == "session_suggestion":
                    clients = msg.get("available_clients", [])
                    print(f"[SESSION] Also online: {', '.join(clients)}")

                elif msg_type == "cross_client":
                    action = msg.get("action", "")
                    print(f"[CROSS] Action: {action}")

                elif msg_type in ("ping", "connected", "client_status_update", "auth_response"):
                    pass  # Already handled or silent

        except websockets.ConnectionClosed:
            print("[WS] Connection closed")
        except Exception as e:
            print(f"[WS] Receive error: {e}")

    # ── Main Connection Loop ──────────────────────────────────────

    async def run(self) -> None:
        """Main entry point — connect, authenticate, stream."""
        print("=" * 50)
        print("  Omni Hub Smart Glasses Client")
        print(f"  Backend: {self.server}")
        print(f"  ESP32:   {self.esp32_ip}")
        print(f"  Mic:     {self.mic_source}")
        print("=" * 50 + "\n")

        self._running = True
        reconnect_delay = 3

        async with aiohttp.ClientSession() as http:
            # Verify ESP32 camera connectivity
            frame = await self._fetch_frame(http)
            if not frame:
                print("[CAM] Warning: ESP32 camera unreachable — will keep retrying")
            else:
                print(f"[CAM] Camera OK ({len(frame) // 1024}KB)")

            while self._running:
                try:
                    await self._connect_session(http)
                    reconnect_delay = 3  # Reset on successful session
                except Exception as e:
                    print(f"\n[ERROR] {type(e).__name__}: {e}")

                if self._running:
                    print(f"[WS] Reconnecting in {reconnect_delay}s...")
                    await asyncio.sleep(reconnect_delay)
                    reconnect_delay = min(reconnect_delay * 2, 30)

    async def _connect_session(self, http: aiohttp.ClientSession) -> None:
        """Single WebSocket session — authenticate and stream."""
        uri = f"{self.server}/ws/live"
        print(f"\n[WS] Connecting to {uri}")

        async with websockets.connect(
            uri,
            max_size=10 * 1024 * 1024,  # 10MB for image frames
            ping_interval=20,
            ping_timeout=10,
        ) as ws:
            # Phase 1 — Auth handshake
            auth_msg = {
                "type": "auth",
                "token": self.token,
                "client_type": "glasses",
                "capabilities": GLASSES_CAPABILITIES,
                "local_tools": GLASSES_LOCAL_TOOLS,
            }
            await ws.send(json.dumps(auth_msg))

            # Wait for auth response
            raw = await asyncio.wait_for(ws.recv(), timeout=10)
            resp = json.loads(raw)
            if resp.get("type") == "auth_response":
                if resp.get("status") != "ok":
                    print(f"[AUTH] Failed: {resp.get('error', 'unknown')}")
                    return
                user_id = resp.get("user_id", "?")
                tools = resp.get("available_tools", [])
                others = resp.get("other_clients_online", [])
                print(f"[AUTH] Authenticated as {user_id}")
                if tools:
                    print(f"[AUTH] Tools: {', '.join(tools[:8])}{'...' if len(tools) > 8 else ''}")
                if others:
                    print(f"[AUTH] Other clients: {', '.join(others)}")

            print("\n" + "=" * 50)
            print("  Smart glasses active!")
            print("  Camera frames every {:.0f}s".format(self._current_interval))
            print("  Mic: {}".format(self.mic_source))
            print("  Press Ctrl+C to stop")
            print("=" * 50 + "\n")

            # Phase 2 — Parallel tasks
            tasks: list[asyncio.Task] = []

            # Always: receive messages + play speaker
            tasks.append(asyncio.create_task(
                self._receive_messages(ws, http), name="receiver"
            ))
            tasks.append(asyncio.create_task(
                self._play_speaker(), name="speaker"
            ))

            # Camera frames
            tasks.append(asyncio.create_task(
                self._send_camera_frames(ws, http), name="camera"
            ))

            # Mic (based on source)
            if self.mic_source == "host":
                tasks.append(asyncio.create_task(
                    self._stream_host_mic(ws), name="host_mic"
                ))
            elif self.mic_source == "esp32":
                tasks.append(asyncio.create_task(
                    self._stream_esp32_mic(ws, http), name="esp32_mic"
                ))
            # else: "none" — no mic

            # Wait until any task completes (disconnect/error)
            done, pending = await asyncio.wait(
                tasks, return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)

    def stop(self) -> None:
        """Gracefully stop the client."""
        self._running = False
        self._pya.terminate()


# ── CLI entry point ──────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Omni Hub Smart Glasses Client",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python glasses_client.py --token <jwt>
  python glasses_client.py --token-file token.txt --mic esp32
  python glasses_client.py --token <jwt> --esp32-ip 192.168.1.42 --interval 3
  python glasses_client.py --token <jwt> --no-mic
        """,
    )
    p.add_argument("--server", default=DEFAULT_SERVER, help="Backend WebSocket URL")
    p.add_argument("--token", help="Firebase ID token (JWT)")
    p.add_argument("--token-file", help="File containing the Firebase ID token")
    p.add_argument("--esp32-ip", default=DEFAULT_ESP32_IP, help="ESP32-CAM IP address")
    p.add_argument("--interval", type=float, default=DEFAULT_SNAPSHOT_INTERVAL,
                    help="Seconds between camera frames (default: 5)")
    p.add_argument("--mic", choices=["host", "esp32", "none"], default="host",
                    help="Microphone source: host (default), esp32 (INMP441), or none")
    p.add_argument("--no-mic", action="store_true", help="Disable microphone (camera only)")
    return p.parse_args()


async def async_main() -> None:
    args = parse_args()

    # Resolve token
    token = args.token
    if not token and args.token_file:
        with open(args.token_file) as f:
            token = f.read().strip()
    if not token:
        token = os.environ.get("OMNI_TOKEN", "")
    if not token:
        print("Error: Provide --token, --token-file, or set OMNI_TOKEN env var")
        sys.exit(1)

    mic_source = "none" if args.no_mic else args.mic

    client = GlassesClient(
        server=args.server,
        token=token,
        esp32_ip=args.esp32_ip,
        snapshot_interval=args.interval,
        mic_source=mic_source,
    )

    try:
        await client.run()
    except KeyboardInterrupt:
        pass
    finally:
        client.stop()
        print("\n[STOPPED]")


if __name__ == "__main__":
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print("\n[STOPPED]")
